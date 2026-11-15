# AD-03 virtual flow meter implementation plan

**Updated:** 3 November 2026  
**Status:** implementation plan; hardware operation and real-world accuracy have not yet been demonstrated.  
**Build basis:** the purchased AD-03 pump and its measured electrical and hydraulic behavior. Earlier AD20P assumptions do not apply to this rig.

## 1. Goal and first deliverable

Build a **12 V fixed-speed, centrifugal-pump virtual flow meter** using the purchased AD-03 pump. The ESP32 measures pump voltage and current with an INA219 and water temperature with a DS18B20. A 5 kg load cell and HX711 measure collected water during commissioning. A model fitted from those reference collections estimates flow from measured pump electrical power while water recirculates. The laptop shows the estimate, source, validity, and measured calibration evidence.

The first demonstrable deliverable is **power-only, reference-calibrated flow estimation over a measured valid flow range**. It is not a pressure/power fusion system until a suitable pressure sensor is added. Do not claim drift detection, autonomous recalibration, wear diagnosis, multi-speed performance, or physical accuracy before the corresponding measurements and software exist.

## 2. Confirmed facts and open measurements

The label on the purchased pump reads **AD-03, DC 12 V, 20 W, Hmax 6.0 m, Qmax 15 L/min, IPX8**. Hmax and Qmax are separate operating extremes, not a simultaneous flow/head point. Nominal current from the label is `20 W / 12 V ≈ 1.67 A`; actual running and starting current are unmeasured. A 6 m water head is approximately 59 kPa, so the old 0–40 kPa HX710B cannot cover the pump's full potential pressure range.

| Item | Current state | Measurement or decision needed |
|---|---|---|
| ESP32 | User already owns one | Confirm WROOM versus WROVER, USB connector, and accessible pins. |
| Pump and 12 V supply | AD-03 and regulated 12 V, 5 A adapter purchased | Measure adapter polarity/voltage, pump outlet outside diameter, connector fit, running current, startup behavior, and actual flow. |
| Power sensor | INA219 breakout purchased | Read shunt marking/board rating; confirm wiring and temperature at measured pump current. The chip rating alone does not establish breakout current capacity. |
| Temperature | Waterproof DS18B20 and 4.7 kΩ resistor purchased | Verify three-wire colors against the actual probe and confirm readings in water. |
| Reference mass | 5 kg load cell and HX711 purchased | Build a stable platform, verify wiring, tare, calibrate with known masses, measure vessel mass. |
| Valve | MG996R purchased | Choose a water valve, matching hose fittings, bracket and shaft coupler; verify that servo torque and travel move it without binding. |
| Power wiring | LM2596, switch, one 2 A fuse, two holders, capacitor, jumpers, perfboard, DC jack purchased | Obtain multimeter, appropriate power wire, USB data cable, breadboard, and a second fuse after current measurements. Verify switch, fuse holder, jack, and INA219 board ratings. |
| Pressure | None purchased | Defer. If added later, select a 0–100 kPa **gauge** sensor with an ESP32-compatible electrical interface and an air-tube or water-compatible fitting. |
| Plumbing | Not confirmed as purchased | Measure pump outlet before buying hose, T, valve, clamps and return/diverter fittings. |

The previously illustrated AD20P pump and HX710B diagrams are **not build instructions for the AD-03 rig**.

## 3. Physical architecture

Normal flow path:

```text
reservoir → submerged AD-03 → discharge hose → manual/servo valve → return to reservoir
```

Reference collection path:

```text
reservoir → submerged AD-03 → discharge hose → same valve → diverter/movable outlet
                                                       → catch vessel on load cell
```

All discharge water must pass through the control valve before it reaches either return or catch. Do not add an always-open branch around the valve. For the first calibration, a **manual valve position** is acceptable even though the servo is owned; automate the valve only after safe end stops and a firm coupling are demonstrated. Keep the pump submerged and keep electronics above the water and away from leaks.

With the pressure upgrade, insert a T **between pump and control valve**. The T's side port goes upward through a short, air-filled tube to the gauge sensor, which stays above the water line. Water must not reach an air-only sensor. The pressure method and zero reference need a water-column check; do not assume a generated diagram proves the plumbing.

## 4. Electrical architecture and build order

Planned final wiring, subject to inspection of actual module ratings:

```text
12 V adapter + → DC-rated switch → split
  pump branch: appropriately selected fuse → INA219 VIN+ → VIN− → pump +
  servo branch: 2 A fuse → LM2596 IN+; LM2596 OUT+ at 5.0 V → servo +
12 V adapter − → pump −, LM2596 IN−, ESP32 GND, sensor GND, servo GND
ESP32 USB ← laptop (power, flashing and debugging)
```

Place the 470–1000 µF, ≥16 V electrolytic across **servo 5 V and ground**, near the servo, observing polarity. **Do not connect the servo or ESP32 directly to 12 V.** Do not carry pump or servo current through breadboard contacts or thin signal jumpers. Connect the ESP32's ground to the 12 V system ground even while the ESP32 is USB-powered.

The existing 2 A fuse can be used for a short **pump-only test** if the holder is DC-rated and wired securely; a startup trip may occur. It is not a confirmed final pump fuse. Select the permanent pump fuse after measuring startup/running current and checking the pump cable, switch, connector and INA219 board current ratings. For the final split wiring, provide a separate fuse for each branch. Do not bypass a repeatedly blowing fuse with an oversized fuse.

| Signal | Proposed ESP32 pin | Notes |
|---|---|---|
| INA219 SDA / SCL | GPIO21 / GPIO22 | Supply breakout logic at 3.3 V if its exact board allows it. INA219 is in the pump-positive branch. |
| HX711 DT / SCK | GPIO16 / GPIO17 | WROOM. If the board is WROVER, use GPIO25 / GPIO26 because 16/17 may be used by PSRAM. |
| DS18B20 DATA | GPIO4 | 4.7 kΩ from DATA to 3.3 V; probe VCC and GND per verified lead colors. |
| Servo signal | GPIO13 | Servo power comes from LM2596, not from GPIO or ESP32 5 V. |
| Future pressure I²C | GPIO21 / GPIO22 shared bus | Only if the chosen sensor is a 3.3 V I²C part; its protocol and address must be verified. Other sensor types need a different interface. |

**Bench sequence:** (1) multimeter-check adapter polarity and voltage; (2) submerge and briefly run pump alone through switch and fuse with return hose; (3) power LM2596 without servo, set and verify 5.0 V; (4) power ESP32 by USB and read INA219 with pump off; (5) install INA219 high-side and compare its current with a multimeter; (6) read DS18B20; (7) tare/calibrate HX711; (8) move servo unloaded, then with valve coupling; (9) assemble perfboard only after each test passes. Disconnect 12 V before changing wiring.

## 5. Reference-flow measurement

At each test point, choose a valve opening, allow current and flow to settle, then divert **all** outlet water to the catch vessel for a measured interval. Record mass before and after. Weigh after splashing has stopped so water impact does not distort the reference. Return the outlet to the reservoir and restore its level before the next run.

For water density `ρ` in kg/L, collected mass `Δm` in kg and collection duration `Δt` in seconds:

```text
Q_ref [L/min] = 60 × Δm / (ρ × Δt)
approximately Q_ref = 60 × Δm_kg / Δt_s when ρ ≈ 1 kg/L
```

The 5 kg rating includes the vessel and platform loading. At the **label maximum** 15 L/min, water would add 0.25 kg/s; a 20-second run could add 5 kg before vessel weight. Start with short 5–10 second collections and extend only after measuring actual flow, vessel mass, and remaining capacity. Ensure the load cell is mounted in its intended bending direction and the vessel cannot tip.

For each point, save: pump serial/label, source `hardware`, session ID, valve command or manual mark, water temperature, supply voltage, pump current, electrical power, load-cell zero, start/end mass, start/end monotonic times, flow calculation, any spill/leak/air observation, and raw readings. At least 6–8 distinct valve settings with repeat collections are desirable; the actual usable range depends on measured behavior. Keep near-closed runs brief and stop if current, temperature, sound or leaks become abnormal.

## 6. Calibration and validation method

1. Calibrate the load cell with zero and at least two known masses that span the expected catch-vessel load. Check repeatability after removing and replacing the vessel.
2. Verify INA219 voltage and current against a multimeter at pump-off and running conditions. Compute `P_elec = V_pump × I_pump` using **pump-branch** measurements only. Do not include servo power.
3. Collect repeated `P_elec, Q_ref` pairs at steady valve settings. Include independent runs on different fills or times where practical.
4. Plot power versus reference flow before fitting. Check whether it is single-valued and monotonic over any region. Power may be flat or non-monotonic; do not force a quadratic inverse through an ambiguous region.
5. Fit a bounded model only on a defensible region (for example monotonic interpolation or a constrained curve). Record its valid voltage, temperature, valve/flow and power ranges. Use voltage as a measured covariate or constrain the supply tightly; do not assume an ideal fixed 12.000 V.
6. Hold out **whole repeated collections or runs** for validation. Report MAE, RMSE, bias and maximum absolute error in L/min and percent of measured reference where meaningful. Plot predicted versus measured flow and errors by flow band.
7. If the power curve is too flat or validation fails, report power-only flow as **unreliable or unavailable** in that region. The next step is a better input, such as a suitable pressure sensor; do not display fabricated precision.

Calibration results must be stored in a separate, versioned **AD-03 hardware profile** with raw-data links, coefficients/lookup points, units, valid range, fit/validation split, sensor scale/tare and a checksum. The root `config.json` contains simulation placeholders and must not be presented as measured pump calibration.

## 7. Software implementation against the current repository

The repository currently has a Python simulator, a 10 Hz two-path fast loop, telemetry v1 schema, a read-only HTTP gateway, and a simulation dashboard. It has **no ESP32 firmware directory, hardware reader, MQTT ingest, persistent session store, measured AD-03 curve or pressure-free estimator**. `vfm.fastloop.FastLoop.update()` currently requires `rpm` and `dp_kpa`; its `valid` flag requires both inversions. Real AD-03 samples cannot be passed into it unchanged.

### Stage A: contracts and Python reference

- Add a hardware sample contract with nullable `rpm` and pressure, measured `volts`, `amps`, `temp_c`, sensor-quality fields, and `source: hardware`. Keep simulation packets distinguishable.
- Define reference collection records separately from estimated telemetry; include mass, duration, uncertainty and session linkage. Avoid inserting reference flow into live input as if it were a sensor.
- Add a **fixed-speed, power-only** Python estimator that can return no estimate outside a validated range. Use a new path or mode rather than silently reinterpreting `dp_kpa`.
- Evolve telemetry so `head_flow_l_min = null` when pressure is absent; `power_flow_l_min` and `flow_l_min` may be present only when the power model is valid. Define `valid` as an actually usable estimate rather than “both routes valid.” Preserve the existing dashboard read API while versioning the contract.
- Add a calibration tool that ingests measured CSV/JSONL collections, fits a model, evaluates held-out runs and writes the versioned hardware profile.

### Stage B: ESP32 sensor firmware and data capture

- Create `firmware/` for INA219, DS18B20, HX711, servo output, timing and quality checks. Implement one driver at a time using serial diagnostics. Confirm ESP32 module and board pins before flashing.
- Sample voltage/current and temperature at a known rate, timestamp with monotonic time, reject impossible/stale readings, and keep the pump powered independently of ESP32 resets. Maintain a unique boot ID and increasing sequence counter.
- Log raw measurements and reference collection boundaries. Begin with USB serial for bench inspection and cross-checking; it is a commissioning channel, not the promised final communications architecture.
- Port the validated fixed-speed power-only estimator to ESP32. Replay saved readings through Python and firmware and compare results within a defined tolerance before showing live flow.

### Stage C: laptop gateway and dashboard

- Add Mosquitto MQTT publishing from ESP32 and a gateway subscriber that validates `hardware` packets, deduplicates by device/boot/sequence and persists sessions. Keep `GET /api/telemetry?limit=120` usable for the existing dashboard.
- Show **hardware versus simulation**, fresh/stale state, measured pump V/A/W, water temperature, estimated flow, model version, valid range and uncertainty or “unavailable.” Show reference collections and validation plots separately from live estimates.
- Measure ESP32 timing, memory, Wi-Fi outage behavior and message rate. During network loss, the ESP32 continues local measurement/estimation and buffers only a bounded amount; reconnect handling must not duplicate data.

### Stage D: valve automation and advanced project features

- Only after manual valve calibration succeeds, attach the MG996R to a suitable valve. Map safe command limits, test end stops with pump off, then test short sweeps while supervising pump current and supply voltage. Commanded servo angle is **not** measured valve position.
- Add guarded sweeps, fault handling, durable commands/acknowledgements and an audit record before enabling dashboard control. A UI button must not bypass device checks.
- Treat data-only drift candidates as **advisory**. Reference flow is required for a recalibration claim or active-model replacement. Implement approval, rollback and unlearning only after the base measured estimator and reference workflow pass validation.
- When pressure is affordable, add an appropriate 0–100 kPa gauge sensor, verify its electrical interface and pneumatic/water coupling, then collect a **new** pressure/head-versus-flow calibration. Only then implement two-path fusion, pressure/power disagreement and pressure-dependent interlocks.

## 8. Milestones and acceptance evidence

| Milestone | Work | Evidence required to pass |
|---|---|---|
| M0. Power and pump | Measure adapter, submerged pump test, return hose, switch/fuse, running current. | Photo of label/wiring, voltage/current log, leak-free flow, physical switch stops pump. |
| M1. Sensor bench | INA219, DS18B20, HX711 tested separately; load cell calibrated. | Raw readings and cross-checks, known-mass errors, no overheating or unstable wires. |
| M2. Manual calibration rig | Valve and catch/return routing; repeated timed mass collections. | Dataset with 6–8 settings where feasible, repeated runs, all water passes the valve, no load-cell overload. |
| M3. Power model | Fit and held-out validation in Python, valid operating band. | Versioned profile, plots, MAE/RMSE/bias/max error; explicit invalid regions. |
| M4. ESP32 estimate | Port validated model and compare against Python replay. | Same input trace yields matching results; faults and missing inputs yield unavailable output. |
| M5. Live app | MQTT gateway, storage and dashboard show real packets. | Hardware-labelled session survives restart; loss/reconnect handling and stale status demonstrated. |
| M6. Servo and later research | Valve control, supervisor, reference-anchored updates; optional pressure path. | End-stop test, safe sweep, audited decisions, measured validation for every new model path. |

## 9. Immediate next session

1. Confirm that a multimeter, ESP32 USB data cable, bucket, main hose and breadboard are available. Measure pump outlet and adapter connector fit.
2. With the pump submerged and hose returning to the bucket, verify adapter polarity/voltage and perform a **brief fused pump-only test**. Record running voltage and current if the meter supports the measurement safely. Stop if the fuse trips repeatedly, the pump runs dry, or wiring warms.
3. Power the LM2596 with its output unloaded. Adjust to 5.0 V and record it; leave the servo disconnected until its individual test.
4. Start the INA219 on USB-powered ESP32, then compare its pump V/A values with the multimeter. This measured result decides the final pump fuse and whether the purchased INA219 breakout is suitable.

Do not connect every component at once. Each milestone has an observable result that can be checked before proceeding.
