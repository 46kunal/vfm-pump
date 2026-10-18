import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np
from vfm.config import load
from vfm.fastloop import FastLoop, solve_curve, water_density
from vfm.slowloop import LearningModule, phi_of, Cusum, excitation_gate
from vfm.sim import SimHAL
from vfm.supervisor import Supervisor, ScriptedOperator
from vfm.faults import FaultDetector

cfg = load()

def test_worked_example():
    """PDF section 3.1: 88 kPa at ~20 C is ~9.0 m, which on H=10-0.1Q-0.02Q^2 is ~5 L/min."""
    fl = FastLoop(cfg)
    rho = water_density(20.0)
    s = {"t": 0, "dp_kpa": 9.0 * rho * 9.81 / 1000, "volts": 12.0, "amps": 10.75 / 12.0,
         "rpm": cfg["n_ref"], "temp_c": 20.0, "valve_pct": .35, "quality": 1}
    o = fl.update(s)
    assert abs(o["Q_h"] - 5.0) < 0.05, o["Q_h"]
    assert abs(o["Q_p"] - 5.0) < 0.1, o["Q_p"]
    assert abs(88.0 - s["dp_kpa"]) < 1.0
    print("worked example ok: Q_h=%.3f Q_p=%.3f dp=%.1f kPa" % (o["Q_h"], o["Q_p"], s["dp_kpa"]))

def test_invalid_head_not_forced():
    q, sl, ok = solve_curve(cfg["head_curve"], 11.0, cfg["q_max"], False)   # above shutoff
    assert not ok

def _learner(n=300, lam=0.99, seed=3):
    rng = np.random.default_rng(seed)
    th_true = np.array([9.0, -0.1, -0.02])
    lm = LearningModule(cfg["head_curve"], np.diag(cfg["rls_p0"]), lam)
    for i in range(n):
        q = rng.uniform(2.5, 12); y = phi_of(q) @ th_true + rng.normal(0, 0.05)
        lm.add(phi_of(q), y, 1 / 0.05 ** 2, t=i)
    return lm

def test_rls_matches_batch():
    lm = _learner(); th, P = lm.batch_oracle()
    assert np.abs(lm.theta - th).max() < 1e-9

def test_downdate_exact_vs_retrain():
    lm = _learner(); ids = list(range(100, 140))
    th_o, P_o = lm.batch_oracle(ids); th_r, _ = lm.replay(ids)
    res = lm.downdate(ids)
    err = np.linalg.norm(lm.theta - th_o) / np.linalg.norm(th_o)
    assert res["status"] == "OK" and res["method"] == "downdate"
    assert err < 1e-10 and np.abs(th_r - th_o).max() < 1e-10
    print("downdate vs retrain relative error: %.2e" % err)

def test_downdate_fallback_when_unsafe():
    lm = LearningModule([10, -.1, -.02], np.diag(cfg["rls_p0"]), 1.0)
    ids = [lm.add(phi_of(5.0), 8.0, 1e6, t=0)]           # one sample alone fixes a direction
    res = lm.downdate(ids, g_min=0.5)
    assert res["method"] == "replay"

def test_rollback():
    lm = _learner(50); lm.checkpoint("x"); th = lm.theta.copy()
    lm.add(phi_of(5.0), 99.0, 1e4); assert np.abs(lm.theta - th).max() > 1
    lm.rollback(); assert np.abs(lm.theta - th).max() < 1e-12

def test_gate_parked_vs_sweep():
    rng = np.random.default_rng(0)
    parked = list(5 + rng.normal(0, .02, 60))
    sweep = [x for x in (2.75, 3.8, 5.2, 7.1, 9.3, 12.0) for _ in range(8)]
    gp, gs = excitation_gate(parked, cfg), excitation_gate(sweep, cfg)
    assert not gp["ok"] and gs["ok"], (gp, gs)
    print("gate lambda_min parked=%.2e sweep=%.2e (eps=%.1e)" % (gp["lambda_min"], gs["lambda_min"], cfg["gate_eps"]))

def test_cusum_quiet_then_alarm():
    rng = np.random.default_rng(1)
    cu = Cusum(cfg["cusum_k"], cfg["cusum_h"])
    for i in range(7200):                       # 2 h at 1 Hz of healthy noise
        assert cu.update(rng.normal(), i) == 0
    for i in range(20):
        if cu.update(3.0 + rng.normal(), 7200 + i):
            break
    assert cu.alarm == 1

def test_apply_model_refuses_without_approval():
    hal = SimHAL(cfg); fl = FastLoop(cfg); sup = Supervisor(cfg, fl, hal, ScriptedOperator())
    try:
        sup.apply_model([9, -.1, -.02], None, 0.0)
        raise AssertionError("should have refused")
    except PermissionError:
        pass
    assert fl.theta_h[0] == 10.0 and sup.model_changes == 0

def test_fault_detector():
    fd = FaultDetector(cfg); out = None
    for i in range(40):
        out = fd.update({"t": i * .1, "dp_kpa": 80.0}) or out
    assert out and out[0] == "stuck"

if __name__ == "__main__":
    n = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); n += 1; print("PASS", name)
    print(n, "tests passed")
