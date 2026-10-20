# Role D: Operator dashboard

Own the browser interface that makes device estimates and state understandable to an operator. You have an actual running dashboard to extend from day one.

**Current base:** `dashboard/index.html`, `styles.css`, and `app.js` already show live flow, uncertainty, confidence, state, source, and a chart. `gateway/app.py` serves these files and `GET /api/telemetry?limit=120`. Open `http://127.0.0.1:8765` after starting the app. No frontend framework is required; you can improve the existing vanilla HTML/CSS/JS.

**First feature (Stage 1):** Make the read-only operator view complete and trustworthy: show head and power path readings and their disagreement, clear quality and missing-data states, a useful history view, connection/staleness indicators, and a responsive layout. Add a pending-candidate view using a local example payload while the command contract is being agreed. Label simulation and replay visibly.

Use `contracts/examples/pending_candidate.json` for that pending card. It is explicitly an example; the baseline has no live approval endpoint.

**How:** Start by reading the telemetry schema and browser code. Extend `app.js` with small functions for formatting, rendering, and charting. Use `textContent` for external values. Add browser-side test fixtures or lightweight tests in `tests/dashboard/`; also run the browser manually at wide and narrow widths and with the gateway stopped. Do not assume null flow is zero.

**Acceptance:** In a demo the browser displays live simulator telemetry, accurately distinguishes disconnected/stale from fresh data, shows null readings honestly, and remains readable on a narrow screen. A pending-candidate example is visually reviewable without claiming that approval works yet.

**Next stage:** After the lead lands authenticated command and acknowledgement schemas, add approve/reject, mode selection, sweep abort, annotation, and reference-reading entry. Show pending and rejected states until the device acknowledges completion; never mark a click itself as a completed action.

## Shared start and handoff

1. Install `requirements-dev.txt`, run `python -m gateway.app`, and open
   `http://127.0.0.1:8765`. Run `python -m pytest` before editing.
2. Work in your own clone or worktree and a `codex/d-...` branch.
3. Change only your owned files. Put new tests in your role's `tests/` folder.
4. Preserve existing interfaces; propose shared contract changes to the lead.
5. Run all tests and demonstrate the feature with changed input. Explain
   what you changed, tests, and remaining limits in your PR.

The input curves, thresholds, and output of the simulator are placeholders.
Measured calibration and hardware evidence come later.
