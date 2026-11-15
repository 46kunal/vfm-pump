import json
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from gateway.app import TelemetryStore, make_handler
from gateway.hardware import HardwareStore, ReadingError, UnknownSensor, validate_reading
from tools.serial_bridge import forward_line


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


@pytest.fixture
def server():
    clock = Clock()
    hardware = HardwareStore(clock=clock)
    httpd = ThreadingHTTPServer(
        ("127.0.0.1", 0), make_handler(TelemetryStore(), hardware, token="secret"))
    thread = Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}", clock
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=2)


def post(base, path, payload, token="secret"):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-VFM-Token"] = token
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return urlopen(Request(base + path, data=body, headers=headers, method="POST"))


def status_of(call):
    try:
        with call() as response:
            return response.status
    except HTTPError as error:
        return error.code


def get(base, path):
    with urlopen(base + path) as response:
        return json.load(response)


def test_ina219_gets_power_and_validation_rejects_bad_values():
    values = validate_reading("ina219", {"volts": 12.0, "amps": 0.5})
    assert values["power_w"] == 6.0
    for bad in ({"volts": 12.0}, {"volts": "12", "amps": 1}, {"volts": True, "amps": 1},
                {"volts": 99, "amps": 1}, {"volts": 12, "amps": 1, "extra": 1},
                {"volts": float("nan"), "amps": 1}):
        with pytest.raises(ReadingError):
            validate_reading("ina219", bad)
    with pytest.raises(UnknownSensor):
        validate_reading("lidar", {})
    with pytest.raises(ReadingError):
        validate_reading("hx711", {})
    assert validate_reading("hx711", {"raw": -566400.0}) == {"raw": -566400}


def test_nothing_is_reported_until_real_data_arrives(server):
    base, _ = server
    latest = get(base, "/api/hardware/latest")
    assert latest["source"] == "hardware"
    assert all(value is None for value in latest["sensors"].values())
    assert get(base, "/api/telemetry")["items"] == []
    assert get(base, "/api/hardware/history?sensor=ina219")["items"] == []


def test_post_each_sensor_then_read_back_and_go_stale(server):
    base, clock = server
    assert post(base, "/api/hardware/ina219", {"volts": 12.3, "amps": 0.62}).status == 200
    assert post(base, "/api/hardware/ds18b20", {"temp_c": 24.5}).status == 200
    assert post(base, "/api/hardware/hx711", {"raw": -566400, "mass_g": 12.5}).status == 200
    assert post(base, "/api/hardware/servo", {"angle_deg": 90}).status == 200
    sensors = get(base, "/api/hardware/latest")["sensors"]
    assert sensors["ina219"]["volts"] == 12.3
    assert sensors["ds18b20"]["temp_c"] == 24.5
    assert sensors["hx711"]["raw"] == -566400
    assert sensors["servo"]["angle_deg"] == 90
    assert not sensors["ina219"]["stale"]
    clock.now += 10
    assert get(base, "/api/hardware/latest")["sensors"]["ina219"]["stale"]
    history = get(base, "/api/hardware/history?sensor=ina219&limit=5")
    assert [row["volts"] for row in history["items"]] == [12.3]


def test_sample_endpoint_is_all_or_nothing(server):
    base, _ = server
    good = {"ina219": {"volts": 12.0, "amps": 0.4}, "ds18b20": {"temp_c": 20}}
    assert post(base, "/api/hardware/sample", good).status == 200
    bad = {"ina219": {"volts": 11.0, "amps": 0.4}, "ds18b20": {"temp_c": 999}}
    assert status_of(lambda: post(base, "/api/hardware/sample", bad)) == 400
    assert get(base, "/api/hardware/latest")["sensors"]["ina219"]["volts"] == 12.0


def test_error_statuses(server):
    base, _ = server
    ok = {"volts": 12, "amps": 0.1}
    assert status_of(lambda: post(base, "/api/hardware/ina219", ok, token=None)) == 401
    assert status_of(lambda: post(base, "/api/hardware/ina219", ok, token="nope")) == 401
    assert status_of(lambda: post(base, "/api/hardware/lidar", ok)) == 404
    assert status_of(lambda: post(base, "/api/hardware/ina219", b"not json")) == 400
    assert status_of(lambda: post(base, "/api/hardware/ina219", b'{"volts": NaN, "amps": 1}')) == 400
    assert status_of(lambda: post(base, "/api/hardware/ina219", b"x" * 5000)) == 413
    assert status_of(lambda: urlopen(base + "/api/hardware/history?sensor=lidar")) == 400
    assert status_of(lambda: urlopen(base + "/api/hardware/history?sensor=ina219&limit=0")) == 400


def test_serial_bridge_forwards_json_and_skips_log_lines(server):
    base, _ = server
    assert forward_line("ets Jun  8 2016 boot", base)[0] == "skip"
    assert forward_line("{not json", base)[0] == "skip"
    line = '{"ina219":{"volts":12.1,"amps":0.5},"hx711":{"raw":1000}}'
    assert forward_line(line, base, token="secret")[0] == "ok"
    sensors = get(base, "/api/hardware/latest")["sensors"]
    assert sensors["ina219"]["volts"] == 12.1 and sensors["hx711"]["raw"] == 1000
    assert forward_line(line, base, token="wrong")[0] == "error"
    assert forward_line(line, "http://127.0.0.1:1", timeout=0.5)[0] == "error"
