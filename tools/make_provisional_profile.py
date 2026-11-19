"""Write a PROVISIONAL power-to-flow profile so the dashboard can show a flow value now.

  python tools/make_provisional_profile.py

This is NOT a calibration. It draws a straight line between two anchors:
  - about 5 W at zero flow: the lowest power seen with the pump running against the valve
  - 20 W at 15 L/min: the rating on the AD-03 label (20 W, Qmax 15 L/min)
The label maxima are endpoint ratings, not a measured operating point, so every number this
profile produces is a placeholder to be replaced by tools/fit_power_model.py once collections
exist. The dashboard labels it PROVISIONAL / NOT VERIFIED wherever it is shown.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gateway.estimator import SCHEMA, profile_checksum  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "real" / "profiles" / "ad03_provisional_label_anchored.json"

P_ZERO_FLOW_W = 5.0          # measured: lowest running power on the bench
P_LABEL_W, Q_LABEL_L_MIN = 20.0, 15.0   # label rating (separate maxima, not a measured point)


def build_provisional(created=None):
    slope = (P_LABEL_W - P_ZERO_FLOW_W) / Q_LABEL_L_MIN          # W per L/min
    body = {
        "schema": SCHEMA,
        "created_utc": (created or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
        "source": "hardware",
        "provisional": True,
        "pump_id": "AD-03-1",
        "model": {"form": "power_w = c0 + c1*q, inverted to estimate flow (PROVISIONAL line "
                          "between a measured low-power anchor and the label rating)",
                  "degree": 1, "coefficients": [P_ZERO_FLOW_W, slope, 0.0],
                  "units": {"q": "L/min", "power": "W"}},
        "domain": {"flow_l_min": [0.0, Q_LABEL_L_MIN], "power_w": [4.0, P_LABEL_W],
                   "volts": [11.0, 13.0], "temp_c": [5.0, 45.0]},
        "power_noise_w": 0.25,
        "monotonic": True,
        "weak_regions_l_min": [],
        "evaluation": {"method": "provisional_unvalidated", "metrics": {}},
        "data": {"files": [], "n_training": 0, "n_validation": 0, "n_excluded": 0,
                 "n_settings": 0, "loadcell_calibration_ids": []},
        "warnings": ["PROVISIONAL: a straight line between a bench low-power reading and the "
                     "label rating. Not calibrated against a weighed reference. Replace it with "
                     "a profile from tools/fit_power_model.py."],
    }
    body["checksum_sha256"] = profile_checksum(body)
    return body


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    profile = build_provisional()
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    print(f"Wrote {path} (id {profile['checksum_sha256'][:12]})")
    print("PROVISIONAL, not verified. Start the gateway with:")
    print(f"  python -m gateway.app --profile {path} --allow-unvalidated")


if __name__ == "__main__":
    main()
