
const elementIds = [
  "connection", "freshness", "flow", "uncertainty",
  "head-flow", "power-flow", "disagreement",
  "confidence", "state", "mode", "source", "device",
  "sequence", "model-version", "validity", "samples",
  "updated", "chart-note", "candidate-id", "candidate-reason",
  "active-a0", "candidate-a0", "candidate-drift"
];

const ids = Object.fromEntries(
  elementIds.map(id => [id, document.getElementById(id)])
);

const REFRESH_INTERVAL = 1000;
const STALE_AFTER_MS = 5000;
const MAX_HISTORY = 120;

let lastSuccessfulFetch = 0;
let history = [];

function setText(id, value) {
  if (ids[id]) {
    ids[id].textContent = value;
  }
}

function number(value, digits = 2) {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toFixed(digits)
    : "N/A";
}

function isNumber(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function setStatus(element, text, status) {
  element.textContent = text;
  element.className = `status-tag ${status}`;
}

function updateConnection(status, message) {
  ids.connection.className = `status-pill ${status}`;
  ids.connection.innerHTML =
    '<span class="status-dot"></span>';
  ids.connection.append(document.createTextNode(` ${message}`));
}

function updateFreshness() {
  if (!lastSuccessfulFetch) {
    setText("freshness", "Awaiting telemetry");
    return;
  }

  const age = Date.now() - lastSuccessfulFetch;

  if (age > STALE_AFTER_MS) {
    setText("freshness", "Telemetry may be stale");
    updateConnection("bad", "Stale data");
  } else {
    setText("freshness", "Live updates active");
  }
}

function drawChart(items) {
  const canvas = document.getElementById("chart");
  const ctx = canvas.getContext("2d");

  const w = canvas.width;
  const h = canvas.height;

  ctx.clearRect(0, 0, w, h);

  const left = 58;
  const right = w - 20;
  const top = 24;
  const bottom = h - 38;

  ctx.strokeStyle = "#294052";
  ctx.lineWidth = 1;

  for (let i = 0; i <= 4; i++) {
    const y = top + (bottom - top) * i / 4;
    ctx.beginPath();
    ctx.moveTo(left, y);
    ctx.lineTo(right, y);
    ctx.stroke();
  }

  const valid = items.filter(
    item => isNumber(item.t_s) &&
      item.valid === true &&
      isNumber(item.flow_l_min)
  );

  if (!valid.length) {
    ctx.fillStyle = "#8ca2b3";
    ctx.font = "15px sans-serif";
    ctx.fillText("No valid flow readings available", left, h / 2);
    return;
  }

  const times = items
    .filter(item => isNumber(item.t_s))
    .map(item => item.t_s);

  const t0 = Math.min(...times);
  const t1 = Math.max(...times);

  const values = valid.map(item => item.flow_l_min);
  const min = Math.max(0, Math.min(...values) - 0.5);
  const max = Math.max(...values) + 0.5;

  const x = t =>
    left + (right - left) * ((t - t0) / (t1 - t0 || 1));

  const y = q =>
    bottom - (bottom - top) * ((q - min) / (max - min || 1));

  ctx.fillStyle = "#8ca2b3";
  ctx.font = "12px sans-serif";
  ctx.fillText(max.toFixed(1), 8, top + 5);
  ctx.fillText(min.toFixed(1), 8, bottom);

  ctx.fillText(`${t0.toFixed(1)} s`, left, h - 10);
  ctx.fillText(`${t1.toFixed(1)} s`, right - 48, h - 10);

  ctx.strokeStyle = "#35d6c2";
  ctx.lineWidth = 3;
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  ctx.beginPath();

  let drawing = false;

  for (const item of items) {
    if (
      item.valid !== true ||
      !isNumber(item.flow_l_min) ||
      !isNumber(item.t_s)
    ) {
      drawing = false;
      continue;
    }

    if (drawing) {
      ctx.lineTo(x(item.t_s), y(item.flow_l_min));
    } else {
      ctx.moveTo(x(item.t_s), y(item.flow_l_min));
      drawing = true;
    }
  }

  ctx.stroke();
}

function updateCandidate() {
  try {
    const element = document.getElementById("pending-candidate-data");
    const candidate = JSON.parse(element.textContent);

    if (candidate.example_only !== true) {
      throw new Error("Candidate is not marked as an example");
    }

    setText("candidate-id", candidate.candidate_id ?? "N/A");
    setText("candidate-reason", candidate.reason ?? "No reason provided");

    setText(
      "active-a0",
      number(candidate.theta_active?.[0])
    );

    setText(
      "candidate-a0",
      number(candidate.theta_candidate?.[0])
    );

    const drift = isNumber(candidate.a0_drift_pct)
      ? `${number(candidate.a0_drift_pct)}%`
      : "N/A";

    setText("candidate-drift", drift);
  } catch (error) {
    setText("candidate-id", "Example unavailable");
    setText("candidate-reason", "Could not load local example data.");
    setText("active-a0", "N/A");
    setText("candidate-a0", "N/A");
    setText("candidate-drift", "N/A");
  }
}

function updateDashboard(items) {
  if (!Array.isArray(items)) {
    throw new Error("Invalid telemetry response: items must be an array");
  }

  setText("samples", `${items.length} samples`);

  if (!items.length) {
    setText("chart-note", "Gateway connected. Waiting for first telemetry reading.");
    drawChart([]);
    return;
  }

  const current = items[items.length - 1];

  if (!current || typeof current !== "object") {
    throw new Error("Invalid telemetry item");
  }

  const validFlow = current.valid === true &&
    isNumber(current.flow_l_min);

  setText("flow", validFlow ? number(current.flow_l_min) : "Unavailable");

  setText(
    "uncertainty",
    `Uncertainty: ${number(current.sigma_l_min)} L/min`
  );

  setText("head-flow", number(current.head_flow_l_min));
  setText("power-flow", number(current.power_flow_l_min));

  const hasBothEstimates =
    isNumber(current.head_flow_l_min) &&
    isNumber(current.power_flow_l_min);

  setText(
    "disagreement",
    hasBothEstimates
      ? number(Math.abs(current.head_flow_l_min - current.power_flow_l_min))
      : "N/A"
  );

  setText("confidence", current.confidence ?? "N/A");
  setText("state", current.state ?? "N/A");
  setText("mode", current.mode ?? "N/A");
  setText("source", current.source ?? "N/A");
  setText("device", current.device_id ?? "N/A");
  setText("sequence", current.sequence ?? "N/A");
  setText("model-version", current.model_version ?? "N/A");

  if (current.valid === true) {
    setStatus(ids.validity, "VALID READING", "good");
  } else {
    setStatus(ids.validity, "INVALID READING", "bad");
  }

  if (current.confidence === "high") {
    // Confidence is an estimator output, not a validity substitute.
    setText("confidence", "HIGH");
  } else if (current.confidence === "low") {
    setText("confidence", "LOW");
  }

  setText(
    "updated",
    `Device time: ${number(current.t_s, 1)} s`
  );

  const missing = items.some(
    item => item.valid !== true || !isNumber(item.flow_l_min)
  );

  setText(
    "chart-note",
    missing
      ? "Gaps indicate invalid or unavailable flow estimates."
      : "Recent valid simulator or device estimates."
  );

  history = items.slice(-MAX_HISTORY);
  drawChart(history);
}

async function refresh() {
  try {
    const response = await fetch(
      "/api/telemetry?limit=120",
      { cache: "no-store" }
    );

    if (!response.ok) {
      throw new Error(`Gateway returned HTTP ${response.status}`);
    }

    const payload = await response.json();

    if (payload.schema_version !== 1) {
      throw new Error("Unsupported telemetry schema version");
    }

    updateDashboard(payload.items);

    lastSuccessfulFetch = Date.now();
    updateConnection("ok", "Connected");
    updateFreshness();

  } catch (error) {
    updateConnection("bad", "Disconnected");
    setText("freshness", "Unable to refresh telemetry");
    setText("updated", "Last displayed reading may be stale");
    setText("chart-note", "Gateway unavailable. Waiting to reconnect.");
  }
}

updateCandidate();
refresh();

setInterval(refresh, REFRESH_INTERVAL);
setInterval(updateFreshness, 1000);
