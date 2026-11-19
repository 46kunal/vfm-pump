// Host harness: reads "power_w volts temp_c" lines from stdin (any value may be "nan") and prints
// "available flow reason" using the exact estimator the ESP32 firmware compiles.
#include <cstdio>
#include <cstdlib>
#include <cmath>
#include "profile.h"

static double parse(const char* text) {
  return (text[0] == 'n' || text[0] == 'N') ? NAN : std::atof(text);
}

int main() {
  char p[32], v[32], t[32];
  while (std::scanf("%31s %31s %31s", p, v, t) == 3) {
    const EdgeResult r =
        edgeEstimate(EDGE_PROFILE, (float)parse(p), (float)parse(v), (float)parse(t));
    std::printf("%d %.6f %d\n", r.available ? 1 : 0, r.available ? r.flow : 0.0f, r.reason);
  }
  return 0;
}
