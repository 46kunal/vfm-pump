"""Plant simulator and SimHAL. TEST SCAFFOLDING ONLY: results from this are never rig results.

Models: pump head/power curves with speed scaling (affinity laws), a valve-set system curve,
different sensor lags for head and power (so valve bumps create transient residuals),
Gaussian sensor noise, wear (a0 drop) and sensor faults. All numbers are placeholders.
"""
import numpy as np
from .hal import HAL
from .fastloop import water_density

G = 9.81

class SimPlant:
    def __init__(self, cfg, seed=0, valve=0.45, rpm=None):
        self.cfg = cfg
        self.rng = np.random.default_rng(seed)
        self.t = 0.0
        self.n_ref = cfg["n_ref"]
        self.rpm = self.n_ref if rpm is None else rpm
        self.temp = 20.0
        self.a = list(cfg["head_curve"])        # TRUE head curve (can wear)
        self.b = list(cfg["power_curve"])       # TRUE power curve
        self.k0 = 0.0411                        # valve full-open system coefficient
        self.valve_cmd = valve
        self.valve = valve
        self.slew = 0.4                         # valve travel per second
        self.tau_h, self.tau_p = 0.15, 0.6      # sensor lags (s)
        self.faults = {"dp_offset_kpa": 0.0, "dp_stuck": None}
        self._cache_key = None
        self._q = self._h = self._p = None
        self.h_f = self.p_f = None
        self._solve()
        self.h_f, self.p_f = self._h, self._p

    # ---- true physics -------------------------------------------------
    def _head_ref(self, q):
        return self.a[0] + self.a[1] * q + self.a[2] * q * q

    def _solve(self):
        key = (round(self.valve, 5), round(self.rpm, 3), tuple(self.a), tuple(self.b))
        if key == self._cache_key:
            return
        s = self.rpm / self.n_ref
        k = self.k0 / max(self.valve, 0.02) ** 2
        lo, hi = 1e-6, 40.0 * s
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            pump = s * s * self._head_ref(mid / s)
            if pump - k * mid * mid > 0:
                lo = mid
            else:
                hi = mid
        q = 0.5 * (lo + hi)
        qr = q / s
        self._q = q
        self._h = s * s * self._head_ref(qr)
        self._p = s ** 3 * (self.b[0] + self.b[1] * qr + self.b[2] * qr * qr)
        self._cache_key = key

    @property
    def q_true(self):
        return self._q

    # ---- time stepping --------------------------------------------------
    def set_valve_cmd(self, v):
        self.valve_cmd = float(np.clip(v, 0.1, 1.0))

    def step(self, dt):
        d = self.valve_cmd - self.valve
        mv = self.slew * dt
        self.valve += float(np.clip(d, -mv, mv))
        self._solve()
        self.h_f += dt / (self.tau_h + dt) * (self._h - self.h_f)
        self.p_f += dt / (self.tau_p + dt) * (self._p - self.p_f)
        self.t += dt

    def sample(self):
        c, r = self.cfg, self.rng
        rho = water_density(self.temp)
        dp = self.h_f * rho * G / 1000.0 + self.faults["dp_offset_kpa"] + r.normal(0, c["sigma_dp_kpa"])
        if self.faults["dp_stuck"] is not None:
            dp = self.faults["dp_stuck"]
        volts = c["supply_volts"]
        amps = (self.p_f + r.normal(0, c["sigma_p_w"])) / volts
        return {"t": self.t, "dp_kpa": dp, "volts": volts, "amps": amps,
                "rpm": self.rpm + r.normal(0, c["sigma_rpm"]),
                "temp_c": self.temp + r.normal(0, 0.05),
                "valve_pct": self.valve, "quality": 1}


class SimHAL(HAL):
    def __init__(self, cfg, seed=0, valve=0.45, rpm=None):
        self.cfg = cfg
        self.plant = SimPlant(cfg, seed, valve, rpm)

    def read_sensors(self):
        self.plant.step(self.cfg["dt"])
        return self.plant.sample()

    def set_valve(self, pct):
        self.plant.set_valve_cmd(pct)

    def get_valve(self):
        return self.plant.valve_cmd
