import json
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.request import urlopen

import pytest

from gateway.app import TelemetryStore, make_handler
from gateway.estimator import PowerEstimator, ProfileError, load_profile
from gateway.hardware import HardwareStore
from tools.fit_power_model import build_profile


def make_rows(with_validation=True):
    """Synthetic collections on the curve power = 3 + 0.8 q + 0.05 q^2 at about 12 V."""
    rows = []
    for i, q in enumerate([1.0, 2.0, 3.0, 4.0, 5.0, 6.0]):
        for run in range(2):
            rows.append(_row(q + 0.01 * run, f"v{i}", "training"))
    if with_validation:
        for i, q in enumerate([1.5, 3.5, 5.5]):
            rows.append(_row(q, f"val{i}", "validation"))
    return rows


def _row(q, label, split):
    return {"pump_id": "AD-03-1", "q_ref_l_min": q, "power_w_mean": 3 + 0.8 * q + 0.05 * q * q,
            "power_w_std": 0.05, "volts_mean": 12.3, "temp_c_mean": 27.0,
            "valve_label": label, "split": split, "loadcell_calibration_id": "cal1"}


def write_profile(tmp_path, rows=None, mutate=None, **kwargs):
    profile = build_profile(rows or make_rows(), ["day1.jsonl"], **kwargs)
    if mutate:
        mutate(profile)
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(profile))
    return path


def sensors(volts=12.3, amps=None, power=None, temp=27.0, stale=False):
    power = 3 + 0.8 * 3.0 + 0.05 * 9.0 if power is None else power
    amps = power / volts if amps is None else amps
    return {"ina219": {"volts": volts, "amps": amps, "power_w": power, "stale": stale},
            "ds18b20": {"temp_c": temp, "stale": False} if temp is not None else None,
            "hx711": None, "servo": None}


def test_valid_profile_gives_flow(tmp_path):
    estimator = PowerEstimator(load_profile(write_profile(tmp_path)))
    result = estimator.estimate(sensors())
    assert result["available"] is True
    assert result["flow_l_min"] == pytest.approx(3.0, abs=0.05)
    assert result["validated"] is True
    assert result["model_id"]


def test_tampered_profile_is_rejected(tmp_path):
    def tamper(profile):
        profile["model"]["coefficients"][1] = 9.9
    with pytest.raises(ProfileError, match="checksum"):
        load_profile(write_profile(tmp_path, mutate=tamper))


def test_wrong_schema_is_rejected(tmp_path):
    def wrong(profile):
        profile["schema"] = "something-else"
    with pytest.raises(ProfileError, match="schema"):
        load_profile(write_profile(tmp_path, mutate=wrong))


def test_missing_file_is_rejected(tmp_path):
    with pytest.raises(ProfileError):
        load_profile(tmp_path / "nope.json")


def test_unvalidated_profile_needs_explicit_permission(tmp_path):
    path = write_profile(tmp_path, rows=make_rows(with_validation=False))
    with pytest.raises(ProfileError, match="held-out"):
        load_profile(path)
    profile = load_profile(path, allow_unvalidated=True)
    result = PowerEstimator(profile).estimate(sensors())
    assert result["available"] is True
    assert result["validated"] is False


def test_power_outside_range_is_unavailable(tmp_path):
    estimator = PowerEstimator(load_profile(write_profile(tmp_path)))
    for power in (0.0, 50.0):
        result = estimator.estimate(sensors(power=power))
        assert result["available"] is False
        assert "power" in result["reason"]
        assert "flow_l_min" not in result


def test_voltage_outside_range_is_unavailable(tmp_path):
    estimator = PowerEstimator(load_profile(write_profile(tmp_path)))
    result = estimator.estimate(sensors(volts=9.0))
    assert result["available"] is False
    assert "voltage" in result["reason"]


def test_missing_or_stale_power_reading_is_unavailable(tmp_path):
    estimator = PowerEstimator(load_profile(write_profile(tmp_path)))
    assert estimator.estimate({"ina219": None, "ds18b20": None})["available"] is False
    assert estimator.estimate(sensors(stale=True))["available"] is False


def test_temperature_far_outside_range_is_unavailable(tmp_path):
    estimator = PowerEstimator(load_profile(write_profile(tmp_path)))
    assert estimator.estimate(sensors(temp=60.0))["available"] is False
    assert estimator.estimate(sensors(temp=None))["available"] is True


def test_weak_region_is_unavailable(tmp_path):
    def flatten(profile):
        profile["weak_regions_l_min"] = [[2.5, 3.5]]
        from gateway.estimator import profile_checksum
        profile["checksum_sha256"] = profile_checksum(profile)
    estimator = PowerEstimator(load_profile(write_profile(tmp_path, mutate=flatten)))
    result = estimator.estimate(sensors())
    assert result["available"] is False
    assert "weak" in result["reason"]


def test_no_profile_reports_unavailable():
    result = PowerEstimator(None).estimate(sensors())
    assert result == {"available": False, "reason": "No calibrated profile loaded"}


@pytest.fixture
def served(tmp_path):
    def start(estimator):
        hardware = HardwareStore()
        httpd = ThreadingHTTPServer(
            ("127.0.0.1", 0), make_handler(TelemetryStore(), hardware, estimator=estimator))
        Thread(target=httpd.serve_forever, daemon=True).start()
        started.append(httpd)
        return f"http://127.0.0.1:{httpd.server_port}", hardware
    started = []
    yield start
    for httpd in started:
        httpd.shutdown()
        httpd.server_close()


def test_latest_includes_estimate(served, tmp_path):
    estimator = PowerEstimator(load_profile(write_profile(tmp_path)))
    base, hardware = served(estimator)
    hardware.update_many({"ina219": {"volts": 12.3, "amps": 5.85 / 12.3}})
    with urlopen(base + "/api/hardware/latest") as response:
        body = json.load(response)
    assert body["estimate"]["available"] is True
    assert body["estimate"]["flow_l_min"] == pytest.approx(3.0, abs=0.1)


def test_latest_without_profile_says_unavailable(served):
    base, hardware = served(None)
    hardware.update_many({"ina219": {"volts": 12.3, "amps": 0.4}})
    with urlopen(base + "/api/hardware/latest") as response:
        body = json.load(response)
    assert body["estimate"] == {"available": False, "reason": "No calibrated profile loaded"}


def test_provisional_profile_is_flagged_and_unvalidated(tmp_path):
    from tools.make_provisional_profile import build_provisional
    path = tmp_path / "prov.json"
    path.write_text(json.dumps(build_provisional()))
    with pytest.raises(ProfileError, match="held-out"):
        load_profile(path)
    estimator = PowerEstimator(load_profile(path, allow_unvalidated=True))
    result = estimator.estimate(sensors(power=7.4))
    assert result["available"] and result["provisional"] and not result["validated"]
    assert result["flow_l_min"] == pytest.approx(2.4, abs=0.01)
    assert estimator.describe()["provisional"] is True


def test_estimate_is_never_negative(tmp_path):
    from tools.make_provisional_profile import build_provisional
    path = tmp_path / "prov.json"
    path.write_text(json.dumps(build_provisional()))
    estimator = PowerEstimator(load_profile(path, allow_unvalidated=True))
    assert estimator.estimate(sensors(power=5.0))["flow_l_min"] >= 0.0


def test_profile_endpoint(served, tmp_path):
    base, _ = served(PowerEstimator(load_profile(write_profile(tmp_path))))
    with urlopen(base + "/api/profile") as response:
        body = json.load(response)
    assert body["loaded"] is True and body["validated"] is True and body["provisional"] is False
    assert len(body["coefficients"]) == 3
    base2, _ = served(None)
    with urlopen(base2 + "/api/profile") as response:
        assert json.load(response) == {"loaded": False}


def test_edge_reading_is_stored_and_compared(served, tmp_path):
    base, hardware = served(PowerEstimator(load_profile(write_profile(tmp_path))))
    hardware.update_many({
        "ina219": {"volts": 12.3, "amps": 5.85 / 12.3},
        "edge": {"available": 1, "flow_l_min": 3.02, "reason": 0, "window_n": 10,
                 "compute_us": 41, "loop_max_us": 900}})
    with urlopen(base + "/api/hardware/latest") as response:
        body = json.load(response)
    edge = body["edge"]
    assert edge["reporting"] and edge["available"]
    assert edge["flow_l_min"] == pytest.approx(3.02)
    assert edge["delta_l_min"] == pytest.approx(0.02, abs=0.1)
    assert edge["compute_us"] == 41


def test_edge_refusal_is_reported_with_its_reason(served):
    base, hardware = served(None)
    hardware.update_many({"edge": {"available": 0, "reason": 4, "window_n": 10}})
    with urlopen(base + "/api/hardware/latest") as response:
        edge = json.load(response)["edge"]
    assert edge["reporting"] and not edge["available"]
    assert edge["reason"] == "pump power outside range"


def test_no_edge_firmware_means_not_reporting(served):
    base, hardware = served(None)
    hardware.update_many({"ina219": {"volts": 12.3, "amps": 0.4}})
    with urlopen(base + "/api/hardware/latest") as response:
        assert json.load(response)["edge"] == {"reporting": False}
