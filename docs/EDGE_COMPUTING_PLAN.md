# Edge computing plan

Status key: **[Done]** built and checked here, **[Needs hardware]** built, but you must flash or measure on the rig, **[Planned]** not built.

## 1. What "edge computing" means in this project

Edge computing means doing the work next to the sensor instead of shipping raw data away to be processed somewhere else. In the VFM that gives four concrete properties:

| Property | How this project delivers it |
|---|---|
| **Local decisions** | The ESP32 turns pump power into a flow estimate itself (`vfm_estimator.h`). The estimate does not need the laptop. |
| **Less data on the wire** | A 10 Hz fast loop averages 10 samples and sends one summary per second. |
| **Resilience** | If USB, Wi-Fi or the laptop goes away, the device keeps measuring and estimating. |
| **Low, predictable latency** | The estimate is computed in microseconds on the device. The fast-loop time and the compute time are reported, so they are measured, not assumed. |

The laptop gateway still has a job: storage, the dashboard, calibration, and an independent second estimate to cross-check the device.

## 2. Where the work happens

```
ESP32 (edge)                                 Laptop (gateway)
-----------------------------------------    -----------------------------------
10 Hz fast loop: INA219 power, V, I          Receives 1 Hz summaries
1 s window mean                              Runs its own estimate from the same profile
Edge estimate + validity gates               Compares edge vs gateway (delta)
Reason code when it refuses                  Stores history, serves the dashboard
Compute time + loop jitter                   Fits new profiles from weighed collections
One summary line per second  --------------> Exports the profile header back to the device
```

The model travels one way: the gateway fits a profile from weighed reference runs, `tools/export_edge_profile.py` turns it into `profile.h`, and you flash it. The same coefficients and the same valid ranges run in both places.

## 3. Execution plan

### Phase 0: portable estimator and proof of equivalence. [Done]
- `device/firmware/vfm_edge/vfm_estimator.h`: plain C++ estimator, no Arduino dependency.
- `tools/export_edge_profile.py`: verifies a profile (checksum, monotonic, validation) and writes `profile.h`.
- `tests/device/test_edge_estimator.py`: compiles the C++ on the PC and compares it with the Python estimator on 340 inputs for two profiles (a provisional line and a fitted curve with weak ranges). It checks the flow value and the refusal reason.
- Gateway accepts an `edge` reading, compares it with its own estimate and reports the difference.

**Exit criterion met:** C++ and Python agree on availability, flow (within 0.002 L/min) and refusal reason.

### Phase 1: run it on the real ESP32. [Needs hardware]
1. Flash `device/firmware/vfm_edge/vfm_edge.ino` (same libraries as `vfm_sensors`).
2. Close the Serial Monitor, start the gateway with the profile and the bridge.
3. Open the dashboard's Edge computing section.

Pass when: the device estimate appears, `delta` stays within about 0.05 L/min of the gateway estimate while the pump runs, `compute_us` is reported, and `loop_max_us` stays well under the 100 ms period.

### Phase 2: replace the provisional model with a calibrated one. [Needs hardware]
1. Mount and calibrate the load cell, record collections, run `tools/fit_power_model.py`.
2. `python tools/export_edge_profile.py <profile.json> --output device/firmware/vfm_edge/profile.h`.
3. Re-flash. Restart the gateway with the same profile.

Pass when: the dashboard says "validated" with held-out error, and edge and gateway use the same model id.

### Phase 3: prove the data reduction. [Planned]
Count bytes per hour for (a) streaming every 10 Hz sample and (b) the 1 Hz summary, using the bridge's log. Report the ratio next to the accuracy.

### Phase 4: prove the resilience claim. [Planned]
Power the ESP32 from a wall adapter with the laptop off, add a local status indicator (an LED or small display showing available and refusing), and check that estimates continue. On reconnect, send a bounded buffer of missed summaries with sequence numbers so gaps are visible, not hidden.

### Phase 5: move from USB to Wi-Fi and MQTT. [Planned]
Mosquitto broker on the laptop. The ESP32 publishes the same 1 Hz summary, a retained status topic, and a Last Will message. The gateway subscribes, de-duplicates by boot id and sequence, and feeds the same dashboard. USB stays as the commissioning channel.

### Phase 6: more intelligence at the edge. [Planned]
Only after Phase 2 passes: port the guards that exist in simulation (drift detection, excitation gate, interlocks) to the device, and test each against the simulation as the reference. Recalibration stays operator-approved and reference-anchored.

## 4. Evidence to collect

| Metric | Where it comes from |
|---|---|
| Edge vs gateway difference (L/min) | Dashboard `delta`, logged |
| Estimate compute time (µs) | `compute_us` from the device |
| Fast-loop worst-case time (µs) | `loop_max_us` from the device |
| Bytes per hour, raw vs summary | Bridge log (Phase 3) |
| Behavior with the laptop off | Phase 4 test |
| Held-out flow error | `tools/fit_power_model.py` report |

## 5. Risks

| Risk | Mitigation |
|---|---|
| Device and gateway run different profiles | Both show the model id; `delta` exposes a mismatch; export and flash from the same file |
| Float rounding differences on the device | The host test checks a 0.002 L/min tolerance on a grid |
| The model is provisional | Labelled PROVISIONAL everywhere; replaced in Phase 2 |
| I2C or sensor stalls blocking the fast loop | `loop_max_us` is reported; an INA219 failure yields a refusal, not a stale number |
| Over-claiming | Learning, unlearning and the supervisor stay labelled simulation until ported and tested |
