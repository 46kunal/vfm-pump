# Self-Calibrating Virtual Flow Meter: software scaffolding (Python reference)

Everything here runs without hardware. **All numbers in `config.json` and all results from `scenarios/` are
simulation placeholders. None of them is a rig result.** Real results come only from the physical rig.

## Run
```
python3 tests/test_core.py          # 10 unit tests, incl. downdate == retrain to ~1e-15
python3 scenarios/run_all.py        # E1-E7 in simulation, writes outputs/*.png and results_sim.json
```
Needs numpy and matplotlib only.

## Layout and owners (names from the team PDF)

| File                           | What                                                                                                                     |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------ |
| `config.json`, `vfm/config.py` | every tunable number; nothing hard-coded                                                                                 |
| `vfm/hal.py`                   | hardware interface + CSV schema (`t, dp_kpa, volts, amps, rpm, temp_c, valve_pct, quality`)                              |
| `vfm/sim.py`                   | plant simulator + `SimHAL` (test scaffolding only)                                                                       |
| `vfm/fastloop.py`              | head, affinity normalisation, head/power paths, variances, Kalman, steady-state flag                                     |
| `vfm/slowloop.py`              | CUSUM, excitation gate, weighted RLS, exact downdate, checkpoint/rollback/replay, candidate checks, wear %               |
| `vfm/supervisor.py`            | state machine, Manual/Assisted/Auto, sweep controller, interlocks, audit, `apply_model()` gate, annotation to unlearning |
| `vfm/faults.py`                | stuck / spike / out-of-range detector                                                                                    |
| (not started)                  | MQTT bridge + JSON schemas, dashboard                                                                                    |
| (not started)                  | C++ port for the ESP32 (outputs must match these Python results)                                                         |

## Swapping in the real rig
Write one class that implements `HAL.read_sensors / set_valve / get_valve` and returns the same sample dict
(units: kPa, V, A, rpm, C, valve 0..1). Nothing else changes. Log real data with the same CSV schema into `data/real/`.
Keep `data/sim/` and `data/real/` separate and label every plot.

## Authority rules that are enforced in code (not just by convention)
- Every state change goes through `Supervisor.transition()`, which writes the audit entry.
- The active curve changes only in `Supervisor.apply_model()`, which raises `PermissionError` without an approval record.
- Automatic unlearning edits only the candidate learner; the active curve is untouched.
- No new sweep starts while the network is down; a sweep in progress goes to SAFE (valve restored).

## Deliberate differences from the PDF (decide with your guide)
1. **CUSUM input.** Residual is normalised per sample by sqrt(sigma_h^2 + sigma_p^2) instead of a single sigma_r, and the slow loop
   feeds CUSUM 1 Hz window means (scaled by sqrt(n)). With 1 Hz samples, k=0.5 and h=12 give an in-control run length of about 1e6 samples
   (h=4-5 would false-alarm roughly every 8 minutes). Re-tune k, h on real residuals.
2. **Sample weights come from variance** (w = 1/sigma_y^2, including the error from the power-path flow used as regressor), not a fixed
   multiplier r. Operator reference readings simply carry a small sigma, hence a large weight.
3. **Fit uses only samples collected after the alarm.** The CUSUM onset estimate can reach back into pre-drift samples and drag the
   candidate toward the old curve (this happened in testing).
4. **Replay keeps the time index.** A removed sample becomes a zero-weight decay step, so replay, downdate and the batch oracle agree exactly.

## Known limits of the simulation (say these before anyone asks)
- The simulator uses the same affinity laws and curve family as the estimator, so E1 passing at three speeds is true by construction,
  not evidence. Only the rig can test the affinity assumption.
- Only the head curve wears in the sim (a0 drops); the power curve does not. On a real pump both move, so the power-path flow used as
  the RLS regressor can be biased. The operator's reference reading is the real anchor.
- Noise is Gaussian and white; real sensors will be worse. The gate threshold (`gate_eps`), CUSUM settings and noise sigmas are placeholders.
- Sensor lags (0.15 s head, 0.6 s power) and valve slew are guesses.
