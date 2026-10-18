"""Supervisor: state machine, graded autonomy, sweep controller, interlocks, audit trail.
Reference implementation for AN. Non-blocking: call tick(sample, fast_out) every cycle.

Safety/authority rules enforced by construction:
  * every state change goes through transition(), which writes the audit entry
  * the active curve changes only inside apply_model(), which refuses without an approval record
  * automatic unlearning only edits the candidate learner, never the active curve
"""
from collections import deque
from enum import Enum
import numpy as np
from .slowloop import (Cusum, excitation_gate, LearningModule, phi_of, check_candidate, wear_pct)

class State(Enum):
    BOOT = 0; MONITOR = 1; CHECK_EXCITATION = 2; REQUEST_SWEEP = 3; SWEEP = 4
    CANDIDATE = 5; PENDING_APPROVAL = 6; APPLY = 7; SAFE = 8

class ScriptedOperator:
    """Stand-in for the dashboard. decide()/approve_sweep() return None until `delay_s` passed."""
    def __init__(self, sweep="approve", update="approve", delay_s=5.0):
        self.sweep, self.update, self.delay = sweep, update, delay_s
        self._seen = {}

    def _wait(self, key, t):
        t0 = self._seen.setdefault(key, t)
        if (t - t0) >= self.delay:
            del self._seen[key]          # next request starts a fresh delay
            return True
        return False

    def approve_sweep(self, req, t):
        return (self.sweep == "approve") if self._wait("sweep", t) else None

    def decide(self, pending, t):
        return self.update if self._wait(("upd", pending["id"]), t) else None

    def ack_safe(self, t):
        return True


class Supervisor:
    def __init__(self, cfg, fast, hal, operator, mode="assisted", audit_cb=None):
        self.cfg, self.fast, self.hal, self.op = cfg, fast, hal, operator
        self.mode = mode
        self.state = State.BOOT
        self.audit, self.audit_cb = [], audit_cb
        self.cusum = Cusum(cfg["cusum_k"], cfg["cusum_h"])
        self.recent = deque(maxlen=cfg["recent_max"])     # (t, q, y, w)
        self._win = []
        self.a0_comm = cfg["wear_baseline_a0"]
        self.pending = None
        self.learning = None
        self.checkpoints = [{"theta": list(fast.theta_h), "reason": "commissioned", "t": 0.0}]
        self.cooldown_until = 0.0
        self.sweep_attempts = 0
        self.net_up = True
        self.pending_id = 0
        self.sweep_idx = 0
        self.sweep_t0 = 0.0
        self.valve_before = None
        self.last_approval = None
        self.model_changes = 0
        self.abort_cycles = None
        self.alarm_t = 0.0
        self.transition(State.MONITOR, "boot ok", 0.0)

    # ------------------------------------------------------------ audit + guards
    def transition(self, to, reason, t):
        entry = {"t": round(t, 2), "from": self.state.name, "to": to.name, "reason": reason,
                 "mode": self.mode}
        self.audit.append(entry)
        if self.audit_cb:
            self.audit_cb(entry)
        self.state = to

    def apply_model(self, theta, approval, t):
        """The ONLY place the active curve changes."""
        if not approval:
            raise PermissionError("model change refused: no approval record")
        self.fast.set_head_curve(theta)
        self.checkpoints.append({"theta": [float(v) for v in theta], "reason": approval["by"], "t": t})
        self.model_changes += 1

    def set_mode(self, mode, t):
        self.audit.append({"t": round(t, 2), "from": self.state.name, "to": self.state.name,
                           "reason": f"mode {self.mode}->{mode}", "mode": mode})
        self.mode = mode

    def network(self, up, t):
        self.net_up = up
        if not up and self.state == State.SWEEP:
            self._trip("network lost during sweep", t)

    def _trip(self, why, t):
        self.hal.set_valve(self.valve_before if self.valve_before is not None else 0.45)
        self.abort_cycles = 1
        self.transition(State.SAFE, why, t)

    def abort_sweep(self, t):
        if self.state == State.SWEEP:
            self._trip("operator abort", t)

    # ------------------------------------------------------------ window ingest
    def _ingest(self, fo, t):
        if not (fo["steady"] and fo["valid"]):
            self._win = []
            return None
        self._win.append(fo)
        n = self.cfg["window_n"]
        if len(self._win) < n:
            return None
        w = self._win; self._win = []
        z = float(np.mean([f["resid_z"] for f in w])) * np.sqrt(n)
        q = float(np.mean([f["Qref_p"] for f in w])); y = float(np.mean([f["H_ref"] for f in w]))
        slope = float(np.mean([f["slope_h"] for f in w]))
        var_y = (w[0]["sigH_ref"] ** 2 + (slope * w[0]["sigQref_p"]) ** 2) / n
        self.recent.append((t, q, y, 1.0 / var_y))
        return z

    # ------------------------------------------------------------ main tick
    def tick(self, s, fo):
        t, c = s["t"], self.cfg
        z = self._ingest(fo, t)

        if self.state == State.SWEEP:
            if s["dp_kpa"] > c["max_dp_kpa"]:
                return self._trip("interlock: max dP", t)
            if fo["Q"] < c["min_flow"]:
                return self._trip("interlock: min flow", t)

        st = self.state
        if st == State.MONITOR:
            if z is not None and t >= self.cooldown_until:
                if self.cusum.update(z, t):
                    self.alarm_t = t
                    self.transition(State.CHECK_EXCITATION,
                                    f"CUSUM alarm ({'+' if self.cusum.alarm > 0 else '-'})", t)
                    self._check_excitation(t)
        elif st == State.REQUEST_SWEEP:
            if not self.net_up:
                return                    # offline rule: no new sweeps while the network is down
            if self.mode == "auto" and self._auto_guards(s, fo):
                self._start_sweep(t, "auto mode, guards ok")
            else:
                d = self.op.approve_sweep({"reason": "insufficient excitation"}, t)
                if d is True:
                    self._start_sweep(t, "operator approved sweep")
                elif d is False:
                    self.cooldown_until = t + c["cooldown_s"]
                    self.transition(State.MONITOR, "sweep rejected; cooldown", t)
        elif st == State.SWEEP:
            if t - self.sweep_t0 >= c["sweep_dwell_s"]:
                self.sweep_idx += 1
                if self.sweep_idx >= len(c["sweep_positions"]):
                    self.hal.set_valve(self.valve_before)
                    self.transition(State.CHECK_EXCITATION, "sweep done, valve restored", t)
                    self._check_excitation(t)
                else:
                    self.hal.set_valve(c["sweep_positions"][self.sweep_idx])
                    self.sweep_t0 = t
        elif st == State.PENDING_APPROVAL:
            self._pending_tick(t)
        elif st == State.SAFE:
            if self.op.ack_safe(t):
                self.cusum.reset()
                self.transition(State.MONITOR, "operator acknowledged", t)

    # ------------------------------------------------------------ steps
    def _auto_guards(self, s, fo):
        return self.net_up and fo["Q"] > self.cfg["min_flow"] and self.sweep_attempts < self.cfg["sweep_max_attempts"]

    def _samples_since_alarm(self):
        # Only data gathered after the alarm is used for the fit: the CUSUM onset estimate can
        # reach back into pre-drift samples, which would pull the candidate toward the old curve.
        return [r for r in self.recent if r[0] >= self.alarm_t]

    def _check_excitation(self, t):
        samples = self._samples_since_alarm()
        g = excitation_gate([r[1] for r in samples], self.cfg)
        self.last_gate = g
        if g["ok"]:
            self.transition(State.CANDIDATE, f"gate open (lam_min={g['lambda_min']:.4g}, span={g['span']:.2f})", t)
            self._build_candidate(t, samples)
        elif self.sweep_attempts >= self.cfg["sweep_max_attempts"]:
            self.cooldown_until = t + self.cfg["cooldown_s"]
            self.sweep_attempts = 0
            self.cusum.reset()
            self.transition(State.MONITOR, "excitation still insufficient after sweeps; alert", t)
        elif self.mode == "manual":
            self.cooldown_until = t + self.cfg["cooldown_s"]
            self.cusum.reset()
            self.transition(State.MONITOR, "excitation insufficient; manual mode: operator alerted", t)
        else:
            self.transition(State.REQUEST_SWEEP, f"gate closed (lam_min={g['lambda_min']:.4g}, span={g['span']:.2f})", t)

    def _start_sweep(self, t, why):
        self.sweep_attempts += 1
        self.valve_before = self.hal.get_valve()
        self.sweep_idx, self.sweep_t0 = 0, t
        self.hal.set_valve(self.cfg["sweep_positions"][0])
        self.transition(State.SWEEP, why, t)

    def _build_candidate(self, t, samples):
        c = self.cfg
        lm = LearningModule(self.fast.theta_h, np.diag(c["rls_p0"]), c["rls_lambda"])
        for (ts, q, y, w) in sorted(samples):
            lm.add(phi_of(q), y, w, t=ts)
        self.learning = lm
        self._publish_candidate(t, samples)

    def _publish_candidate(self, t, samples):
        c = self.cfg
        fails = check_candidate(self.learning.theta, self.learning.P, self.fast.theta_h,
                                self.a0_comm, samples, c)
        if fails:
            self.cooldown_until = t + c["cooldown_s"]
            self.cusum.reset(); self.sweep_attempts = 0
            self.transition(State.MONITOR, "candidate rejected by checks: " + "; ".join(fails), t)
            return
        self.pending_id += 1
        self.pending = {"id": self.pending_id, "t": t, "theta_old": list(self.fast.theta_h),
                        "theta_new": [float(v) for v in self.learning.theta],
                        "a0_drift_pct": 100 * (self.learning.theta[0] - self.fast.theta_h[0]) / self.fast.theta_h[0],
                        "wear_pct_new": wear_pct(self.a0_comm, self.learning.theta[0])}
        self.transition(State.PENDING_APPROVAL, "candidate passed checks; waiting for decision", t)

    def _pending_tick(self, t):
        c, p = self.cfg, self.pending
        if t - p["t"] > c["pending_max_age_s"]:
            self.pending = None
            self.transition(State.MONITOR, "pending candidate too old: discarded", t)
            return
        within = abs(p["theta_new"][0] - self.a0_comm) / self.a0_comm <= c["auto_bound"]
        if self.mode == "auto" and within:
            self._apply({"by": "policy:auto-bound", "t": t}, t)
            return
        d = self.op.decide(p, t)
        if d == "approve":
            self._apply({"by": "operator", "t": t}, t)
        elif d == "reject":
            self.pending = None; self.learning = None
            self.cooldown_until = t + c["cooldown_s"]
            self.cusum.reset(); self.sweep_attempts = 0
            self.transition(State.MONITOR, "operator rejected; model unchanged; cooldown", t)

    def _apply(self, approval, t):
        self.transition(State.APPLY, f"approved by {approval['by']}", t)
        self.apply_model(self.pending["theta_new"], approval, t)
        self.learning.checkpoint("applied")
        self.last_approval = approval
        self.pending = None
        self.cusum.reset(); self.recent.clear(); self.sweep_attempts = 0
        self.transition(State.MONITOR, "model applied; CUSUM reset", t)

    # ------------------------------------------------------------ annotation -> unlearning
    def annotate(self, t0, t1, reason, t):
        """Operator marks a bad window. Edits only the CANDIDATE learner, never the active curve."""
        self.audit.append({"t": round(t, 2), "from": self.state.name, "to": self.state.name,
                           "reason": f"annotation [{t0},{t1}]: {reason}", "mode": self.mode})
        self.recent = deque([r for r in self.recent if not (t0 <= r[0] <= t1)], maxlen=self.cfg["recent_max"])
        if self.learning is not None and self.state == State.PENDING_APPROVAL:
            ids = self.learning.ids_in_window(t0, t1)
            res = self.learning.downdate(ids)
            self.audit.append({"t": round(t, 2), "from": self.state.name, "to": self.state.name,
                               "reason": f"unlearn {res['removed']} samples via {res['method']} ({res['status']})",
                               "mode": self.mode})
            samples = [(r["t"], r["phi"][1], r["y"], r["w"]) for r in self.learning.records if r["active"]]
            self._publish_candidate(t, samples)
            return res
        return None
