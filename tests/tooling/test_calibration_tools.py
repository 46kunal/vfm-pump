"""Tests for the load-cell calibration, collection recorder and power-model fitting tools.

The rows below are made-up inputs that exercise the maths; they are not pump data.
"""
import json
from datetime import datetime, timezone

import pytest

from tools import calibrate_loadcell, fit_power_model, record_collection
from tools.gateway_client import GatewayError, average_field


# ------------------------------------------------------------------ load cell

def test_fit_calibration_recovers_counts_per_gram_and_offset():
    k, offset = -420.5, -566400.0
    points = [(m, offset + k * m) for m in (0, 500, 1000, 2000)]
    fit = calibrate_loadcell.fit_calibration(points)
    assert fit["counts_per_gram"] == pytest.approx(k)
    assert fit["offset_counts"] == pytest.approx(offset)
    assert fit["max_abs_residual_g"] < 1e-6
    cal = {"counts_per_gram": k, "offset_counts": offset}
    assert calibrate_loadcell.mass_from_raw(offset + k * 750, cal) == pytest.approx(750)


def test_fit_calibration_rejects_bad_input():
    with pytest.raises(ValueError):
        calibrate_loadcell.fit_calibration([(0, 1.0), (500, 2.0)])
    with pytest.raises(ValueError):
        calibrate_loadcell.fit_calibration([(0, 1.0), (500, 1.0), (1000, 1.0)])
    with pytest.raises(ValueError):
        calibrate_loadcell.fit_calibration([(0, 1.0), (0, 2.0), (500, 3.0)])


def test_average_field_uses_distinct_fresh_samples_only():
    ticks = iter(range(1000))
    clock_value = {"now": 0.0}

    def fetch():
        t = next(ticks) // 2          # every reading is returned twice: duplicates must collapse
        return {"sensors": {"hx711": {"raw": 100 + t, "t_s": float(t), "stale": False}}}

    def clock():
        return clock_value["now"]

    def sleep(seconds):
        clock_value["now"] += seconds

    mean, std, n = average_field("hx711", "raw", 1.0, fetch, sleep=sleep, clock=clock, interval=0.15)
    assert n == 4                    # eight reads, each value seen twice
    assert mean == pytest.approx(101.5)

    def stale():
        return {"sensors": {"hx711": {"raw": 1, "t_s": 1.0, "stale": True}}}

    with pytest.raises(GatewayError):
        average_field("hx711", "raw", 0.3, stale, sleep=sleep, clock=clock)
    with pytest.raises(GatewayError):
        average_field("hx711", "raw", 0.3, lambda: {"sensors": {"hx711": None}},
                      sleep=sleep, clock=clock)


def test_calibration_session_end_to_end(tmp_path, monkeypatch):
    state = {"mass": 0.0}

    def fake_average(sensor, key, seconds, fetch, **kwargs):
        assert (sensor, key) == ("hx711", "raw")
        return -566400.0 - 420.0 * state["mass"], 5.0, 20

    monkeypatch.setattr(calibrate_loadcell, "average_field", fake_average)
    masses = iter(["500", "1000", "2000", ""])
    lines = []

    def ask(prompt):
        if "Place a known mass" in prompt:
            text = next(masses)
            state["mass"] = float(text) if text else 0.0
            return text
        if "Remove everything" in prompt:
            state["mass"] = 0.0
        return ""

    class Args:
        gateway = "http://unused"
        seconds = 1.0
        output = str(tmp_path / "cal.json")

    body = calibrate_loadcell.run(Args, ask=ask, say=lines.append,
                                  now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    saved = calibrate_loadcell.load_calibration(Args.output)
    assert saved["id"] == body["id"]
    assert saved["counts_per_gram"] == pytest.approx(-420.0)
    assert abs(saved["zero_drift_g"]) < 1e-6
    assert any("HX_COUNTS_PER_GRAM" in line for line in lines)


# ------------------------------------------------------------------ collections

def test_reference_flow_uses_water_density():
    q, rho = record_collection.reference_flow_l_min(1000.0, 10.0, 20.0)
    assert rho == pytest.approx(0.9982, abs=1e-3)
    assert q == pytest.approx(60 * 1.0 / (rho * 10), rel=1e-9)
    q_default, rho_default = record_collection.reference_flow_l_min(1000.0, 10.0)
    assert rho_default == 1.0 and q_default == pytest.approx(6.0)
    with pytest.raises(ValueError):
        record_collection.reference_flow_l_min(0.0, 10.0)
    with pytest.raises(ValueError):
        record_collection.reference_flow_l_min(500.0, 0.0)


def test_window_stats_selects_rows_in_time_window():
    rows = [{"t_s": t, "volts": 12.0 + t} for t in range(10)]
    stats = record_collection.window_stats(rows, "volts", 2.0, 4.0)
    assert stats["n"] == 3 and stats["mean"] == pytest.approx(15.0)
    assert record_collection.window_stats(rows, "volts", 50, 60) == \
        {"mean": None, "std": None, "n": 0}


def _record(duration=12.0, delta=1200.0):
    ina = [{"t_s": float(t), "volts": 12.3, "amps": 0.6, "power_w": 12.3 * 0.6}
           for t in range(40)]
    temp = [{"t_s": float(t), "temp_c": 20.0} for t in range(40)]
    return record_collection.build_record(
        {"session": "s1", "pump_id": "AD-03-1", "split": "training", "valve_label": "3 of 8"},
        start_t=10.0, end_t=10.0 + duration, mass_start_g=100.0, mass_end_g=100.0 + delta,
        ina_rows=ina, temp_rows=temp, calibration_id="abc123",
        created=datetime(2026, 1, 1, tzinfo=timezone.utc))


def test_build_record_has_flow_electrical_means_and_flags():
    record = _record()
    assert record["source"] == "hardware"
    assert record["q_ref_l_min"] == pytest.approx(
        60 * 1.2 / (record["density_kg_per_l"] * 12.0))
    assert record["power_w_mean"] == pytest.approx(12.3 * 0.6)
    assert record["electrical_samples"] >= 3
    assert record["flags"] == []
    json.dumps(record, allow_nan=False)
    short = _record(duration=5.0, delta=500.0)
    assert "short_collection_timing_error_large" in short["flags"]
    assert "near_load_cell_capacity" in _record(delta=4600.0)["flags"]
    with pytest.raises(ValueError):
        _record(delta=-50.0)


# ------------------------------------------------------------------ fitting

def make_rows(c0, c1, c2, flows, split="training", noise_std=0.05, prefix="v"):
    return [{
        "record_type": "reference_collection", "source": "hardware", "pump_id": "AD-03-1",
        "split": split, "valve_label": f"{prefix}{i}", "q_ref_l_min": q,
        "power_w_mean": c0 + c1 * q + c2 * q * q, "power_w_std": noise_std,
        "volts_mean": 12.3, "temp_c_mean": 21.0, "flags": [], "loadcell_calibration_id": "cal1",
    } for i, q in enumerate(flows)]


TRAIN_FLOWS = [1, 2, 3, 4, 5, 6, 7, 8]


def test_fit_recovers_curve_and_validates_on_held_out_runs():
    rows = make_rows(5.0, 0.8, 0.05, TRAIN_FLOWS) + \
        make_rows(5.0, 0.8, 0.05, [1.5, 3.5, 6.5], split="validation", prefix="h")
    profile = fit_power_model.build_profile(rows, [], degree="2")
    assert profile["model"]["coefficients"] == pytest.approx([5.0, 0.8, 0.05], abs=1e-6)
    assert profile["monotonic"] is True
    assert profile["evaluation"]["method"] == "held_out_validation"
    metrics = profile["evaluation"]["metrics"]
    assert metrics["n"] == 3 and metrics["max_abs_error_l_min"] < 1e-6
    assert profile["warnings"] == []
    assert profile["checksum_sha256"]
    # Out-of-range power gives no estimate rather than an extrapolated one.
    dom, sigma = profile["domain"], profile["power_noise_w"]
    assert fit_power_model.estimate_flow(profile["model"]["coefficients"], 500.0, dom, sigma) is None


def test_without_validation_runs_it_says_so():
    profile = fit_power_model.build_profile(make_rows(5.0, 0.8, 0.05, TRAIN_FLOWS), [])
    assert profile["evaluation"]["method"] == "leave_one_out_on_training_runs"
    assert any("No held-out validation" in w for w in profile["warnings"])


def test_refuses_too_little_data_and_mixed_pumps():
    with pytest.raises(ValueError, match="need at least"):
        fit_power_model.build_profile(make_rows(5.0, 0.8, 0.05, [1, 2, 3]), [])
    fit_power_model.build_profile(make_rows(5.0, 0.8, 0.05, [1, 2, 3]), [], allow_small=True)
    rows = make_rows(5.0, 0.8, 0.05, TRAIN_FLOWS)
    rows[0]["pump_id"] = "other"
    with pytest.raises(ValueError, match="several pumps"):
        fit_power_model.build_profile(rows, [])


def test_flat_power_curve_is_reported_as_weak():
    rows = make_rows(10.0, 0.01, 0.0, TRAIN_FLOWS)
    profile = fit_power_model.build_profile(rows, [], degree="1")
    assert profile["weak_regions_l_min"]
    assert any("barely changes" in w for w in profile["warnings"])


def test_fault_runs_are_excluded_and_checksum_tracks_content():
    rows = make_rows(5.0, 0.8, 0.05, TRAIN_FLOWS) + \
        make_rows(50.0, 0.0, 0.0, [4.0], split="fault", prefix="f")
    profile = fit_power_model.build_profile(rows, [])
    assert profile["data"]["n_excluded"] == 1
    assert profile["model"]["coefficients"] == pytest.approx([5.0, 0.8, 0.05], abs=1e-6)
    changed = dict(profile, pump_id="changed")
    changed.pop("checksum_sha256")
    original = {k: v for k, v in profile.items() if k != "checksum_sha256"}
    assert fit_power_model.checksum(changed) != fit_power_model.checksum(original)
    assert fit_power_model.checksum(original) == profile["checksum_sha256"]


def test_load_collections_checks_files(tmp_path):
    good = make_rows(5.0, 0.8, 0.05, [1.0, 2.0])
    path = tmp_path / "s.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in good) + "\n", encoding="utf-8")
    rows, files = fit_power_model.load_collections([path])
    assert len(rows) == 2 and files[0]["rows"] == 2 and len(files[0]["sha256"]) == 64
    simulated = dict(good[0], source="simulation")
    path.write_text(json.dumps(simulated) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not hardware"):
        fit_power_model.load_collections([path])
    incomplete = {k: v for k, v in good[0].items() if k != "power_w_mean"}
    path.write_text(json.dumps(incomplete) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing"):
        fit_power_model.load_collections([path])
