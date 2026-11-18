# Product Requirements Document: Self-Calibrating Virtual Flow Meter (VFM)

| | |
|---|---|
| Product | Self-Calibrating Virtual Flow Meter for an AD-03 12 V submersible pump |
| Document status | Working draft for the Thursday demo |
| Status tags | **[Built]** exists in the repo, **[Partial]** exists but incomplete, **[Planned]** not built, **[Sim]** exists only in simulation, **[Out]** excluded |
| Rule for this document | Where something has not been measured, it says so. No accuracy number is promised before held-out validation produces one. |

---

## 1. Overview

### 1.1 One-line summary
Estimate the water flow of a pump from its **electrical power alone**, using a weighed-water load cell as the independent reference that calibrates and validates the estimate. No physical flow sensor is used in the final system.

### 1.2 What the product is
A small bench system made of an ESP32, a power sensor (INA219), a temperature sensor (DS18B20), a load cell with amplifier (5 kg + HX711), a pump, and a software stack (firmware, serial bridge, gateway, dashboard, calibration tools). It:

1. Reads the pump's voltage, current and power while the pump runs.
2. Measures the true flow by weighing the water that arrives in a jug over a timed window.
3. Fits a curve that maps pump power to flow.
4. Checks that curve against runs it was not trained on.
5. Shows the live flow estimate on a dashboard only when a validated profile exists, and shows "Unavailable" otherwise.

### 1.3 Why "virtual"
A virtual sensor replaces a physical one with a model. A flow sensor such as a YF-S201 would give flow directly but defeats the purpose of the project. The load cell is used **only as the calibration and validation reference**, not as part of the running product.

### 1.4 Scope of this release
Demo on Thursday on a single bench rig with a single pump. The hardware chain (sensors, serial, gateway, dashboard) and the calibration workflow are the core. Adaptive learning, unlearning and the digital-triplet supervisor exist as simulation and are presented as such.

---

## 2. Problem statement and motivation

### 2.1 Problem
Physical flow meters add cost, pressure drop, fouling risk and another point of failure to a pumping system. Small pumps often run without any flow measurement at all.

### 2.2 Insight
A centrifugal pump's electrical power changes with hydraulic load. In principle, a calibrated model can recover flow from power.

### 2.3 Why this is hard
- The power-to-flow relationship is **pump-specific, supply-specific and rig-specific**. It cannot be copied from a datasheet.
- Over some flow ranges, power barely changes, so flow is not identifiable there.
- A model that reports a confident number when it is invalid is worse than no number.

### 2.4 Therefore the product principle
**Calibrate against a real reference, validate on held-out runs, report the error honestly, and refuse to answer when the model is not valid.**

---

## 3. Goals, non-goals and design principles

### 3.1 Goals

| ID | Goal | Measured by |
|---|---|---|
| G1 | Measure pump voltage, current and power live | INA219 values appear on the dashboard |
| G2 | Produce ground-truth flow from weighed water | `Q_ref = 60 x delta_m / (rho x delta_t)` per run |
| G3 | Fit a power-to-flow model (degree 1 or 2) | Profile file with coefficients |
| G4 | Validate on held-out runs and report error | MAE, RMSE, bias, max error by flow band |
| G5 | Show live sensor data and the estimate | Dashboard |
| G6 | Refuse to estimate without a validated profile | Dashboard shows "Unavailable" |
| G7 | Tie the build to the course theory | Section 11 mapping |

### 3.2 Non-goals
- No physical flow sensor in the final system.
- No accuracy claim beyond what held-out validation shows.
- No cloud, MQTT or multi-pump deployment for the demo.
- No enclosure, certification or safety approval.
- No water-compatible pressure sensing in the core build.

### 3.3 Design principles
1. **Honesty over appearance.** A missing or failed sensor is left out of the data, never invented.
2. **Reference is separate from product.** The load cell calibrates; it is not needed at run time.
3. **Traceability.** Every profile records the raw files with hashes, load-cell calibration ids, warnings and a checksum.
4. **Real data stays separate from simulation.** Real outputs go under `data/real/`, never into `config.json`, which holds simulation placeholders.

---

## 4. Users, personas and use cases

### 4.1 Personas

| Persona | Description | Needs |
|---|---|---|
| Demo presenter | Runs the demo on Thursday | Reliable startup, live values, a clear estimate-vs-reference story |
| Calibration operator | Records collections and fits the model | Clear prompts, few manual steps, saved data |
| Team member | Reviews code, runs collections | Reproducible commands, documented data format |
| Evaluator | Judges rigor and theory fit | Honest error, traceable data, clear simulation vs hardware boundary |

### 4.2 Use cases

| ID | Use case | Actor | Outcome |
|---|---|---|---|
| UC1 | View live telemetry | Presenter | Voltage, current, power, temperature, load cell mass updating live |
| UC2 | Calibrate the load cell | Operator | Counts-per-gram and offset saved and pasted into firmware |
| UC3 | Record a reference collection | Operator | One line of reference flow plus mean pump power saved |
| UC4 | Fit and validate | Operator | Profile with held-out error and warnings |
| UC5 | See the estimate | Presenter | Estimated flow shown only if profile valid |
| UC6 | Compare estimate to reference | Presenter | Side-by-side numbers at several valve positions |
| UC7 | Handle a bad state | Presenter | Dashboard shows "Waiting for the ESP32" or "Unavailable", not a guess |

---

## 5. System architecture

### 5.1 Data flow
```
12 V adapter -> switch -> 2 A fuse -> INA219 (VIN+ -> VIN-) -> pump
                                        |
Load cell -> HX711 --------------------+
DS18B20 -------------------------------+--> ESP32 --USB serial, JSON line every 500 ms-->
                                                    tools/serial_bridge.py
                                                    --HTTP POST /api/hardware/...-->
                                                    gateway/app.py --> dashboard
                                                    tools/*.py read the gateway for calibration
```

### 5.2 Layers

| Layer | Component | Responsibility | Status |
|---|---|---|---|
| Edge firmware | `device/firmware/vfm_sensors/vfm_sensors.ino` | Read sensors, print one JSON line per 500 ms | Built, not yet flashed or verified end to end |
| Transport | `tools/serial_bridge.py` | Read serial lines, POST to the gateway | Built, needs pyserial installed |
| Gateway | `gateway/app.py`, `gateway/hardware.py` | Accept readings, serve latest/history, serve dashboard, own the sensor spec | Built |
| Calibration tools | `tools/calibrate_loadcell.py`, `record_collection.py`, `fit_power_model.py` | Produce a validated profile | Built |
| Profile consumer | Gateway loading a profile to compute estimated flow | Planned |
| Simulation core | `vfm/` (fastloop, slowloop, supervisor, faults, hal, sim) | Edge loop, online learning, unlearning, supervisor | Sim |

### 5.3 Gateway HTTP interface
- `GET /api/hardware/latest` returns the most recent reading per sensor.
- `GET /api/hardware/history` returns recent readings.
- `POST /api/hardware/<sensor>` accepts a reading (the bridge uses this; `--token` optional).
- `GET /api/telemetry` serves the dashboard's simulation telemetry.
- Default address: `http://127.0.0.1:8765`.

### 5.4 Process startup
```powershell
python -m gateway.app                        # terminal 1
python tools/serial_bridge.py --port COM13   # terminal 2 (use your COM port)
```
The Arduino Serial Monitor must be closed or it holds the port.

### 5.5 Non-functional constraints
- Sensor line rate: one JSON line per 500 ms (2 Hz) from hardware.
- A sensor that fails to read is omitted from that line.
- Real hardware data is never mixed into simulation config.

---

## 6. Hardware specification

### 6.1 Bill of materials

| Part | Role | Status | Notes |
|---|---|---|---|
| ESP32 DevKit on female headers | Controller | Wired | One 3V3 pin and two GND pins, hence the rails |
| INA219 | Pump voltage/current, high side | Verified | About 12.3 V, 415 to 735 mA, 5 to 9 W running; 12.58 V and 0 mA with switch off |
| DS18B20 + 4.7 kΩ pull-up | Water temperature, density | Verified | Reads on the perfboard |
| 5 kg bar load cell + HX711 | Reference mass | Responds, **unstable** | Needs rigid clamp and retest |
| AD-03 12 V submersible pump | Plant | Working | Max head 6 m (about 59 kPa) |
| 12 V 5 A adapter, switch, 2 A fuse | Power | Wired | |
| LM2596 buck converter | 5 to 6 V servo supply | Not connected | Optional |
| MG996R servo | Automatic valve positioning | Not connected | Optional; use the 2-arm horn |
| 8 mm braided clear PVC hose, red inline valve, hose clamps | Plumbing | Dry-fit OK | Pipe and valve fit |
| Araldite, M-seal, glue-gun sticks | Mounting and sealing | Bought | |
| Perfboard with 3V rail and G rail | Wiring | Built | |
| HX710B pressure module | Optional pressure | Not obtained | Skipped |

### 6.2 Pin and wiring map

| Signal | ESP32 pin | Notes |
|---|---|---|
| INA219 SDA / SCL | GPIO21 / GPIO22 | I2C; INA219 VCC to 3V rail, GND to G rail |
| DS18B20 DATA | GPIO4 | 4.7 kΩ from DATA to 3V rail; strip order G / D / 3V |
| HX711 DT / SCK | GPIO25 / GPIO26 | VCC to 3V rail, GND to G rail |
| Load cell to HX711 | | Red E+, black E−, white A−, green A+ |
| Servo signal | GPIO13 | Servo power from buck, never from ESP32 pins |

Pump power path (high side): adapter red, then fuse, then switch, then INA219 VIN+, then VIN−, then pump red. Adapter black and pump black join a ground link to the ESP32 GND and G rail. Add a 470 µF capacitor across servo 5 V and GND if the servo is used.

### 6.3 Power
- 12 V adapter powers the pump through the INA219.
- Servo (optional) is powered from the buck output set to about 5.0 to 5.5 V, never from ESP32 pins. The INA219 can serve as a voltmeter to set the buck before connecting the servo.
- ESP32 is powered over USB.

### 6.4 Mechanical layout
- Pump submerged in the reservoir.
- Hose piece A (about 50 cm): pump outlet to the valve.
- Hose piece B (about 30 to 40 cm): valve to a point above the jug.
- The jug rests on the load cell. The load cell is clamped at the wired end as a cantilever, fixed to a board or table.
- Piece B's end hangs free above the jug and never touches it.
- Hose and valve are fixed to something solid so they do not pull on the load cell.
- Jug plus water stays under 4.5 kg (load cell limit 5 kg).

### 6.5 Pressure sensing (optional, excluded from core)
Pressure at the pump outlet is a possible second input because power can be flat across valve positions.

| Option | Verdict |
|---|---|
| HX710B 0 to 40 kPa module | Air sensor; needs a syringe air-trap tap; limited to 40 kPa while the pump can reach about 59 kPa; not obtained |
| 5 V 0.5 to 4.5 V G1/4 water transducer + ADS1115 | Reads water directly; total cost likely well above the budget |
| No pressure | Core build; dashboard shows pressure as Unavailable |

If added later it needs a syringe-nozzle tee, a `hx710b` spec in `gateway/hardware.py`, firmware changes, and dashboard support. The valve must never be fully closed with the HX710B connected.

---

## 7. Functional requirements

Priority: **M** must, **S** should, **C** could.

### 7.1 Firmware

| ID | Requirement | Pri | Status | Acceptance |
|---|---|---|---|---|
| FR1 | Print one JSON line every 500 ms containing `ina219`, `ds18b20`, `hx711` | M | Built | Serial Monitor at 115200 shows all three keys |
| FR2 | Omit a sensor that fails to read; never invent values | M | Built | Unplug DS18B20 and its key disappears |
| FR3 | HX711 reports `raw`, and `mass_g` once `HX_COUNTS_PER_GRAM` is non-zero | M | Built | After pasting constants, `mass_g` appears |
| FR4 | Reject out-of-range temperature (outside −55 to 125 °C) | S | Built | Disconnected probe is omitted |

### 7.2 Transport and gateway

| ID | Requirement | Pri | Status | Acceptance |
|---|---|---|---|---|
| FR5 | Bridge forwards each valid JSON line to the gateway | M | Built | Dashboard values change when the pump runs |
| FR6 | Gateway exposes latest and history for each sensor | M | Built | `GET /api/hardware/latest` returns current values |
| FR7 | Dashboard shows an honest waiting state with no data | M | Built | Shows "Waiting for the ESP32" before the bridge runs |
| FR8 | Dashboard shows live voltage, current, power, temperature, mass | M | Partial | All five visible with real data |

### 7.3 Calibration

| ID | Requirement | Pri | Status | Acceptance |
|---|---|---|---|---|
| FR9 | Load cell calibration produces counts-per-gram and offset, plus a drift check | M | Built | Worst residual and drift at or under 5 g |
| FR10 | Collection tool records 6 to 8 valve settings, at least 2 runs each | M | Built | Lines saved under `data/real/collections/<session>.jsonl` |
| FR11 | Mark whole runs as validation; they are never used for fitting | M | Built | Fit report distinguishes training from validation |
| FR12 | Fit tool fits degree 1 or 2, enforces monotonicity, reports MAE, RMSE, bias, max error by flow band | M | Built | Report printed and profile saved |
| FR13 | Fit tool flags flow ranges where power barely changes | M | Built | Listed in the profile |
| FR14 | Profile is versioned with raw-file hashes and a checksum | M | Built | Profile JSON contains them |

### 7.4 Estimation and presentation

| ID | Requirement | Pri | Status | Acceptance |
|---|---|---|---|---|
| FR15 | Gateway loads a validated profile and computes estimated flow | M | Planned | Estimate appears only with a valid profile |
| FR16 | Estimate is Unavailable outside the profile's valid ranges (flow, power, voltage, temperature) | M | Planned | Out-of-range input shows Unavailable |
| FR17 | Dashboard shows estimate beside load cell reference | S | Planned | Both visible at once |
| FR18 | Servo drives the valve in Manual, Assisted and Auto modes | C | Planned | Valve moves to a commanded position |
| FR19 | Online adaptation (RLS, CUSUM drift, excitation gate) | C | Sim | Runs in simulation only |
| FR20 | Machine unlearning via Sherman-Morrison downdate | C | Sim | Removes a run's influence in simulation |

---

## 8. Calibration and validation method

### 8.1 Load cell calibration
1. Clamp the wired end of the cell firmly; the free end carries the platform.
2. Run `python tools/calibrate_loadcell.py`.
3. It asks for the empty platform, then each known mass in grams (for example 500, 1000, 2000 using bottles weighed on a kitchen scale), then the empty platform again.
4. It fits a straight line, prints the worst residual and drift, saves `data/real/loadcell_calibration.json`, and prints two lines to paste into `vfm_sensors.ino`: `HX_COUNTS_PER_GRAM` and `HX_OFFSET`.
5. A worst residual or drift above 5 g means mounting or wiring needs another look.

Pre-check before calibrating (the HX711 stability test):
1. With nothing on the cell, watch raw for 30 s. It should stay within a few hundred counts.
2. Rest a bottle on the free end. The value should jump and hold.
3. Remove it. The value should return to about the start.

### 8.2 Reference collections
Command:
```powershell
python tools/record_collection.py --pump-id AD-03-1 --session day1
```
Per run: it reads the start mass, you press Enter when water starts entering the vessel and again when you divert it, then it reads the end mass after splashing settles. It computes:

`Q_ref = 60 x delta_mass / (density x duration)`

with density from the DS18B20 temperature, and the mean pump voltage, current and power over the window.

Rules:
- 6 to 8 valve settings, at least 2 collections per setting.
- Mark some whole runs as validation (answer `v` when asked, or use `--split validation`).
- Runs of 10 s or more; Enter-key timing is the largest error.
- Keep vessel plus water under 4.5 kg (tool warns above 4.5 kg).
- Note leaks, bubbles and spills; deliberate-fault runs are marked `fault` and excluded.
- Options: `--settle` (seconds before the end mass, default 3), `--trim` (seconds trimmed from the window ends), `--mass-seconds` (averaging window for mass).

### 8.3 Fit and validate
Command:
```powershell
python tools/fit_power_model.py data/real/collections/day1.jsonl
```
- Model: `power = c0 + c1*Q + c2*Q^2`, degree 1 or 2 (auto picks the better one that stays monotonic), then inverted to estimate flow.
- Reports MAE, RMSE, bias and maximum error on validation runs, by low, middle and high flow band.
- Refuses to fit with fewer than 5 valve settings or 6 training runs unless `--allow-small` is passed.
- With no validation runs it falls back to leave-one-out and says that is weaker evidence.

### 8.4 Profile contents
`data/real/profiles/ad03_power_profile_<time>.json` records: coefficients, valid flow/power/voltage/temperature ranges, flow ranges where power barely changes, raw files with hashes, load-cell calibration ids, warnings and a checksum.

### 8.5 Publishing rule
The gateway must not show an estimated flow until a validated profile exists and the validation error is judged acceptable. A good result applies only to this pump, supply and rig.

---

## 9. Data model and files

| Path | Content |
|---|---|
| `data/real/loadcell_calibration.json` | Load cell calibration with an id |
| `data/real/collections/<session>.jsonl` | One line per reference run |
| `data/real/profiles/ad03_power_profile_<time>.json` | Fitted, versioned profile |
| `config.json` | Simulation placeholders only, never real data |

A collection line contains (conceptually): pump id, session, split (training, validation or fault), start and end mass, duration, density, `Q_ref`, mean voltage, mean current, mean power, and notes.

---

## 10. User interface (dashboard)

### 10.1 States
| State | Condition | Display |
|---|---|---|
| Waiting | No data from the ESP32 | "Waiting for the ESP32" |
| Live, uncalibrated | Data present, no profile | Live values; estimated flow "Unavailable" |
| Live, calibrated | Data present, valid profile | Live values plus estimated flow |
| Out of range | Input outside profile validity | Estimate "Unavailable" with reason |
| Sensor missing | A sensor omitted from the line | That sensor shown as unavailable |

### 10.2 Content
- Pump voltage, current and power.
- Water temperature.
- Load cell mass and (after calibration) grams.
- Estimated flow vs reference flow (planned).
- Pressure shown as Unavailable.

---

## 11. Theory mapping

| Theory | Where it lives | Hardware or sim |
|---|---|---|
| Edge computing | ESP32 reads sensors and runs the fast loop; `vfm/fastloop.py` in simulation (10 Hz) | Firmware reads on hardware; fast loop Sim |
| Online machine learning (RLS, CUSUM drift, excitation gate) | `vfm/slowloop.py` | Sim |
| Machine unlearning (Sherman-Morrison downdate) | `vfm/slowloop.py` | Sim |
| Digital triplet (Manual, Assisted, Auto) | `vfm/supervisor.py` | Sim |
| Fault handling | `vfm/faults.py` | Sim |
| Real-vs-reference calibration | `tools/` | Built on hardware |

Presentation rule: state clearly that the learning, unlearning and supervisor behaviors are demonstrated in simulation, and that the hardware path demonstrates sensing, reference measurement and offline calibration.

---

## 12. Success metrics and acceptance criteria

| # | Criterion | Target | Status |
|---|---|---|---|
| A1 | All three sensors in one serial JSON line | Yes | Not yet verified |
| A2 | Dashboard updates with real values via the bridge | Yes | Not yet verified |
| A3 | HX711 no-load stability over 30 s | Within a few hundred counts | Failing in the handheld test; retest after mounting |
| A4 | HX711 returns to baseline after load removal | Yes | Untested |
| A5 | Load cell calibration worst residual and drift | 5 g or less | Not run |
| A6 | Collections recorded | 6 to 8 settings, at least 2 runs each, some validation | Not run |
| A7 | Held-out flow error | Reported honestly; no fixed target promised | Not measured |
| A8 | Estimate refused without a valid profile | Yes | Built for the "no profile" case |
| A9 | Demo completes without editing files by hand | Yes | Not yet |

---

## 13. Risks and mitigations

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | HX711 drift and spikes | High until mounted | Bad reference, bad model | Rigid cantilever clamp; stability test before calibrating |
| R2 | Power barely changes across some valve positions | Medium | High error, unidentifiable range | Flag weak ranges; report honestly; Unavailable there |
| R3 | Hose or valve pulls on the load cell | Medium | Reference error | Free-pouring outlet, fixed plumbing |
| R4 | Jug overload | Low | Load cell damage | Under 4.5 kg; short runs |
| R5 | Enter-key timing error on short runs | High | Reference error | Runs of 10 s or more |
| R6 | Supply sag changes power at a given flow | Medium | Model bias | Record voltage; profile stores valid voltage range |
| R7 | Water temperature shifts density and viscosity | Low | Small bias | Density from DS18B20; profile stores valid temperature range |
| R8 | Air in the pump or leaks | Medium | Outlier runs | Note and exclude faulty runs |
| R9 | One day to build and calibrate | High | Schedule | Prioritize FR1 to FR16; servo and pressure optional |
| R10 | Over-claiming simulation features | Medium | Credibility | Section 11 presentation rule |
| R11 | Serial port held by Arduino Serial Monitor | Medium | Bridge fails | Close the Serial Monitor first |
| R12 | Perfboard solder joint fault | Low | Intermittent readings | Reflow and re-test |

---

## 14. Plan to Thursday

### 14.1 Today
1. Dry-fit plumbing (done: pipe and valve fit).
2. Flash `vfm_sensors.ino`; confirm all three sensors print in one line.
3. `pip install pyserial`; close the Serial Monitor; run the bridge; confirm live dashboard values.

### 14.2 Tomorrow morning
1. Mount the load cell as a cantilever; run the stability test.
2. Run `tools/calibrate_loadcell.py`; paste `HX_COUNTS_PER_GRAM` and `HX_OFFSET`; re-flash.

### 14.3 Tomorrow afternoon
1. Record collections at 6 to 8 valve settings, at least 2 runs each, several marked validation; runs of 10 s or more.
2. Run `tools/fit_power_model.py`; read the validation error and warnings.

### 14.4 Tomorrow evening
1. If the validation error is acceptable, wire the profile into the gateway (FR15, FR16).
2. Rehearse the demo; prepare slides with the theory mapping.

### 14.5 Optional if time remains
- Set the buck with the INA219 as voltmeter; mount and test the servo with the 470 µF capacitor.
- Pressure tap (needs the HX710B).

### 14.6 Team tasks

| Task | Notes |
|---|---|
| Collection crew (three people) | One on the valve, one timing and pressing Enter, one noting leaks and spills |
| Load cell mount | Board, clamp, spacers; keep it rigid |
| Slides and theory mapping | Use Section 11 |
| Code review and testing | `tools/` and `gateway/` tests |
| Circuit and plumbing diagrams | From Section 6 |
| Demo script and rehearsal | From Section 15 |

---

## 15. Demo script

1. Power the rig; start the gateway and bridge. Show the dashboard with real values.
2. Show the "Unavailable" estimated flow before calibration and explain why.
3. Show the load cell calibration result (residual and drift).
4. Show collected data and the fit result, including held-out error and weak-range warnings.
5. Run the pump at two or three valve positions; show the estimate beside the weighed reference (if FR15 to FR17 are done), or the stored fit if not.
6. Explain the theory mapping, stating what is simulated.
7. Close with limitations: single pump and rig, error as measured, no pressure input.

Fallback if the live rig misbehaves: show a recorded collection file and the fit report, and the simulation dashboard.

---

## 16. Out of scope and future work

- Gateway profile hot-reload and profile versioning UI.
- Automatic mass-rise detection on the ESP32 instead of Enter-key timing.
- Pressure as a second model input.
- MQTT and cloud deployment.
- Multi-pump support and fleet calibration.
- Online adaptation and unlearning running on the ESP32.
- Servo-driven automatic collection sweeps.

---

## 17. Open questions

1. Will profile loading in the gateway be finished before Thursday?
2. Are the servo and pressure sensor in or out for the demo? (Currently out.)
3. What held-out error will the team commit to quoting? (Decide after measuring.)
4. Does the load cell stay stable once clamped? (Settled by the stability test.)

---

## 18. Glossary

| Term | Meaning |
|---|---|
| VFM | Virtual flow meter |
| Q_ref | Reference flow computed from weighed water |
| Held-out / validation run | A run never used for fitting |
| Profile | Versioned, checksummed fit with valid ranges and warnings |
| INA219 | Voltage/current/power sensor |
| HX711 | Load cell amplifier |
| Cantilever mount | Wired end fixed, free end carries the load |
| RLS | Recursive least squares |
| CUSUM | Cumulative-sum drift detector |
| Sherman-Morrison | Rank-one matrix update used for unlearning |
