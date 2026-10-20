const ids = Object.fromEntries([
  "connection", "flow", "uncertainty", "confidence", "state", "mode",
  "source", "device", "samples", "updated", "chart-note"
].map(id => [id, document.getElementById(id)]));

function number(value, digits = 2) {
  return value === null || value === undefined ? "N/A" : Number(value).toFixed(digits);
}

function drawChart(items) {
  const canvas = document.getElementById("chart");
  const ctx = canvas.getContext("2d");
  const { width: w, height: h } = canvas;
  ctx.clearRect(0, 0, w, h);
  const left = 48, right = w - 20, top = 20, bottom = h - 32;
  ctx.strokeStyle = "#d6e2e7";
  ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(left, top); ctx.lineTo(left, bottom); ctx.lineTo(right, bottom); ctx.stroke();
  const valid = items.filter(item => Number.isFinite(item.flow_l_min));
  if (!valid.length) return;
  const t0 = items[0].t_s, t1 = items.at(-1).t_s;
  const values = valid.map(item => item.flow_l_min);
  const min = Math.max(0, Math.min(...values) - 0.5), max = Math.max(...values) + 0.5;
  const x = t => left + (right - left) * ((t - t0) / (t1 - t0 || 1));
  const y = q => bottom - (bottom - top) * ((q - min) / (max - min || 1));
  ctx.fillStyle = "#627783"; ctx.font = "13px system-ui";
  ctx.fillText(max.toFixed(1), 5, top + 5); ctx.fillText(min.toFixed(1), 5, bottom);
  ctx.fillText(t0.toFixed(1) + " s", left, h - 7);
  ctx.fillText(t1.toFixed(1) + " s", right - 50, h - 7);
  ctx.strokeStyle = "#087b83"; ctx.lineWidth = 3; ctx.beginPath();
  let drawing = false;
  for (const item of items) {
    if (!Number.isFinite(item.flow_l_min)) { drawing = false; continue; }
    if (drawing) ctx.lineTo(x(item.t_s), y(item.flow_l_min));
    else { ctx.moveTo(x(item.t_s), y(item.flow_l_min)); drawing = true; }
  }
  ctx.stroke();
}

async function refresh() {
  try {
    const response = await fetch("/api/telemetry?limit=120", { cache: "no-store" });
    if (!response.ok) throw new Error("Gateway unavailable");
    const payload = await response.json();
    const items = payload.items;
    if (!items.length) return;
    const current = items.at(-1);
    ids.flow.textContent = number(current.flow_l_min);
    ids.uncertainty.textContent = `Uncertainty: ${number(current.sigma_l_min)} L/min`;
    ids.confidence.textContent = current.confidence;
    ids.state.textContent = current.state;
    ids.mode.textContent = `Mode: ${current.mode}`;
    ids.source.textContent = current.source;
    ids.device.textContent = `Device: ${current.device_id}`;
    ids.samples.textContent = `${items.length} recent samples`;
    ids.updated.textContent = `Elapsed device time: ${number(current.t_s, 1)} s`;
    ids["chart-note"].textContent = items.some(i => i.flow_l_min === null)
      ? "Gaps indicate unavailable flow estimates." : "Recent simulator estimates.";
    ids.connection.textContent = "Connected";
    ids.connection.className = "pill ok";
    drawChart(items);
  } catch (error) {
    ids.connection.textContent = "Disconnected";
    ids.connection.className = "pill bad";
    ids.updated.textContent = "Last displayed reading may be stale";
  }
}

refresh();
setInterval(refresh, 1000);
