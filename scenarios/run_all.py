"""Runs the simulated scenarios E1-E7 and writes figures to ./outputs.
EVERYTHING HERE IS SIMULATION: scaffolding for the software, never a rig result."""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from vfm.slowloop import LearningModule, phi_of

OUT = os.path.join(os.path.dirname(__file__), "..", "outputs")
os.makedirs(OUT, exist_ok=True)
FS = 12.0   # full-scale flow used for % of FS (L/min)
results = {}

def banner(s): print("\n=== " + s)

# ---------------------------------------------------------------- E1 accuracy (sim)
banner("E1 accuracy across flow and speed (SIM)")
errs = []
for rpm in (2400.0, 2700.0, 3000.0):
    for v in (0.2, 0.3, 0.45, 0.7, 1.0):
        cfg, hal, fast, sup = build(seed=int(rpm) + int(v * 100), valve=v)
        hal.plant.rpm = rpm
        log = {}
        run(hal, fast, sup, 40, log=log)
        e = rms_pct(log, 25, 40, FS)
        errs.append((rpm, v, e))
rms = float(np.sqrt(np.mean([e ** 2 for _, _, e in errs])))
print("RMS error over all points: %.2f %% of FS (max %.2f %%)" % (rms, max(e for *_, e in errs)))
results["E1_rms_pct_fs"] = rms

# ---------------------------------------------------------------- E2 no false alarm
banner("E2 valve bumps for 1 simulated hour: false alarms (SIM)")
cfg, hal, fast, sup = build(seed=11, valve=0.45)
rng = np.random.default_rng(5)
events = [(t, (lambda v=float(rng.uniform(0.3, 0.9)): hal.set_valve(v))) for t in np.arange(30, 3600, 75)]
run(hal, fast, sup, 3600, events=events)
alarms = sum(1 for a in sup.audit if a["to"] == "CHECK_EXCITATION")
print("valve bumps: %d, false alarms: %d" % (len(events), alarms))
results["E2_false_alarms"] = alarms

# ---------------------------------------------------------------- E3 wear -> recalibration
banner("E3 wear (a0 10 -> 9 m), recalibration with operator approval (SIM)")
cfg, hal, fast, sup = build(seed=2, valve=0.35)
log = {}
run(hal, fast, sup, 600, events=[(120.0, lambda: hal.plant.__setattr__("a", [9.0, hal.plant.a[1], hal.plant.a[2]]))], log=log)
for a in sup.audit:
    print("  t=%6.1f  %-17s -> %-17s %s" % (a["t"], a["from"], a["to"], a["reason"]))
t_end = log["t"][-1]
e_h, e_w, e_a = rms_pct(log, 30, 120, FS), rms_pct(log, 126, 200, FS), rms_pct(log, t_end - 60, t_end + 1, FS)
print("flow RMS error (%% of FS): healthy %.2f | worn, static curve %.2f | after recalibration %.2f" % (e_h, e_w, e_a))
print("a0 true 9.00 -> estimated %.3f ; wear indicator %.1f %%" % (fast.theta_h[0], (10 - fast.theta_h[0]) / 10 * 100))
results.update(E3_err_healthy=e_h, E3_err_worn_static=e_w, E3_err_after=e_a, E3_a0_est=fast.theta_h[0],
               E3_model_changes=sup.model_changes)
t = np.array(log["t"]); Q = np.array(log["Q"]); sg = np.array(log["sigma"]); Qt = np.array(log["Qtrue"])
fig, ax = plt.subplots(3, 1, figsize=(9, 8), sharex=True)
ax[0].plot(t, Qt, "k", lw=1, label="true flow (sim)"); ax[0].plot(t, Q, "C0", lw=.8, label="fused estimate")
ax[0].fill_between(t, Q - 2 * sg, Q + 2 * sg, color="C0", alpha=.2, label="+/-2 sigma")
ax[0].set_ylabel("flow (L/min)"); ax[0].legend(loc="upper right"); ax[0].set_title("E3 (simulation): wear at t=120 s, sweep, approval, recalibration")
ax[1].plot(t, log["cusum"], "C3"); ax[1].axhline(cfg["cusum_h"], color="grey", ls="--"); ax[1].set_ylabel("CUSUM")
ax[2].plot(t, log["a0"], "C2", label="active a0"); ax[2].axhline(9.0, color="k", ls=":", label="true a0 after wear")
ax[2].set_ylabel("a0 (m)"); ax[2].set_xlabel("time (s)"); ax[2].legend()
plt.tight_layout(); plt.savefig(os.path.join(OUT, "E3_wear_recalibration.png"), dpi=130); plt.close()

# ---------------------------------------------------------------- E4 reject
banner("E4 operator rejects the update (SIM)")
cfg, hal, fast, sup = build(seed=2, valve=0.35, operator=ScriptedOperator(update="reject"))
run(hal, fast, sup, 400, events=[(120.0, lambda: hal.plant.__setattr__("a", [9.0, -0.1, -0.02]))])
print("model changes: %d, a0 still %.2f, last transition: %s" % (sup.model_changes, fast.theta_h[0], sup.audit[-1]["reason"]))
results["E4_model_changes"] = sup.model_changes

# ---------------------------------------------------------------- E5 / E6 safe stop
banner("E5 network lost mid-sweep; E6 interlock trip (SIM)")
cfg, hal, fast, sup = build(seed=2, valve=0.35)
state = {}
def drop(): sup.network(False, hal.plant.t)
run(hal, fast, sup, 170, events=[(120.0, lambda: hal.plant.__setattr__("a", [9.0, -0.1, -0.02])), (155.0, drop)])
tr = [a for a in sup.audit if a["to"] == "SAFE"]
sweeps_after = [a for a in sup.audit if a["to"] == "SWEEP" and a["t"] > tr[0]["t"]]
print("E5:", tr[0]["reason"], "at t=%.1f; valve back at %.2f; new sweeps while offline: %d; estimation continues (Q=%.2f)" % (tr[0]["t"], hal.get_valve(), len(sweeps_after), fast.x))
results["E5_sweeps_while_offline"] = len(sweeps_after)
cfg, hal, fast, sup = build(seed=2, valve=0.35)
t_inj = {}
def inject(): hal.plant.faults["dp_offset_kpa"] = 200.0; t_inj["t"] = hal.plant.t
run(hal, fast, sup, 160, events=[(120.0, lambda: hal.plant.__setattr__("a", [9.0, -0.1, -0.02])), (150.0, inject)])
tr = [a for a in sup.audit if a["to"] == "SAFE"]
cycles = (tr[0]["t"] - t_inj["t"]) / cfg["dt"]
print("E6:", tr[0]["reason"], "| abort latency %.1f control cycle(s)" % cycles)
results["E6_abort_cycles"] = cycles

# ---------------------------------------------------------------- E7 unlearning, 4 traces
banner("E7 unlearning: a0 through a corrupted window (SIM)")
cfg7 = load(); cfg7["recent_max"] = 3000
cfg, hal, fast, sup = build(seed=21, valve=0.45, mode="manual", cfg=cfg7)
sup.cooldown_until = 1e9                      # observe only: collect windows, no CUSUM actions
hal.plant.a[0] = 9.0
rng = np.random.default_rng(8)
vs = {float(t): float(rng.uniform(0.2, 1.0)) for t in np.arange(0, 1800, 12)}
events = [(t, (lambda v=v: hal.set_valve(v))) for t, v in vs.items()]
T0, T1 = 700.0, 900.0
events += [(T0, lambda: hal.plant.faults.__setitem__("dp_offset_kpa", 4.0)),   # mis-zeroed sensor
           (T1, lambda: hal.plant.faults.__setitem__("dp_offset_kpa", 0.0))]
run(hal, fast, sup, 1800, events=events)
samples = sorted(sup.recent)
print("collected %d window samples" % len(samples))
P0 = np.diag(cfg["rls_p0"]); th0 = cfg["head_curve"]
def make(lam):
    return LearningModule(th0, P0, lam)
none, forget, unl, retr = make(1.0), make(0.99), make(0.99), make(0.99)
tr = {k: [] for k in ("none", "forget", "unlearn", "retrain")}; idx = []
annot_done = False
for i, (ts, q, y, w) in enumerate(samples):
    ph = phi_of(q)
    none.add(ph, y, w, t=ts); forget.add(ph, y, w, t=ts); unl.add(ph, y, w, t=ts)
    retr.add(ph, y, 0.0 if T0 <= ts <= T1 else w, t=ts)          # zero-weight step keeps the time index
    if (not annot_done) and ts > T1 + 60:                        # operator annotates 60 s after window
        ids = unl.ids_in_window(T0, T1)
        res = unl.downdate(ids); annot_done = True; i_annot = i
        print("annotation: removed %d samples via %s (%s), smallest g=%.3f" % (res["removed"], res["method"], res["status"], res["g_min"]))
    tr["none"].append(none.theta[0]); tr["forget"].append(forget.theta[0])
    tr["unlearn"].append(unl.theta[0]); tr["retrain"].append(retr.theta[0]); idx.append(ts)
rel = float(np.linalg.norm(unl.theta - retr.theta) / np.linalg.norm(retr.theta))
print("a0 at end: none %.3f | forgetting %.3f | unlearned %.3f | retrained %.3f (true 9.000)" %
      (none.theta[0], forget.theta[0], unl.theta[0], retr.theta[0]))
print("relative parameter difference, unlearned vs retrained: %.2e" % rel)
results.update(E7_rel_diff=rel)
fig, ax = plt.subplots(figsize=(9, 4.5))
for k, c, lbl in (("none", "C3", "do nothing (lambda=1)"), ("forget", "C1", "forgetting only (lambda=0.99)"),
                  ("unlearn", "C2", "unlearning (downdate)"), ("retrain", "k", "retrained without window")):
    ax.plot(idx, tr[k], c, lw=1.2 if k != "retrain" else 1.8, ls="--" if k == "retrain" else "-", label=lbl)
ax.axvspan(T0, T1, color="red", alpha=.1); ax.axhline(9.0, color="grey", ls=":")
ax.set_xlabel("time (s)"); ax.set_ylabel("estimated a0 (m)"); ax.legend(); ax.set_ylim(8.6, 9.8)
ax.set_title("E7 (simulation): a0 through a mis-zeroed pressure sensor window (shaded)")
plt.tight_layout(); plt.savefig(os.path.join(OUT, "E7_unlearning_traces.png"), dpi=130); plt.close()

with open(os.path.join(OUT, "results_sim.json"), "w") as f:
    json.dump({k: float(v) for k, v in results.items()}, f, indent=2)
print("\nSaved figures and results_sim.json to outputs/ (SIMULATION ONLY)")
