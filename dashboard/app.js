
const elementIds = [
  "connection", "freshness", "flow", "uncertainty",
  "head-flow", "power-flow", "disagreement",
  "confidence", "state", "mode", "source", "device",
  "sequence", "model-version", "validity", "samples",
  "updated", "chart-note", "banner-title", "banner-text", "banner-tag",
  "power-samples", "power-chart-note"
];

const ids = Object.fromEntries(
  elementIds.map(id => [id, document.getElementById(id)])
);

const REFRESH_INTERVAL = 1000;
const STALE_AFTER_MS = 5000;
const MAX_HISTORY = 120;

let lastSuccessfulFetch = 0;
let history = [];
let hardwareNote = "Gateway reachable. Waiting for the ESP32";

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
    setText("freshness", hardwareNote);
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

function updateDashboard(items) {
  if (!Array.isArray(items)) {
    throw new Error("Invalid telemetry response: items must be an array");
  }

  setText("samples", `${items.length} samples`);

  if (!items.length) {
    setText("flow", "Unavailable");
    setText("uncertainty", "No calibrated model yet");
    setText("chart-note", "No estimated flow yet. A calibrated model is needed first.");
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
      : "Recent valid flow estimates."
  );

  history = items.slice(-MAX_HISTORY);
  drawChart(history);
}

function drawSeries(canvasId, items, key, emptyText) {
  const canvas = document.getElementById(canvasId);
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  const left = 58, right = w - 20, top = 24, bottom = h - 38;
  ctx.strokeStyle = "#294052";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = top + (bottom - top) * i / 4;
    ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(right, y); ctx.stroke();
  }

  const points = items.filter(item => isNumber(item.t_s) && isNumber(item[key]));
  if (!points.length) {
    ctx.fillStyle = "#8ca2b3";
    ctx.font = "15px sans-serif";
    ctx.fillText(emptyText, left, h / 2);
    return;
  }

  const t0 = points[0].t_s;
  const t1 = points[points.length - 1].t_s;
  const values = points.map(item => item[key]);
  const min = Math.min(0, ...values);
  const max = Math.max(...values) + 0.5;
  const x = t => left + (right - left) * ((t - t0) / (t1 - t0 || 1));
  const y = v => bottom - (bottom - top) * ((v - min) / (max - min || 1));

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
  points.forEach((item, i) => {
    if (i) ctx.lineTo(x(item.t_s), y(item[key]));
    else ctx.moveTo(x(item.t_s), y(item[key]));
  });
  ctx.stroke();
}

function setSensor(id, sensor, value, digits, okNote) {
  const el = document.getElementById(id);
  const note = document.getElementById(`${id}-note`);
  const card = el.closest(".metric-card");
  if (!sensor || !isNumber(value)) {
    el.textContent = "N/A";
    card.classList.add("dim");
    note.textContent = sensor ? "Not reported by the sensor" : "No data yet";
    return;
  }
  el.textContent = number(value, digits);
  card.classList.toggle("dim", sensor.stale);
  note.textContent = sensor.stale
    ? `Stale: last seen ${number(sensor.age_s, 1)} s ago`
    : okNote;
}

function setMass(sensor) {
  const el = document.getElementById("mass");
  const unit = document.getElementById("mass-unit");
  const note = document.getElementById("mass-note");
  const card = el.closest(".metric-card");
  if (!sensor) {
    el.textContent = "N/A";
    unit.textContent = "g";
    note.textContent = "No data yet";
    card.classList.add("dim");
    return;
  }
  card.classList.toggle("dim", sensor.stale);
  const stale = `Stale: last seen ${number(sensor.age_s, 1)} s ago`;
  if (isNumber(sensor.mass_g)) {
    el.textContent = number(sensor.mass_g, 1);
    unit.textContent = "g";
    note.textContent = sensor.stale ? stale : "HX711, calibrated";
  } else {
    el.textContent = String(sensor.raw);
    unit.textContent = "raw";
    note.textContent = sensor.stale ? stale : "HX711, not calibrated yet";
  }
}

function setBanner(title, text, tag) {
  setText("banner-title", title);
  setText("banner-text", text);
  setText("banner-tag", tag);
}

function updateHardware(latest, powerItems) {
  const s = latest.sensors;
  setSensor("volts", s.ina219, s.ina219 && s.ina219.volts, 2, "INA219");
  setSensor("amps", s.ina219, s.ina219 && s.ina219.amps * 1000, 0, "INA219");
  setSensor("power", s.ina219, s.ina219 && s.ina219.power_w, 2, "Volts x amps");
  setSensor("temp", s.ds18b20, s.ds18b20 && s.ds18b20.temp_c, 1, "DS18B20");
  setSensor("servo", s.servo, s.servo && s.servo.angle_deg, 0, "Servo commanded angle");
  setMass(s.hx711);

  const seen = Object.values(s).filter(Boolean);
  const live = seen.some(sensor => !sensor.stale);
  const newest = seen.length
    ? Math.min(...seen.map(sensor => sensor.age_s))
    : null;

  if (!seen.length) {
    updateConnection("neutral", "Waiting for ESP32");
    setBanner("Waiting for the ESP32",
      "No readings yet. Start the serial bridge or post to /api/hardware/sample. No simulated values are shown.",
      "NO DATA");
    hardwareNote = "Gateway reachable. Waiting for the ESP32";
    setText("updated", "No readings yet");
  } else if (live) {
    updateConnection("ok", "Receiving live data");
    setBanner("Live hardware data",
      "Readings come from the ESP32. No simulated values are shown.", "LIVE");
    hardwareNote = "Live updates active";
    setText("source", "hardware");
    setText("updated", `Last reading ${number(newest, 1)} s ago`);
  } else {
    updateConnection("bad", "Hardware data stale");
    setBanner("Hardware data is stale",
      "The ESP32 stopped sending. Check the USB cable and the serial bridge.", "STALE");
    hardwareNote = "ESP32 readings are stale";
    setText("updated", `Last reading ${number(newest, 1)} s ago`);
  }

  setText("power-samples", `${powerItems.length} samples`);
  setText("power-chart-note", powerItems.length
    ? "Recent measured pump power."
    : "Waiting for INA219 data...");
  drawSeries("power-chart", powerItems, "power_w", "No power readings yet");
}

async function getJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Gateway returned HTTP ${response.status}`);
  }
  return response.json();
}

async function refresh() {
  try {
    const [telemetry, latest, power] = await Promise.all([
      getJson("/api/telemetry?limit=120"),
      getJson("/api/hardware/latest"),
      getJson("/api/hardware/history?sensor=ina219&limit=120")
    ]);

    if (telemetry.schema_version !== 1) {
      throw new Error("Unsupported telemetry schema version");
    }

    updateDashboard(telemetry.items);
    updateHardware(latest, power.items);

    lastSuccessfulFetch = Date.now();
    updateFreshness();

  } catch (error) {
    updateConnection("bad", "Disconnected");
    setText("freshness", "Unable to refresh data");
    setText("updated", "Last displayed reading may be stale");
    setText("chart-note", "Gateway unavailable. Waiting to reconnect.");
  }
}

refresh();

setInterval(refresh, REFRESH_INTERVAL);
setInterval(updateFreshness, 1000);
