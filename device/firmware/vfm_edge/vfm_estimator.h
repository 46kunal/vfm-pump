// On-device (edge) power-only flow estimator. Plain C++ with no Arduino dependency, so the
// same file is compiled on a PC and checked against the Python estimator (gateway/estimator.py).
//
// Model: power = c0 + c1*q + c2*q^2. Flow is found by inverting it on the rising branch.
// It never forces an answer: outside the calibrated ranges it reports why it has none.

#pragma once
#include <math.h>

struct EdgeProfile {
  float c0, c1, c2;                 // power (W) = c0 + c1*q + c2*q^2, q in L/min
  float flow_lo, flow_hi;           // calibrated flow range, L/min
  float power_lo, power_hi;         // calibrated pump power range, W
  float volts_lo, volts_hi;         // calibrated supply voltage range, V
  float temp_lo, temp_hi;           // calibrated water temperature range, degrees C
  float power_noise;                // W, one sigma
  int weak_count;                   // flow ranges where power barely changes (max 4)
  float weak_lo[4], weak_hi[4];
  const char* model_id;
};

enum EdgeReason {
  EDGE_OK = 0,
  EDGE_NO_POWER = 1,        // no usable pump power reading
  EDGE_VOLTAGE = 2,         // supply voltage outside the calibrated range
  EDGE_TEMP = 3,            // water temperature outside the calibrated range
  EDGE_POWER_RANGE = 4,     // pump power outside the calibrated range
  EDGE_NO_FLOW = 5,         // power does not map to a flow in the calibrated range
  EDGE_WEAK = 6             // flow falls where power barely changes with flow
};

struct EdgeResult {
  bool available;
  float flow;               // L/min, valid only when available
  int reason;               // EdgeReason
};

// Same margins as gateway/estimator.py.
static const float EDGE_VOLT_MARGIN = 0.5f;
static const float EDGE_TEMP_MARGIN = 10.0f;
static const float EDGE_Q_TOLERANCE = 0.5f;

// temp_c: pass NAN when the temperature sensor has no reading (the check is then skipped).
inline EdgeResult edgeEstimate(const EdgeProfile& p, float power_w, float volts, float temp_c) {
  EdgeResult out = {false, 0.0f, EDGE_NO_POWER};
  if (!isfinite(power_w) || !isfinite(volts)) return out;

  if (!(volts >= p.volts_lo - EDGE_VOLT_MARGIN && volts <= p.volts_hi + EDGE_VOLT_MARGIN)) {
    out.reason = EDGE_VOLTAGE;
    return out;
  }
  if (isfinite(temp_c) &&
      !(temp_c >= p.temp_lo - EDGE_TEMP_MARGIN && temp_c <= p.temp_hi + EDGE_TEMP_MARGIN)) {
    out.reason = EDGE_TEMP;
    return out;
  }
  if (!(power_w >= p.power_lo - 2.0f * p.power_noise &&
        power_w <= p.power_hi + 2.0f * p.power_noise)) {
    out.reason = EDGE_POWER_RANGE;
    return out;
  }

  // Solve c0 + c1 q + c2 q^2 = power on the rising branch within [0, flow_hi].
  const float a = p.c2, b = p.c1, cc = p.c0 - power_w;
  float roots[2];
  int n = 0;
  if (fabsf(a) < 1e-12f) {
    if (fabsf(b) > 1e-12f) roots[n++] = -cc / b;
  } else {
    const float disc = b * b - 4.0f * a * cc;
    if (disc >= 0.0f) {
      const float s = sqrtf(disc);
      roots[n++] = (-b + s) / (2.0f * a);
      roots[n++] = (-b - s) / (2.0f * a);
    }
  }
  bool found = false;
  float q = 0.0f;
  for (int i = 0; i < n; i++) {
    const float r = roots[i];
    if (r < 0.0f || r > p.flow_hi) continue;
    if (b + 2.0f * a * r <= 0.0f) continue;     // falling branch: not a valid inverse
    q = r;
    found = true;
    break;
  }
  if (!found || q < p.flow_lo - EDGE_Q_TOLERANCE) {
    out.reason = EDGE_NO_FLOW;
    return out;
  }
  if (q < 0.0f) q = 0.0f;
  for (int i = 0; i < p.weak_count; i++) {
    if (q >= p.weak_lo[i] && q <= p.weak_hi[i]) {
      out.reason = EDGE_WEAK;
      return out;
    }
  }
  out.available = true;
  out.flow = q;
  out.reason = EDGE_OK;
  return out;
}
