"""Fit a power-to-flow model from recorded collections and validate it on held-out runs.

  python tools/fit_power_model.py data/real/collections/*.jsonl

Fits pump power P(Q) from the training collections, then inverts it to estimate flow from
power. Reports error on collections marked validation (held-out runs). With none, it falls
back to leave-one-out and says so: that is weaker evidence. The profile lists the power and
flow range where the model is valid and the flow ranges where power barely changes with flow
(estimate unavailable there). It never reuses the simulation values in config.json.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vfm.fastloop import solve_curve  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "data" / "real" / "profiles"
Q_TOLERANCE_L_MIN = 0.5     # flow change the power signal should be able to resolve
MIN_SETTINGS = 5            # distinct valve settings in the training set
MIN_TRAIN = 6
REQUIRED = ("q_ref_l_min", "power_w_mean", "volts_mean", "valve_label", "split")


def load_collections(paths):
    rows, files = [], []
    for path in paths:
        raw = Path(path).read_bytes()
        count = 0
        for number, line in enumerate(raw.decode("utf-8").splitlines(), 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("record_type") != "reference_collection":
                continue
            missing = [key for key in REQUIRED if row.get(key) is None]
            if missing:
                raise ValueError(f"{path}:{number} is missing {', '.join(missing)}")
            if row.get("source") != "hardware":
                raise ValueError(f"{path}:{number} is not hardware data")
            rows.append(row)
            count += 1
        files.append({"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "rows": count})
    return rows, files


def split_rows(rows):
    train = [r for r in rows if r["split"] == "training"]
    validation = [r for r in rows if r["split"] == "validation"]
    excluded = [r for r in rows if r["split"] not in ("training", "validation")]
    return train, validation, excluded


def fit_power_curve(rows, degree):
    q = np.array([r["q_ref_l_min"] for r in rows], dtype=float)
    p = np.array([r["power_w_mean"] for r in rows], dtype=float)
    if degree == 1:
        c1, c0 = np.polyfit(q, p, 1)
        return [float(c0), float(c1), 0.0]
    c2, c1, c0 = np.polyfit(q, p, 2)
    return [float(c0), float(c1), float(c2)]


def slope(coeffs, q):
    return coeffs[1] + 2.0 * coeffs[2] * q


def domain_of(rows):
    def span(key):
        values = [r[key] for r in rows if r.get(key) is not None]
        return [float(min(values)), float(max(values))] if values else None
    return {"flow_l_min": span("q_ref_l_min"), "power_w": span("power_w_mean"),
            "volts": span("volts_mean"), "temp_c": span("temp_c_mean")}


def power_noise(rows):
    values = [r["power_w_std"] for r in rows if r.get("power_w_std") is not None]
    return max(float(np.mean(values)) if values else 0.1, 0.02)


def is_monotonic(coeffs, dom):
    grid = np.linspace(dom["flow_l_min"][0], dom["flow_l_min"][1], 101)
    return bool(np.all(slope(coeffs, grid) > 0))


def weak_regions(coeffs, dom, sigma_p):
    """Flow ranges where a 0.5 L/min change moves power by less than 2 sigma."""
    lo, hi = dom["flow_l_min"]
    grid = np.linspace(lo, hi, 101)
    weak = np.abs(slope(coeffs, grid)) * Q_TOLERANCE_L_MIN < 2.0 * sigma_p
    regions, start = [], None
    for q, bad in zip(grid, weak):
        if bad and start is None:
            start = q
        if not bad and start is not None:
            regions.append([float(start), float(q)])
            start = None
    if start is not None:
        regions.append([float(start), float(hi)])
    return regions


def estimate_flow(coeffs, power_w, dom, sigma_p):
    """Flow in L/min, or None when the power is outside the calibrated range."""
    p_lo, p_hi = dom["power_w"]
    if not p_lo - 2 * sigma_p <= power_w <= p_hi + 2 * sigma_p:
        return None
    q, _, valid = solve_curve(coeffs, power_w, dom["flow_l_min"][1], True)
    if not valid or q < dom["flow_l_min"][0] - Q_TOLERANCE_L_MIN:
        return None
    return float(q)


def evaluate(coeffs, rows, dom, sigma_p):
    errors, refs, unavailable = [], [], 0
    for row in rows:
        estimate = estimate_flow(coeffs, row["power_w_mean"], dom, sigma_p)
        if estimate is None:
            unavailable += 1
            continue
        errors.append(estimate - row["q_ref_l_min"])
        refs.append(row["q_ref_l_min"])
    if not errors:
        return {"n": 0, "n_unavailable": unavailable}
    err, ref = np.array(errors), np.array(refs)
    lo, hi = dom["flow_l_min"]
    edges = np.linspace(lo, hi, 4)
    bands = {}
    for name, a, b in zip(("low", "middle", "high"), edges[:-1], edges[1:]):
        mask = (ref >= a) & (ref <= b if name == "high" else ref < b)
        if mask.any():
            bands[name] = {"n": int(mask.sum()), "mae_l_min": float(np.mean(np.abs(err[mask]))),
                           "range_l_min": [float(a), float(b)]}
    return {"n": len(err), "n_unavailable": unavailable,
            "mae_l_min": float(np.mean(np.abs(err))),
            "rmse_l_min": float(np.sqrt(np.mean(err ** 2))),
            "bias_l_min": float(np.mean(err)),
            "max_abs_error_l_min": float(np.max(np.abs(err))),
            "mae_percent_of_mean_flow": float(np.mean(np.abs(err)) / np.mean(ref) * 100),
            "bands": bands}


def leave_one_out(train, degree):
    errors_rows = []
    for i in range(len(train)):
        rest = train[:i] + train[i + 1:]
        if len({r["valve_label"] for r in rest}) < 3:
            continue
        coeffs = fit_power_curve(rest, degree)
        dom = domain_of(rest)
        errors_rows.append((coeffs, dom, power_noise(rest), train[i]))
    errors, refs, unavailable = [], [], 0
    for coeffs, dom, sigma, row in errors_rows:
        estimate = estimate_flow(coeffs, row["power_w_mean"], dom, sigma)
        if estimate is None:
            unavailable += 1
            continue
        errors.append(estimate - row["q_ref_l_min"])
        refs.append(row["q_ref_l_min"])
    if not errors:
        return {"n": 0, "n_unavailable": unavailable}
    err, ref = np.array(errors), np.array(refs)
    return {"n": len(err), "n_unavailable": unavailable,
            "mae_l_min": float(np.mean(np.abs(err))),
            "rmse_l_min": float(np.sqrt(np.mean(err ** 2))),
            "bias_l_min": float(np.mean(err)),
            "max_abs_error_l_min": float(np.max(np.abs(err))),
            "mae_percent_of_mean_flow": float(np.mean(np.abs(err)) / np.mean(ref) * 100)}


def checksum(body):
    text = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_profile(rows, files, degree="auto", allow_small=False, created=None):
    train, validation, excluded = split_rows(rows)
    pumps = {r.get("pump_id") for r in rows}
    if len(pumps) > 1:
        raise ValueError(f"collections from several pumps: {sorted(map(str, pumps))}")
    settings = len({r["valve_label"] for r in train})
    if (settings < MIN_SETTINGS or len(train) < MIN_TRAIN) and not allow_small:
        raise ValueError(
            f"need at least {MIN_SETTINGS} valve settings and {MIN_TRAIN} training collections "
            f"(have {settings} and {len(train)}). Collect more, or pass --allow-small to experiment.")
    if len(train) < 3:
        raise ValueError("need at least 3 training collections")

    dom = domain_of(train)
    sigma_p = power_noise(train)
    candidates = []
    for d in ([1, 2] if degree == "auto" else [int(degree)]):
        coeffs = fit_power_curve(train, d)
        mono = is_monotonic(coeffs, dom)
        if validation:
            metrics, method = evaluate(coeffs, validation, dom, sigma_p), "held_out_validation"
        else:
            metrics, method = leave_one_out(train, d), "leave_one_out_on_training_runs"
        candidates.append({"degree": d, "coeffs": coeffs, "mono": mono,
                           "metrics": metrics, "method": method})
    candidates.sort(key=lambda c: (not c["mono"], c["metrics"].get("rmse_l_min", float("inf")),
                                   c["degree"]))
    best = candidates[0]

    warnings = []
    if not validation:
        warnings.append("No held-out validation runs: error shown is leave-one-out, which is weaker "
                        "evidence. Record validation runs before trusting this model.")
    if not best["mono"]:
        warnings.append("Power is not monotonic in flow over the calibrated range; the inverse "
                        "may be ambiguous. Treat results with caution.")
    weak = weak_regions(best["coeffs"], dom, sigma_p)
    if weak:
        warnings.append("In the weak ranges power barely changes with flow; the estimate there "
                        "should be reported as unavailable.")
    flagged = sum(1 for r in rows if r.get("flags"))
    if flagged:
        warnings.append(f"{flagged} collection(s) carry warning flags; review them.")
    if best["metrics"].get("n_unavailable"):
        warnings.append(f"{best['metrics']['n_unavailable']} evaluation point(s) were outside "
                        "the calibrated range.")
    cal_ids = sorted({str(r.get("loadcell_calibration_id")) for r in rows})
    if len(cal_ids) > 1:
        warnings.append(f"Several load-cell calibrations were used: {', '.join(cal_ids)}.")

    body = {
        "schema": "ad03-power-profile-v1",
        "created_utc": (created or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
        "source": "hardware",
        "pump_id": next(iter(pumps)),
        "model": {"form": "power_w = c0 + c1*q + c2*q^2, inverted to estimate flow",
                  "degree": best["degree"], "coefficients": best["coeffs"],
                  "units": {"q": "L/min", "power": "W"}},
        "domain": dom,
        "power_noise_w": sigma_p,
        "monotonic": best["mono"],
        "weak_regions_l_min": weak,
        "evaluation": {"method": best["method"], "metrics": best["metrics"]},
        "data": {"files": files, "n_training": len(train), "n_validation": len(validation),
                 "n_excluded": len(excluded), "n_settings": settings,
                 "loadcell_calibration_ids": cal_ids},
        "warnings": warnings,
    }
    body["checksum_sha256"] = checksum(body)
    return body


def report(profile, say=print):
    model, metrics = profile["model"], profile["evaluation"]["metrics"]
    say(f"Degree {model['degree']} fit, coefficients c0,c1,c2 = "
        + ", ".join(f"{c:.5g}" for c in model["coefficients"]))
    dom = profile["domain"]
    say(f"Valid flow {dom['flow_l_min'][0]:.2f}..{dom['flow_l_min'][1]:.2f} L/min, "
        f"power {dom['power_w'][0]:.2f}..{dom['power_w'][1]:.2f} W")
    say(f"Evaluation: {profile['evaluation']['method']}")
    if metrics.get("n"):
        say(f"  n={metrics['n']}  MAE {metrics['mae_l_min']:.3f}  RMSE {metrics['rmse_l_min']:.3f}  "
            f"bias {metrics['bias_l_min']:+.3f}  max {metrics['max_abs_error_l_min']:.3f} L/min  "
            f"({metrics['mae_percent_of_mean_flow']:.1f}% of mean flow)")
    else:
        say("  no evaluable points")
    if profile["weak_regions_l_min"]:
        say("Weak (unavailable) flow ranges: "
            + ", ".join(f"{a:.2f}..{b:.2f}" for a, b in profile["weak_regions_l_min"]))
    for warning in profile["warnings"]:
        say(f"WARNING: {warning}")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("collections", nargs="+", help="collection .jsonl files")
    parser.add_argument("--degree", choices=["auto", "1", "2"], default="auto")
    parser.add_argument("--allow-small", action="store_true",
                        help="fit with too few collections, for experiments only")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    try:
        rows, files = load_collections(args.collections)
        profile = build_profile(rows, files, args.degree, args.allow_small)
    except (ValueError, OSError) as problem:
        sys.exit(f"Not fitted: {problem}")
    report(profile)
    output = Path(args.output) if args.output else PROFILES / (
        "ad03_power_profile_" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    print(f"Saved {output}")


if __name__ == "__main__":
    main()
