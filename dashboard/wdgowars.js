const STATUS_URL = "/dashboard/status.json";
const WHOAMI_URL = "/dashboard/api/whoami";
const HISTORY_URL = "/dashboard/api/muninn/history";
const REFRESH_MS = 5000;
const WHOAMI_TTL_MS = 5 * 60 * 1000;

const $ = (id) => document.getElementById(id);
let whoamiCache = { at: 0, data: null };

function setText(id, value) {
  const el = $(id);
  if (el) el.textContent = value;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function fmtTime(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function shortSummary(text) {
  const s = String(text || "").trim();
  if (s.length <= 80) return s;
  return `${s.slice(0, 77)}…`;
}

async function fetchJson(url) {
  const res = await fetch(url, { cache: "no-store" });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

async function apiPost(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  const data = await res.json();
  if (!res.ok && !data.summary) {
    throw new Error(data.error || `HTTP ${res.status}`);
  }
  return data;
}

function renderWhoami(data) {
  if (!data?.ok) {
    setText("wdg-user", data?.user || "—");
    setText("wdg-aircraft-score", "—");
    setText("wdg-total-score", "—");
    setText("wdg-wifi-score", "—");
    setText("wdg-ble-score", "—");
    return;
  }
  setText("wdg-user", data.user || "—");
  setText("wdg-aircraft-score", data.aircraft != null ? data.aircraft.toLocaleString() : "—");
  setText("wdg-total-score", data.total != null ? data.total.toLocaleString() : "—");
  setText("wdg-wifi-score", data.wifi != null ? data.wifi.toLocaleString() : "—");
  setText("wdg-ble-score", data.ble != null ? data.ble.toLocaleString() : "—");
}

async function loadWhoami(force = false) {
  const now = Date.now();
  if (!force && whoamiCache.data && now - whoamiCache.at < WHOAMI_TTL_MS) {
    renderWhoami(whoamiCache.data);
    return;
  }
  try {
    const data = await fetchJson(WHOAMI_URL);
    whoamiCache = { at: now, data };
    renderWhoami(data);
  } catch {
    renderWhoami(whoamiCache.data);
  }
}

function historyResultClass(entry) {
  const s = String(entry.summary || "").toLowerCase();
  if (/skip|nothing to upload/.test(s)) return "warn";
  if (entry.ok === true || /upload accepted/.test(s)) return "ok";
  return "bad";
}

function historyResultLabel(entry) {
  const cls = historyResultClass(entry);
  if (cls === "ok") return "OK";
  if (cls === "warn") return "Skip";
  return "Fail";
}

function renderHistory(data) {
  const body = $("history-rows");
  const statsEl = $("history-stats");
  if (!body) return;

  const stats = data.stats_24h || {};
  if (statsEl) {
    statsEl.textContent = `Last 24h: ${stats.ok ?? 0} OK · ${stats.skip ?? 0} skipped · ${stats.fail ?? 0} failed`;
  }

  const entries = data.entries || [];
  if (!entries.length) {
    body.innerHTML = '<tr><td colspan="3" class="empty">No uploads yet</td></tr>';
    return;
  }

  body.innerHTML = entries
    .map((entry) => {
      const cls = historyResultClass(entry);
      const label = historyResultLabel(entry);
      return `<tr>
        <td>${escapeHtml(fmtTime(entry.time))}</td>
        <td><span class="pill ${cls}">${label}</span></td>
        <td>${escapeHtml(entry.summary || "—")}</td>
      </tr>`;
    })
    .join("");
}

function renderMuninnStatus(status) {
  const muninn = status.muninn || {};
  const summaryEl = $("wdg-summary");
  const summary = shortSummary(muninn.last_summary || "—");
  if (summaryEl) {
    summaryEl.textContent = summary;
    summaryEl.title = muninn.last_summary || "";
    summaryEl.className = `wdg-summary-line${muninn.last_ok === false ? " bad-text" : ""}`;
  }
  const nextRun = muninn.next_run ? fmtTime(muninn.next_run) : "—";
  const nextIn = muninn.next_run_in ? ` in ${muninn.next_run_in}` : "";
  setText("wdg-next", `Next scheduled upload${nextIn}${muninn.next_run ? ` · ${nextRun}` : ""}`);

  const logEl = $("muninn-log");
  if (logEl) {
    const lines = (status.muninn_log || []).filter(Boolean);
    if (lines.length) {
      logEl.textContent = lines.join("\n");
    } else {
      logEl.textContent = "No uploads yet.";
    }
  }
}

async function refresh() {
  try {
    const [status, history] = await Promise.all([
      fetchJson(STATUS_URL),
      fetchJson(HISTORY_URL),
    ]);
    renderMuninnStatus(status);
    renderHistory(history);
    setText("updated", `Updated ${new Date().toLocaleTimeString()}`);
  } catch (err) {
    setText("updated", `Refresh failed: ${err.message}`);
  }
  loadWhoami();
}

async function manualPush() {
  const btn = $("push-btn");
  const statusEl = $("push-status");
  if (!btn || !statusEl) return;
  btn.disabled = true;
  statusEl.textContent = "Uploading…";
  statusEl.className = "push-status pending";
  try {
    const data = await apiPost("/dashboard/api/push");
    statusEl.textContent = data.summary || (data.ok ? "Done" : "Failed");
    statusEl.className = `push-status ${data.ok ? "ok" : "bad"}`;
    await refresh();
    await loadWhoami(true);
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.className = "push-status bad";
  } finally {
    btn.disabled = false;
  }
}

function initCollapsibles() {
  document.querySelectorAll(".collapse-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = document.getElementById(btn.dataset.target);
      if (!target) return;
      const expanded = btn.getAttribute("aria-expanded") === "true";
      btn.setAttribute("aria-expanded", String(!expanded));
      btn.textContent = expanded ? "Show" : "Hide";
      target.classList.toggle("collapsed", expanded);
    });
  });
}

async function init() {
  const wdg = await applyWdgNavVisibility();
  const configured = wdg?.configured === true;

  if (!configured) {
    $("wdg-main").hidden = true;
    $("wdg-setup").hidden = false;
    return;
  }

  $("wdg-main").hidden = false;
  $("wdg-setup").hidden = true;

  $("push-btn")?.addEventListener("click", manualPush);
  initCollapsibles();
  await refresh();
  setInterval(refresh, REFRESH_MS);
}

init();
