# Software build plan

## Running baseline (Stage 0)

```
SimHAL -> FastLoop -> Supervisor -> telemetry v1 -> local gateway -> browser
```

`python -m gateway.app` starts a 10 Hz simulator worker and a localhost HTTP
server. `GET /api/telemetry?limit=120` returns `{ "schema_version": 1,
"items": [...] }`. The browser polls that API. The gateway serves only fixed
static assets and has no control endpoint. The dashboard labels the data as
simulation. `vfm.runtime` can also emit finite JSONL recordings.

This is the common stage all four people can run and inspect before coding.
It establishes the engineering-unit telemetry contract, a visible dashboard,
and integration tests. It does not claim physical accuracy or safe control.

## Stage 1: independent software work

| Owner | Build on the baseline | Demonstrate |
|---|---|---|
| A, algorithms | Harden sensor-to-flow calculations and candidate checks; add dataset comparison or commissioning helpers | Known readings, invalid readings, and a candidate accepted/rejected by tests |
| B, device (lead) | Connect fault detection and quality handling to the runtime/supervisor; protect sweeps and model application | Inject bad readings and show state/audit behavior without changing the active curve unexpectedly |
| C, gateway | Persist the telemetry stream as versioned sessions and replay it through the same read API | Stop/restart the gateway and inspect/replay a labeled simulation session |
| D, dashboard | Add a proper operator view: head/power comparison, uncertainty/history, fault/stale states, and a pending-candidate view using supplied example data | Navigate the browser view and explain normal, invalid, and pending states |

Each person can develop with the existing simulator and fixtures. C and D
preserve the current read API. A and B preserve the existing Python method
signatures until an agreed contract change is merged.

## Stage 2: integrate the four contributions

The lead merges one PR at a time, runs all tests, and demonstrates simulator
telemetry through storage and the dashboard. Define command and acknowledgement
schemas together before building approve/reject or sweep controls. Commands
must be validated by the device supervisor, not trusted merely because a
button was clicked. Add durable audit and model state before enabling commands.

## Stage 3: hardware-ready path

Keep `HAL.read_sensors`, `set_valve`, and `get_valve` as the device boundary.
Implement a real adapter when sensors and valve arrive; convert raw readings
to kPa, V, A, rpm, degrees C, and valve fraction 0..1. Separate measured
position from commanded position. Calibrate sensors and pump curves from real
reference measurements and store a versioned calibration profile. Compare a
C++/ESP32 implementation with Python on the same saved data. Measure timing,
RAM, interlocks, offline behavior, and accuracy on the rig. The current
simulation does not substitute for those measurements.

## Shared rules

- Telemetry fields and units are in `contracts/telemetry.schema.json`.
- `source` identifies simulation, replay, or hardware; never relabel a recorded
  simulation as physical data.
- Invalid numeric outputs are JSON null, not NaN or an invented zero.
- Control actions and model changes require a recorded, validated decision.
- Generated files go under ignored `outputs/local/`; real rig logs later go in
  a separately labeled `data/real/` dataset.
