"""Record timed reference collections (weighed water) for calibrating the flow model.

Run the gateway and the serial bridge first. For each valve setting:
  empty vessel on the platform -> read start mass -> press Enter when water starts
  entering the vessel -> press Enter when you divert it away -> mass is read after
  the splashing settles. The reference flow is 60 * delta_mass / (density * duration).

Each saved collection is one JSON line in data/real/collections/<session>.jsonl and also
stores the pump voltage, current, power and water temperature averaged over the window.
Your Enter-key timing is the largest error source, so use collections of 10 s or more.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.calibrate_loadcell import DEFAULT_OUTPUT as DEFAULT_CAL  # noqa: E402
from tools.calibrate_loadcell import load_calibration, mass_from_raw  # noqa: E402
from tools.gateway_client import (DEFAULT_URL, GatewayError, average_field,  # noqa: E402
                                  history, latest, mean_std)
from vfm.fastloop import water_density  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
COLLECTIONS = ROOT / "data" / "real" / "collections"
CAPACITY_WARN_G = 4500.0
SCHEMA = "collection-v1"


def reference_flow_l_min(delta_g, duration_s, temp_c=None):
    """Return (Q_ref in L/min, density in kg/L). Falls back to 1.0 kg/L without a temperature."""
    if duration_s <= 0:
        raise ValueError("duration must be positive")
    if delta_g <= 0:
        raise ValueError("no water was collected (the mass did not increase)")
    rho = water_density(temp_c) / 1000.0 if temp_c is not None else 1.0
    return 60.0 * (delta_g / 1000.0) / (rho * duration_s), rho


def window_stats(rows, key, t0, t1):
    values = [row[key] for row in rows if t0 <= row["t_s"] <= t1 and row.get(key) is not None]
    mean, std = mean_std(values)
    return {"mean": mean, "std": std, "n": len(values)}


def build_record(meta, start_t, end_t, mass_start_g, mass_end_g, ina_rows, temp_rows,
                 trim_s=1.0, calibration_id=None, created=None):
    duration = end_t - start_t
    window_start = start_t + trim_s
    volts = window_stats(ina_rows, "volts", window_start, end_t)
    amps = window_stats(ina_rows, "amps", window_start, end_t)
    power = window_stats(ina_rows, "power_w", window_start, end_t)
    temp = window_stats(temp_rows, "temp_c", start_t, end_t)
    delta = mass_end_g - mass_start_g
    q_ref, rho = reference_flow_l_min(delta, duration, temp["mean"])

    flags = []
    if duration < 10:
        flags.append("short_collection_timing_error_large")
    if power["n"] < 3:
        flags.append("few_electrical_samples")
    if temp["n"] == 0:
        flags.append("no_temperature_density_assumed_1")
    if mass_end_g > CAPACITY_WARN_G:
        flags.append("near_load_cell_capacity")
    return {
        "schema": SCHEMA,
        "record_type": "reference_collection",
        "source": "hardware",
        "created_utc": (created or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
        "session_id": meta["session"],
        "pump_id": meta["pump_id"],
        "split": meta["split"],
        "valve_label": meta["valve_label"],
        "start_t_s": start_t,
        "end_t_s": end_t,
        "duration_s": duration,
        "mass_start_g": mass_start_g,
        "mass_end_g": mass_end_g,
        "delta_mass_g": delta,
        "density_kg_per_l": rho,
        "q_ref_l_min": q_ref,
        "volts_mean": volts["mean"],
        "amps_mean": amps["mean"],
        "power_w_mean": power["mean"],
        "power_w_std": power["std"],
        "electrical_samples": power["n"],
        "temp_c_mean": temp["mean"],
        "loadcell_calibration_id": calibration_id,
        "flags": flags,
        "notes": meta.get("notes", ""),
    }


def run(args, ask=input, say=print, sleep=time.sleep):
    base = args.gateway

    def fetch():
        return latest(base)

    calibration = None
    if Path(args.calibration).exists():
        calibration = load_calibration(args.calibration)
        say(f"Using load-cell calibration {calibration['id']}")
    else:
        say("No load-cell calibration file; using the ESP32's mass_g values if present.")

    def current_mass():
        if calibration:
            raw, std, _ = average_field("hx711", "raw", args.mass_seconds, fetch)
            return mass_from_raw(raw, calibration), std / abs(calibration["counts_per_gram"])
        mass, std, _ = average_field("hx711", "mass_g", args.mass_seconds, fetch)
        return mass, std

    session = args.session or datetime.now().strftime("%Y%m%d-%H%M%S")
    path = COLLECTIONS / f"{session}.jsonl"
    saved = 0
    while True:
        label = ask("\nValve setting label (for example '3 of 8' or an angle; blank to finish): ").strip()
        if not label:
            break
        split = ask(f"Training or validation run? [t/v] (default {args.split[0]}): ").strip().lower()
        split = "validation" if split.startswith("v") else "training" if split.startswith("t") else args.split
        ask("Empty vessel on the platform, hose pointed away from it. Press Enter to read the start mass... ")
        mass_start, mass_start_std = current_mass()
        say(f"  start mass {mass_start:.1f} g (std {mass_start_std:.2f} g)")
        ask("Press Enter the instant water starts entering the vessel... ")
        start_t = fetch()["server_t_s"]
        ask("Press Enter the instant you divert the water away... ")
        end_t = fetch()["server_t_s"]
        say(f"  letting the splashing settle for {args.settle:g} s...")
        sleep(args.settle)
        mass_end, mass_end_std = current_mass()
        say(f"  end mass {mass_end:.1f} g (std {mass_end_std:.2f} g)")
        notes = ask("Anomalies (leaks, bubbles, spills; blank for none): ").strip()
        try:
            record = build_record(
                {"session": session, "pump_id": args.pump_id, "split": split,
                 "valve_label": label, "notes": notes},
                start_t, end_t, mass_start, mass_end,
                history(base, "ina219"), history(base, "ds18b20"),
                trim_s=args.trim, calibration_id=calibration["id"] if calibration else None)
        except ValueError as problem:
            say(f"  Not saved: {problem}")
            continue
        say(f"  duration {record['duration_s']:.1f} s, collected {record['delta_mass_g']:.0f} g")
        say(f"  reference flow {record['q_ref_l_min']:.2f} L/min | pump {record['volts_mean']:.2f} V, "
            f"{record['amps_mean'] * 1000:.0f} mA, {record['power_w_mean']:.2f} W "
            f"({record['electrical_samples']} samples)")
        for flag in record["flags"]:
            say(f"  WARNING: {flag}")
        if ask("Save this collection? [Y/n] ").strip().lower().startswith("n"):
            say("  Discarded.")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, allow_nan=False) + "\n")
        saved += 1
        say(f"  Saved to {path}")
    say(f"\n{saved} collection(s) saved this run.")
    return saved


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pump-id", default="AD-03-1")
    parser.add_argument("--session", default=None, help="session name (default: timestamp)")
    parser.add_argument("--gateway", default=DEFAULT_URL)
    parser.add_argument("--calibration", default=str(DEFAULT_CAL))
    parser.add_argument("--split", choices=["training", "validation"], default="training")
    parser.add_argument("--settle", type=float, default=3.0, help="seconds to wait before the end mass")
    parser.add_argument("--trim", type=float, default=1.0,
                        help="seconds ignored at the start of the electrical average")
    parser.add_argument("--mass-seconds", type=float, default=2.0)
    args = parser.parse_args()
    try:
        run(args)
    except (GatewayError, ValueError) as problem:
        sys.exit(f"Recording stopped: {problem}")
    except (KeyboardInterrupt, EOFError):
        sys.exit("\nStopped. Collections saved so far are kept.")


if __name__ == "__main__":
    main()
