# Role A: Estimation and calibration

Own the calculations that turn sensor readings into a flow estimate and decide whether a proposed pump curve is valid. Your work should improve the **running** Python reference, not create a detached report tool.

**Current base:** `vfm/fastloop.py` computes two flow paths and their Kalman fusion; `vfm/slowloop.py` contains CUSUM, excitation, weighted RLS, candidate checks, and unlearning. The gateway already displays `flow_l_min`, `sigma_l_min`, and confidence from this code. Inspect `tests/test_core.py` and the telemetry contract before changing outputs.

**First feature (Stage 1):** Make estimator and candidate validation robust to missing/non-finite or impossible input and coefficients. Agree with B on which readings are invalid; return an explicit low-confidence/invalid output rather than contaminating filter state. Ensure candidate checks reject non-finite or under-supported models. Add focused regression tests for both paths, single-path behavior, and candidate rejection. Preserve existing valid outputs and the current public keys.

**How:** Reproduce the failing cases with small samples, add tests under `tests/algorithms/`, make the smallest changes to `vfm/fastloop.py` and `vfm/slowloop.py`, and compare before/after behavior with `python -m pytest` and `python -m gateway.app`. Use `algorithms/` for independent commissioning or analysis helpers when needed.

**Acceptance:** Healthy simulated telemetry still appears on the dashboard; bad numeric inputs do not leave non-finite model/filter state; invalid candidate coefficients are rejected; all core and new tests pass. Demo a healthy reading and an invalid reading with the resulting confidence.

**Next stage:** Fit and tune curves and noise from measured commissioning data, then provide Python reference vectors for the future C++ port. This later work requires physical measurements.

## Shared start and handoff

1. Install `requirements-dev.txt`, run `python -m gateway.app`, and open
   `http://127.0.0.1:8765`. Run `python -m pytest` before editing.
2. Work in your own clone or worktree and a `codex/a-...` branch.
3. Change only your owned files. Put new tests in your role's `tests/` folder.
4. Preserve existing interfaces; propose shared contract changes to the lead.
5. Run all tests and demonstrate the feature with changed input. Explain
   what you changed, tests, and remaining limits in your PR.

The input curves, thresholds, and output of the simulator are placeholders.
Measured calibration and hardware evidence come later.
