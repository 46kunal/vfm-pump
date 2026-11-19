// Virtual Flow Meter dashboard. Reads the gateway; invents nothing.
// Data: /api/hardware/latest (sensors, estimate, edge), /api/profile (active model),
// /api/hardware/history (pump power).

const REFRESH_MS = 1000;
const PROFILE_EVERY = 5;          // refresh the model description every N polls
const STALE_AFTER_MS = 5000;
const MAX_POINTS = 120;
const VOLT_MARGIN = 0.5;          // same margins as gateway/estimator.py
const TEMP_MARGIN = 10;

const $ = id => document.getElementById(id);
const isNumber = v => typeof v === "number" && Number.isFinite(v);
const number = (v, digits = 2) => (isNumber(v) ? v.toFixed(digits) : "N/A");

function setText(id, value) {
  const el = $(id);
  if (el) el.textContent = value;
}

let lastSuccessfulFetch = 0;
let hardwareNote = "Gateway reachable. Waiting for the ESP32";
let profile = { loaded: false };
let pollCount = 0;
const startedAt = Date.now();
const flowHistory = [];          // {t: seconds since page load, v: L/min or null}

/* ---------- connection and banner ---------- */

function updateConnection(status, message) {
  const el = $("connection");
  el.className = `status-pill ${status}`;
  el.innerHTML = '<span class="status-dot"></span>';
  el.append(document.createTextNode(` ${message}`));
}

function updateFreshness() {
  if (!lastSuccessfulFetch) {
    setText("freshness", "Awaiting telemetry");
    return;
  }
  if (Date.now() - lastSuccessfulFetch > STALE_AFTER_MS) {
    setText("freshness", "Telemetry may be stale");
    updateConnection("bad", "Stale data");
  } else {
    setText("freshness", hardwareNote);
  }
}

function setBanner(title, text, tag) {
  setText("banner-title", title);
  setText("banner-text", text);
  setText("banner-tag", tag);
}

/* ---------- charts ---------- */

function drawSeries(canvasId, points, emptyText, fixedMin) {
  const canvas = $(canvasId);
  const ctx = canvas.getContext("2d");
  const w = canvas.width, h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  const left = 58, right = w - 20, top = 24, bottom = h - 38;
  ctx.strokeStyle = "#294052";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = top + (bottom - top) * i / 4;
    ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(right, y); ctx.stroke();
  }

  const real = points.filter(p => isNumber(p.x) && isNumber(p.y));
  if (!real.length) {
    ctx.fillStyle = "#8ca2b3";
    ctx.font = "15px sans-serif";
    ctx.fillText(emptyText, left, h / 2);
    return;
  }

  const x0 = points[0].x, x1 = points[points.length - 1].x;
  const ys = real.map(p => p.y);
  const min = isNumber(fixedMin) ? Math.min(fixedMin, ...ys) : Math.min(...ys) - 0.2;
  const max = Math.max(...ys) + 0.4;
  const X = x => left + (right - left) * ((x - x0) / (x1 - x0 || 1));
  const Y = y => bottom - (bottom - top) * ((y - min) / (max - min || 1));

  ctx.fillStyle = "#8ca2b3";
  ctx.font = "12px sans-serif";
  ctx.fillText(max.toFixed(1), 8, top + 5);
  ctx.fillText(min.toFixed(1), 8, bottom);
  ctx.fillText(`${x0.toFixed(0)} s`, left, h - 10);
  ctx.fillText(`${x1.toFixed(0)} s`, right - 48, h - 10);

  ctx.strokeStyle = "#35d6c2";
  ctx.lineWidth = 3;
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  ctx.beginPath();
  let drawing = false;
  for (const p of points) {
    if (!isNumber(p.y) || !isNumber(p.x)) { drawing = false; continue; }
    if (drawing) ctx.lineTo(X(p.x), Y(p.y));
    else { ctx.moveTo(X(p.x), Y(p.y)); drawing = true; }
  }
  ctx.stroke();
}

/* ---------- sensors ---------- */

function setSensor(id, sensor, value, digits, okNote) {
  const el = $(id), note = $(`${id}-note`), card = el.closest(".metric-card");
  if (!sensor || !isNumber(value)) {
    el.textContent = "N/A";
    card.classList.add("dim");
    note.textContent = sensor ? "Not reported by the sensor" : "No data yet";
    return;
  }
  el.textContent = number(value, digits);
  card.classList.toggle("dim", sensor.stale);
  note.textContent = sensor.stale ? `Stale: last seen ${number(sensor.age_s, 1)} s ago` : okNote;
}

function setMass(sensor) {
  const el = $("mass"), unit = $("mass-unit"), note = $("mass-note"), card = el.closest(".metric-card");
  if (!sensor) {
    el.textContent = "N/A"; unit.textContent = "g"; note.textContent = "No data yet";
    card.classList.add("dim");
    return;
  }
  card.classList.toggle("dim", sensor.stale);
  const stale = `Stale: last seen ${number(sensor.age_s, 1)} s ago`;
  if (isNumber(sensor.mass_g)) {
    el.textContent = number(sensor.mass_g, 1); unit.textContent = "g";
    note.textContent = sensor.stale ? stale : "HX711, calibrated";
  } else {
    el.textContent = String(sensor.raw); unit.textContent = "raw";
    note.textContent = sensor.stale ? stale : "HX711, not calibrated yet";
  }
}

/* ---------- hero estimate ---------- */

function renderHero(estimate) {
  const card = $("hero-card"), badge = $("flow-badge");
  card.classList.remove("provisional", "unavailable");
  const estimateOk = estimate && estimate.available === true && isNumber(estimate.flow_l_min);

  if (estimateOk) {
    setText("flow", number(estimate.flow_l_min));
    if (estimate.provisional) {
      badge.textContent = "PROVISIONAL"; badge.className = "badge provisional";
      card.classList.add("provisional");
      setText("flow-reason", "Placeholder estimate from an unverified model. It will be checked and replaced after calibration.");
    } else if (estimate.validated) {
      badge.textContent = "VALIDATED"; badge.className = "badge validated";
      const err = isNumber(estimate.error_mae_l_min) ? ` Typical error ${number(estimate.error_mae_l_min)} L/min on held-out runs.` : "";
      setText("flow-reason", "Estimated from pump power with a calibrated model." + err);
    } else {
      badge.textContent = "NOT VALIDATED"; badge.className = "badge provisional";
      card.classList.add("provisional");
      setText("flow-reason", "Estimated with a model that has no held-out validation yet.");
    }
    setText("flow-model", `Model ${estimate.model_id}`);
    return;
  }

  card.classList.add("unavailable");
  setText("flow", "Unavailable");
  if (!estimate || estimate.reason === "No calibrated profile loaded") {
    badge.textContent = "NO MODEL"; badge.className = "badge neutral";
    setText("flow-reason", "No calibrated model is loaded, so no flow estimate is shown.");
  } else {
    badge.textContent = "UNAVAILABLE"; badge.className = "badge unavailable";
    setText("flow-reason", estimate.reason);
  }
  setText("flow-model", profile.loaded ? `Model ${profile.model_id}` : "");
}

/* ---------- how it works: live walk-through and checks ---------- */

function inRange(v, range, margin = 0) {
  return Array.isArray(range) && isNumber(v) && v >= range[0] - margin && v <= range[1] + margin;
}

function renderWalkthrough(latest) {
  const s = latest.sensors, est = latest.estimate;
  const ina = s.ina219;
  const fresh = ina && !ina.stale;

  setText("step-power", fresh
    ? `P = V × I = ${number(ina.volts)} V × ${number(ina.amps, 3)} A = ${number(ina.power_w)} W`
    : "No fresh power reading.");

  if (!profile.loaded) {
    setText("step-model", "No model is loaded.");
    setText("step-invert", "Nothing to invert.");
  } else {
    const [c0, c1, c2] = profile.coefficients;
    const linear = Math.abs(c2) < 1e-12;
    setText("step-model", linear
      ? `P(Q) = ${number(c0)} + ${number(c1, 3)} · Q`
      : `P(Q) = ${number(c0)} + ${number(c1, 3)} · Q + ${number(c2, 4)} · Q²`);
    if (fresh && est && est.available) {
      setText("step-invert", linear
        ? `Q = (${number(ina.power_w)} − ${number(c0)}) / ${number(c1, 3)} = ${number(est.flow_l_min)} L/min`
        : `Solve P(Q) = ${number(ina.power_w)} W on the rising branch: Q = ${number(est.flow_l_min)} L/min`);
    } else {
      setText("step-invert", "No flow can be read from this power.");
    }
  }

  setText("step-result", est && est.available
    ? `${number(est.flow_l_min)} L/min${est.provisional ? " (provisional)" : ""}`
    : `Unavailable: ${est ? est.reason : "no estimate"}`);

  renderGates(latest);
}

function renderGates(latest) {
  const list = $("gates");
  list.textContent = "";
  const add = (state, label, detail) => {
    const li = document.createElement("li");
    li.className = state;
    const mark = document.createElement("span");
    mark.className = "mark";
    mark.textContent = state === "pass" ? "✓" : state === "fail" ? "✕" : "–";
    const text = document.createElement("span");
    text.textContent = label;
    li.append(mark, text);
    if (detail) {
      const small = document.createElement("small");
      small.textContent = detail;
      li.append(small);
    }
    list.append(li);
  };

  if (!profile.loaded) {
    add("none", "A calibrated profile is loaded", "none yet");
    return;
  }
  const s = latest.sensors, est = latest.estimate, d = profile.domain;
  const ina = s.ina219;
  const fresh = !!ina && !ina.stale;
  const sigma = profile.power_noise_w || 0;

  add(fresh ? "pass" : "fail", "Fresh pump power reading", fresh ? `${number(ina.age_s, 1)} s old` : "missing or stale");
  if (!fresh) return;

  const vOk = inRange(ina.volts, d.volts, VOLT_MARGIN);
  add(vOk ? "pass" : "fail", "Supply voltage in range", `${number(ina.volts)} V, allowed ${number(d.volts[0] - VOLT_MARGIN, 1)} to ${number(d.volts[1] + VOLT_MARGIN, 1)}`);

  const temp = s.ds18b20;
  if (temp && !temp.stale && d.temp_c) {
    const tOk = inRange(temp.temp_c, d.temp_c, TEMP_MARGIN);
    add(tOk ? "pass" : "fail", "Water temperature in range", `${number(temp.temp_c, 1)} °C`);
  } else {
    add("none", "Water temperature in range", "no reading, check skipped");
  }

  const pOk = inRange(ina.power_w, d.power_w, 2 * sigma);
  add(pOk ? "pass" : "fail", "Pump power in calibrated range",
    `${number(ina.power_w)} W, allowed ${number(d.power_w[0] - 2 * sigma, 1)} to ${number(d.power_w[1] + 2 * sigma, 1)}`);

  const reason = est && est.reason ? est.reason : "";
  const mapFail = reason.includes("does not map");
  const weakFail = reason.includes("weak");
  const upstreamOk = vOk && pOk;
  if (!upstreamOk) {
    add("none", "Power maps to a flow", "not reached");
    add("none", "Flow is outside weak ranges", "not reached");
  } else {
    add(mapFail ? "fail" : "pass", "Power maps to a flow", mapFail ? "no flow in range" : "");
    add(weakFail ? "fail" : (est && est.available ? "pass" : "none"), "Flow is outside weak ranges", weakFail ? "power barely changes here" : "");
  }
}

/* ---------- pipeline labels ---------- */

function renderPipeline(latest) {
  const s = latest.sensors, est = latest.estimate, edge = latest.edge || {};
  const ina = s.ina219;
  const fresh = ina && !ina.stale;
  setText("pl-power", fresh ? `${number(ina.power_w)} W` : "no data");
  setText("pl-ina", fresh ? `${number(ina.volts)} V · ${number(ina.amps * 1000, 0)} mA` : "no data");
  setText("pl-edge", edge.reporting
    ? (edge.available ? `${number(edge.flow_l_min)} L/min on device` : "refusing, see Edge")
    : "gateway estimating");
  setText("pl-gw", est && est.available ? `${number(est.flow_l_min)} L/min` : "unavailable");
  setText("pl-dash", fresh ? "live" : "waiting");
}

/* ---------- edge computing ---------- */

function renderEdge(latest) {
  const edge = latest.edge || { reporting: false };
  const est = latest.estimate;
  const status = $("edge-status");
  const gwOk = est && est.available;
  setText("gw-flow", gwOk ? number(est.flow_l_min) : "Unavailable");

  if (!edge.reporting) {
    status.textContent = "NOT REPORTING"; status.className = "status-tag neutral";
    for (const id of ["edge-flow", "edge-delta", "edge-compute", "edge-loop", "edge-window", "edge-reason"]) setText(id, "—");
    setText("edge-note", "The edge firmware is not flashed yet, so only the gateway is computing. Flash device/firmware/vfm_edge to see the device's own estimate here.");
    return;
  }
  status.textContent = edge.stale ? "STALE" : "LIVE";
  status.className = `status-tag ${edge.stale ? "bad" : "good"}`;
  setText("edge-flow", edge.available ? number(edge.flow_l_min) : "Unavailable");
  setText("edge-delta", isNumber(edge.delta_l_min) ? `${edge.delta_l_min >= 0 ? "+" : ""}${number(edge.delta_l_min, 3)}` : "—");
  setText("edge-compute", isNumber(edge.compute_us) ? `${number(edge.compute_us, 0)} µs` : "—");
  setText("edge-loop", isNumber(edge.loop_max_us) ? `${number(edge.loop_max_us / 1000, 2)} ms` : "—");
  setText("edge-window", isNumber(edge.window_n) ? `${edge.window_n}` : "—");
  setText("edge-reason", edge.available ? "none, estimate given" : edge.reason);
  setText("edge-note", "The device computed this estimate itself from a one-second average of ten samples. The gateway repeats the calculation from the reported values, and the difference should stay close to zero.");
}

/* ---------- model panel and honesty note ---------- */

function renderModel() {
  const state = $("model-state");
  if (!profile.loaded) {
    state.textContent = "NONE"; state.className = "status-tag neutral";
    for (const id of ["model-id", "model-form", "model-coeffs", "model-power", "model-flow", "model-evidence", "model-error"]) setText(id, "—");
    setText("model-warning", "No profile is loaded. Start the gateway with --profile once a model exists.");
    setText("honesty-text", "No flow model is loaded, so no flow estimate is shown. Learning, unlearning and the supervisor run in simulation only.");
    return;
  }
  if (profile.provisional) { state.textContent = "PROVISIONAL"; state.className = "status-tag warning"; }
  else if (profile.validated) { state.textContent = "VALIDATED"; state.className = "status-tag good"; }
  else { state.textContent = "NOT VALIDATED"; state.className = "status-tag warning"; }

  const d = profile.domain;
  setText("model-id", profile.model_id);
  setText("model-form", profile.degree === 1 ? "Straight line" : `Polynomial, degree ${profile.degree}`);
  setText("model-coeffs", profile.coefficients.map(c => number(c, 4)).join(", "));
  setText("model-power", `${number(d.power_w[0], 1)} to ${number(d.power_w[1], 1)} W`);
  setText("model-flow", `${number(d.flow_l_min[0], 1)} to ${number(d.flow_l_min[1], 1)} L/min`);
  setText("model-evidence", profile.provisional
    ? "None. A placeholder line, not fitted to data."
    : `${profile.n_training ?? "?"} training and ${profile.n_validation ?? "?"} validation runs`);
  const mae = profile.metrics && profile.metrics.mae_l_min;
  setText("model-error", isNumber(mae) ? `${number(mae)} L/min` : "Not measured");
  setText("model-warning", (profile.warnings || []).join(" "));

  if (profile.provisional) {
    setText("honesty-text", "The flow number comes from a provisional model: a straight line between a low-power reading on the bench and the pump's label rating. It is a placeholder, not a measurement, and it will be replaced by a model calibrated against weighed water. Learning, unlearning and the supervisor run in simulation only.");
  } else if (profile.validated) {
    setText("honesty-text", `The model was fitted to weighed reference runs and checked on held-out runs${isNumber(mae) ? `, with a typical error of ${number(mae)} L/min` : ""}. It applies only to this pump, supply and rig. Learning, unlearning and the supervisor run in simulation only.`);
  } else {
    setText("honesty-text", "The loaded model has no held-out validation, so its error is not established. Learning, unlearning and the supervisor run in simulation only.");
  }
}

/* ---------- main update ---------- */

function updateHardware(latest, powerItems) {
  const s = latest.sensors;
  setSensor("volts", s.ina219, s.ina219 && s.ina219.volts, 2, "INA219");
  setSensor("amps", s.ina219, s.ina219 && s.ina219.amps * 1000, 0, "INA219");
  setSensor("power", s.ina219, s.ina219 && s.ina219.power_w, 2, "Volts x amps");
  setSensor("temp", s.ds18b20, s.ds18b20 && s.ds18b20.temp_c, 1, "DS18B20");
  setMass(s.hx711);

  const seen = Object.values(s).filter(Boolean);
  const live = seen.some(sensor => !sensor.stale);
  const newest = seen.length ? Math.min(...seen.map(sensor => sensor.age_s)) : null;

  if (!seen.length) {
    updateConnection("neutral", "Waiting for ESP32");
    setBanner("Waiting for the ESP32", "No readings yet. Start the serial bridge. No simulated values are shown.", "NO DATA");
    hardwareNote = "Gateway reachable. Waiting for the ESP32";
    setText("updated", "No readings yet");
  } else if (live) {
    updateConnection("ok", "Receiving live data");
    setBanner("Live hardware data", "Readings come from the ESP32. No simulated values are shown.", "LIVE");
    hardwareNote = "Live updates active";
    setText("updated", `Last reading ${number(newest, 1)} s ago`);
  } else {
    updateConnection("bad", "Hardware data stale");
    setBanner("Hardware data is stale", "The ESP32 stopped sending. Check the USB cable and the serial bridge.", "STALE");
    hardwareNote = "ESP32 readings are stale";
    setText("updated", `Last reading ${number(newest, 1)} s ago`);
  }

  renderHero(latest.estimate);
  renderPipeline(latest);
  renderWalkthrough(latest);
  renderEdge(latest);

  // Estimated-flow history, kept in this page from the estimates it has seen.
  const est = latest.estimate;
  flowHistory.push({ x: (Date.now() - startedAt) / 1000, y: est && est.available ? est.flow_l_min : null });
  if (flowHistory.length > MAX_POINTS) flowHistory.shift();
  const shown = flowHistory.filter(p => p.y !== null).length;
  setText("flow-samples", `${shown} samples`);
  setText("flow-chart-note", shown
    ? (est && est.provisional ? "Provisional estimates. Gaps mean the estimate was unavailable." : "Gaps mean the estimate was unavailable.")
    : "No estimate yet. A calibrated model and a running pump are needed.");
  drawSeries("flow-chart", flowHistory, "No estimated flow yet", 0);

  const power = powerItems.filter(i => isNumber(i.t_s) && isNumber(i.power_w)).map(i => ({ x: i.t_s, y: i.power_w }));
  setText("power-samples", `${power.length} samples`);
  setText("power-chart-note", power.length ? "Recent measured pump power." : "Waiting for INA219 data...");
  drawSeries("power-chart", power, "No power readings yet", 0);
}

async function getJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`Gateway returned HTTP ${response.status}`);
  return response.json();
}

async function refresh() {
  try {
    const wantProfile = pollCount++ % PROFILE_EVERY === 0;
    const [latest, power, prof] = await Promise.all([
      getJson("/api/hardware/latest"),
      getJson("/api/hardware/history?sensor=ina219&limit=120"),
      wantProfile ? getJson("/api/profile") : Promise.resolve(null)
    ]);
    if (prof) { profile = prof; renderModel(); }
    updateHardware(latest, power.items);
    lastSuccessfulFetch = Date.now();
    updateFreshness();
  } catch (error) {
    updateConnection("bad", "Disconnected");
    setText("freshness", "Unable to refresh data");
    setText("updated", "Last displayed reading may be stale");
  }
}

refresh();
setInterval(refresh, REFRESH_MS);
setInterval(updateFreshness, 1000);
