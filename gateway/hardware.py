"""Validated real-sensor readings posted by the ESP32. No simulated values here."""

from collections import deque
import math
import threading
import time

HISTORY = 600
STALE_AFTER_S = 3.0

# sensor -> (required fields, optional fields); each field -> (minimum, maximum)
SENSORS = {
    "ina219": ({"volts": (0.0, 32.0), "amps": (-3.5, 3.5)}, {}),
    "ds18b20": ({"temp_c": (-55.0, 125.0)}, {}),
    "hx711": ({}, {"mass_g": (-10000.0, 10000.0), "raw": (-8388608.0, 8388607.0)}),
    "servo": ({"angle_deg": (0.0, 180.0)}, {}),
}


class ReadingError(ValueError):
    """The posted reading is malformed or physically impossible."""


class UnknownSensor(ReadingError):
    """The sensor name is not one of SENSORS."""


def _number(name, value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReadingError(f"{name} must be a number")
    value = float(value)
    if not math.isfinite(value):
        raise ReadingError(f"{name} must be finite")
    if not low <= value <= high:
        raise ReadingError(f"{name} out of range {low}..{high}")
    return value


def validate_reading(sensor, payload):
    if sensor not in SENSORS:
        raise UnknownSensor(f"unknown sensor: {sensor}")
    if not isinstance(payload, dict):
        raise ReadingError(f"{sensor} payload must be a JSON object")
    required, optional = SENSORS[sensor]
    extra = set(payload) - set(required) - set(optional)
    if extra:
        raise ReadingError(f"{sensor}: unknown fields: {', '.join(sorted(extra))}")
    values = {}
    for name, (low, high) in required.items():
        if name not in payload:
            raise ReadingError(f"{sensor}: missing field: {name}")
        values[name] = _number(name, payload[name], low, high)
    for name, (low, high) in optional.items():
        if name in payload:
            values[name] = _number(name, payload[name], low, high)
    if sensor == "hx711":
        if not values:
            raise ReadingError("hx711 needs mass_g or raw")
        if "raw" in values:
            values["raw"] = int(round(values["raw"]))
    if sensor == "ina219":
        values["power_w"] = values["volts"] * values["amps"]
    return values


class HardwareStore:
    def __init__(self, history=HISTORY, clock=time.monotonic):
        self.history_capacity = history
        self._clock = clock
        self._start = clock()
        self._lock = threading.Lock()
        self._latest = {}
        self._history = {name: deque(maxlen=history) for name in SENSORS}

    def update_many(self, readings):
        """Validate every reading first, then store them all or none."""
        if not isinstance(readings, dict) or not readings:
            raise ReadingError("expected a JSON object with at least one sensor")
        checked = {sensor: validate_reading(sensor, payload)
                   for sensor, payload in readings.items()}
        now = self._clock()
        t_s = round(now - self._start, 3)
        with self._lock:
            for sensor, values in checked.items():
                record = {"t_s": t_s, **values}
                self._latest[sensor] = (now, record)
                self._history[sensor].append(record)
        return sorted(checked)

    def snapshot(self, stale_after=STALE_AFTER_S):
        now = self._clock()
        with self._lock:
            latest = dict(self._latest)
        sensors = {}
        for name in SENSORS:
            if name not in latest:
                sensors[name] = None
                continue
            seen, record = latest[name]
            age = now - seen
            sensors[name] = {**record, "age_s": round(age, 3), "stale": age > stale_after}
        return {"schema": "hardware-v1", "source": "hardware",
                "server_t_s": round(now - self._start, 3),
                "stale_after_s": stale_after, "sensors": sensors}

    def history(self, sensor, limit=120):
        if sensor not in SENSORS:
            raise UnknownSensor(f"unknown sensor: {sensor}")
        with self._lock:
            return list(self._history[sensor])[-limit:]
