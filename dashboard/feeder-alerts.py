#!/usr/bin/env python3
"""Send alerts for squawks, watchlist, overhead aircraft, and feeder health."""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

from feeder_paths import AIRCRAFT_JSON, ALERT_STATE, DASHBOARD_DIR, STATUS_JSON
from notify import alerts_enabled, send_alert
from squawk_alerts import EMERGENCY_SQUAWKS, load_squawk_codes, squawk_label, squawk_priority

STATE_FILE = ALERT_STATE
WATCHLIST_FILE = DASHBOARD_DIR / "watchlist.json"
STATUS_FILE = STATUS_JSON

OVERHEAD_KM = float(os.environ.get("ALERT_OVERHEAD_KM", "5"))
OVERHEAD_FT = float(os.environ.get("ALERT_OVERHEAD_FT", "3000"))
WATCHLIST_COOLDOWN_S = 30 * 60
OVERHEAD_COOLDOWN_S = 15 * 60
SQUAWK_COOLDOWN_S = 15 * 60


def load_json(path: Path, default: dict | list) -> dict | list:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p = math.pi / 180
    a = (
        math.sin((lat2 - lat1) * p / 2) ** 2
        + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def aircraft_alt_ft(ac: dict) -> float | None:
    alt = ac.get("alt_baro")
    if alt is None:
        alt = ac.get("alt_geom")
    if alt is None:
        return None
    try:
        return float(alt)
    except (TypeError, ValueError):
        return None


def load_watchlist() -> dict:
    data = load_json(WATCHLIST_FILE, {"callsigns": [], "hex": []})
    return {
        "callsigns": [str(c).strip().upper() for c in data.get("callsigns", []) if str(c).strip()],
        "hex": [str(h).strip().lower() for h in data.get("hex", []) if str(h).strip()],
    }


def watchlist_match(ac: dict, watchlist: dict) -> bool:
    hex_id = str(ac.get("hex", "")).lower()
    flight = str(ac.get("flight", "")).strip().upper()
    if hex_id and hex_id in watchlist["hex"]:
        return True
    if flight:
        for prefix in watchlist["callsigns"]:
            if flight.startswith(prefix) or prefix in flight:
                return True
    return False


def now_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


def should_fire(state: dict, key: str, cooldown_s: int | None = None) -> bool:
    if cooldown_s is None:
        return key not in state.get("active", {})
    last = state.get("cooldowns", {}).get(key, 0)
    return now_ts() - last >= cooldown_s


def mark_active(state: dict, key: str) -> None:
    state.setdefault("active", {})[key] = now_ts()


def clear_active(state: dict, key: str) -> None:
    state.get("active", {}).pop(key, None)


def mark_cooldown(state: dict, key: str) -> None:
    state.setdefault("cooldowns", {})[key] = now_ts()


def main() -> int:
    if not alerts_enabled():
        return 0

    squawk_codes = load_squawk_codes()
    state = load_json(STATE_FILE, {"active": {}, "cooldowns": {}})
    status = load_json(STATUS_FILE, {})
    loc = status.get("location") or {}
    lat0 = loc.get("lat")
    lon0 = loc.get("lon")

    services = status.get("services") or {}
    readsb_ok = str(services.get("readsb", "")).lower() == "active"
    tar1090_ok = str(services.get("tar1090", "")).lower() == "active"
    feeder_ok = readsb_ok and tar1090_ok

    if not feeder_ok:
        if should_fire(state, "feeder_down"):
            host = status.get("hostname", "feeder")
            send_alert(
                f"{host}: feeder down",
                f"readsb={services.get('readsb', '?')}, tar1090={services.get('tar1090', '?')}",
                priority=8,
            )
            mark_active(state, "feeder_down")
    else:
        clear_active(state, "feeder_down")

    if not AIRCRAFT_JSON.exists():
        save_state(state)
        return 0

    try:
        data = json.loads(AIRCRAFT_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        save_state(state)
        return 0

    aircraft = data.get("aircraft", [])
    watchlist = load_watchlist()
    current_squawk_keys: set[str] = set()

    for ac in aircraft:
        hex_id = str(ac.get("hex", "")).lower()
        if not hex_id:
            continue
        flight = str(ac.get("flight", "")).strip() or hex_id.upper()
        squawk = str(ac.get("squawk", "")).strip()

        if squawk_codes and squawk in squawk_codes:
            key = f"squawk:{hex_id}:{squawk}"
            current_squawk_keys.add(key)
            is_emergency = squawk in EMERGENCY_SQUAWKS
            if should_fire(state, key, None if is_emergency else SQUAWK_COOLDOWN_S):
                label = squawk_label(squawk)
                send_alert(
                    f"Squawk {squawk}",
                    f"{flight} ({hex_id.upper()}) — {label}",
                    priority=squawk_priority(squawk),
                )
                if is_emergency:
                    mark_active(state, key)
                else:
                    mark_cooldown(state, key)

        if watchlist_match(ac, watchlist):
            key = f"watch:{hex_id}"
            if should_fire(state, key, WATCHLIST_COOLDOWN_S):
                send_alert("Watchlist aircraft", f"{flight} ({hex_id.upper()})", priority=8)
                mark_cooldown(state, key)

        if lat0 and lon0 and ac.get("lat") is not None and ac.get("lon") is not None:
            try:
                dist_m = haversine_m(float(lat0), float(lon0), float(ac["lat"]), float(ac["lon"]))
            except (TypeError, ValueError):
                dist_m = None
            alt_ft = aircraft_alt_ft(ac)
            if dist_m is not None and alt_ft is not None:
                if dist_m < OVERHEAD_KM * 1000 and alt_ft < OVERHEAD_FT:
                    key = f"overhead:{hex_id}"
                    if should_fire(state, key, OVERHEAD_COOLDOWN_S):
                        send_alert(
                            "Aircraft overhead",
                            f"{flight} at {(dist_m / 1000):.1f} km, {alt_ft:.0f} ft",
                        )
                        mark_cooldown(state, key)

    for key in list(state.get("active", {})):
        if key.startswith("squawk:") and key not in current_squawk_keys:
            clear_active(state, key)

    save_state(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
