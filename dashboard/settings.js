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

function setField(id, value) {
  const el = $(id);
  if (el) el.value = value;
}

function setChecked(id, checked) {
  const el = $(id);
  if (el) el.checked = checked;
}

function fillAlerts(alerts) {
  setField("gotify-url", alerts.gotify_url || "");
  const tokenInput = $("gotify-app-token");
  if (tokenInput) {
    tokenInput.value = "";
    tokenInput.placeholder = alerts.gotify_token_set
      ? "•••••••• (saved — paste to replace)"
      : "App token from Gotify → Apps";
  }
  setField("alert-overhead-km", alerts.alert_overhead_km ?? 5);
  setField("alert-overhead-ft", alerts.alert_overhead_ft ?? 3000);
  const hint = $("alerts-hint");
  if (hint) {
    hint.textContent = alerts.gotify_configured
      ? "Gotify is configured. Token is stored on the Pi (not shown)."
      : "Set Gotify URL and app token to enable push alerts.";
  }
}

function fillWatchlist(watchlist) {
  setField("watchlist-callsigns", (watchlist.callsigns || []).join("\n"));
  setField("watchlist-hex", (watchlist.hex || []).join("\n"));
}

function fillSquawk(squawk) {
  setChecked("squawk-enabled", squawk.enabled !== false);
  setChecked("squawk-emergency", squawk.emergency !== false);
  setField("squawk-extra", (squawk.extra_codes || []).join("\n"));
}

function fillWdgwars(wdg) {
  setChecked("wdgwars-enabled", !!wdg.enabled);
  setField("wdgwars-interval", String(wdg.upload_interval_min || 5));
  const keyInput = $("wdgwars-api-key");
  if (keyInput) {
    keyInput.value = "";
    keyInput.placeholder = wdg.api_key_set
      ? "•••••••• (saved — paste to replace)"
      : "Paste WDGoWars API key";
  }
  const hint = $("wdgwars-hint");
  if (hint) {
    if (wdg.configured) {
      hint.textContent = `Configured · uploads every ${wdg.upload_interval_min || 5} min${
        wdg.timer_active ? " (timer active)" : " (timer stopped)"
      }.`;
    } else if (wdg.api_key_set) {
      hint.textContent = "API key saved — enable uploads below.";
    } else {
      hint.textContent = "Paste your API key from wdgwars.pl → profile → API Key.";
    }
  }
}

function readSquawkForm() {
  return {
    enabled: $("squawk-enabled").checked,
    emergency: $("squawk-emergency").checked,
    extra_codes: $("squawk-extra").value,
  };
}

function fillLocation(location) {
  setField("location-lat", location.lat || "");
  setField("location-lon", location.lon || "");
  setField("location-alt", location.alt || "12m");
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

function readWdgwarsForm() {
  return {
    enabled: $("wdgwars-enabled").checked,
    upload_interval_min: Number($("wdgwars-interval").value),
  };
}

function setLoadStatus(message, ok) {
  const el = $("settings-load-status");
  if (!el) return;
  el.textContent = message || "";
  el.className = `subtitle${ok === true ? " ok-text" : ok === false ? " bad-text" : ""}`;
}

async function loadSettings() {
  setLoadStatus("Loading…", null);
  try {
    const data = await apiGet(SETTINGS_URL);
    fillAlerts(data.alerts || {});
    fillSquawk(data.squawk || {});
    fillWatchlist(data.watchlist || {});
    fillLocation(data.location || {});
    fillWdgwars(data.wdgwars || {});

    const gotifyUrl = $("gotify-url");
    if (gotifyUrl && !gotifyUrl.value) {
      const host = window.location.hostname;
      if (host && host !== "localhost") {
        gotifyUrl.placeholder = `http://${host}:8090`;
      }
    }

    try {
      const status = await apiGet(STATUS_URL);
      const gain = status.reception?.gain;
      if (gain) setField("gain-input", "");
      const gainInput = $("gain-input");
      if (gainInput && gain) gainInput.placeholder = String(gain);
    } catch {
      // optional status enrichment
    }

    if (typeof applyWdgNavVisibility === "function") {
      await applyWdgNavVisibility();
    }
    setLoadStatus("Settings loaded.", true);
  } catch (err) {
    setLoadStatus(`Failed to load settings: ${err.message}`, false);
    throw err;
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

async function testWdgKey() {
  setStatus("wdgwars-status", "Testing API key…", null);
  try {
    const key = $("wdgwars-api-key").value.trim();
    const data = await apiPost("/dashboard/api/muninn/test-key", key ? { key } : {});
    setStatus("wdgwars-status", data.summary || "API key OK.", true);
  } catch (err) {
    setStatus("wdgwars-status", err.message, false);
  }
}

async function saveWdgKey() {
  const key = $("wdgwars-api-key").value.trim();
  if (!key) {
    setStatus("wdgwars-status", "Paste an API key to save.", false);
    return;
  }
  setStatus("wdgwars-status", "Saving API key…", null);
  try {
    const data = await apiPost("/dashboard/api/muninn/save-key", { key });
    fillWdgwars(data.wdgwars || {});
    $("wdgwars-api-key").value = "";
    const extra = data.timer_summary ? ` ${data.timer_summary}` : "";
    setStatus("wdgwars-status", (data.summary || "Key saved.") + extra, true);
    if (typeof applyWdgNavVisibility === "function") {
      await applyWdgNavVisibility();
    }
  } catch (err) {
    setStatus("wdgwars-status", err.message, false);
  }
}

async function saveWdgwars(event) {
  event.preventDefault();
  setStatus("wdgwars-status", "Saving…", null);
  try {
    const data = await apiPost(SETTINGS_URL, { wdgwars: readWdgwarsForm() });
    fillWdgwars(data.wdgwars || {});
    const parts = ["WDGoWars settings saved."];
    if (data.wdgwars?.timer_active) {
      parts.push(`Uploads every ${data.wdgwars.upload_interval_min} min.`);
    } else if (!data.wdgwars?.enabled) {
      parts.push("Upload timer stopped.");
    }
    setStatus("wdgwars-status", parts.join(" "), true);
    if (typeof applyWdgNavVisibility === "function") {
      await applyWdgNavVisibility();
    }
  } catch (err) {
    setStatus("wdgwars-status", err.message, false);
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
  $("wdgwars-form")?.addEventListener("submit", saveWdgwars);
  $("wdgwars-test-key-btn")?.addEventListener("click", testWdgKey);
  $("wdgwars-save-key-btn")?.addEventListener("click", saveWdgKey);

  document.querySelectorAll(".preset-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      $("gain-input").value = btn.dataset.gain || "auto";
      applyGain(new Event("submit"));
    });
  });

  loadSettings().catch(() => {
    /* status shown in settings-load-status */
  });
}

init();
