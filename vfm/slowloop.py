"""Slow loop pieces: CUSUM, excitation gate, RLS with exact unlearning, candidate checks, wear."""
import numpy as np

# ---------------------------------------------------------------- CUSUM
class Cusum:
    """Two-sided CUSUM on normalised residuals. Freeze during sweeps/safe/fault windows."""
    def __init__(self, k, h):
        self.k, self.h = k, h
        self.reset()

    def reset(self):
        self.sp = self.sm = 0.0
        self.t_start = None
        self.alarm = 0          # +1 head path reads high, -1 reads low, 0 none

    def update(self, z, t):
        was_zero = self.sp == 0.0 and self.sm == 0.0
        self.sp = max(0.0, self.sp + z - self.k)
        self.sm = max(0.0, self.sm - z - self.k)
        if was_zero and (self.sp > 0 or self.sm > 0):
            self.t_start = t
        if self.sp == 0.0 and self.sm == 0.0:
            self.t_start = None
        if self.sp > self.h:
            self.alarm = +1
        elif self.sm > self.h:
            self.alarm = -1
        return self.alarm


# ---------------------------------------------------------------- excitation gate
def excitation_gate(qs, cfg):
    """lambda_min of R = mean(phi phi^T), phi=[1,q,q^2], q scaled to 0..1, plus flow-span check."""
    if len(qs) < 5:
        return {"ok": False, "lambda_min": 0.0, "span": 0.0}
    q = np.asarray(qs, float) / cfg["q_max"]
    Phi = np.stack([np.ones_like(q), q, q * q], axis=1)
    R = Phi.T @ Phi / len(q)
    lam_min = float(np.linalg.eigvalsh(R)[0])
    span = float(q.max() - q.min())
    return {"ok": bool(lam_min > cfg["gate_eps"] and span >= cfg["gate_span_frac"]),
            "lambda_min": lam_min, "span": span}


# ---------------------------------------------------------------- RLS with exact unlearning
def phi_of(q):
    return np.array([1.0, q, q * q])

class LearningModule:
    """Weighted RLS with forgetting, plus sample records, checkpoints, exact downdate,
    rollback-and-replay and a batch oracle. Double precision throughout.

    Every add() is one time step. Information of sample i after n steps is
    omega_i = w_i * lam^(n - n_i). Removing a sample = subtracting omega_i*phi*phi^T from P^-1
    (Sherman-Morrison). Replay keeps the time index by applying a zero-weight (decay-only) step
    where a sample was removed, so replay and downdate agree exactly.
    """
    def __init__(self, theta0, P0, lam):
        self.lam = float(lam)
        self.theta0 = np.array(theta0, float)
        self.P0 = np.array(P0, float)
        self.theta = self.theta0.copy()
        self.P = self.P0.copy()
        self.n = 0
        self.records = []          # dicts: id, n, t, phi, y, w, active, src
        self.checkpoints = []
        self._next_id = 0

    # --- core update -----------------------------------------------------
    @staticmethod
    def _step(theta, P, lam, phi, y, w):
        if w <= 0.0:
            P = P / lam
            return theta, 0.5 * (P + P.T)
        Pphi = P @ phi
        K = Pphi / (lam / w + phi @ Pphi)
        theta = theta + K * (y - phi @ theta)
        P = (P - np.outer(K, phi @ P)) / lam
        return theta, 0.5 * (P + P.T)

    def add(self, phi, y, w, t=0.0, src="steady"):
        self.n += 1
        self.theta, self.P = self._step(self.theta, self.P, self.lam, phi, y, w)
        rec = {"id": self._next_id, "n": self.n, "t": t, "phi": np.array(phi, float),
               "y": float(y), "w": float(w), "active": True, "src": src}
        self._next_id += 1
        self.records.append(rec)
        return rec["id"]

    def omega(self, rec):
        return rec["w"] * self.lam ** (self.n - rec["n"])

    # --- checkpoints -----------------------------------------------------
    def checkpoint(self, reason=""):
        self.checkpoints.append({"theta": self.theta.copy(), "P": self.P.copy(), "n": self.n,
                                 "reason": reason})
        return len(self.checkpoints) - 1

    def rollback(self, k=-1):
        cp = self.checkpoints[k]
        self.theta, self.P, self.n = cp["theta"].copy(), cp["P"].copy(), cp["n"]
        self.records = [r for r in self.records if r["n"] <= cp["n"]]

    # --- unlearning ------------------------------------------------------
    def replay(self, skip_ids=()):
        """Exact recomputation from the initial state, skipping given ids (keeps time index)."""
        skip = set(skip_ids)
        th, P = self.theta0.copy(), self.P0.copy()
        by_n = {r["n"]: r for r in self.records}
        for step in range(1, self.n + 1):
            r = by_n.get(step)
            if r is None or r["id"] in skip or not r["active"]:
                th, P = self._step(th, P, self.lam, None, 0.0, 0.0)
            else:
                th, P = self._step(th, P, self.lam, r["phi"], r["y"], r["w"])
        return th, P

    def downdate(self, ids, g_min=1e-6):
        """Exact removal of samples by id. Falls back to replay if numerically unsafe."""
        ids = set(ids)
        recs = [r for r in self.records if r["id"] in ids and r["active"]]
        th, P = self.theta.copy(), self.P.copy()
        theta_before = th.copy()
        g_smallest, method, status = 1.0, "downdate", "OK"
        for r in recs:
            om, phi = self.omega(r), r["phi"]
            Pphi = P @ phi
            g = 1.0 - om * (phi @ Pphi)
            g_smallest = min(g_smallest, g)
            if g < g_min:
                method = "replay"
                break
            e = r["y"] - phi @ th
            th = th - om * Pphi * e / g
            P = P + om * np.outer(Pphi, Pphi) / g
            P = 0.5 * (P + P.T)
            if np.linalg.eigvalsh(P)[0] <= 0:
                method = "replay"
                break
        if method == "replay":
            status = "FELL_BACK"
            th, P = self.replay(ids)
            if np.linalg.eigvalsh(P)[0] <= 0 or not np.all(np.isfinite(th)):
                return {"status": "FAILED", "method": method, "g_min": g_smallest,
                        "dtheta": np.zeros(3), "removed": 0}
        for r in recs:
            r["active"] = False
        self.theta, self.P = th, P
        return {"status": status, "method": method, "g_min": g_smallest,
                "dtheta": th - theta_before, "removed": len(recs)}

    def ids_in_window(self, t0, t1):
        return [r["id"] for r in self.records if t0 <= r["t"] <= t1 and r["active"]]

    # --- oracle for tests ---------------------------------------------------
    def batch_oracle(self, skip_ids=()):
        """Closed-form weighted LS with the decayed prior; must equal replay and downdate."""
        skip = set(skip_ids)
        lam_n = self.lam ** self.n
        A = lam_n * np.linalg.inv(self.P0)
        b = lam_n * np.linalg.inv(self.P0) @ self.theta0
        for r in self.records:
            if r["id"] in skip or not r["active"]:
                continue
            om = self.omega(r)
            A = A + om * np.outer(r["phi"], r["phi"])
            b = b + om * r["phi"] * r["y"]
        P = np.linalg.inv(A)
        return P @ b, P


# ---------------------------------------------------------------- candidate checks
def check_candidate(theta_new, P_new, theta_active, a0_comm, samples, cfg):
    """Return list of failed checks (empty list = candidate may be shown to the operator).
    samples: list of (t, q, y, w)."""
    fails = []
    a0, a1, a2 = theta_new
    qs = np.linspace(0.5, cfg["q_max"] * 0.9, 50)
    if a0 <= 0:
        fails.append("a0 not positive")
    if np.any(a1 + 2 * a2 * qs >= 0):
        fails.append("head curve not falling with flow")
    if abs(a0 - a0_comm) / a0_comm > cfg["check_a0_bound"]:
        fails.append("a0 change beyond sane bound")
    ev = np.linalg.eigvalsh(P_new)
    if ev[0] <= 0 or ev[-1] / ev[0] > cfg["check_max_cond"]:
        fails.append("covariance not well-behaved")
    if samples:
        q = np.array([s[1] for s in samples]); y = np.array([s[2] for s in samples])
        w = np.array([s[3] for s in samples])
        Phi = np.stack([np.ones_like(q), q, q * q], axis=1)
        e_new = np.sum(w * (y - Phi @ np.array(theta_new)) ** 2)
        e_old = np.sum(w * (y - Phi @ np.array(theta_active)) ** 2)
        if not e_new < cfg["check_improve_factor"] * e_old:
            fails.append("does not reduce residual on buffered samples")
    return fails


def wear_pct(a0_comm, a0_now):
    return (a0_comm - a0_now) / a0_comm * 100.0
