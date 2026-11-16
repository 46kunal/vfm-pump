"""Helpers shared by the command-line tools that read the gateway."""

import json
import math
import time
import urllib.error
import urllib.request

DEFAULT_URL = "http://127.0.0.1:8765"


class GatewayError(RuntimeError):
    """The gateway is unreachable or is not sending usable readings."""


def get_json(base_url, path, timeout=2.0):
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + path, timeout=timeout) as response:
            return json.load(response)
    except (urllib.error.URLError, OSError, ValueError) as problem:
        raise GatewayError(f"gateway request failed ({path}): {problem}") from problem


def latest(base_url):
    return get_json(base_url, "/api/hardware/latest")


def history(base_url, sensor, limit=600):
    return get_json(base_url, f"/api/hardware/history?sensor={sensor}&limit={limit}")["items"]


def mean_std(values):
    values = [float(v) for v in values]
    if not values:
        return None, None
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    return mean, math.sqrt(var)


def average_field(sensor, key, seconds, fetch, sleep=time.sleep, clock=time.monotonic,
                  interval=0.15):
    """Average distinct, fresh readings of sensors[sensor][key] over `seconds`.

    Returns (mean, std, n). Raises GatewayError if fewer than 3 fresh samples arrive.
    """
    samples = {}
    start = clock()
    while True:
        reading = fetch()["sensors"].get(sensor)
        if reading and not reading["stale"] and reading.get(key) is not None:
            samples[reading["t_s"]] = reading[key]
        if clock() - start >= seconds:
            break
        sleep(interval)
    if len(samples) < 3:
        raise GatewayError(
            f"only {len(samples)} fresh {sensor}.{key} samples in {seconds} s; "
            "is the ESP32 sending and the bridge running?")
    mean, std = mean_std(samples.values())
    return mean, std, len(samples)
