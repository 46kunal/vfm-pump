# Shared contracts v1 (lead-owned)

Changes here require agreement with affected owners. Consumers must not copy and
independently modify these definitions.

## Existing internal Python API

Retain these interfaces while implementing your package:

- `vfm.config.load(path=None) -> dict`: shared configuration.
- `HAL.read_sensors() -> dict`: `t` (elapsed seconds), `dp_kpa`, `volts`,
  `amps`, `rpm`, `temp_c`, `valve_pct` (fraction 0â€“1), `quality`.
- `HAL.set_valve(fraction)` and `HAL.get_valve()`: the current simulator getter
  returns the command, not measured feedback. The lead can add an additive
  measured-position field rather than silently changing this meaning.
- `FastLoop(cfg).update(sample) -> dict`: existing keys `t`, `Q`, `sigma`,
  `Q_h`, `Q_p`, `sig_h`, `sig_p`, `resid_z`, `steady`, `conf`, `valid`,
  `Qref_p`, `sigQref_p`, `H_ref`, `sigH_ref`, `slope_h`.
- `Supervisor(cfg, fast, hal, operator).tick(sample, estimate)`: owns state,
  candidate lifecycle, and approval. Keep existing constructor defaults.
- `LearningModule` and candidate helpers remain in `vfm.slowloop`.

`valid` currently means both paths have valid inversions, not that every input
passed a sensor-quality check. `quality=1` is the simulator's existing marker,
not a complete per-signal quality specification. Extensions are lead-owned.

## External telemetry v1

See `telemetry.schema.json` and `examples/telemetry.json`. Runtime output is
newline-delimited JSON, one telemetry object per line.

- `t_s` is elapsed monotonic device time, not Unix/UTC time.
- `boot_id` identifies a runtime session; `sequence` increases within that session.
- All flow fields and uncertainty are L/min. Unavailable numeric readings are
  `null`, never JSON NaN or Infinity.
- `source` is simulation, replay, or hardware. The starter only emits simulation.
- `model_version` in the starter counts model changes in the current session;
  it is not yet a durable global model identity.
- `state`, `mode`, `confidence`, and `valid` reflect current device outputs.
- No simulator ground-truth flow is exposed to the application.

The initial fixture is a mock message, not a measured pump result. The runtime
adapter is in `vfm/runtime.py`, owned by the lead.

## Contracts still to agree

The lead owns future command, acknowledgement, audit, pending candidate,
reference, and annotation schemas. These are outside the four current tasks. Include identity, expiration, candidate/model
binding, units, result semantics, and timestamps. The lead merges agreed shared
schemas before consumers depend on them.

Root `config.json` stays lead-owned for compatibility. Propose additions in your
own role notes; do not create conflicting copies of shared calibration values.
Local experiments can use ignored configuration files under `outputs/local/`.

## Local read API (baseline)

`python -m gateway.app` serves `GET /api/telemetry?limit=120` at localhost:8765.
The response is `{ "schema_version": 1, "items": [telemetry_v1, ...] }`, oldest
to newest, with a bounded in-memory history. Limit must be 1..300. The
response can contain an empty list on startup. The browser polls once per
second. Preserve this response when adding storage or changing the dashboard.
There is no command API yet; the lead will agree its schema before controls are
enabled. These readings are simulation only until a real HAL is connected.
