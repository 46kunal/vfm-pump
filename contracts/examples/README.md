# Shared development fixtures (lead-owned)

These are synthetic examples, not rig measurements. Each feature can use them
without waiting for any other teammate.

- `experiment.csv`: 60 artificial estimate/reference pairs for A's report.
- `sensors.csv`: 12 artificial sensor rows including a pressure jump, a repeated
  pressure run, and one bad quality flag for B's health report.
- `telemetry_session.jsonl`: 60 simulator-derived messages for C and D. Ten rows
  were deliberately changed to contain null flow/uncertainty and low confidence
  so the logger and dashboard exercise missing-data behavior. These edits are
  test fixtures, not a claim about the current estimator's fault response.
- `telemetry.json`: one simple mock telemetry message.
- `pending_candidate.json`: illustrative proposed curve for the dashboard's
  read-only pending card. It is not a real approved update or a live endpoint.

Do not regenerate shared fixtures in a feature PR. Put personal experiments in
`outputs/local/`. JSONL means one complete JSON object per line.
