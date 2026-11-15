# AD-03 Virtual Flow Meter — Hardware Implementation Guide

This is the standalone build guide for the physical rig. It covers the **first, power-only build** and the later pressure-sensor upgrade. The full research and software plan is in [VFM_FULL_PROJECT_PLAN.md](VFM_FULL_PROJECT_PLAN.md).

## 1. What the finished rig does

```text
Water: reservoir → submerged AD-03 → pressure tee → control valve → selector
                                                        ├→ reservoir return
                                                        └→ catch vessel on load cell

Power: 12 V adapter → switch → two protected branches
                         ├→ current sensor → pump
                         └→ 5 V buck → servo

Signals: INA219 + DS18B20 + HX711 → ESP32 → Wi-Fi/dashboard
                                    └→ servo signal
```

The pressure tee can be capped during the first build. There is no permanent inline flow sensor. Collected mass and time give an independent flow reference for calibration. The AD-03 label says **12 V DC, 20 W, Hmax 6.0 m, Qmax 15 L/min, IPX8**. The maxima are separate endpoints, not a simultaneous operating point. Its actual current, flow curve, outlet diameter, and startup behavior must be measured.

## 2. Build inventory

### Electronic parts and power

| Item | Quantity | Role / requirement |
| --- | ---: | --- |
| AD-03 submersible centrifugal pump | 1 | Water circulation at regulated 12 V |
| ESP32 DevKit | 1 | Sensor reading, estimator, servo command, Wi-Fi |
| INA219 breakout | 1 | Pump-branch voltage/current; **verify board/shunt current rating** before insertion |
| Waterproof three-wire DS18B20 | 1 | Water temperature |
| 5 kg single-point load cell and HX711 | 1 each | Reference mass measurement |
| MG996R positional servo | 1 | Turns the control valve through a bracket/coupler |
| Regulated 12 V, 5 A adapter | 1 | Pump and buck input |
| LM2596 adjustable buck | 1 | Set to 5.0 V for servo only |
| DC switch | 1 | At least 12 V, 5 A DC rating |
| Branch fuses and matching holders | 2 branches | Final pump fuse chosen after current/rating checks; servo branch protected separately. One 2 A fuse is already available, but neither branch assignment nor final pump value is assumed |
| Electrolytic capacitor | 1 | 470–1000 µF, at least 16 V; across servo 5 V/GND near servo |
| Resistor | 1 | 4.7 kΩ, 0.25 W; DS18B20 DATA pull-up to 3.3 V |
| DC input jack/connector, terminals, suitably rated power wire | As needed | Secure 12 V distribution; match adapter polarity and current |
| Perfboard, female headers, signal jumpers, heat shrink, strain relief | As needed | Final dry mounting after bench checks |
| USB data cable and multimeter | 1 each | ESP32 power/programming and electrical verification |
| Breadboard | 1 | **Sensor signal tests only**; never carry pump or servo current through it |

Do not use thin jumper leads for the pump or servo power path. The adapter being rated 5 A does not prove the INA219 breakout, jack, switch, buck, wires, or fuse holders are rated for the load. Check each part's actual marking or specification.

### Water-loop and mounting items

| Item | Quantity | Sizing / purpose |
| --- | ---: | --- |
| Covered reservoir | 1 | Holds pump fully submerged with adequate water above intake |
| Catch vessel | 1 | Fits platform; vessel plus collected water stays below 5 kg and below vessel capacity |
| Water tubing | Length to fit layout | Inside diameter matches the **measured** AD-03 outlet barb; maintain suitable bore through fittings |
| Hose clamps / compatible retaining fittings | At each hose connection | Secure every pressurized connection |
| Discharge T-joint and removable cap | 1 each | Pressure tap upstream of control valve; cap during first build |
| Water control valve | 1 | Shaft and operating torque compatible with servo/coupler; hose fittings match tubing |
| Return/catch diverter or movable outlet | 1 | Directs all discharge after the control valve to return or weighing vessel |
| Valve fittings/adapters | As required | Match actual threads, barb diameters and sealing method |
| Servo bracket, shaft coupler, fasteners | 1 set | Rigid, aligned valve actuation with no tubing twist |
| Load-cell base, top platform, spacers/fasteners | 1 set | Correct single-point bending mount; no alternate load path |
| Dry mounting board/enclosure, drip loops, cable ties | As required | Keep electronics away from splash and strain |

Measure the pump outlet outside diameter, valve connection size, tee connection size, and desired tube run before buying plumbing fittings. The previous AD20P parts and diagrams are **not** dimensional specifications for the AD-03.

## 3. Exact electrical connections

Disconnect the adapter while changing wiring. Verify DC jack center/sleeve polarity with a meter; do not infer it from wire color.

```text
Adapter positive → DC jack positive → main switch → +12 V distribution
  Pump branch: +12 V → pump fuse → INA219 VIN+ → INA219 VIN− → AD-03 positive
  Servo branch: +12 V → servo fuse → LM2596 IN+
                LM2596 OUT+ (verified 5.0 V) → MG996R V+

Adapter negative → DC jack negative → common ground distribution
  → AD-03 negative, LM2596 IN−, LM2596 OUT−, MG996R GND,
    ESP32 GND, INA219 GND, HX711 GND, DS18B20 GND

Laptop USB → ESP32 USB
ESP32 GPIO13 → MG996R signal
470–1000 µF capacitor: positive to local servo 5 V; negative to servo GND
```

The INA219's `VIN+` and `VIN−` screw terminals form the high-side **pump-current path**. Its small `VCC/GND/SDA/SCL` pins are logic connections. Do not include the servo load in the INA219 path, and do not bridge its shunt with a parallel wire. Check the breakout's shunt current capability and its temperature at measured load; replace the board with an appropriately rated sensor if needed. The final fuse must protect the wire and module while surviving normal startup. A 2 A fuse may trip on pump startup. Do not replace a repeatedly tripping fuse with a larger one until the cause and ratings are known.

Set the LM2596 output with no servo attached and verify **5.0 V** with the multimeter. Then connect the servo and verify the rail again during movement. Never connect 12 V to the ESP32 or servo. USB powers the ESP32; the common ground provides a reference for the servo signal and INA219 readings.

### ESP32 pin table

| Component pin | ESP32 / supply connection | Note |
| --- | --- | --- |
| INA219 VCC/GND | 3V3/GND if that breakout supports 3.3 V | Confirm actual board logic requirements |
| INA219 SDA/SCL | GPIO21/GPIO22 | I²C; scan address before pump test |
| DS18B20 VCC/GND/DATA | 3V3/GND/GPIO4 | 4.7 kΩ DATA to 3V3; verify probe wire colors |
| HX711 VCC/GND | 3V3/GND if module supports 3.3 V | Confirm with module documentation |
| HX711 DT/SCK | GPIO16/GPIO17 on ESP32-WROOM | On WROVER, use GPIO25/GPIO26 to avoid PSRAM pins |
| Load cell E+/E−, A+/A− | Matching HX711 labelled terminals | Follow the actual cell's wiring chart; colors vary |
| MG996R signal | GPIO13 | Servo V+ from buck, GND common |
| Future pressure sensor | To be assigned after exact device selection | Sensor range, voltage and interface must first be verified |

## 4. Assemble the water loop

1. Place the pump inside the reservoir on a stable support so its intake is clear of the floor and walls. Fill above its safe minimum submersion level and mark a low-water limit. Route the pump cable upward with a drip loop.
2. Secure tubing to the pump outlet using the measured matching size and clamp. Route it to the T-joint. Cap the side port securely for the first build.
3. Fix the tee in place, upstream of the control valve. Record the tee height relative to the water surface for the pressure upgrade. Keep its position and main hose route the same for calibration and normal operation.
4. Connect tee → valve → diverter. Route one diverter outlet firmly back to the reservoir and the other into the catch vessel. **All water must pass through the same control valve** in either mode.
5. Turn the valve by hand to find its true direction and stops. Attach the servo bracket and aligned coupler without forcing the shaft. Record safe servo angles before powering the pump. Avoid sustained operation at a fully closed valve.
6. Mount the load cell with one end fixed and one end supporting the top plate, following its mechanical drawing. The vessel must sit entirely on that plate; the hose must not press on the vessel or platform. Prevent tipping and overflow.
7. Run a brief return-path leak test, then a short catch-path test. Check each connection and dry the rig before energizing electronics nearby.

## 5. Build and test in order

| Stage | Procedure | Accept when |
| --- | --- | --- |
| A. Supply | Measure unloaded adapter voltage and polarity; inspect switch, jack, fuse holders and power wire | Near 12 V, correct polarity, secure terminals |
| B. Pump alone | With the pump submerged and outlet returning, run briefly through a protected branch; measure running and startup current if meter supports capture | Reliable flow, no leaks, overheating or repeated fuse trips |
| C. Current sensor | Compare measured current with INA219 board/shunt rating; only then insert it high-side | INA219 V/A match a trusted meter within expected tolerance; board does not heat abnormally |
| D. Buck and servo | Set buck to 5.0 V without servo; add local capacitor and move servo unloaded | 5 V stays stable and servo does not hit a hard stop |
| E. Sensors | Power ESP32 by USB; test INA219, DS18B20, HX711 one at a time | Stable plausible readings and correct units |
| F. Scale | Calibrate empty platform and known masses at two or more points; replace vessel several times | Repeatable tare and known-mass reading |
| G. Valve actuation | Attach servo to valve; test angles pump-off, then briefly with water flowing | No binding, excessive noise, stall, slip or tube movement |
| H. Integrated rig | Move tested wiring to dry terminal/perfboard assembly; retest all branches | Wiring secure; full-system data matches individual tests |
| I. First collection | Start with 5–10 s catch intervals; compare scale and stopwatch | All water lands in vessel; mass stays comfortably below 5 kg |

Power down and disconnect 12 V between wiring changes. Keep pump and servo supply wires off the signal breadboard. Stop the test on leakage, dry running, unexpected heating, smoke, or a repeatedly blown fuse. Investigate the cause before continuing.

## 6. Reference collection procedure

1. Tare the empty vessel and note its physical mass relative to the load-cell capacity.
2. Select a valve setting and let current and flow settle with the outlet returning to the reservoir.
3. Start a timed collection when **all** outlet water enters the vessel. Keep the hose from touching the platform.
4. Stop/divert before reaching the safe mass or vessel capacity. Let splashing settle, then record final mass and elapsed time.
5. Calculate `Q_ref [L/min] = 60 × Δm [kg] / (ρ [kg/L] × Δt [s])`. For a first approximation, `ρ≈1 kg/L`; use DS18B20 temperature for a refined density value later.
6. Repeat at least twice for each of 6–8 safe valve settings. Refill/restore reservoir level and note any spill, bubbles or unstable readings. Reserve separate repeated runs for validation.

At the pump's **label maximum**, 15 L/min adds roughly 0.25 kg per second. Five kilograms could arrive in 20 seconds before accounting for vessel weight. That is why initial catch periods are short. Do not assume actual flow equals the label maximum.

Log the pump ID, adapter voltage, branch current, temperature, valve command/mark, load-cell tare, collected mass, collection start/stop times, hose/tee configuration, and any anomaly. These measurements define the usable calibration range.

## 7. Pressure sensor upgrade

The AD-03's labelled 6 m maximum head corresponds to about **59 kPa** of water pressure. The previously discussed 0–40 kPa HX710B cannot be assumed safe or useful over the full range. Choose a gauge sensor with suitable range, preferably around 0–100 kPa if verified for this rig, and an interface compatible with the ESP32. Its **wetted-material and dry-sensor restrictions** determine how it connects to the tee.

For an air-only sensor, use the tee's side port and a narrow tube rising to a sensor mounted above the tee and water level, trapping air so liquid cannot reach it. For a water-compatible transducer, use its specified liquid fitting and seal. Verify pump-off zero and response against a known water column. Record the tee height and water level. Only after this test should the pressure route be calibrated against independently weighed flow. The pressure sensor's exact power, signal wiring, and GPIO assignment are intentionally open until the device is selected.

## 8. Build records and completion criteria

Record the actual measured pump outlet diameter, tube and fitting sizes, supply voltage, pump running/startup current, INA219 shunt/rating, selected fuse types and values, buck output under servo movement, load-cell scale factor and repeatability, safe servo angle range, tee height, pressure zero method (when installed), and clear photos of final wiring and plumbing. Label every connection in the final circuit drawing using the **actual terminal markings**.

The hardware is ready for flow-model calibration when the return and catch paths are leak-tight; the pump remains submerged; every electrical branch is correctly protected and within rating; sensor readings are stable; the load-cell reference is repeatable; servo motion is bounded; and short collections capture all discharge without exceeding the scale. Hardware completion does not imply that virtual flow accuracy has been established; that requires the held-out collections described in the full plan.
