/**
 * RailGuard AI — Dashboard JavaScript
 * Connects to Flask SSE stream for live updates, manages charts,
 * renders threat list + alert log, and handles RPF modal dispatch.
 */

"use strict";

// ── State ─────────────────────────────────────────────────────────────────────
const state = {
  alerts:        [],
  tracked:       [],
  ramanHistory:  [],
  stats:         {},
  activeAlertId: null,   // alert open in modal
  alertFilter:   "ALL",
};

// ── Activity chart ring buffers ───────────────────────────────────────────────
const ACTIVITY_MAX_POINTS = 30;
const activityLabels = [];
const activityDataTotal    = [];
const activityDataWarning  = [];
const activityDataCritical = [];

// ── Chart instances ───────────────────────────────────────────────────────────
let activityChart, ramanChart, donutChart;

// ═════════════════════════════════════════════════════════════════════════════
//  CLOCK
// ═════════════════════════════════════════════════════════════════════════════
function updateClock() {
  const now = new Date();
  const str = now.toLocaleTimeString("en-IN", { hour12: false });
  document.getElementById("topbar-clock").textContent = str;
  document.getElementById("ov-time").textContent = str;
}
setInterval(updateClock, 1000);
updateClock();


// ═════════════════════════════════════════════════════════════════════════════
//  SSE – live data from Flask
// ═════════════════════════════════════════════════════════════════════════════
function connectSSE() {
  const es = new EventSource("/stream");

  es.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      applyPayload(payload);
    } catch (e) {
      console.error("SSE parse error", e);
    }
  };

  es.onerror = () => {
    console.warn("SSE connection lost — reconnecting in 3 s…");
    es.close();
    setTimeout(connectSSE, 3000);
  };
}

function applyPayload(payload) {
  const { stats, tracked, alerts, raman_history, new_alert } = payload;

  state.stats        = stats || {};
  state.tracked      = tracked || [];
  state.alerts       = alerts || [];
  state.ramanHistory = raman_history || [];

  // Stats cards
  updateStats(stats);

  // FPS
  document.getElementById("fps-val").textContent = stats.fps ?? 0;

  // Tracked objects panel
  renderTrackedList(state.tracked);

  // Alert log
  renderAlertLog(state.alerts);

  // Latest Raman result
  if (state.ramanHistory.length > 0) {
    renderRamanCard(state.ramanHistory[state.ramanHistory.length - 1]);
  }

  // Charts
  pushActivityPoint(stats);
  updateRamanChart(state.ramanHistory);
  updateDonutChart(stats);

  // Banner + toast for brand-new alerts
  if (new_alert) {
    const newest = state.alerts[state.alerts.length - 1];
    if (newest) showAlertBanner(newest);
    if (newest?.status === "CRITICAL") {
      showToast("Critical threat detected — " + newest.location, "error");
      playAlertSound();
    } else if (newest?.status === "WARNING") {
      showToast("Warning: unattended object at " + newest.location, "warn");
    }
  }
}


// ═════════════════════════════════════════════════════════════════════════════
//  STAT CARDS
// ═════════════════════════════════════════════════════════════════════════════
function updateStats(stats) {
  setTextAnimated("stat-total-objects", stats.total_objects   ?? 0);
  setTextAnimated("stat-warning",       stats.warning_objects ?? 0);
  setTextAnimated("stat-critical",      stats.critical_objects?? 0);
  setTextAnimated("stat-alerts",        stats.total_alerts    ?? 0);
  setTextAnimated("stat-raman-scans",   stats.raman_scans     ?? 0);
  setTextAnimated("stat-threats",       stats.threats_detected?? 0);
}

function setTextAnimated(id, value) {
  const el = document.getElementById(id);
  if (!el) return;
  const current = parseInt(el.textContent, 10) || 0;
  if (current !== value) {
    el.textContent = value;
    el.classList.remove("flash");
    void el.offsetWidth;   // reflow
    el.classList.add("flash");
  }
}


// ═════════════════════════════════════════════════════════════════════════════
//  TRACKED OBJECTS LIST
// ═════════════════════════════════════════════════════════════════════════════
function renderTrackedList(objects) {
  const container = document.getElementById("threat-list");
  const empty     = document.getElementById("threat-empty");
  const badge     = document.getElementById("tracked-count-badge");

  badge.textContent = `${objects.length} object${objects.length !== 1 ? "s" : ""}`;

  if (objects.length === 0) {
    container.innerHTML = "";
    container.appendChild(empty);
    return;
  }

  empty.remove();

  // Keep existing DOM items, add/update/remove as needed
  const existingIds = new Set(
    Array.from(container.querySelectorAll(".threat-item")).map(el => el.dataset.id)
  );
  const incomingIds = new Set(objects.map(o => String(o.id)));

  // Remove stale
  container.querySelectorAll(".threat-item").forEach(el => {
    if (!incomingIds.has(el.dataset.id)) el.remove();
  });

  objects.forEach(obj => {
    const statusLower = obj.status.toLowerCase();
    let el = container.querySelector(`.threat-item[data-id="${obj.id}"]`);

    if (!el) {
      el = document.createElement("div");
      el.className = "threat-item";
      el.dataset.id = obj.id;
      el.innerHTML = threatItemHTML(obj);
      container.appendChild(el);
    } else {
      // Update in place
      el.className = `threat-item threat-item--${statusLower}`;
      el.querySelector(".threat-item__status").textContent = obj.status;
      el.querySelector(".threat-item__status").className   = `threat-item__status threat-item__status--${statusLower}`;
      el.querySelector(".threat-item__timer").textContent  = obj.time_label;
      el.querySelector(".threat-item__conf").textContent   = `Conf: ${(obj.confidence * 100).toFixed(0)}%`;
      const bar = el.querySelector(".conf-bar");
      bar.style.width     = `${(obj.confidence * 100).toFixed(0)}%`;
      bar.className       = `conf-bar conf-bar--${statusLower}`;
    }
  });
}

function threatItemHTML(obj) {
  const statusLower = obj.status.toLowerCase();
  const confPct = (obj.confidence * 100).toFixed(0);
  return `
    <span class="threat-item__id">OBJ ${obj.id}</span>
    <div class="threat-item__info">
      <div class="threat-item__status threat-item__status--${statusLower}">${obj.status}</div>
      <div class="threat-item__timer">${obj.time_label}</div>
      <div class="threat-item__conf">Conf: ${confPct}%</div>
    </div>
    <div class="conf-bar-wrap">
      <div class="conf-bar conf-bar--${statusLower}" style="width:${confPct}%"></div>
    </div>`;
}


// ═════════════════════════════════════════════════════════════════════════════
//  RAMAN CARD
// ═════════════════════════════════════════════════════════════════════════════
function renderRamanCard(scan) {
  if (!scan) return;

  const card     = document.getElementById("raman-result-card");
  const badgeEl  = document.getElementById("raman-badge");
  const label    = scan.threat_label || "CLEAR";

  document.getElementById("raman-substance").textContent = scan.substance;
  document.getElementById("raman-snr").textContent       = scan.snr_db;
  document.getElementById("raman-conf").textContent      = `${(scan.confidence * 100).toFixed(0)}%`;
  document.getElementById("raman-time").textContent      = new Date(scan.timestamp * 1000)
    .toLocaleTimeString("en-IN", { hour12: false });
  document.getElementById("raman-desc").textContent      = scan.description;

  // Badge
  badgeEl.textContent  = label;
  badgeEl.className    = `raman-result__badge raman-result__badge--${label}`;

  // Card colour
  card.className = "raman-result " + (
    scan.risk_level >= 4 ? "raman-result--threat"   :
    scan.risk_level >= 2 ? "raman-result--moderate" :
                           "raman-result--clear"
  );

  // Peaks
  const peaksEl = document.getElementById("raman-peaks");
  peaksEl.innerHTML = (scan.peaks_found || [])
    .map(p => `<span class="raman-peak-chip">${p}</span>`)
    .join("");
}


// ═════════════════════════════════════════════════════════════════════════════
//  ALERT LOG
// ═════════════════════════════════════════════════════════════════════════════
function renderAlertLog(alerts) {
  const container = document.getElementById("alert-log");
  const empty     = document.getElementById("alert-empty");
  const filter    = state.alertFilter;

  let filtered = [...alerts].reverse();   // newest first
  if (filter === "CRITICAL")   filtered = filtered.filter(a => a.status === "CRITICAL");
  if (filter === "WARNING")    filtered = filtered.filter(a => a.status === "WARNING");
  if (filter === "UNACKED")    filtered = filtered.filter(a => !a.acknowledged);

  if (filtered.length === 0) {
    container.innerHTML = "";
    container.appendChild(empty);
    return;
  }
  empty.remove();

  const existingIds = new Set(
    Array.from(container.querySelectorAll(".alert-item")).map(el => el.dataset.alertId)
  );
  const incomingIds = new Set(filtered.map(a => a.alert_id));

  // Remove stale
  container.querySelectorAll(".alert-item").forEach(el => {
    if (!incomingIds.has(el.dataset.alertId)) el.remove();
  });

  filtered.forEach(alert => {
    let el = container.querySelector(`.alert-item[data-alert-id="${alert.alert_id}"]`);
    if (!el) {
      el = document.createElement("div");
      el.className = `alert-item alert-item--${alert.status.toLowerCase()}` +
                     (alert.acknowledged ? " alert-item--acked" : "");
      el.dataset.alertId = alert.alert_id;
      el.setAttribute("role", "button");
      el.setAttribute("tabindex", "0");
      el.innerHTML = alertItemHTML(alert);
      el.addEventListener("click", () => openModal(alert.alert_id));
      el.addEventListener("keydown", e => { if (e.key === "Enter") openModal(alert.alert_id); });
      container.insertAdjacentElement("afterbegin", el);
    } else if (alert.acknowledged && !el.classList.contains("alert-item--acked")) {
      el.classList.add("alert-item--acked");
      const ackEl = el.querySelector(".alert-item__ack");
      if (ackEl) ackEl.hidden = false;
    }
  });
}

function alertItemHTML(alert) {
  const ramanStr = alert.raman
    ? `<i class="fa-solid fa-flask-vial"></i> Raman: <b>${alert.raman.substance}</b> — ${alert.raman.threat_label}`
    : `<i class="fa-solid fa-flask-vial"></i> Raman: pending`;

  return `
    <div class="alert-item__row1">
      <span class="alert-item__id">#${alert.alert_id}</span>
      <span class="alert-item__status-tag alert-item__status-tag--${alert.status.toLowerCase()}">${alert.status}</span>
      <span class="alert-item__time">${alert.time_str}</span>
    </div>
    <div class="alert-item__location">
      <i class="fa-solid fa-location-dot"></i> ${alert.station} · ${alert.location}
    </div>
    <div class="alert-item__raman">${ramanStr}</div>
    <div class="alert-item__ack" ${alert.acknowledged ? "" : "hidden"}>
      <i class="fa-solid fa-check-double"></i> Acknowledged · RPF Notified
    </div>`;
}


// ═════════════════════════════════════════════════════════════════════════════
//  CHARTS
// ═════════════════════════════════════════════════════════════════════════════
const CHART_DEFAULTS = {
  responsive: true,
  maintainAspectRatio: false,
  animation: { duration: 400 },
  plugins: { legend: { display: false } },
};

function initCharts() {
  // Activity timeline
  activityChart = new Chart(document.getElementById("activity-chart"), {
    type: "line",
    data: {
      labels: activityLabels,
      datasets: [
        {
          label: "Total",
          data: activityDataTotal,
          borderColor: "#6b9fff",
          backgroundColor: "rgba(107,159,255,0.1)",
          fill: true, tension: 0.4, pointRadius: 0, borderWidth: 2,
        },
        {
          label: "Warning",
          data: activityDataWarning,
          borderColor: "#ff9100",
          backgroundColor: "rgba(255,145,0,0.08)",
          fill: true, tension: 0.4, pointRadius: 0, borderWidth: 2,
        },
        {
          label: "Critical",
          data: activityDataCritical,
          borderColor: "#ff1744",
          backgroundColor: "rgba(255,23,68,0.1)",
          fill: true, tension: 0.4, pointRadius: 0, borderWidth: 2,
        },
      ],
    },
    options: {
      ...CHART_DEFAULTS,
      plugins: {
        legend: {
          display: true,
          position: "top",
          labels: { color: "#8892a4", boxWidth: 10, font: { size: 10 } },
        },
        tooltip: { mode: "index", intersect: false },
      },
      scales: {
        x: { ticks: { color: "#4e5a70", font: { size: 9 } }, grid: { color: "#1e2535" } },
        y: { ticks: { color: "#4e5a70", stepSize: 1, font: { size: 9 } }, grid: { color: "#1e2535" }, min: 0 },
      },
    },
  });

  // Raman history bar
  ramanChart = new Chart(document.getElementById("raman-chart"), {
    type: "bar",
    data: {
      labels: [],
      datasets: [
        {
          label: "Risk Level",
          data: [],
          backgroundColor: [],
          borderRadius: 4,
        },
      ],
    },
    options: {
      ...CHART_DEFAULTS,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => {
              const labels = ["Clear", "Low", "Moderate", "High", "Critical", "Critical"];
              return ` Risk: ${labels[ctx.raw] ?? ctx.raw}`;
            },
          },
        },
      },
      scales: {
        x: { ticks: { color: "#4e5a70", font: { size: 9 }, maxRotation: 45 }, grid: { color: "#1e2535" } },
        y: { min: 0, max: 5, ticks: { color: "#4e5a70", stepSize: 1, font: { size: 9 } }, grid: { color: "#1e2535" } },
      },
    },
  });

  // Threat breakdown donut
  donutChart = new Chart(document.getElementById("threat-donut"), {
    type: "doughnut",
    data: {
      labels: ["Normal", "Warning", "Critical"],
      datasets: [{
        data: [0, 0, 0],
        backgroundColor: ["#00e676", "#ff9100", "#ff1744"],
        borderColor: "#111520",
        borderWidth: 3,
      }],
    },
    options: {
      ...CHART_DEFAULTS,
      cutout: "65%",
      plugins: {
        legend: {
          display: true, position: "bottom",
          labels: { color: "#8892a4", boxWidth: 10, font: { size: 10 } },
        },
      },
    },
  });
}

function pushActivityPoint(stats) {
  const now = new Date().toLocaleTimeString("en-IN", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
  activityLabels.push(now);
  activityDataTotal.push(stats.total_objects ?? 0);
  activityDataWarning.push(stats.warning_objects ?? 0);
  activityDataCritical.push(stats.critical_objects ?? 0);

  if (activityLabels.length > ACTIVITY_MAX_POINTS) {
    activityLabels.shift();
    activityDataTotal.shift();
    activityDataWarning.shift();
    activityDataCritical.shift();
  }
  activityChart.update("none");
}

function updateRamanChart(history) {
  const recent = history.slice(-20);
  const riskColors = ["#00e676", "#64dd17", "#ff9100", "#ff6d00", "#ff1744", "#ff1744"];

  ramanChart.data.labels = recent.map(r =>
    new Date(r.timestamp * 1000).toLocaleTimeString("en-IN", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" })
  );
  ramanChart.data.datasets[0].data            = recent.map(r => r.risk_level);
  ramanChart.data.datasets[0].backgroundColor = recent.map(r => riskColors[r.risk_level] ?? "#888");
  ramanChart.update("none");
}

function updateDonutChart(stats) {
  const normal   = Math.max(0, (stats.total_objects ?? 0) - (stats.warning_objects ?? 0) - (stats.critical_objects ?? 0));
  const warning  = stats.warning_objects  ?? 0;
  const critical = stats.critical_objects ?? 0;

  if (normal === 0 && warning === 0 && critical === 0) return;
  donutChart.data.datasets[0].data = [normal, warning, critical];
  donutChart.update("none");
}


// ═════════════════════════════════════════════════════════════════════════════
//  RPF MODAL
// ═════════════════════════════════════════════════════════════════════════════
function openModal(alertId) {
  const alert = state.alerts.find(a => a.alert_id === alertId);
  if (!alert) return;

  state.activeAlertId = alertId;

  // Basic fields
  document.getElementById("m-alert-id").textContent    = `#${alert.alert_id}`;
  document.getElementById("m-obj-id").textContent      = `OBJ-${alert.object_id}`;
  document.getElementById("m-status").textContent      = alert.status;
  document.getElementById("m-status").style.color      = alert.status === "CRITICAL" ? "var(--red)" : "var(--orange)";
  document.getElementById("m-confidence").textContent  = `${(alert.confidence * 100).toFixed(0)}%`;
  document.getElementById("m-location").textContent    = `${alert.station} · ${alert.location}`;
  document.getElementById("m-camera").textContent      = alert.camera_id;
  document.getElementById("m-timestamp").textContent   = `${alert.date_str}  ${alert.time_str}`;

  // Raman results
  const ramanBody  = document.getElementById("m-raman-body");
  const ramanEmpty = document.getElementById("m-raman-empty");
  if (alert.raman) {
    const r = alert.raman;
    ramanBody.hidden  = false;
    ramanEmpty.hidden = true;
    document.getElementById("m-raman-substance").textContent = r.substance;
    document.getElementById("m-raman-substance").style.color = r.color || "var(--text-primary)";
    document.getElementById("m-raman-category").textContent  = r.category;
    document.getElementById("m-raman-risk").textContent      = `Risk: ${r.risk_level}/5`;
    document.getElementById("m-raman-conf").textContent      = `Conf: ${(r.confidence * 100).toFixed(0)}%`;
    document.getElementById("m-raman-desc").textContent      = r.description;
    document.getElementById("m-raman-peaks").textContent     = (r.peaks_found || []).join(", ") + " cm⁻¹";
    document.getElementById("m-raman-snr").textContent       = r.snr_db;
    document.getElementById("m-raman-scan-time").textContent = r.scan_time_ms;
  } else {
    ramanBody.hidden  = true;
    ramanEmpty.hidden = false;
  }

  // RPF message preview
  document.getElementById("rpf-message-preview").textContent = buildRPFMessage(alert);

  // Show modal
  const backdrop = document.getElementById("rpf-modal-backdrop");
  backdrop.hidden = false;
  backdrop.querySelector(".modal__close").focus();
}

function closeModal() {
  document.getElementById("rpf-modal-backdrop").hidden = true;
  state.activeAlertId = null;
}

function acknowledgeFromModal() {
  const alertId = state.activeAlertId;
  if (!alertId) return;

  fetch(`/api/alerts/${alertId}/acknowledge`, { method: "POST" })
    .then(r => r.json())
    .then(data => {
      closeModal();
      if (data.ok) {
        showToast(`Alert #${alertId} acknowledged. RPF notified.`, "success");
      } else {
        showToast(data.message || "Failed to acknowledge.", "error");
      }
    })
    .catch(() => showToast("Network error — unable to reach server.", "error"));
}

function buildRPFMessage(alert) {
  const r = alert.raman;
  const ramanLine = r
    ? `CHEMICAL SCAN : ${r.substance} (${r.category}) — Risk ${r.risk_level}/5, Conf ${(r.confidence * 100).toFixed(0)}%`
    : `CHEMICAL SCAN : Pending`;

  return [
    `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`,
    `  ⚠  RPF ALERT DISPATCH — RailGuard AI`,
    `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`,
    `ALERT ID     : #${alert.alert_id}`,
    `STATUS       : ${alert.status}`,
    `STATION      : ${alert.station}`,
    `LOCATION     : ${alert.location}`,
    `CAMERA       : ${alert.camera_id}`,
    `TIME         : ${alert.date_str}  ${alert.time_str}`,
    `CONFIDENCE   : ${(alert.confidence * 100).toFixed(0)}%`,
    ``,
    ramanLine,
    ``,
    `ACTION REQUIRED: Please dispatch personnel to`,
    `${alert.location} IMMEDIATELY for inspection`,
    `and confirmation.`,
    `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`,
  ].join("\n");
}


// ═════════════════════════════════════════════════════════════════════════════
//  ALERT BANNER
// ═════════════════════════════════════════════════════════════════════════════
function showAlertBanner(alert) {
  const banner  = document.getElementById("alert-banner");
  const textEl  = document.getElementById("alert-banner-text");
  textEl.textContent = `${alert.status}: Unattended baggage detected — ${alert.station}, ${alert.location} [ID: #${alert.alert_id}]`;
  banner.classList.add("visible");
}

function dismissBanner() {
  document.getElementById("alert-banner").classList.remove("visible");
}


// ═════════════════════════════════════════════════════════════════════════════
//  FORCE RAMAN SCAN (demo buttons)
// ═════════════════════════════════════════════════════════════════════════════
function forceScan(substance) {
  fetch("/api/raman/force_scan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ substance }),
  })
    .then(r => r.json())
    .then(data => {
      if (data.ok) {
        renderRamanCard(data.result);
        const label = data.result.threat_label;
        const type  = data.result.is_threat ? (data.result.risk_level >= 4 ? "error" : "warn") : "success";
        showToast(`Raman scan: ${data.result.substance} — ${label}`, type);
      } else {
        showToast(data.message, "error");
      }
    })
    .catch(() => showToast("Scan request failed.", "error"));
}


// ═════════════════════════════════════════════════════════════════════════════
//  TOAST
// ═════════════════════════════════════════════════════════════════════════════
const TOAST_ICONS = { success: "fa-check-circle", warn: "fa-triangle-exclamation", error: "fa-circle-xmark", info: "fa-circle-info" };

function showToast(message, type = "info", duration = 4000) {
  const container = document.getElementById("toast-container");
  const toast     = document.createElement("div");
  toast.className = `toast toast--${type}`;
  toast.innerHTML = `<i class="fa-solid ${TOAST_ICONS[type] || "fa-circle-info"}"></i><span>${message}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity   = "0";
    toast.style.transform = "translateX(30px)";
    toast.style.transition = "all 0.3s";
    setTimeout(() => toast.remove(), 300);
  }, duration);
}


// ═════════════════════════════════════════════════════════════════════════════
//  ALERT SOUND (Web Audio API – soft beep)
// ═════════════════════════════════════════════════════════════════════════════
function playAlertSound() {
  try {
    const ctx  = new (window.AudioContext || window.webkitAudioContext)();
    const osc  = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type      = "square";
    osc.frequency.setValueAtTime(880, ctx.currentTime);
    osc.frequency.setValueAtTime(660, ctx.currentTime + 0.1);
    gain.gain.setValueAtTime(0.15, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.5);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.5);
  } catch (e) {
    // audio not available — silent fail
  }
}


// ═════════════════════════════════════════════════════════════════════════════
//  FULLSCREEN VIDEO
// ═════════════════════════════════════════════════════════════════════════════
document.getElementById("fullscreen-btn").addEventListener("click", () => {
  const panel = document.querySelector(".panel--video");
  const icon  = document.querySelector("#fullscreen-btn i");
  panel.classList.toggle("fullscreen");
  icon.className = panel.classList.contains("fullscreen")
    ? "fa-solid fa-compress"
    : "fa-solid fa-expand";
});


// ═════════════════════════════════════════════════════════════════════════════
//  ALERT FILTER
// ═════════════════════════════════════════════════════════════════════════════
document.getElementById("alert-filter").addEventListener("change", e => {
  state.alertFilter = e.target.value;
  renderAlertLog(state.alerts);
});


// ═════════════════════════════════════════════════════════════════════════════
//  MODAL KEYBOARD CLOSE
// ═════════════════════════════════════════════════════════════════════════════
document.addEventListener("keydown", e => {
  if (e.key === "Escape") closeModal();
});
document.getElementById("rpf-modal-backdrop").addEventListener("click", e => {
  if (e.target === e.currentTarget) closeModal();
});


// ═════════════════════════════════════════════════════════════════════════════
//  FLASH ANIMATION (stat cards)
// ═════════════════════════════════════════════════════════════════════════════
const flashStyle = document.createElement("style");
flashStyle.textContent = `
  @keyframes flashNum {
    0%   { opacity: 0.3; transform: scale(1.15); }
    100% { opacity: 1;   transform: scale(1); }
  }
  .flash { animation: flashNum 0.35s ease; }
`;
document.head.appendChild(flashStyle);


// ═════════════════════════════════════════════════════════════════════════════
//  INIT
// ═════════════════════════════════════════════════════════════════════════════
document.addEventListener("DOMContentLoaded", () => {
  initCharts();
  connectSSE();
  showToast("RailGuard AI dashboard connected", "info");
});
