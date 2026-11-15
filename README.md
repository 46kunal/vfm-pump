# Self-Calibrating Virtual Flow Meter

A Python reference and local software for a pump flow estimator. The live
dashboard shows **only real ESP32 readings** (pump V/A, water temperature, load
cell). The simulator remains only for offline tests and scenarios; its curves and
results are placeholders, not physical-rig results.

## Run the integrated baseline

```powershell
python -m pip install -r requirements-dev.txt
python -m gateway.app
```

Open `http://127.0.0.1:8765`. Nothing is shown until the ESP32 posts readings:
see [docs/HARDWARE_ENDPOINTS.md](docs/HARDWARE_ENDPOINTS.md) for every endpoint and
`tools/serial_bridge.py` to forward the USB serial output. Estimated flow stays
N/A until a calibrated model exists. Stop the process with Ctrl+C.

```powershell
python -m pytest
python -m vfm.runtime --steps 20
python scenarios/run_all.py
```

The last command runs E1-E7 in simulation and regenerates the tracked baseline
plots/results in `outputs/`. Use `outputs/local/` for new experiments.

## Where to start

- [Software build plan](docs/ARCHITECTURE.md): baseline, parallel work,
  integration, and hardware path.
- [Team workflow](CONTRIBUTING.md): four owners including the lead, file
  boundaries, branches, and reviews.
- [Individual role guides](docs/team/): exact first contributions and later
  responsibilities.
- [Telemetry contract](contracts/README.md): schema, units, and read API.

## Code layout

| Area | Purpose |
|---|---|
| `vfm/fastloop.py`, `vfm/slowloop.py` | Flow estimation, calibration candidate, CUSUM, unlearning |
| `vfm/hal.py`, `vfm/sim.py`, `vfm/supervisor.py`, `vfm/faults.py` | Device boundary, simulator, states, interlocks, fault checks |
| `vfm/runtime.py` | Simulator-to-telemetry adapter and JSONL output |
| `gateway/app.py` | Local read API and static dashboard serving |
| `dashboard/` | Browser app served by the gateway |
| `contracts/` | Shared telemetry schema and simulated fixtures |
| `tests/`, `scenarios/` | Automated checks and simulated experiments |

## Hardware boundary and known limitations

The eventual real adapter implements `HAL.read_sensors()`, `set_valve()`, and
`get_valve()` and converts readings to kPa, V, A, rpm, degrees C, and a valve
fraction from 0 to 1. Real sensor calibration, pump curves, valve feedback,
ESP32 timing, accuracy, and safety behavior must be measured on the physical
rig. The simulator uses the same curve family and affinity laws as the
estimator, with simplified Gaussian noise and head-only wear, so its passing
accuracy scenarios are not evidence of real accuracy.

The current gateway and dashboard are read-only. Operator commands, MQTT,
authenticated approval, durable model storage, and the ESP32 port are later
stages. Keep simulation and hardware data labeled separately.
