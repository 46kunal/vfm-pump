# Virtual Flow Meter: Full Project Blueprint

## 1. Purpose and final outcome

Build an ESP32-based **virtual flow meter** for a small centrifugal water pump. The device estimates water flow continuously from electrical power and, in the complete version, discharge pressure. A load-cell collection station supplies independent flow measurements for calibration and periodic checks. The ESP32 runs the estimator and supervisor locally; a laptop hosts MQTT, storage, and a dashboard.

“Virtual” describes the **continuous flow measurement**: there is no inline flow meter in the operating pipe. The pump, sensors, valve, and occasional weighing reference are physical. The load cell is a calibration/reference instrument, not the source of every displayed estimate.

The defensible claim is **drift-detecting, reference-recalibrated virtual flow measurement**. Two models disagreeing can reveal inconsistency but cannot establish which model is wrong. They can also drift together. An active calibration change therefore requires independent measured flow. A fit made only against another estimate remains advisory.

### Success criteria

1. Estimate flow at a declared operating range and update rate while the pump runs, including when the laptop or Wi-Fi is unavailable.
2. Quantify accuracy against held-out timed mass collection, separately for low, middle, and high flow.
3. Show measurement quality, uncertainty, and explicit invalid/unavailable states instead of forcing a number when the physics is uninformative.
4. Detect plausible changes, request a reference check, and apply a new model only after reference evidence and an auditable approval.
5. Demonstrate bounded valve control, safe aborts, offline operation, and selective removal of contaminated learning samples.

## 2. System boundary and assumptions

The installed pump is the **AD-03 submersible centrifugal pump**, labelled 12 V DC, 20 W, maximum head 6.0 m, and maximum flow 15 L/min. These are separate endpoint ratings, not a measured operating curve. Its nominal label current is about 1.67 A; running and startup current, outlet size, RPM availability, and actual curves must be measured. The project begins at a fixed regulated 12 V. Speed normalization and affinity-law claims remain outside the demonstrated system until a measured RPM signal and validated speed control exist.

The selected electrical design includes an ESP32 DevKit, INA219, waterproof DS18B20, 5 kg single-point load cell with HX711, MG996R servo, 12 V 5 A supply, LM2596 set to 5 V for the servo, switch, fuse protection, common ground, and removable module wiring. The pressure route is a planned expansion because the sensor is currently a cost constraint. A 0–40 kPa sensor is undersized against a possible 6 m water head (about 59 kPa); select a suitable roughly 0–100 kPa **gauge** device only after checking the actual pump and pressure-interface arrangement. Do not assume a specific breakout pinout until the part is selected.

The 5 kg load cell limits the mass that can be collected in one run. At the label maximum 15 L/min, 5 kg arrives in about 20 seconds. Collection time must leave headroom below the platform and vessel limits. A kitchen scale and stopwatch can cross-check the station.

## 3. Physical arrangement

```text
Covered reservoir → submerged AD-03 → discharge pressure tee → servo-driven valve
       ↑                                      (future sensor)        ↓
       └──────────── return diverter ◀──────────────────────────────┤
                                  └── catch vessel on load cell ──┘
```

The pump remains fully submerged. Tubing from the discharge goes first to a pressure tee, then to a flow-control valve, then to a selector that directs the discharge either back to the reservoir for steady operation or into a catch vessel for reference measurements. The selector must not bypass the control valve during calibration. Fix the pressure tee and tubing so their height and geometry do not change between calibration and use. Secure connections against leaks and provide splash separation from electronics.

For a pressure sensor that must stay dry, run a narrow tube upward from the tee and trap an air pocket; mount the sensor above the water line. Validate that the pocket remains stable and that response delay is acceptable. A water-compatible gauge transducer may instead contact the water directly if its datasheet allows it. Never expose an air-only breakout to water.

The servo turns a **mechanically compatible** needle or gate valve through a coupler and hard stops. A commanded angle is not measured valve position. Determine the safe angle limits and direction by hand before energizing the servo. If the coupling slips or the valve sticks, the controller must not infer position from the command alone.

## 4. Electrical and data architecture

```text
12 V 5 A adapter → main switch → protected distribution
                            ├→ pump fuse → INA219 high side → AD-03 pump
                            └→ servo fuse → LM2596 at 5 V → MG996R

Laptop USB → ESP32 DevKit → INA219, DS18B20, HX711, future pressure sensor
                         └→ servo PWM signal
All DC and ESP32 grounds meet at a common ground reference.

ESP32 fast loop + supervisor → Wi-Fi/MQTT → laptop broker/store/dashboard
                                      ← versioned, authenticated commands
```

Place the INA219 **only in the pump branch** so its reading represents pump current and voltage, not servo transients. Confirm that the actual INA219 board's shunt and continuous current rating tolerate AD-03 running and startup current; the chip's bus-voltage range alone does not establish board current capacity. Select final pump-branch fuse size from measured current, wire capacity, and board rating. A 2 A fuse may nuisance-trip at startup or fail to protect an underrated breakout. Use holders of the correct fuse type and rating. The LM2596 is adjusted and verified at 5.0 V before attaching the servo. Put 470–1000 µF, at least 16 V, across the servo's local 5 V/GND supply with correct polarity. The ESP32 is powered by laptop USB, never by the servo's 5 V rail unless a separately engineered power path is used.

Initial ESP32 mapping: INA219 SDA/SCL on GPIO21/22, HX711 DT/SCK on GPIO16/17 for WROOM (use 25/26 if a WROVER's PSRAM occupies 16/17), DS18B20 data on GPIO4 with 4.7 kΩ pull-up to 3.3 V, and servo signal on GPIO13. Sensor breakout VCC must match each board's supported logic voltage; prefer 3.3 V-compatible modules. The pressure sensor interface and pins are assigned after the exact device is selected. Do not use the ESP32's bare ADC as the precision pressure measurement path without separately validating its accuracy.

### Hardware implementation: what to assemble and how

The hardware is built in four independently testable sections: the water loop, 12 V pump branch, 5 V servo branch, and 3.3 V sensing/reference platform. Use the exact markings and datasheets of the parts in hand to confirm polarity and ratings before connecting them. A wiring sketch does not establish the terminal order of a particular breakout.

**Mechanical items to size after measuring the AD-03 outlet:** a water reservoir large enough to keep the pump submerged; a stable catch vessel; tubing with inside diameter matched to the pump barb; compatible hose barbs/adapters, clamps, and sealant where appropriate; a pressure tee with a capped side port until the sensor is installed; a valve with an appropriate shaft/coupler; a servo bracket and rigid valve mount; a return/catch selector or movable outlet; a rigid load-cell base and top platform; drip management and a dry enclosure or mounting board for electronics. Measure the pump outlet's outside diameter and the valve/tee thread and bore before ordering fittings. Keep the tube bore reasonably consistent so it does not become the dominant restriction. The selector and all return/catch routes remain downstream of the control valve.

**Electrical assembly items:** adequately rated pump/servo power wire and connectors or screw terminals; a multimeter; USB data cable; breadboard and jumpers for sensor-only bench tests; insulation/heat shrink and strain relief; two appropriately selected DC fuse/holder combinations for the final split; and a dry mounting surface. Run pump and servo current through dedicated wire and terminal connections, not a breadboard power rail, perfboard trace of unknown capacity, or thin signal jumper. The purchased single 2 A fuse is not automatically the correct fuse for both branches. Confirm the switch, DC jack, adapter, wire, connectors, and INA219 shunt can carry the measured current.

#### Water loop assembly

1. Place the AD-03 on a stable support inside the reservoir with its intake clear of the bottom and walls. Fill well above the minimum safe submersion depth; mark a low-water cutoff level. Keep the power cable outside the wet area with a drip loop.
2. Attach the pump outlet tube and secure it with a correctly sized clamp. Add the pressure tee immediately downstream, with its side port capped for the first power-only build. Mount the tee in a fixed location and note its height relative to the water surface for the later pressure model.
3. Connect the tee's main outlet to the controllable valve. Mount the valve rigidly so the servo cannot twist the tubing. Connect the valve outlet to a selector that sends **all** water either back to the reservoir or to the catch vessel. Secure the return so it cannot jump out of the reservoir.
4. Before attaching the servo horn, turn the valve by hand and mark its closed and open directions. Do not run the pump against a fully closed valve for sustained periods. Choose a safe minimum opening based on the pump's observed behavior. Attach the servo with a rigid bracket and aligned coupler only after the unloaded servo travel is limited in firmware.
5. Leak-test the plumbing with the outlet returning to the reservoir. Then switch to the catch path for a short interval and verify that no water misses the vessel. The catch vessel must sit only on the load-cell platform and must not touch hoses, wires, or the table in a way that bypasses its measured load.

#### Power distribution and exact connection order

```text
Adapter +12 V → input jack + → DC switch → distribution +
  → pump fuse → INA219 VIN+ → INA219 VIN− → AD-03 +
  → servo fuse → LM2596 IN+ → LM2596 OUT+ (5.0 V) → servo red/V+

Adapter 0 V → input jack − → distribution ground
  → AD-03 −, LM2596 IN−, LM2596 OUT−, ESP32 GND,
    INA219 GND, HX711 GND, DS18B20 GND, servo brown/black GND

Laptop USB → ESP32 USB (ESP32 power and programming)
ESP32 GPIO13 → servo signal (usually orange/yellow)
```

The INA219 `VIN+`/`VIN−` terminals are the **high-current measurement path**; its `VCC`, `GND`, `SDA`, and `SCL` pins power/control the breakout and are not pump-power terminals. Verify the actual board's shunt value and current rating before inserting it. If it cannot tolerate measured startup and continuous current, replace it with a properly rated high-side current sensor. Do not parallel extra wire around the shunt; that makes current readings wrong. Keep the servo capacitor close to the servo supply terminals, `+` to 5 V and `−` to ground. Adjust the LM2596 to 5.0 V with a meter **before** connecting the MG996R. The ESP32 ground-to-12 V ground connection is needed for I²C/bus sensing and servo signal reference even though the ESP32 gets power from USB. Do not connect 12 V to any ESP32 pin or the servo.

#### Sensor and reference-platform wiring

| Device | Device terminal | ESP32 / circuit connection | Bench check |
| --- | --- | --- | --- |
| INA219 | VCC, GND | 3V3 and GND, if breakout supports 3.3 V logic | Detected on I²C; voltage reasonable with pump off |
| INA219 | SDA, SCL | GPIO21, GPIO22 | Stable pump-branch V/A/W after current-path verification |
| DS18B20 three-wire probe | VCC, GND, DATA | 3V3, GND, GPIO4; 4.7 kΩ from DATA to 3V3 | Plausible room and water temperatures; verify probe lead colors |
| HX711 | VCC, GND, DT, SCK | 3V3, GND, GPIO16, GPIO17 on WROOM | Stable zero and known-mass change; verify module works at 3.3 V |
| Load cell | E+/E− and A+/A− (or labelled equivalents) | HX711 excitation and differential input, following the cell/module markings | Correct sign and repeatability with a known mass |
| MG996R | V+, GND, signal | Buck 5.0 V, common GND, GPIO13 | Unloaded sweep within limits; then valve-coupled sweep |
| Future gauge pressure sensor | Supply, ground, data/output per selected device | Assign after part and voltage/interface are verified | Zero and known water-column pressure check |

Load-cell wire colors are not universal; use its labels or seller wiring sheet. Mount a single-point cell as specified by its manufacturer: one end fixed to a base, the other supporting a rigid platform with no second load path. Calibrate with zero and at least two known masses spanning the intended collection range. Count vessel mass toward the 5 kg capacity and leave margin for splashing/overflow. Verify a repeated known mass after moving the vessel off and back on.

#### Bring-up sequence and pass conditions

| Step | Action with power disconnected between wiring changes | Pass condition |
| --- | --- | --- |
| 1 | Inspect adapter plug polarity, jack pinout, switch and fuse holder; measure open-circuit adapter voltage | Correct polarity and near 12 V |
| 2 | Test only the submerged pump through a suitable protected branch and return hose; measure current, including startup if the meter supports it | Pump runs and water returns without leaks, overheating, or repeated fuse trips |
| 3 | Inspect INA219 shunt rating against measured current; insert it high-side and compare its V/A reading with a trusted meter | Board remains within rating and reads plausibly |
| 4 | Power LM2596 from 12 V without servo; set output to 5.0 V, then attach servo and local capacitor | 5 V remains stable during an unloaded sweep |
| 5 | Power ESP32 by USB; test INA219, DS18B20, and HX711 separately with sensor-only jumper wiring | Each sensor returns stable, correctly scaled readings |
| 6 | Calibrate and mount the weighing platform; test empty vessel and known masses | Tare and repeatability are adequate for reference-flow error target |
| 7 | Attach servo to the mounted valve, test travel while pump is off, then run a brief wet sweep | No binding, leaking, stall, or tubing twist; safe angle limits recorded |
| 8 | Move tested connections to a dry perfboard/terminal assembly with removable ESP32/modules and strain relief | Repeated full-system test matches bench readings |
| 9 | Make first 5–10 s catch collections, then extend only if total vessel load stays safely below 5 kg | All discharge reaches vessel and mass/time reference is repeatable |

Record measured adapter voltage, pump running and startup current, buck voltage under servo movement, sensor offsets, load-cell calibration factors, valve angle limits, pump outlet diameter, tube dimensions, tee height, and any leaks. These values become the hardware configuration, not assumptions copied from a drawing. If the INA219 is undersized, that is a **hardware design change** to resolve before the combined run. If a fuse trips, investigate the cause and component ratings before selecting a new value.

#### Pressure upgrade assembly

Once the power-only system works, measure discharge pressure with a properly rated temporary gauge or choose a sensor whose range comfortably covers the plausible AD-03 maximum. Mount the sensor connection at the fixed tee upstream of the valve. For an air-only sensor, route its tube upward and prevent water reaching the sensing element; for a wetted gauge sensor, use only a water-compatible fitting and specified sealing method. Establish the pressure zero reference with the pump off and validate against a known water column. Measure tee elevation and observe whether water level changes during catch runs. Only then wire the selected sensor, add its driver, collect paired pressure/power/reference points, and enable head-route estimation.

## 5. Measurement and reference data

At a fixed interval, timestamp the pump branch voltage `V`, current `I`, electrical power `P=VI`, water temperature, valve command, and quality flags. With the pressure upgrade, also record discharge gauge pressure and its sensor state. Record the raw load-cell readings and stable tare during a reference session. Keep raw readings, calibrated physical units, and model outputs separate.

For water collected over a measured interval:

`Q_ref [L/min] = 60 × Δm [kg] / (ρ [kg/L] × Δt [s])`

Use temperature-corrected density when available; at ordinary room temperature, 1 kg/L is an adequate *initial approximation*, with the approximation recorded. Start/stop timestamps must correspond to water entering the vessel. Tare before collection and read settled mass after splashing stops. If a diverter is used, account for fluid in transit and exclude transition periods. Keep the flow-reference data independent of the virtual estimate. Label every record with session ID, pump ID, valve setting, sensor calibration versions, temperature, and whether it is training, validation, or fault injection.

### Pressure-to-head conversion

With a flooded inlet and the discharge tee at height `h_T` above the reservoir free surface, an approximate pump head is `H ≈ p_T/(ρg) + h_T`, where `p_T` is the **actual gauge pressure** at the tee and `g≈9.81 m/s²`. This omits velocity head and the loss between pump and tee, so it is a rig model, not a general pump test standard. Check the zero convention carefully: a pump-off tare at the tee can remove hydrostatic offset, and blindly adding `h_T` afterward may double-count it. Validate the pressure zero and height correction with a known water column and pump-off/pump-on checks before fitting a curve. Record pressure as `p_discharge_kpa`; do not call it differential pressure when only one gauge sensor exists.

## 6. Establishing the pump model

The virtual meter relies on the centrifugal pump's repeatable relationship among flow, head, and electrical power at a fixed operating condition. Collect reference points at 6–8 valve settings from safe low flow to fully open. At each setting, allow the flow and power to settle, average the sensor readings over the collection window, measure collected mass and elapsed time, and repeat at least twice. Keep separate runs or settings out of fitting for a genuine validation set. Include cold and warm water sessions if temperature variation is material. Never use the label's `Hmax` and `Qmax` as if they define the actual curve.

Fit and store a bounded, versioned power curve `P(Q)` first. Inspect it for monotonicity and local slope. Where the measured power difference per unit flow is smaller than electrical noise, mark the estimate weak or unavailable. An inverse lookup/interpolation with an empirical uncertainty band may be more robust than forcing a quadratic. The power curve is specific to this pump, supply condition, and wiring; monitor voltage and refuse out-of-domain extrapolation.

After adding pressure, fit a head curve such as `H(Q)=a0+a1Q+a2Q²` only if the data supports that form, or use a monotone lookup table. The pressure route estimates flow by inverting the validated head relation within its calibrated domain. Compare both routes across flow bands, including dead zones. At fixed 12 V without RPM sensing, do not apply pump affinity scaling. If variable speed is later added, measure RPM and refit/validate at multiple speeds before enabling scaling.

### Combined estimate

Each route produces a candidate flow, validity flag, and uncertainty estimated from sensor noise, curve residuals, and local sensitivity. Flat curve segments amplify measurement noise and therefore receive lower weight. Combine valid routes using uncertainty-aware weighting or a simple Kalman filter whose noise settings come from held-out data. If only one route is valid, report its estimate with a source label and wider uncertainty. If neither is valid, report `unavailable` and the reason. Clamp only to the calibrated physical domain; never hide a sensor fault by silently clipping an impossible reading.

## 7. ESP32 runtime

The ESP32 owns the operating estimate and safety state. A nominal 10 Hz fast loop reads sensors, checks freshness/ranges, converts units, runs the route estimators and fusion, updates uncertainty and health flags, and publishes a compact summary. The slow loop handles residual monitoring, excitation eligibility, candidate fitting, calibration states, and event creation. Separating acquisition, estimation, supervisor, and communication work prevents Wi-Fi or dashboard delays from blocking the fast loop. Measure actual cycle time and jitter rather than assuming 10 Hz is achieved.

Store a validated active model, version, CRC/checksum, calibration domain, and rollback copy in nonvolatile storage. Candidate changes are stored separately. On reboot, load the last valid active model; if none exists, display `uncalibrated` and allow only the safe commissioning workflow. Keep the pump and valve in an explicitly chosen safe state on reboot or communication loss. Log boot reason and configuration version.

Before the pressure path exists, the runtime is **power-only**: it can estimate flow only in power-sensitive ranges and compare the estimate with periodic weighed references. It cannot claim pressure/power agreement, pressure-based wear, or full dual-route drift diagnosis.

## 8. Drift detection and reference recalibration

With both routes validated, monitor route disagreement and normalized residuals using CUSUM or a similar sequential detector. Set thresholds from baseline runs so false alarms and detection delay can be measured. A trigger means **investigate**, not automatically assign blame. Correlated pump wear can shift both routes while they still agree, so schedule weighed reference checks even when no alarm appears.

A candidate update begins with sufficient excitation: flow must span informative valve settings, sensors must be healthy, and data must have a known operating condition. A bounded automatic sweep can command 5–7 valve positions, dwell until stable, log the data, and restore the prior setting if it aborts. A reference-free RLS fit can track a *candidate* trend and guide the next check, but cannot be activated. A reference calibration session records independently measured `(inputs, Q_ref)` pairs, fits a candidate, and tests it against held-out reference data, physical curve shape, uncertainty, domain coverage, and safety bounds. The operator reviews a clear before/after comparison and approves a versioned model. Rejection preserves the current active model and audit record.

An optional wear indicator may track validated shutoff-head or other curve parameters after the pressure path is commissioned. It should be presented as a **relative trend for this pump**, not a diagnosis of impeller damage. A power-only trend is advisory. If using different pumps or a recirculation bypass as wear stand-ins, establish a separate baseline for each and distinguish deliberate restriction from actual wear.

## 9. Digital triplet and control authority

The **physical** member is the pump, water loop, sensors, valve, and catch scale. The **virtual** member is the ESP32's curves, fused flow state, uncertainty, drift sums, candidate parameters, and event log. The **human** member is the operator who selects mode, performs a reference collection, annotates a fault window, approves or rejects model changes, and can override control. This is a design framework for the demonstration, not a formal industrial standard.

| Mode | Valve authority | Model authority |
| --- | --- | --- |
| Manual | Operator commands valve within hard limits | Operator initiates/approves reference-based update |
| Assisted | ESP32 proposes sweeps or settings; operator starts them | ESP32 proposes candidates; operator approves after reference checks |
| Auto | ESP32 may perform pre-authorized bounded control/sweeps when online and healthy | Reference-free candidates remain advisory; activation still requires independent reference and recorded approval |

Centralize mode transitions and model application in one supervisor so every change has a reason, timestamp, command ID, operator identity where available, and active-model version. A servo command is never proof that the valve physically moved. Do not close the loop around an unmeasured valve position as though it were a feedback actuator.

## 10. Selective machine unlearning

When a known bad interval contaminates a candidate fit, the operator marks its start/end and reason (for example disconnected pressure tube, manual valve movement, or sensor spike). Store accepted RLS samples in a bounded ring buffer with feature vector, target, weight, timestamp, source, and model version, plus periodic checkpoints. Remove the marked samples from the **candidate** using a numerically checked Sherman–Morrison downdate or rollback and replay. Re-symmetrize covariance and reject a downdate if conditioning fails. The active model remains untouched until a separately verified approval.

Validate the method on a PC against batch weighted least squares on the same retained samples. Report relative parameter difference and a flow-error comparison before and after removal; the team's target is at most 1% parameter difference for the test case. Demonstrate with an explicitly labelled injected fault, then show do-nothing, ordinary forgetting, unlearning, and retraining-without-window traces. Do not call normal drift or real wear a fault sample merely because it is inconvenient to the model.

## 11. Safety and fault behavior

The water/electronics boundary is the first safety requirement: stable covered vessels, strain relief, dry electronics, drip loops, and a reachable power switch. Validate supply polarity, the buck output, fuse placement, common ground, and branch current before connecting the pump and servo together. The pump remains submerged and must not run dry. Keep tubing secured against disconnection and overflow.

Firmware interlocks use **measured** limits: pump overcurrent; pressure maximum after the sensor is validated; temperature limits if applicable; minimum-flow protection only where the estimate is trustworthy and its threshold has been tested. A sensor fault or uncertain estimate blocks autonomous sweeps and model activation. On an abort, stop the sweep and return the valve to a documented safe command if the actuator remains operable; switch off the pump when required by the fault policy. A hardware switch remains the reliable emergency stop. Define and test the exact action for power loss, reboot, watchdog reset, Wi-Fi loss, broker loss, sensor dropout, stuck servo, and full catch vessel.

The chosen supply is 12 V 5 A, but actual pump startup current and servo stall current are unknown until measured. Confirm the current-sensing board, buck, wires, connectors, fuse values, and adapter can handle their respective branches. Never use the INA219 module if its shunt rating is below the measured pump current.

## 12. Communications, storage, and dashboard

Use MQTT between ESP32 and a laptop Mosquitto broker. Publish a bounded-rate summary (for example 1 Hz) plus immediate fault, calibration, mode, and model events; retain local buffering during short outages. During Wi-Fi loss, the fast estimate and interlocks continue, new autonomous sweeps do not start, and candidate model updates remain pending. On reconnect, publish ordered events with sequence numbers so gaps are visible. Measure bytes per hour against raw 10 Hz streaming.

Messages should carry schema version, device/pump ID, boot/session ID, monotonic sequence, device timestamp, active-model version, raw/physical measurements, estimate, uncertainty, route validity, mode, health, and event cause. Separate commands from telemetry. Commands need authenticated origin, unique ID, expiry, expected model/config version, bounded arguments, acknowledgment, and replay protection. Keep credentials out of the repository.

The dashboard should show live flow with units and confidence/quality, power/voltage/current, temperature, pressure when fitted, valve command, connectivity, mode, active model, calibration age, reference-session workflow, drift/event history, candidate comparison, approval/rejection, unlearning annotation, and safety state. A missing or invalid estimate appears as such, never as zero flow by default. Charts should distinguish simulated, hardware, reference, and injected-fault data. Store raw reference runs and immutable event/audit records for later analysis.

## 13. End-to-end implementation sequence and gates

| Stage | Work | Gate before moving on |
| --- | --- | --- |
| A. Mechanical and electrical bench | Assemble leak-tight reservoir loop and reference catch path; bench-check supply, branches, sensor logic, servo motion, and pump current | No leaks, correct polarity/voltage, protected wiring, repeatable servo range, safe shutdown |
| B. Instrument commissioning | Calibrate load cell and temperature sensor; log INA219 at fixed 12 V; characterize pump startup, steady current, and valve response | Stable, timestamped physical measurements with documented uncertainty |
| C. Reference campaign | Run repeated timed mass collections across 6–8 safe valve settings; reserve held-out runs | Reference data spans the intended range and passes mass/timing quality checks |
| D. First virtual meter | Fit power-only model; port estimator to ESP32; report range-dependent validity and uncertainty | Held-out flow error and 10 Hz timing are measured and reported |
| E. Network and triplet | Add MQTT, durable events, dashboard, Manual/Assisted control, offline behavior | Live data matches logged ESP32 output; offline fast loop and interlocks continue |
| F. Pressure upgrade | Choose correctly ranged sensor; validate tee/zero/head conversion; fit pressure route; implement fusion | Each route and fusion pass held-out tests; weak regions are flagged |
| G. Drift and recalibration | Tune CUSUM, excitation gate, RLS candidate, reference session, approval and rollback | No reference-free model activation; seeded drift triggers a reviewable event |
| H. Unlearning and autonomy | Candidate-only sample removal, bounded Auto sweeps, fault handling and audit | PC comparison passes; injected fault is removed; all aborts restore safe state |
| I. Final evidence | Run the experiment matrix, summarize limits and produce demo/report | Every numerical claim is traceable to hardware reference data and test logs |

The stages are logical gates, not promised calendar durations. Pressure fusion, RPM scaling, wear experiments, and Auto mode should be presented as later capabilities until physically tested. A working power-only meter can be a valid interim result if its observable range and limitations are reported.

## 14. Validation program

1. **E1, steady accuracy:** repeated held-out reference collections across flow bands; add multiple speeds only if RPM and speed control are measured.
2. **E2, transients:** valve steps, settling, estimate latency, and false readings during unstable periods.
3. **E3, physical change:** a separately baselined second pump or clearly labelled bypass/impeller intervention; distinguish manufacturing differences from wear.
4. **E4, candidate rejection:** inject an implausible or reference-free candidate and verify it cannot become active.
5. **E5, network loss:** disconnect Wi-Fi during a sweep or candidate workflow; measure local continuation, abort policy, buffering, and recovery.
6. **E6, safety interlock:** induce a safe, controlled current/pressure/sensor fault and record response time and final state.
7. **E7, unlearning:** annotate an injected contaminated window and compare downdate/replay with batch retraining.
8. **E8, sensor fault:** disconnect, freeze, bias, or spike one measurement; check route gating, dashboard labeling, and no unsafe model update.
9. **E9, soak:** sustained operation to measure drift, dropped samples, buffer growth, resets, and leaks.

Report flow MAE, RMSE, bias, maximum error, and error by flow band in L/min and percent where a nonzero reference allows it. Report uncertainty coverage, invalid/unavailable fraction, drift detection delay and false alarms, candidate acceptance/rejection results, unlearning parameter difference, fast-loop timing and jitter, memory use, MQTT traffic, offline duration/recovery, and interlock response time. Include confidence intervals or repeated-run spread where practical. Compare against simple baselines such as constant-flow assumption, power-only lookup, pressure-only lookup, and fusion. Simulator results are development evidence, never hardware accuracy evidence.

## 15. Main decisions and risks

| Decision or risk | Evidence needed | Response |
| --- | --- | --- |
| AD-03 power curve too flat in part of range | Repeated `P` versus weighed `Q`, local slope/noise | Flag that range as low confidence; use pressure route or narrow claimed range |
| INA219 breakout current capacity | Board shunt value/rating and measured startup current | Use a correctly rated current sensor/shunt if inadequate |
| Suitable pressure interface and range | Actual tee pressure across valve range and sensor datasheet | Choose roughly 0–100 kPa gauge or a range justified by measurement; keep sensor dry if air-only |
| Unstable air pocket or height correction | Pump-off zero, water-column check, repeated runs | Fix interface, re-tare correctly, or change to water-compatible transducer |
| Servo valve slip, hysteresis, or stall | Repeated command/flow sweeps, stall current | Improve coupling/valve choice; restrict Auto if position cannot be trusted |
| Pump-to-pump variation | Individual reference curves | Baseline each pump before any wear comparison |
| Missing RPM signal | Actual pump wiring and tach inspection | Remain fixed-speed; add a measurable speed system before affinity claims |
| Insufficient independent reference points | Held-out mass collection coverage | Collect more runs before accepting a new model or quoting accuracy |

## 16. Final deliverables

The completed project should include the assembled rig and wiring/plumbing drawings; ESP32 firmware and configuration; pump-specific calibration/reference dataset; model-fitting and cross-check scripts; MQTT broker/gateway/dashboard; documented message schema; active/candidate model records and audit log; repeatable calibration and unlearning procedures; and an experiment report with measured results, failed cases, and limits. The presentation should show the physical flow path, why the meter is virtual, the power and pressure inference paths, the independent weighing reference, the human approval loop, and only experiments actually performed.

### Source hierarchy for this blueprint

This plan follows the team's *Self-Calibrating Virtual Flow Meter — Complete Project Document v1* for the overall research architecture and `VFM_CONTEXT_UPDATE.md` for the later corrections to calibration, edge execution, digital triplet, unlearning, and autonomy. It adapts their earlier pump-specific details to the purchased AD-03 and its label ratings. All unmeasured performance remains a validation task rather than a claimed result.
