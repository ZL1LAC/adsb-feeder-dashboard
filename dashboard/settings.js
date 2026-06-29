const SETTINGS_URL = "/dashboard/api/settings";
const STATUS_URL = "/dashboard/status.json";

const $ = (id) => document.getElementById(id);

function setStatus(id, message, ok) {
  const el = $(id);
  if (!el) return;
  el.textContent = message || "";
  el.className = `meta${ok === true ? " ok-text" : ok === false ? " bad-text" : ""}`;
}

async function apiGet(url) {
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

function fillAlerts(alerts) {
  $("gotify-url").value = alerts.gotify_url || "";
  $("gotify-app-token").value = alerts.gotify_app_token || "";
  $("alert-overhead-km").value = alerts.alert_overhead_km ?? 5;
  $("alert-overhead-ft").value = alerts.alert_overhead_ft ?? 3000;
}

function fillWatchlist(watchlist) {
  $("watchlist-callsigns").value = (watchlist.callsigns || []).join("\n");
  $("watchlist-hex").value = (watchlist.hex || []).join("\n");
}

function fillSquawk(squawk) {
  $("squawk-enabled").checked = squawk.enabled !== false;
  $("squawk-emergency").checked = squawk.emergency !== false;
  $("squawk-extra").value = (squawk.extra_codes || []).join("\n");
}

function readSquawkForm() {
  return {
    enabled: $("squawk-enabled").checked,
    emergency: $("squawk-emergency").checked,
    extra_codes: $("squawk-extra").value,
  };
}

function fillLocation(location) {
  $("location-lat").value = location.lat || "";
  $("location-lon").value = location.lon || "";
  $("location-alt").value = location.alt || "12m";
}

function readAlertsForm() {
  return {
    gotify_url: $("gotify-url").value.trim(),
    gotify_app_token: $("gotify-app-token").value.trim(),
    alert_overhead_km: Number($("alert-overhead-km").value),
    alert_overhead_ft: Number($("alert-overhead-ft").value),
  };
}

function readWatchlistForm() {
  return {
    callsigns: $("watchlist-callsigns").value,
    hex: $("watchlist-hex").value,
  };
}

function readLocationForm() {
  return {
    lat: $("location-lat").value.trim(),
    lon: $("location-lon").value.trim(),
    alt: $("location-alt").value.trim() || "12m",
  };
}

async function loadSettings() {
  const data = await apiGet(SETTINGS_URL);
  fillAlerts(data.alerts || {});
  fillSquawk(data.squawk || {});
  fillWatchlist(data.watchlist || {});
  fillLocation(data.location || {});

  if (!$("gotify-url").value) {
    const host = window.location.hostname;
    if (host && host !== "localhost") {
      $("gotify-url").placeholder = `http://${host}:8090`;
    }
  }

  try {
    const status = await apiGet(STATUS_URL);
    const gain = status.reception?.gain;
    if (gain) $("gain-input").placeholder = gain;
    const minutes = status.muninn?.interval_min;
    if (minutes) $("interval-select").value = String(minutes);
  } catch {
    // optional status enrichment
  }
}

async function saveAlerts(event) {
  event.preventDefault();
  setStatus("alerts-status", "Saving…", null);
  try {
    const data = await apiPost(SETTINGS_URL, { alerts: readAlertsForm() });
    fillAlerts(data.alerts || {});
    setStatus("alerts-status", "Alerts saved.", true);
  } catch (err) {
    setStatus("alerts-status", err.message, false);
  }
}

async function testAlert() {
  setStatus("alerts-status", "Sending test…", null);
  try {
    const data = await apiPost("/dashboard/api/settings/test-alert", {
      alerts: readAlertsForm(),
    });
    setStatus("alerts-status", data.summary || "Test sent.", true);
  } catch (err) {
    setStatus("alerts-status", err.message, false);
  }
}

async function checkGotify() {
  setStatus("alerts-status", "Checking Gotify…", null);
  try {
    const data = await apiPost("/dashboard/api/settings/gotify-check", {
      alerts: readAlertsForm(),
    });
    setStatus("alerts-status", data.summary || "Gotify OK.", true);
  } catch (err) {
    setStatus("alerts-status", err.message, false);
  }
}

async function saveSquawk(event) {
  event.preventDefault();
  setStatus("squawk-status", "Saving…", null);
  try {
    const data = await apiPost(SETTINGS_URL, { squawk: readSquawkForm() });
    fillSquawk(data.squawk || {});
    const codes = (data.squawk?.active_codes || []).join(", ") || "none";
    setStatus("squawk-status", `Squawk alerts saved. Watching: ${codes}`, true);
  } catch (err) {
    setStatus("squawk-status", err.message, false);
  }
}

async function saveWatchlist(event) {
  event.preventDefault();
  setStatus("watchlist-status", "Saving…", null);
  try {
    await apiPost(SETTINGS_URL, { watchlist: readWatchlistForm() });
    setStatus("watchlist-status", "Watchlist saved.", true);
  } catch (err) {
    setStatus("watchlist-status", err.message, false);
  }
}

async function saveLocation(event) {
  event.preventDefault();
  setStatus("location-status", "Updating location (restarts readsb)…", null);
  try {
    const data = await apiPost(SETTINGS_URL, { location: readLocationForm() });
    fillLocation(data.location || {});
    setStatus("location-status", data.location_summary || "Location saved.", true);
  } catch (err) {
    setStatus("location-status", err.message, false);
  }
}

async function applyGain(event) {
  event.preventDefault();
  const gain = $("gain-input").value.trim() || "auto";
  setStatus("gain-status", `Setting gain to ${gain}…`, null);
  try {
    const data = await apiPost("/dashboard/api/gain", { gain });
    setStatus("gain-status", data.summary || "Gain updated.", data.ok);
  } catch (err) {
    setStatus("gain-status", err.message, false);
  }
}

async function applyInterval(event) {
  event.preventDefault();
  const minutes = Number($("interval-select").value);
  setStatus("interval-status", `Setting interval to ${minutes} min…`, null);
  try {
    const data = await apiPost("/dashboard/api/muninn/interval", { minutes });
    setStatus("interval-status", data.summary || "Interval updated.", data.ok);
  } catch (err) {
    setStatus("interval-status", err.message, false);
  }
}

function init() {
  $("alerts-form")?.addEventListener("submit", saveAlerts);
  $("test-alert-btn")?.addEventListener("click", testAlert);
  $("check-gotify-btn")?.addEventListener("click", checkGotify);
  $("squawk-form")?.addEventListener("submit", saveSquawk);
  $("watchlist-form")?.addEventListener("submit", saveWatchlist);
  $("location-form")?.addEventListener("submit", saveLocation);
  $("gain-form")?.addEventListener("submit", applyGain);
  $("interval-form")?.addEventListener("submit", applyInterval);

  document.querySelectorAll(".preset-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      $("gain-input").value = btn.dataset.gain || "auto";
      applyGain(new Event("submit"));
    });
  });

  loadSettings().catch((err) => {
    setStatus("alerts-status", `Failed to load settings: ${err.message}`, false);
  });
}

init();
