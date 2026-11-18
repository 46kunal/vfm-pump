"""Power-only flow estimate from a validated AD-03 hardware profile.

The profile comes from tools/fit_power_model.py. This module verifies it, then turns the
latest pump power into a flow estimate. It never forces an answer: outside the calibrated
ranges, or with no profile, the estimate is reported as unavailable with a reason.
"""

import hashlib
import json
from pathlib import Path

from vfm.fastloop import solve_curve

SCHEMA = "ad03-power-profile-v1"
Q_TOLERANCE_L_MIN = 0.5      # same flow tolerance the fit tool uses
VOLT_MARGIN = 0.5            # volts either side of the calibrated supply range
TEMP_MARGIN = 10.0           # degrees C either side of the calibrated water temperature
NO_PROFILE = {"available": False, "reason": "No calibrated profile loaded"}


class ProfileError(ValueError):
    """The profile file is missing, malformed, tampered with or not trustworthy."""


def profile_checksum(profile):
    body = {key: value for key, value in profile.items() if key != "checksum_sha256"}
    text = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_profile(path, allow_unvalidated=False):
    try:
        profile = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as problem:
        raise ProfileError(f"cannot read profile {path}: {problem}") from problem
    if not isinstance(profile, dict) or profile.get("schema") != SCHEMA:
        raise ProfileError(f"unsupported profile schema (expected {SCHEMA})")
    if profile.get("checksum_sha256") != profile_checksum(profile):
        raise ProfileError("profile checksum does not match its contents")
    try:
        coeffs = profile["model"]["coefficients"]
        domain = profile["domain"]
        if len(coeffs) != 3 or not all(domain[k] for k in ("flow_l_min", "power_w", "volts")):
            raise ValueError
        profile["power_noise_w"], profile["weak_regions_l_min"]
        profile["evaluation"]["method"]
    except (KeyError, TypeError, ValueError):
        raise ProfileError("profile is missing required model or range fields") from None
    if profile.get("source") != "hardware":
        raise ProfileError("profile was not made from hardware collections")
    if not profile.get("monotonic"):
        raise ProfileError("profile power curve is not monotonic; refusing to invert it")
    if profile["evaluation"]["method"] != "held_out_validation" and not allow_unvalidated:
        raise ProfileError("profile has no held-out validation; record validation runs, "
                           "or load it explicitly as unvalidated")
    return profile


def _unavailable(reason):
    return {"available": False, "reason": reason}


class PowerEstimator:
    def __init__(self, profile):
        self.profile = profile

    def estimate(self, sensors):
        profile = self.profile
        if profile is None:
            return dict(NO_PROFILE)
        ina = sensors.get("ina219")
        if not ina:
            return _unavailable("No pump power reading")
        if ina.get("stale"):
            return _unavailable("Pump power reading is stale")

        domain = profile["domain"]
        volts_lo, volts_hi = domain["volts"]
        if not volts_lo - VOLT_MARGIN <= ina["volts"] <= volts_hi + VOLT_MARGIN:
            return _unavailable("Supply voltage outside the calibrated range")

        temp = sensors.get("ds18b20")
        if temp and not temp.get("stale") and domain.get("temp_c"):
            temp_lo, temp_hi = domain["temp_c"]
            if not temp_lo - TEMP_MARGIN <= temp["temp_c"] <= temp_hi + TEMP_MARGIN:
                return _unavailable("Water temperature outside the calibrated range")

        power = ina["power_w"]
        sigma = profile["power_noise_w"]
        p_lo, p_hi = domain["power_w"]
        if not p_lo - 2 * sigma <= power <= p_hi + 2 * sigma:
            return _unavailable("Pump power outside the calibrated range")

        q_lo, q_hi = domain["flow_l_min"]
        flow, _, valid = solve_curve(profile["model"]["coefficients"], power, q_hi, True)
        if not valid or flow < q_lo - Q_TOLERANCE_L_MIN:
            return _unavailable("Power does not map to a flow in the calibrated range")
        flow = float(flow)
        for low, high in profile["weak_regions_l_min"]:
            if low <= flow <= high:
                return _unavailable("In a weak range where power barely changes with flow")

        metrics = profile["evaluation"]["metrics"]
        return {
            "available": True,
            "flow_l_min": flow,
            "validated": profile["evaluation"]["method"] == "held_out_validation",
            "evaluation_method": profile["evaluation"]["method"],
            "error_mae_l_min": metrics.get("mae_l_min"),
            "model_id": profile["checksum_sha256"][:12],
            "model_created_utc": profile.get("created_utc"),
        }
