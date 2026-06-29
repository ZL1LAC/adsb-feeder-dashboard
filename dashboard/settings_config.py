"""Read and write feeder dashboard settings (feeder.env + watchlist.json)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from feeder_paths import DASHBOARD_DIR, LOCATION_FILE, REPO_ROOT

ENV_FILE = REPO_ROOT / "feeder.env"
WATCHLIST_FILE = DASHBOARD_DIR / "watchlist.json"

ENV_KEYS = (
    "GOTIFY_URL",
    "GOTIFY_APP_TOKEN",
    "ALERT_OVERHEAD_KM",
    "ALERT_OVERHEAD_FT",
    "ALERT_SQUAWK_ENABLED",
    "ALERT_SQUAWK_EMERGENCY",
    "ALERT_SQUAWK_EXTRA",
)

DEPRECATED_ENV_KEYS = ("NTFY_SERVER", "NTFY_TOPIC", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
HEX_RE = re.compile(r"^[0-9a-fA-F]{6}$")


def read_env_values() -> dict[str, str]:
    values = {key: "" for key in ENV_KEYS}
    if not ENV_FILE.exists():
        return values
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key in values:
            values[key] = value.strip().strip('"').strip("'")
    return values


def write_env_values(updates: dict[str, str]) -> None:
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    touched: set[str] = set()
    out: list[str] = []
    skip_keys = set(DEPRECATED_ENV_KEYS)

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, _, _ = stripped.partition("=")
            key = key.strip()
            if key in skip_keys:
                continue
            if key in updates:
                out.append(f"{key}={updates[key]}")
                touched.add(key)
                continue
        if stripped.startswith("# ntfy") or stripped.startswith("# Telegram"):
            continue
        out.append(line)

    for key in ENV_KEYS:
        if key in updates and key not in touched:
            out.append(f"{key}={updates[key]}")

    ENV_FILE.write_text("\n".join(out) + ("\n" if out else ""), encoding="utf-8")


def read_watchlist() -> dict[str, list[str]]:
    if not WATCHLIST_FILE.exists():
        return {"callsigns": [], "hex": []}
    try:
        data = json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"callsigns": [], "hex": []}
    return {
        "callsigns": [str(c).strip().upper() for c in data.get("callsigns", []) if str(c).strip()],
        "hex": [str(h).strip().lower() for h in data.get("hex", []) if str(h).strip()],
    }


def write_watchlist(callsigns: list[str], hex_ids: list[str]) -> dict[str, list[str]]:
    payload = {
        "callsigns": callsigns,
        "hex": hex_ids,
    }
    WATCHLIST_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def read_location() -> dict:
    loc = {"lat": "", "lon": "", "alt": ""}
    if not LOCATION_FILE.exists():
        return loc
    for line in LOCATION_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("LATITUDE="):
            loc["lat"] = line.split("=", 1)[1].strip().strip('"')
        elif line.startswith("LONGITUDE="):
            loc["lon"] = line.split("=", 1)[1].strip().strip('"')
        elif line.startswith("ALTITUDE="):
            loc["alt"] = line.split("=", 1)[1].strip().strip('"')
    return loc


def parse_callsign_lines(raw: str) -> list[str]:
    items: list[str] = []
    for part in re.split(r"[\n,]+", raw or ""):
        value = part.strip().upper()
        if value and value not in items:
            items.append(value)
    return items


def parse_hex_lines(raw: str) -> list[str]:
    items: list[str] = []
    for part in re.split(r"[\n,\s]+", raw or ""):
        value = part.strip().lower().lstrip("#")
        if not value:
            continue
        if not HEX_RE.match(value):
            raise ValueError(f"invalid ICAO hex: {value} (use 6 hex digits)")
        if value not in items:
            items.append(value)
    return items


def validate_alerts(payload: dict) -> dict[str, str]:
    from notify import validate_gotify_config

    url = str(payload.get("gotify_url", "")).strip()
    app_token = str(payload.get("gotify_app_token", "")).strip()
    url, app_token = validate_gotify_config(url, app_token)

    try:
        km = float(payload.get("alert_overhead_km", 5))
        ft = float(payload.get("alert_overhead_ft", 3000))
    except (TypeError, ValueError) as exc:
        raise ValueError("overhead thresholds must be numbers") from exc
    if not (0.1 <= km <= 100):
        raise ValueError("overhead distance must be 0.1–100 km")
    if not (100 <= ft <= 50000):
        raise ValueError("overhead altitude must be 100–50000 ft")

    return {
        "GOTIFY_URL": url,
        "GOTIFY_APP_TOKEN": app_token,
        "ALERT_OVERHEAD_KM": str(km),
        "ALERT_OVERHEAD_FT": str(int(ft) if ft == int(ft) else ft),
    }


def validate_location(payload: dict) -> dict[str, str]:
    try:
        lat = float(str(payload.get("lat", "")).strip())
        lon = float(str(payload.get("lon", "")).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("latitude and longitude must be numbers") from exc
    if not (-90 <= lat <= 90):
        raise ValueError("latitude must be between -90 and 90")
    if not (-180 <= lon <= 180):
        raise ValueError("longitude must be between -180 and 180")
    alt = str(payload.get("alt", "12m")).strip() or "12m"
    return {"lat": str(lat), "lon": str(lon), "alt": alt}


def get_settings() -> dict:
    from squawk_alerts import squawk_settings_dict

    env = read_env_values()
    watchlist = read_watchlist()
    location = read_location()
    return {
        "ok": True,
        "alerts": {
            "gotify_url": env.get("GOTIFY_URL", ""),
            "gotify_app_token": env.get("GOTIFY_APP_TOKEN", ""),
            "gotify_configured": bool(
                env.get("GOTIFY_URL", "").strip() and env.get("GOTIFY_APP_TOKEN", "").strip()
            ),
            "alert_overhead_km": float(env.get("ALERT_OVERHEAD_KM") or 5),
            "alert_overhead_ft": float(env.get("ALERT_OVERHEAD_FT") or 3000),
        },
        "squawk": squawk_settings_dict(),
        "watchlist": watchlist,
        "location": location,
        "paths": {
            "feeder_env": str(ENV_FILE),
            "watchlist": str(WATCHLIST_FILE),
            "location_file": str(LOCATION_FILE),
        },
    }


def save_settings(body: dict) -> dict:
    saved: list[str] = []

    if "alerts" in body and body["alerts"] is not None:
        env_updates = validate_alerts(body["alerts"])
        write_env_values(env_updates)
        saved.append("alerts")

    if "watchlist" in body and body["watchlist"] is not None:
        wl = body["watchlist"]
        callsigns = wl.get("callsigns")
        hex_ids = wl.get("hex")
        if isinstance(callsigns, str):
            callsigns = parse_callsign_lines(callsigns)
        elif isinstance(callsigns, list):
            callsigns = parse_callsign_lines("\n".join(str(c) for c in callsigns))
        else:
            callsigns = []
        if isinstance(hex_ids, str):
            hex_ids = parse_hex_lines(hex_ids)
        elif isinstance(hex_ids, list):
            hex_ids = parse_hex_lines("\n".join(str(h) for h in hex_ids))
        else:
            hex_ids = []
        write_watchlist(callsigns, hex_ids)
        saved.append("watchlist")

    if "squawk" in body and body["squawk"] is not None:
        from squawk_alerts import validate_squawk_settings

        try:
            squawk_updates = validate_squawk_settings(body["squawk"])
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        write_env_values(squawk_updates)
        saved.append("squawk")

    result = get_settings()
    result["saved"] = saved
    return result
