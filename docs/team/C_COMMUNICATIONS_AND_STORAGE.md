# Role C: Gateway and records

Own the path from device telemetry to a stored, queryable history. Your contribution turns the current transient local view into repeatable experiment evidence.

**Current base:** `gateway/app.py` receives simulator telemetry in memory and serves fixed dashboard assets. `GET /api/telemetry?limit=120` returns schema version 1 and an `items` array; the browser relies on that shape. `contracts/telemetry.schema.json` defines each message.

**First feature (Stage 1):** Add versioned, bounded local session storage and replay to the gateway. Persist source, device/boot ID, sequence, time, model version, and units unchanged. Offer a way to select a saved session through the same read API or a separately documented endpoint without breaking the live one. Handle restart, malformed input, and full storage deliberately. Keep simulated recordings labeled simulation.

**How:** First test the `TelemetryStore` and current API under `tests/gateway/`. Add a small storage module in `gateway/` that writes JSONL or SQLite and validates records against the shared schema. Add CLI/API access to list/replay sessions. Run the baseline app and compare live versus replayed messages for exact data equality. Put local recordings in `outputs/local/`.

**Acceptance:** Record a session, restart the gateway, replay the same values in order, and show that dashboard live polling still works. Tests cover corrupt data, duplicate/reordered sequence, and bounded disk use. The API response remains compatible with the existing dashboard.

**Next stage:** Add MQTT and offline synchronization using a lead-approved message/command contract; measure bytes per hour and reconnect behavior. The device's estimation and safety continue to run without gateway connectivity.

## Shared start and handoff

1. Install `requirements-dev.txt`, run `python -m gateway.app`, and open
   `http://127.0.0.1:8765`. Run `python -m pytest` before editing.
2. Work in your own clone or worktree and a `codex/c-...` branch.
3. Change only your owned files. Put new tests in your role's `tests/` folder.
4. Preserve existing interfaces; propose shared contract changes to the lead.
5. Run all tests and demonstrate the feature with changed input. Explain
   what you changed, tests, and remaining limits in your PR.

The input curves, thresholds, and output of the simulator are placeholders.
Measured calibration and hardware evidence come later.
