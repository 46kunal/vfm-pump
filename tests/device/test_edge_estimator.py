"""The ESP32 estimator (C++) must give the same answer as the gateway estimator (Python)."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest

from gateway.estimator import PowerEstimator, load_profile, profile_checksum
from tools.export_edge_profile import header_text
from tools.fit_power_model import build_profile
from tools.make_provisional_profile import build_provisional

ROOT = Path(__file__).resolve().parents[2]
FIRMWARE = ROOT / "device" / "firmware" / "vfm_edge"
HARNESS = Path(__file__).with_name("edge_estimator_host.cpp")
pytestmark = pytest.mark.skipif(shutil.which("g++") is None, reason="g++ not installed")

REASONS = {
    "No pump power reading": 1, "Pump power reading is stale": 1,
    "Supply voltage outside the calibrated range": 2,
    "Water temperature outside the calibrated range": 3,
    "Pump power outside the calibrated range": 4,
    "Power does not map to a flow in the calibrated range": 5,
    "In a weak range where power barely changes with flow": 6,
}


def _row(q, label, split):
    return {"pump_id": "AD-03-1", "q_ref_l_min": q, "power_w_mean": 3 + 0.8 * q + 0.05 * q * q,
            "power_w_std": 0.05, "volts_mean": 12.3, "temp_c_mean": 27.0,
            "valve_label": label, "split": split, "loadcell_calibration_id": "cal1"}


def fitted_profile():
    rows = [_row(q + 0.01 * r, f"v{i}", "training")
            for i, q in enumerate([1, 2, 3, 4, 5, 6]) for r in range(2)]
    rows += [_row(q, f"val{i}", "validation") for i, q in enumerate([1.5, 3.5, 5.5])]
    profile = build_profile(rows, ["synthetic.jsonl"])
    profile["weak_regions_l_min"] = [[2.4, 2.6], [5.4, 5.6]]
    profile["checksum_sha256"] = profile_checksum(profile)
    return profile


def inputs():
    powers = [0.0, 2.0, 3.5, 4.2, 4.9, 5.0, 5.4, 5.85, 6.5, 7.4, 8.0, 9.0, 12.0, 19.0, 19.9, 20.4, 30.0]
    volts = [9.0, 11.0, 12.3, 13.4, 14.0]
    temps = [float("nan"), 27.0, 60.0, -10.0]
    return [(p, v, t) for p in powers for v in volts for t in temps]


@pytest.fixture(params=["provisional", "fitted_with_weak_ranges"])
def case(request, tmp_path):
    profile = build_provisional() if request.param == "provisional" else fitted_profile()
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(profile))
    (tmp_path / "profile.h").write_text(header_text(profile, "profile.json"))
    exe = tmp_path / "edge_host.exe"
    subprocess.run(
        ["g++", "-std=c++11", "-O1", "-I", str(tmp_path), "-I", str(FIRMWARE),
         str(HARNESS), "-o", str(exe)], check=True, capture_output=True)
    estimator = PowerEstimator(load_profile(profile_path, allow_unvalidated=True))
    return estimator, exe


def test_cpp_matches_python_on_a_grid(case):
    estimator, exe = case
    grid = inputs()
    stdin = "\n".join(f"{p} {v} {'nan' if t != t else t}" for p, v, t in grid) + "\n"
    out = subprocess.run([str(exe)], input=stdin, capture_output=True, text=True,
                         check=True).stdout.split("\n")
    available = 0
    for (power, volts, temp), line in zip(grid, out):
        avail, flow, reason = line.split()
        sensors = {"ina219": {"volts": volts, "amps": power / volts, "power_w": power, "stale": False},
                   "ds18b20": None if temp != temp else {"temp_c": temp, "stale": False}}
        expected = estimator.estimate(sensors)
        assert (avail == "1") == expected["available"], (power, volts, temp, line, expected)
        if expected["available"]:
            available += 1
            assert float(flow) == pytest.approx(expected["flow_l_min"], abs=2e-3), (power, volts, temp)
        else:
            assert int(reason) == REASONS[expected["reason"]], (power, volts, temp, line, expected)
    assert available > 10, "the grid must exercise real estimates, not only refusals"


def test_missing_power_reading_is_refused_on_the_device(case, tmp_path):
    _, exe = case
    out = subprocess.run([str(exe)], input="nan 12.3 27.0\n", capture_output=True, text=True,
                         check=True).stdout.split()
    assert out[0] == "0" and out[2] == "1"
