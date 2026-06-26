const REFRESH_MS = 5000;
const STATUS_URL = "/dashboard/status.json";
const HISTORY_URL = "/dashboard/history.json";
const WHOAMI_TTL_MS = 5 * 60 * 1000;

let whoamiCache = { at: 0, data: null };
let aircraftState = {
  list: [],
  loc: null,
  query: "",
  sortKey: "seen",
  sortAsc: true,
};

const MUNINN_NOISE = [
  "dump1090 network input port",
  "port 30104",
  "port 30001",
  "Remote aircraft data may be mixing",
  "If you see aircraft far outside",
  "Fix: restart dump1090",
];

const $ = (id) => document.getElementById(id);

function setText(id, value) {
  const el = $(id);
  if (el) el.textContent = value;
}

function setHtml(id, value) {
  const el = $(id);
  if (el) el.innerHTML = value;
}

function pill(state) {
  const s = (state || "").toLowerCase();
  if (s === "active") return '<span class="pill ok">active</span>';
  if (s === "activating") return '<span class="pill warn">starting</span>';
  if (s === "connected" || s === true) return '<span class="pill ok">connected</span>';
  if (s === false) return '<span class="pill bad">down</span>';
  return `<span class="pill bad">${state || "unknown"}</span>`;
}

function fmtAlt(a) {
  if (a.alt_baro != null) return `${a.alt_baro} ft`;
  if (a.alt_geom != null) return `${a.alt_geom} ft`;
  return "—";
}

function fmtCoord(v) {
  return v != null ? Number(v).toFixed(4) : "—";
}

function aircraftType(a) {
  if (a.lat != null && a.lon != null) return '<span class="badge ads-b">ADS-B</span>';
  return '<span class="badge mode-s">Mode-S</span>';
}

function filterLogLines(lines) {
  return (lines || []).filter((ln) => !MUNINN_NOISE.some((n) => ln.includes(n)));
}

function highlightLog(text) {
  return text
    .split("\n")
    .map((line) => {
      if (/upload accepted/i.test(line)) return `<span class="log-ok">${line}</span>`;
      if (/nothing to upload|skip:|ERROR|failed/i.test(line)) return `<span class="log-warn">${line}</span>`;
      return line;
    })
    .join("\n");
}

function renderServices(services) {
  const labels = {
    readsb: "readsb (SDR)",
    tar1090: "tar1090 (web map)",
    airplanes_feed: "airplanes.live feed",
    airplanes_mlat: "airplanes.live MLAT",
    muninn: "WDGoWars uploader",
  };
  return Object.entries(services)
    .map(([k, v]) => `<li><span>${labels[k] || k}</span>${pill(v)}</li>`)
    .join("");
}

function renderFeeds(feeds, sdrOk) {
  const sdrPill = sdrOk ? pill("connected") : pill(false);
  return [
    `<li><span>SDR dongle</span>${sdrPill}</li>`,
    `<li><span>airplanes.live beast</span>${pill(feeds.airplanes_live ? "connected" : false)}</li>`,
    `<li><span>airplanes.live MLAT</span>${pill(feeds.airplanes_mlat ? "connected" : false)}</li>`,
  ].join("");
}

function haversineM(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const p = Math.PI / 180;
  const a =
    Math.sin(((lat2 - lat1) * p) / 2) ** 2 +
    Math.cos(lat1 * p) * Math.cos(lat2 * p) * Math.sin(((lon2 - lon1) * p) / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

function aircraftDistance(a, loc) {
  if (!loc?.lat || !loc?.lon || a.lat == null || a.lon == null) return null;
  const lat = Number(loc.lat);
  const lon = Number(loc.lon);
  if (Number.isNaN(lat) || Number.isNaN(lon)) return null;
  return haversineM(lat, lon, a.lat, a.lon);
}

function maxDistFromAircraft(aircraft, loc) {
  let max = 0;
  for (const a of aircraft) {
    const d = aircraftDistance(a, loc);
    if (d != null) max = Math.max(max, d);
  }
  return max > 0 ? max : null;
}

function matchesSearch(a, query) {
  if (!query) return true;
  const q = query.toLowerCase();
  const hex = (a.hex || "").toLowerCase();
  const flight = (a.flight || "").trim().toLowerCase();
  return hex.includes(q) || flight.includes(q);
}

function sortAircraft(list, key, asc, loc) {
  const dir = asc ? 1 : -1;
  return list.slice().sort((a, b) => {
    let av;
    let bv;
    switch (key) {
      case "hex":
        av = (a.hex || "").toUpperCase();
        bv = (b.hex || "").toUpperCase();
        return av.localeCompare(bv) * dir;
      case "flight":
        av = (a.flight || "").trim().toUpperCase();
        bv = (b.flight || "").trim().toUpperCase();
        return av.localeCompare(bv) * dir;
      case "rssi":
        av = a.rssi ?? -999;
        bv = b.rssi ?? -999;
        return (av - bv) * dir;
      case "dist":
        av = aircraftDistance(a, loc) ?? 1e12;
        bv = aircraftDistance(b, loc) ?? 1e12;
        return (av - bv) * dir;
      case "seen":
      default:
        av = a.seen ?? 9999;
        bv = b.seen ?? 9999;
        return (av - bv) * dir;
    }
  });
}

function renderAircraftTable() {
  const { list, loc, query, sortKey, sortAsc } = aircraftState;
  const filtered = list.filter((a) => matchesSearch(a, query));
  const sorted = sortAircraft(filtered, sortKey, sortAsc, loc);
  setText(
    "aircraft-count",
    list.length ? `Showing ${sorted.length} of ${list.length}` : ""
  );
  if (!sorted.length) {
    setHtml(
      "aircraft-rows",
      `<tr><td colspan="10" class="empty">${query ? "No matches" : "No aircraft right now"}</td></tr>`
    );
    return;
  }
  setHtml(
    "aircraft-rows",
    sorted
      .map((a) => {
        const flight = (a.flight || "").trim() || "—";
        const gs = a.gs != null ? `${a.gs.toFixed ? a.gs.toFixed(0) : a.gs} kt` : "—";
        const distM = aircraftDistance(a, loc);
        const dist = distM != null ? `${(distM / 1000).toFixed(0)} km` : "—";
        const rssi = a.rssi != null ? a.rssi.toFixed(1) : "—";
        const seen = a.seen != null ? `${a.seen.toFixed(0)}s` : "—";
        return `<tr>
        <td>${(a.hex || "").toUpperCase()}</td>
        <td>${flight}</td>
        <td>${aircraftType(a)}</td>
        <td class="col-hide-sm">${fmtCoord(a.lat)}</td>
        <td class="col-hide-sm">${fmtCoord(a.lon)}</td>
        <td class="col-hide-sm">${dist}</td>
        <td class="col-hide-sm">${fmtAlt(a)}</td>
        <td class="col-hide-md">${gs}</td>
        <td>${rssi}</td>
        <td>${seen}</td>
      </tr>`;
      })
      .join("")
  );
}

function updateSortHeaders() {
  document.querySelectorAll("th.sortable").forEach((th) => {
    th.classList.toggle("sort-active", th.dataset.sort === aircraftState.sortKey);
    th.classList.toggle("sort-desc", th.dataset.sort === aircraftState.sortKey && !aircraftState.sortAsc);
  });
}

function snrClass(snr) {
  if (snr == null || Number.isNaN(Number(snr))) return "";
  const n = Number(snr);
  if (n > 15) return "snr-good";
  if (n >= 5) return "snr-warn";
  return "snr-bad";
}

function renderSnrHealth(snr, maxDist, positionedCount = 0) {
  const el = $("snr-health");
  if (!el) return;
  const cls = snrClass(snr);
  const hasRange = (maxDist != null && maxDist > 0) || positionedCount > 0;
  let tip = "";
  if (snr != null && Number(snr) < 5) {
    tip = "Low SNR — check antenna cable, reduce nearby interference, try a lower gain preset.";
  } else if (!hasRange) {
    tip = "No range yet — ensure the antenna has clear sky view and readsb is receiving.";
  } else if (snr != null && Number(snr) < 15) {
    tip = "Moderate SNR — fine for testing; higher gain or better placement may help.";
  } else {
    tip = "Reception looks healthy. View coverage on the live map.";
  }
  const label =
    cls === "snr-good" ? "Good" : cls === "snr-warn" ? "Fair" : cls === "snr-bad" ? "Poor" : "Unknown";
  el.innerHTML = `<div class="snr-bar ${cls}">
    <span class="snr-status">${label}</span>
    <span class="snr-tip">${tip} <a href="/tar1090/" target="_blank">Range map</a></span>
  </div>`;
  const snrEl = $("snr");
  if (snrEl) {
    snrEl.classList.remove("snr-good", "snr-warn", "snr-bad");
    if (cls) snrEl.classList.add(cls);
  }
}

function healthChip(label, ok, warn, targetId) {
  const cls = ok ? "ok" : warn ? "warn" : "bad";
  const scroll = !ok && targetId ? ` data-scroll="${targetId}"` : "";
  return `<button type="button" class="health-chip ${cls}"${scroll} title="${label}">${label}</button>`;
}

function renderHealthBanner(status) {
  const el = $("health-banner");
  if (!el) return;
  const services = status.services || {};
  const feeds = status.feeds || {};
  const muninn = status.muninn || {};

  const sdrOk = status.sdr_ok !== false;
  const readsbState = (services.readsb || "").toLowerCase();
  const readsbOk = readsbState === "active";
  const readsbWarn = readsbState === "activating";
  const feedsOk = feeds.airplanes_live && feeds.airplanes_mlat;
  const muninnTimer = (services.muninn || "").toLowerCase() === "active";
  const wdgOk = muninn.last_ok !== false && muninnTimer;

  el.innerHTML = [
    healthChip("SDR", sdrOk, false, "feeds-card"),
    healthChip("readsb", readsbOk, readsbWarn, "services-card"),
    healthChip("Feeds", feedsOk, false, "feeds-card"),
    healthChip("WDGoWars", wdgOk, muninn.last_ok == null && muninnTimer, "wdg-card"),
  ].join("");
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

function shortSummary(text) {
  if (!text || text === "—") return "—";
  const s = text.replace(/\s+/g, " ").trim();
  if (s.length <= 72) return s;
  return `${s.slice(0, 69)}…`;
}

function uploadDotClass(entry) {
  const s = (entry.summary || "").toLowerCase();
  if (entry.ok === false || /error|failed/.test(s)) return "bad";
  if (/skip:|nothing to upload/.test(s)) return "warn";
  if (/upload accepted/.test(s) || entry.ok === true) return "ok";
  return "warn";
}

function renderUploadTimeline(recent) {
  const el = $("upload-timeline");
  if (!el) return;
  const items = (recent || []).slice().reverse();
  if (!items.length) {
    el.innerHTML = '<span class="timeline-empty">No uploads yet</span>';
    return;
  }
  el.innerHTML = items
    .map((r) => {
      const cls = uploadDotClass(r);
      const tip = `${fmtTime(r.time)}: ${r.summary || "—"}`;
      return `<span class="timeline-dot ${cls}" title="${tip.replace(/"/g, "&quot;")}"></span>`;
    })
    .join("");
}

function highlightGainPreset(currentGain) {
  const g = String(currentGain || "auto").toLowerCase();
  document.querySelectorAll(".preset-btn").forEach((btn) => {
    const match = String(btn.dataset.gain || "").toLowerCase() === g;
    btn.classList.toggle("preset-active", match);
  });
}

async function loadWhoami(force = false) {
  const now = Date.now();
  if (!force && whoamiCache.data && now - whoamiCache.at < WHOAMI_TTL_MS) {
    renderWhoami(whoamiCache.data);
    return;
  }
  try {
    const data = await fetchJson("/dashboard/api/whoami");
    whoamiCache = { at: now, data };
    renderWhoami(data);
  } catch {
    renderWhoami(whoamiCache.data);
  }
}

function fmtUptime(isoOrRaw) {
  if (!isoOrRaw) return "";
  const d = new Date(isoOrRaw);
  if (!Number.isNaN(d.getTime())) {
    return `readsb since ${d.toLocaleString()}`;
  }
  return `readsb since ${isoOrRaw}`;
}

function fmtTime(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function renderRecent(recent) {
  return "";
}

async function fetchJson(url) {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`${url} returned ${res.status}`);
  return res.json();
}

async function apiPost(path, body) {
  const opts = { method: "POST", body: body ?? "" };
  if (body && typeof body === "object") {
    opts.headers = { "Content-Type": "application/json" };
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  const data = await res.json();
  if (!res.ok && !data.summary) {
    throw new Error(data.error || `HTTP ${res.status}`);
  }
  return data;
}

async function refresh() {
  try {
    const [aircraft, stats, status, receiver] = await Promise.all([
      fetchJson("/tar1090/data/aircraft.json"),
      fetchJson("/tar1090/data/stats.json"),
      fetchJson(STATUS_URL),
      fetchJson("/tar1090/data/receiver.json").catch(() => ({})),
    ]);

    const list = aircraft.aircraft || [];
    const positioned = list.filter((a) => a.lat != null && a.lon != null);
    const reception = status.reception || {};

    renderHealthBanner(status);

    setText("aircraft-total", list.length);
    setText("aircraft-positioned", positioned.length);
    setText(
      "messages",
      aircraft.messages ?? stats.total?.messages ?? reception.messages ?? "—"
    );

    const snr =
      reception.snr ??
      (reception.signal != null && reception.noise != null
        ? (reception.signal - reception.noise).toFixed(1)
        : null);
    setText("snr", snr != null ? snr : "—");
    const gain = reception.gain ?? "—";
    setText("gain", gain);
    highlightGainPreset(gain);
    const gainInput = $("gain-input");
    if (gainInput) gainInput.placeholder = reception.gain ?? "36 or auto";

    const maxDist =
      reception.max_distance ?? stats.total?.max_distance ?? maxDistFromAircraft(list, status.location);
    setText(
      "max-range",
      maxDist != null && maxDist > 0 ? `${(maxDist / 1000).toFixed(0)} km` : "—"
    );

    renderSnrHealth(snr, maxDist, positioned.length);

    const uptime = fmtUptime(status.uptime?.readsb);
    const version = receiver.version ? ` · ${receiver.version}` : "";
    setText("readsb-meta", [uptime, version].filter(Boolean).join(""));

    const loc = status.location || {};
    const locStr =
      loc.lat && loc.lon ? `${loc.lat}, ${loc.lon}${loc.alt ? ` · ${loc.alt}` : ""}` : "";
    setText(
      "host-line",
      [status.hostname, locStr, loc.user ? `feeder ${loc.user.slice(0, 8)}…` : ""]
        .filter(Boolean)
        .join(" · ")
    );

    setHtml("services", renderServices(status.services || {}));
    setHtml("feeds", renderFeeds(status.feeds || {}, status.sdr_ok !== false));
    setText("sdr-line", status.sdr ? `USB: ${status.sdr}` : "USB: SDR not detected");

    const recovery = status.watch?.last_recovery;
    setText("recovery-line", recovery ? `Auto-recovered readsb at ${fmtTime(recovery)}` : "");

    aircraftState.list = list;
    aircraftState.loc = loc;
    renderAircraftTable();
    updateSortHeaders();

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
    setText("wdg-next", `Next${nextIn}${muninn.next_run ? ` · ${nextRun}` : ""}`);
    const intervalSelect = $("interval-select");
    if (intervalSelect && muninn.interval_min) {
      intervalSelect.value = String(muninn.interval_min);
    }
    renderUploadTimeline(muninn.recent);

    loadWhoami();

    try {
      const history = await fetchJson(HISTORY_URL);
      if (typeof renderHistoryCharts === "function") {
        renderHistoryCharts(history);
      }
    } catch {
      if (typeof renderHistoryCharts === "function") {
        renderHistoryCharts([]);
      }
    }

    const logLines = filterLogLines(status.muninn_log);
    const logEl = $("muninn-log");
    if (logEl) {
      if (logLines.length) {
        logEl.innerHTML = highlightLog(logLines.join("\n"));
      } else {
        logEl.textContent = "No uploads yet.";
      }
    }

    const when = status.updated
      ? new Date(status.updated).toLocaleString()
      : new Date().toLocaleString();
    setText("updated", `Last refresh: ${when}`);
  } catch (err) {
    setText("updated", `Refresh error: ${err.message}`);
  }
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
    statusEl.textContent = data.summary || "Done";
    statusEl.className = `push-status ${data.ok ? "ok" : "bad"}`;
    if (data.output?.length) {
      const logEl = $("muninn-log");
      if (logEl) {
        logEl.innerHTML = highlightLog(filterLogLines(data.output).join("\n"));
      }
    }
    await refresh();
    await loadWhoami(true);
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.className = "push-status bad";
  } finally {
    btn.disabled = false;
  }
}

async function runOp(path, label) {
  const el = $("ops-status");
  if (!el) return;
  el.textContent = `${label}…`;
  el.className = "meta pending";
  try {
    const data = await apiPost(path);
    el.textContent = data.summary || "Done";
    el.className = `meta ${data.ok ? "ok-text" : "bad-text"}`;
    await refresh();
  } catch (err) {
    el.textContent = err.message;
    el.className = "meta bad-text";
  }
}

async function applyGain() {
  const gainInput = $("gain-input");
  const el = $("ops-status");
  if (!gainInput || !el) return;
  const gain = gainInput.value.trim() || "auto";
  el.textContent = `Setting gain to ${gain}…`;
  el.className = "meta pending";
  try {
    const data = await apiPost("/dashboard/api/gain", { gain });
    el.textContent = data.summary || "Gain updated";
    el.className = `meta ${data.ok ? "ok-text" : "bad-text"}`;
    await refresh();
  } catch (err) {
    el.textContent = err.message;
    el.className = "meta bad-text";
  }
}

async function applyGainValue(gain) {
  const gainInput = $("gain-input");
  if (gainInput) gainInput.value = gain;
  await applyGain();
}

async function applyInterval() {
  const select = $("interval-select");
  const el = $("interval-status");
  if (!select || !el) return;
  const minutes = Number(select.value);
  el.textContent = `Setting interval to ${minutes} min…`;
  el.className = "meta pending";
  try {
    const data = await apiPost("/dashboard/api/muninn/interval", { minutes });
    el.textContent = data.summary || "Interval updated";
    el.className = `meta ${data.ok ? "ok-text" : "bad-text"}`;
    await refresh();
  } catch (err) {
    el.textContent = err.message;
    el.className = "meta bad-text";
  }
}

function initCollapsibles() {
  const mobile = window.matchMedia("(max-width: 700px)");
  const applyMobileDefault = () => {
    document.querySelectorAll(".collapsible").forEach((card) => {
      const body = card.querySelector(".collapse-body");
      const btn = card.querySelector(".collapse-btn");
      if (!body || !btn) return;
      if (mobile.matches) {
        card.classList.add("is-collapsed");
        btn.setAttribute("aria-expanded", "false");
        btn.textContent = "Show";
      } else if (!card.dataset.userToggled) {
        card.classList.remove("is-collapsed");
        btn.setAttribute("aria-expanded", "true");
        btn.textContent = "Hide";
      }
    });
  };
  applyMobileDefault();
  mobile.addEventListener("change", applyMobileDefault);

  document.querySelectorAll(".collapse-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const card = btn.closest(".collapsible");
      if (!card) return;
      card.dataset.userToggled = "1";
      const collapsed = card.classList.toggle("is-collapsed");
      btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
      btn.textContent = collapsed ? "Show" : "Hide";
    });
  });
}

function init() {
  $("push-btn")?.addEventListener("click", manualPush);
  $("restart-readsb-btn")?.addEventListener("click", () =>
    runOp("/dashboard/api/restart/readsb", "Restarting readsb")
  );
  $("restart-all-btn")?.addEventListener("click", () =>
    runOp("/dashboard/api/restart/all", "Restarting all services")
  );
  $("gain-btn")?.addEventListener("click", applyGain);
  $("interval-btn")?.addEventListener("click", applyInterval);
  document.querySelectorAll(".preset-btn").forEach((btn) => {
    btn.addEventListener("click", () => applyGainValue(btn.dataset.gain || "auto"));
  });

  $("health-banner")?.addEventListener("click", (e) => {
    const chip = e.target.closest("[data-scroll]");
    if (!chip) return;
    const target = document.getElementById(chip.dataset.scroll);
    target?.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  $("aircraft-search")?.addEventListener("input", (e) => {
    aircraftState.query = e.target.value.trim();
    renderAircraftTable();
  });

  document.querySelectorAll("th.sortable").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (aircraftState.sortKey === key) {
        aircraftState.sortAsc = !aircraftState.sortAsc;
      } else {
        aircraftState.sortKey = key;
        aircraftState.sortAsc = key === "flight" || key === "hex";
      }
      renderAircraftTable();
      updateSortHeaders();
    });
  });

  initCollapsibles();
  refresh();
  setInterval(refresh, REFRESH_MS);
}

init();
