"""Hardware abstraction layer. Algorithms and supervisor only ever call this interface.

Two implementations: SimHAL (vfm/sim.py, used now) and a real-hardware HAL (firmware, later).
Sample schema (identical for sim and real logs):
  t, dp_kpa, volts, amps, rpm, temp_c, valve_pct, quality
valve_pct is 0..1 here (fraction open).
"""
from abc import ABC, abstractmethod

CSV_FIELDS = ["t", "dp_kpa", "volts", "amps", "rpm", "temp_c", "valve_pct", "quality"]

class HAL(ABC):
    @abstractmethod
    def read_sensors(self) -> dict: ...
    @abstractmethod
    def set_valve(self, pct: float) -> None: ...
    @abstractmethod
    def get_valve(self) -> float: ...
