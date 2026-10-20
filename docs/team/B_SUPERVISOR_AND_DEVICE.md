# Role B: Device and supervision

You own the device-facing runtime and supervisor, and coordinate integration. This area controls state, sensor quality, calibration requests, sweeps, approval, and eventual hardware adapters.

**Current base:** `vfm/sim.py` implements `HAL`; `vfm/runtime.py` produces 10 Hz telemetry; `vfm/supervisor.py` runs the state machine; `vfm/faults.py` has a detector that is not yet connected. The gateway and dashboard already consume the runtime's telemetry.

**First feature (Stage 1):** Connect sensor-quality and fault events to the runtime/supervisor. Invalid pressure/flow must never keep a sweep running silently. Block bad samples from CUSUM and candidate fitting. Strengthen model approval so malformed approval records cannot partially change the active model. Keep SAFE recovery and the audit trail explicit. Do not assume a software safety check substitutes for a physical emergency stop.

**How:** Write tests under `tests/device/` for non-finite samples, faulty quality, a fault during a sweep, and approval atomicity. Reuse `vfm/faults.py`, coordinate the expected invalid-estimate shape with A, then wire its result through `vfm/runtime.py` and `vfm/supervisor.py`. Run scenarios and the live dashboard after each change.

**Acceptance:** A simulated fault is visible as a state/quality change; no bad sample trains a candidate; sweep abort and valve restoration are auditable; malformed approval leaves the active curve unchanged; existing scenarios continue to run. Document any behavior that still needs real actuator measurements.

**Next stage:** Define the real HAL adapter, measured valve feedback, power/current interlocks, and C++/ESP32 integration once hardware arrives. As lead, merge A/C/D one at a time and run the full system between merges.

## Shared start and handoff

1. Install `requirements-dev.txt`, run `python -m gateway.app`, and open
   `http://127.0.0.1:8765`. Run `python -m pytest` before editing.
2. Work in your own clone or worktree and a `codex/b-...` branch.
3. Change only your owned files. Put new tests in your role's `tests/` folder.
4. Preserve existing interfaces; propose shared contract changes to the lead.
5. Run all tests and demonstrate the feature with changed input. Explain
   what you changed, tests, and remaining limits in your PR.

The input curves, thresholds, and output of the simulator are placeholders.
Measured calibration and hardware evidence come later.
