# Team workflow

This repository starts as one running local application. Run `python -m gateway.app`
and open `http://127.0.0.1:8765` before taking a role. The simulator supplies
engineering-unit telemetry to the gateway; the dashboard reads its HTTP API.
No hardware or broker is required to develop the first stage.

## Four owners

| Owner | Area | Primary files | First contribution |
|---|---|---|---|
| A - teammate | Estimation and calibration | `vfm/fastloop.py`, `vfm/slowloop.py`, `algorithms/` | Validate estimator inputs and candidate models; add regression tests |
| B - you, lead | Device and supervision | `vfm/supervisor.py`, `vfm/faults.py`, `vfm/hal.py`, `vfm/sim.py`, `vfm/runtime.py`, `device/` | Connect sensor faults and make invalid readings/sweeps safe |
| C - teammate | Gateway and records | `gateway/` | Save and replay telemetry without changing the API response |
| D - teammate | Operator dashboard | `dashboard/` | Expand the live dashboard with useful history and clear fault/stale states |

Each role has a guide in `docs/team/`. The four work areas are comparable in
scope: one substantial, testable feature in the first round, followed by a
hardware or operator integration round. The lead additionally coordinates
interfaces and merges. If the team chooses different people for these roles,
update this table and keep one owner per area.

The ownership checker reads `team/ownership.json`. Shared `config.json`,
`contracts/`, root documentation, CI, integration tests, and `vfm/config.py`
are changed in separate integration PRs by the lead. Never edit another role's
files in a role branch. New tests go in `tests/<area>/`.

## Work in parallel

1. Merge and push this baseline first. Each person creates a separate clone or
   worktree from it; do not share one working directory.
2. Create a short role branch, such as `codex/a-estimator-validation`.
3. Start with the existing input/output contracts in `contracts/README.md` and
   the running app. Keep public fields backward compatible.
4. Implement one demonstrable feature with its own tests and usage notes.
5. Run `python -m pytest` and a local demo. Then check ownership:

```powershell
git fetch origin
python tools/check_ownership.py --role a --base origin/main
```

Replace the letter and default branch as needed. Submit a PR, review another
member's PR, and let the lead merge and run the application after each merge.

Contract changes require a short proposal to the lead first. The lead lands
shared schema changes before code depends on them. This keeps parallel work
independent and avoids unplanned merge conflicts.

## What the baseline does and does not establish

The current dashboard is a read-only simulator view. The existing Python
algorithms are a reference implementation, and configuration values are
simulation placeholders. Later stages add operator commands, persistence,
ESP32 firmware, real sensor adapters, commissioning, and physical-rig evidence.
Simulation results must never be presented as measured rig results.
