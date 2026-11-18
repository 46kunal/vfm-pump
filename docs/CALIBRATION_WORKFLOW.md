# Calibration workflow (real hardware only)

Three command-line tools take you from raw sensor readings to a validated power-to-flow
profile. They read the gateway, so start it and the serial bridge first (see
[HARDWARE_ENDPOINTS.md](HARDWARE_ENDPOINTS.md)). Everything they write goes under
`data/real/`, never into `config.json`, which holds simulation placeholders.

```powershell
python -m gateway.app                        # terminal 1
python tools/serial_bridge.py --port COM13   # terminal 2
```

## 1. Load cell: `tools/calibrate_loadcell.py`

Needs no plumbing. Mount the cell as a cantilever (wired end fixed, free end carrying the
platform), then run it in a third terminal:

```powershell
python tools/calibrate_loadcell.py
```

It asks for the empty platform, then each known mass in grams (for example 500, 1000, 2000
from bottles weighed on a kitchen scale), then the empty platform again as a drift check.
It fits a straight line, prints the worst residual and the drift, and saves
`data/real/loadcell_calibration.json` with an id. It also prints the two lines to paste into
`vfm_sensors.ino`. A worst residual or drift above 5 g means the mounting or wiring needs
another look.

## 2. Reference collections: `tools/record_collection.py`

Needs the plumbing. For each valve setting it reads the start mass, you press Enter when water
starts entering the vessel and again when you divert it, and it reads the end mass after the
splashing settles. It computes `Q_ref = 60 x delta_mass / (density x duration)` (density from
the DS18B20) and the average pump voltage, current and power over the window.

```powershell
python tools/record_collection.py --pump-id AD-03-1 --session day1
```

- Use 6-8 valve settings and at least two collections per setting.
- Mark some whole runs as validation (`v` when asked, or `--split validation`). They are
  never used for fitting.
- Use collections of 10 s or more: your Enter-key timing is the largest error. Keep the
  vessel plus water well under 5 kg (the tool warns above 4.5 kg).
- Each saved run is one line in `data/real/collections/<session>.jsonl`. Note leaks, bubbles
  and spills when prompted. Runs with a deliberate fault go in as `fault` and are excluded.

## 3. Fit and validate: `tools/fit_power_model.py`

```powershell
python tools/fit_power_model.py data/real/collections/day1.jsonl
```

It fits `power = c0 + c1*Q + c2*Q^2` on the training runs (degree 1 or 2, whichever
evaluates better and stays monotonic), inverts it to estimate flow, and reports MAE, RMSE,
bias and maximum error on the validation runs, by low/middle/high flow band. It refuses to
fit with fewer than 5 valve settings or 6 training runs unless you pass `--allow-small`.
With no validation runs it falls back to leave-one-out and says that is weaker evidence.

The profile (`data/real/profiles/ad03_power_profile_<time>.json`) records the coefficients,
the valid flow, power, voltage and temperature ranges, the flow ranges where power barely
changes (flow should read Unavailable there), the raw files with their hashes, the load-cell
calibration ids, warnings, and a checksum.

## 4. Show the estimate: `gateway.app --profile`

Once the validation error is acceptable, restart the gateway with the profile:

```powershell
python -m gateway.app --profile data/real/profiles/ad03_power_profile_<time>.json
```

The gateway checks the profile's checksum and refuses a tampered, non-monotonic or
non-hardware profile. It also refuses one without held-out validation unless you pass
`--allow-unvalidated` (the dashboard then says "NOT validated"). `GET /api/hardware/latest`
gains an `estimate` object, and the dashboard shows it. The estimate is Unavailable, with the
reason, when the power reading is missing or stale, the supply voltage, water temperature or
pump power is outside the calibrated range, or the flow falls in a weak range.

## What this does not do yet

- Timing is by hand. The ESP32 could detect the mass rise automatically later.
- A good validation result applies only to this pump, supply and rig.
