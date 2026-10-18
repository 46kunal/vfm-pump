import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np
from vfm.config import load
from vfm.sim import SimHAL
from vfm.fastloop import FastLoop
from vfm.supervisor import Supervisor, ScriptedOperator, State

def build(seed=0, valve=0.35, mode="assisted", operator=None, cfg=None):
    cfg = cfg or load()
    hal = SimHAL(cfg, seed=seed, valve=valve)
    fast = FastLoop(cfg)
    op = operator or ScriptedOperator()
    sup = Supervisor(cfg, fast, hal, op, mode=mode)
    return cfg, hal, fast, sup

def run(hal, fast, sup, duration, events=None, log=None):
    """Advance the sim. events: list of (t, fn). log: dict of lists to fill."""
    events = sorted(events or [], key=lambda e: e[0])
    dt = hal.cfg["dt"]
    n = int(round(duration / dt))
    for _ in range(n):
        s = hal.read_sensors()
        fo = fast.update(s)
        while events and s["t"] >= events[0][0]:
            events.pop(0)[1]()
        sup.tick(s, fo)
        if log is not None:
            log.setdefault("t", []).append(s["t"])
            log.setdefault("Q", []).append(fo["Q"]); log.setdefault("sigma", []).append(fo["sigma"])
            log.setdefault("Qtrue", []).append(hal.plant.q_true)
            log.setdefault("cusum", []).append(max(sup.cusum.sp, sup.cusum.sm))
            log.setdefault("a0", []).append(fast.theta_h[0])
            log.setdefault("state", []).append(sup.state.value)
            log.setdefault("valve", []).append(s["valve_pct"])

def rms_pct(log, t0, t1, qmax=12.0):
    t = np.array(log["t"]); m = (t >= t0) & (t < t1)
    e = np.array(log["Q"])[m] - np.array(log["Qtrue"])[m]
    return 100 * float(np.sqrt(np.mean(e ** 2))) / qmax
