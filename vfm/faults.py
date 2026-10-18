"""Simple, explainable sensor-fault checks (stuck, out-of-range, spike). Owner: AN."""
from collections import deque
import numpy as np

class FaultDetector:
    def __init__(self, cfg, window=30):
        self.cfg = cfg
        self.dp = deque(maxlen=window)
        self.prev = None
        self.window = window

    def update(self, s):
        """Return None or (fault_type, t)."""
        c = self.cfg
        self.dp.append(s["dp_kpa"])
        if not (-5.0 < s["dp_kpa"] < c["max_dp_kpa"] * 1.5):
            return ("out_of_range", s["t"])
        if self.prev is not None and abs(s["dp_kpa"] - self.prev) > 25 * c["sigma_dp_kpa"]:
            self.prev = s["dp_kpa"]
            return ("spike", s["t"])
        self.prev = s["dp_kpa"]
        if len(self.dp) == self.window and np.std(self.dp) < 0.05 * c["sigma_dp_kpa"]:
            return ("stuck", s["t"])
        return None
