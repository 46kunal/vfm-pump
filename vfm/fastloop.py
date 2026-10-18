"""Fast loop (10 Hz): head, affinity normalisation, two flow paths, variances, Kalman fusion."""
from collections import deque
import numpy as np

G = 9.81

def water_density(t_c):
    """Kell (1975) formula, kg/m^3, valid 0-100 C."""
    return 1000.0 * (1 - ((t_c + 288.9414) / (508929.2 * (t_c + 68.12963))) * (t_c - 3.9863) ** 2)

def solve_curve(c, y, q_hi, rising):
    """Solve c0 + c1 q + c2 q^2 = y on the valid branch within [0, q_hi].
    rising=False: head branch (slope<0). rising=True: power branch (slope>0).
    Returns (q, slope, valid). Never forces an answer."""
    c0, c1, c2 = c
    a, b, cc = c2, c1, c0 - y
    roots = []
    if abs(a) < 1e-12:
        if abs(b) > 1e-12:
            roots = [-cc / b]
    else:
        disc = b * b - 4 * a * cc
        if disc >= 0:
            s = np.sqrt(disc)
            roots = [(-b + s) / (2 * a), (-b - s) / (2 * a)]
    for r in roots:
        slope = b + 2 * a * r
        if r < 0 or r > q_hi:
            continue
        if rising and slope <= 0:
            continue
        if (not rising) and slope >= 0:
            continue
        return r, slope, True
    return float("nan"), float("nan"), False


class FastLoop:
    def __init__(self, cfg, theta_h=None, theta_p=None):
        self.cfg = cfg
        self.theta_h = list(theta_h if theta_h is not None else cfg["head_curve"])
        self.theta_p = list(theta_p if theta_p is not None else cfg["power_curve"])
        self.x = None          # Kalman state: flow
        self.P = None
        self.rej = {"h": 0, "p": 0}
        self.dp_win = deque(maxlen=cfg["steady_window"])
        self.rpm_win = deque(maxlen=cfg["steady_window"])
        self.rejected_total = 0

    def set_head_curve(self, theta):
        """Only called by the supervisor's applyModel(), between cycles."""
        self.theta_h = [float(v) for v in theta]

    def _kf(self, key, z, R):
        c = self.cfg
        if self.x is None:
            self.x, self.P = z, R
            return True
        innov = z - self.x
        if abs(innov) > c["kalman_gate_sigma"] * np.sqrt(self.P + R):
            self.rej[key] += 1
            self.rejected_total += 1
            if self.rej[key] < c["kalman_max_rejects"]:
                return False
            self.x, self.P = z, R          # persistent jump: accept it (real flow step)
            self.rej[key] = 0
            return True
        self.rej[key] = 0
        K = self.P / (self.P + R)
        self.x += K * innov
        self.P *= (1 - K)
        return True

    def update(self, s):
        c = self.cfg
        rho = water_density(s["temp_c"])
        N = max(s["rpm"], 1.0)
        sN = c["n_ref"] / N
        H = s["dp_kpa"] * 1000.0 / (rho * G)
        Pw = s["volts"] * s["amps"]
        H_ref, P_ref = H * sN ** 2, Pw * sN ** 3
        sig_h_ref = c["sigma_dp_kpa"] * 1000.0 / (rho * G) * sN ** 2
        sig_p_ref = c["sigma_p_w"] * sN ** 3

        qh_r, slh, okh = solve_curve(self.theta_h, H_ref, c["q_max"], False)
        qp_r, slp, okp = solve_curve(self.theta_p, P_ref, c["q_max"], True)
        back = 1.0 / sN                       # reference-speed flow -> actual flow
        qh = qh_r * back if okh else float("nan")
        qp = qp_r * back if okp else float("nan")
        sg_h = abs(sig_h_ref / max(abs(slh), 1e-3)) * back if okh else float("nan")
        sg_p = abs(sig_p_ref / max(abs(slp), 1e-3)) * back if okp else float("nan")

        if self.x is not None:
            self.P += c["kalman_q"]
        used = 0
        if okh and self._kf("h", qh, sg_h ** 2):
            used += 1
        if okp and self._kf("p", qp, sg_p ** 2):
            used += 1

        self.dp_win.append(s["dp_kpa"]); self.rpm_win.append(s["rpm"])
        w = c["steady_window"]
        steady = (len(self.dp_win) == w and (max(self.dp_win) - min(self.dp_win)) < c["steady_dp_kpa"]
                  and (max(self.rpm_win) - min(self.rpm_win)) < c["steady_rpm"])
        both = okh and okp
        z = (qh - qp) / np.sqrt(sg_h ** 2 + sg_p ** 2) if both else float("nan")
        sigma = float(np.sqrt(self.P)) if self.x is not None else float("nan")
        conf = "high" if (both and used == 2 and sigma < 0.5) else "low"
        return {"t": s["t"], "Q": self.x if self.x is not None else float("nan"), "sigma": sigma,
                "Q_h": qh, "Q_p": qp, "sig_h": sg_h, "sig_p": sg_p, "resid_z": z, "steady": steady,
                "conf": conf, "valid": both,
                # regression inputs for the slow loop (reference-speed domain)
                "Qref_p": qp_r, "sigQref_p": abs(sig_p_ref / max(abs(slp), 1e-3)) if okp else float("nan"),
                "H_ref": H_ref, "sigH_ref": sig_h_ref, "slope_h": slh}
