# Hardware endpoints (real data only)

The gateway no longer generates any data. The dashboard shows only what the ESP32
posts. Until something is posted, every value reads N/A and the status pill says
"Waiting for ESP32".

## Run it

```powershell
python -m pip install -r requirements-dev.txt
python -m gateway.app                                   # http://127.0.0.1:8765
python tools/serial_bridge.py --port COM13              # forwards ESP32 serial lines
```

Flash `device/firmware/vfm_sensors/vfm_sensors.ino` first. Close the Arduino Serial
Monitor before starting the bridge: only one program can open the port.

## POST endpoints (JSON body, at most 4096 bytes)

| Sensor | Endpoint | Body | Limits |
|---|---|---|---|
| INA219 (pump V/A) | `POST /api/hardware/ina219` | `{"volts": 12.3, "amps": 0.62}` | volts 0..32, amps -3.5..3.5. `power_w` is computed. |
| DS18B20 (water) | `POST /api/hardware/ds18b20` | `{"temp_c": 24.5}` | -55..125 |
| HX711 (load cell) | `POST /api/hardware/hx711` | `{"raw": -566400}` and/or `{"mass_g": 12.5}` | at least one of `raw`, `mass_g` |
| Servo (commanded angle) | `POST /api/hardware/servo` | `{"angle_deg": 90}` | 0..180. This is the command, not measured position. |
| Several at once | `POST /api/hardware/sample` | `{"ina219": {...}, "ds18b20": {...}, "hx711": {...}}` | all-or-nothing |

Responses: `200 {"ok": true, "received": [...]}`, `400` bad or impossible value,
`401` wrong token, `404` unknown sensor, `411`/`413` bad length. Fields not listed,
strings, booleans, NaN and Infinity are rejected. Bad values are never stored.

## GET endpoints

- `GET /api/hardware/latest` returns the newest reading per sensor with `age_s` and
  `stale` (true after 3 s). A sensor that has never reported is `null`.
- `GET /api/hardware/history?sensor=ina219&limit=120` returns up to 600 recent rows.
- `GET /api/telemetry?limit=120` is the unchanged estimated-flow telemetry v1. It
  stays empty until a calibrated estimator feeds it, so the dashboard shows
  estimated flow as N/A. No flow is invented.

## Try it without the ESP32

```powershell
curl -X POST http://127.0.0.1:8765/api/hardware/ina219 -H "Content-Type: application/json" -d "{\"volts\":12.3,\"amps\":0.62}"
```

That posts a value you typed, so it appears on the dashboard. Use it only to test the
wiring of the software, not as data.

## Optional token and Wi-Fi

`python -m gateway.app --token SECRET` requires an `X-VFM-Token: SECRET` header on
every POST (the bridge accepts `--token`). The gateway listens on `127.0.0.1` by
default. Use `--host 0.0.0.0` only if the ESP32 posts over Wi-Fi, and then set a
token and keep it on a trusted network. There is no encryption.

## Load-cell calibration

Until `HX_COUNTS_PER_GRAM` is set in the sketch, only `raw` counts are sent and the
dashboard shows them as "not calibrated". Mass in grams appears after calibration.
