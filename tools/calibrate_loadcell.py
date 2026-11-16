"""Calibrate the HX711 load cell from known masses, using live gateway readings.

Run the gateway and the serial bridge first. Then:  python tools/calibrate_loadcell.py
Steps: empty platform (zero), then each known mass, then empty again (drift check).
Result: data/real/loadcell_calibration.json plus the two lines to paste into the sketch.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.gateway_client import DEFAULT_URL, GatewayError, average_field, latest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "real" / "loadcell_calibration.json"


def fit_calibration(points):
    """Fit raw = offset + counts_per_gram * mass from [(mass_g, raw), ...]."""
    if len(points) < 3:
        raise ValueError("need the empty platform plus at least two known masses")
    masses = np.array([m for m, _ in points], dtype=float)
    raws = np.array([r for _, r in points], dtype=float)
    if len(set(masses.tolist())) < 3:
        raise ValueError("need at least three different masses (including zero)")
    slope, offset = np.polyfit(masses, raws, 1)
    if abs(slope) < 1e-9:
        raise ValueError("raw counts do not change with mass; check wiring and mounting")
    residual_g = (raws - offset) / slope - masses
    return {
        "counts_per_gram": float(slope),
        "offset_counts": float(offset),
        "residuals_g": [float(r) for r in residual_g],
        "max_abs_residual_g": float(np.max(np.abs(residual_g))),
    }


def mass_from_raw(raw, calibration):
    return (raw - calibration["offset_counts"]) / calibration["counts_per_gram"]


def calibration_id(body):
    text = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def load_calibration(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for key in ("counts_per_gram", "offset_counts", "id"):
        if key not in data:
            raise ValueError(f"{path} is not a load-cell calibration (missing {key})")
    return data


def run(args, ask=input, say=print, now=None):
    base = args.gateway

    def fetch():
        return latest(base)

    def measure(label):
        mean, std, n = average_field("hx711", "raw", args.seconds, fetch)
        say(f"  {label}: mean {mean:.0f} counts, std {std:.0f}, {n} samples")
        return mean, std

    ask("1. Remove everything from the platform. Press Enter to measure zero... ")
    zero, zero_std = measure("zero")
    points = [(0.0, zero)]
    readings = [{"mass_g": 0.0, "raw_mean": zero, "raw_std": zero_std}]
    while True:
        text = ask("Place a known mass and type its mass in grams (blank to finish): ").strip()
        if not text:
            break
        try:
            mass = float(text)
        except ValueError:
            say("  Not a number, try again.")
            continue
        if not 0 < mass <= 5000:
            say("  Use a mass above 0 g and up to 5000 g (the cell is rated 5 kg).")
            continue
        ask("  Keep it still on the platform, then press Enter... ")
        raw, std = measure(f"{mass:g} g")
        points.append((mass, raw))
        readings.append({"mass_g": mass, "raw_mean": raw, "raw_std": std})

    fit = fit_calibration(points)
    ask("Remove everything again and press Enter for a drift check... ")
    zero_again, _ = measure("zero again")
    drift_g = (zero_again - fit["offset_counts"]) / fit["counts_per_gram"]

    body = {
        "schema": "loadcell-cal-v1",
        "created_utc": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
        "counts_per_gram": fit["counts_per_gram"],
        "offset_counts": fit["offset_counts"],
        "points": readings,
        "residuals_g": fit["residuals_g"],
        "max_abs_residual_g": fit["max_abs_residual_g"],
        "zero_drift_g": drift_g,
    }
    body["id"] = calibration_id(body)
    say("")
    say(f"counts per gram : {fit['counts_per_gram']:.4f}")
    say(f"offset (tare)   : {fit['offset_counts']:.0f}")
    say(f"worst residual  : {fit['max_abs_residual_g']:.2f} g over {len(points)} points")
    say(f"zero drift      : {drift_g:+.2f} g (empty platform before vs after)")
    if fit["max_abs_residual_g"] > 5 or abs(drift_g) > 5:
        say("WARNING: residual or drift above 5 g. Check the mounting, wires and that")
        say("nothing else touches the platform, then repeat.")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(body, indent=2), encoding="utf-8")
    say(f"Saved {output} (id {body['id']})")
    say("")
    say("To show grams on the dashboard, set these in vfm_sensors.ino and re-upload:")
    say(f"  const float HX_COUNTS_PER_GRAM = {fit['counts_per_gram']:.4f};")
    say(f"  const long HX_OFFSET = {round(fit['offset_counts'])};")
    return body


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gateway", default=DEFAULT_URL)
    parser.add_argument("--seconds", type=float, default=3.0,
                        help="averaging time for each reading")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    try:
        run(args)
    except (GatewayError, ValueError) as problem:
        sys.exit(f"Calibration stopped: {problem}")
    except (KeyboardInterrupt, EOFError):
        sys.exit("\nCalibration cancelled; nothing was saved.")


if __name__ == "__main__":
    main()
