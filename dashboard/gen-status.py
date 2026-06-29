#!/usr/bin/env python3
"""Write feeder dashboard status.json (run as user 'server')."""
import json
import math
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from feeder_paths import (
    AIRCRAFT_JSON,
    LOCATION_FILE,
    READSB_DEFAULT,
    STATS_JSON as STATS,
    UPLOAD_HISTORY as HISTORY,
    UPLOAD_LOG as LOG,
)
from feeder_profile import FEED_PROFILE, apply_location_line, build_feeds, build_services, link_info

OUT = Path(__file__).resolve().parent / "status.json"
HISTORY_LOG = Path(__file__).resolve().parent / "history.jsonl"
HISTORY_CHART = Path(__file__).resolve().parent / "history.json"
HISTORY_HOURLY_LOG = Path(__file__).resolve().parent / "history-hourly.jsonl"
HISTORY_HOURLY_CHART = Path(__file__).resolve().parent / "history-hourly.json"
WATCH_STATE = Path(__file__).resolve().parent / "watch-state.json"
AIRPLANES = LOCATION_FILE

MUNINN_NOISE = (
    "dump1090 network input port",
    "port 30104",
    "port 30001",
    "Remote aircraft data may be mixing",
    "If you see aircraft far outside",
    "Fix: restart dump1090",
)


def run(*args: str) -> str:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=5).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return ""


def service_state(unit: str, user: bool = False) -> str:
    cmd = ["systemctl"]
    if user:
        cmd.append("--user")
    cmd += ["is-active", unit]
    return run(*cmd) or "unknown"


def service_uptime(unit: str) -> str | None:
    raw = run("systemctl", "show", unit, "-p", "ActiveEnterTimestamp", "--value")
    if not raw or raw == "n/a":
        return None
    # systemctl uses locale strings like "Fri 2026-06-26 16:55:45 NZST" — convert
    # to ISO so the dashboard JS Date parser accepts it.
    iso = run("date", "-d", raw, "-Iseconds")
    return iso if iso else raw


def feed_connected() -> dict:
    ss = run("ss", "-tn")
    return {
        "beast": any(p in ss for p in (":30004", ":64004")),
        "mlat": ":31090" in ss and "78.46.234.18" in ss,
    }


def read_location() -> dict:
    loc = {"lat": None, "lon": None, "alt": None, "user": None}
    if not AIRPLANES.exists():
        return loc
    for line in AIRPLANES.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        apply_location_line(line, loc)
    return loc


def read_gain() -> str:
    if not READSB_DEFAULT.exists():
        return "unknown"
    for line in READSB_DEFAULT.read_text().splitlines():
        if "RECEIVER_OPTIONS" in line and "--gain" in line:
            m = re.search(r"--gain\s+(\S+)", line)
            if m:
                return m.group(1)
    return "auto"


def read_stats() -> dict:
    if not STATS.exists():
        return {}
    try:
        data = json.loads(STATS.read_text())
        total = data.get("total", {})
        local = total.get("local", {})
        return {
            "signal": local.get("signal"),
            "noise": local.get("noise"),
            "max_distance": total.get("max_distance"),
            "messages": total.get("messages"),
        }
    except (OSError, json.JSONDecodeError):
        return {}


def sdr_present() -> bool:
    return any("0bda:" in ln.lower() for ln in run("lsusb").splitlines())


def sdr_info() -> str:
    for line in run("lsusb").splitlines():
        if "0bda:" in line.lower() or "rtl" in line.lower():
            return line.strip()
    return "not detected"


def filter_log_line(line: str) -> bool:
    return not any(n in line for n in MUNINN_NOISE)


def muninn_log_tail(n: int = 20) -> list[str]:
    if not LOG.exists():
        return []
    try:
        lines = LOG.read_text(errors="replace").splitlines()
        return [ln for ln in lines if filter_log_line(ln)][-n:]
    except OSError:
        return []


def to_iso_timestamp(raw: str) -> str | None:
    if not raw:
        return None
    iso = run("date", "-d", raw, "-Iseconds")
    return iso if iso else raw


def parse_muninn_meta() -> dict:
    meta = {
        "last_upload": None,
        "last_summary": None,
        "last_ok": None,
        "next_run": None,
        "next_run_in": None,
        "interval_min": None,
        "recent": [],
    }
    if HISTORY.exists():
        try:
            history = json.loads(HISTORY.read_text())
            if history:
                last = history[-1]
                meta["last_upload"] = last.get("time")
                meta["last_summary"] = last.get("summary")
                meta["last_ok"] = last.get("ok")
                meta["recent"] = [
                    {"time": h.get("time"), "summary": h.get("summary"), "ok": h.get("ok")}
                    for h in history[-10:]
                ][::-1]
        except (OSError, json.JSONDecodeError):
            pass
    if not meta["last_summary"] and LOG.exists():
        try:
            for line in reversed(LOG.read_text(errors="replace").splitlines()):
                if filter_log_line(line) and line.strip():
                    meta["last_summary"] = line.strip()
                    meta["last_ok"] = "upload accepted" in line or "nothing to upload" in line
                    break
        except OSError:
            pass
    timer_out = run("systemctl", "--user", "list-timers", "muninn-upload.timer", "--no-pager")
    for line in timer_out.splitlines():
        if "muninn-upload.timer" in line:
            parts = line.split()
            if len(parts) >= 4 and parts[0] not in ("NEXT", "n/a", "-"):
                raw = " ".join(parts[0:4])
                meta["next_run"] = to_iso_timestamp(raw) or raw
            if len(parts) >= 6:
                meta["next_run_in"] = f"{parts[4]} {parts[5]}"
            break
    timer_show = run(
        "systemctl", "--user", "show", "muninn-upload.timer", "-p", "TimersMonotonic", "--value"
    )
    if timer_show:
        m = re.search(r"OnUnitActiveUSec=(\d+)(min|s)", timer_show)
        if m:
            val, unit = int(m.group(1)), m.group(2)
            meta["interval_min"] = val if unit == "min" else max(1, round(val / 60))
    return meta


def max_distance_from_aircraft(loc: dict) -> float | None:
    if not loc.get("lat") or not loc.get("lon") or not AIRCRAFT_JSON.exists():
        return None
    try:
        lat0 = float(loc["lat"])
        lon0 = float(loc["lon"])
        data = json.loads(AIRCRAFT_JSON.read_text())
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None

    def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        r = 6371000.0
        p = math.pi / 180
        a = (
            math.sin((lat2 - lat1) * p / 2) ** 2
            + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
        )
        return 2 * r * math.asin(math.sqrt(a))

    best = 0.0
    for ac in data.get("aircraft", []):
        lat, lon = ac.get("lat"), ac.get("lon")
        if lat is None or lon is None:
            continue
        best = max(best, haversine(lat0, lon0, float(lat), float(lon)))
    return best if best > 0 else None


def read_aircraft_counts() -> dict:
    if not AIRCRAFT_JSON.exists():
        return {"total": 0, "positioned": 0, "messages": 0}
    try:
        data = json.loads(AIRCRAFT_JSON.read_text())
        aircraft = data.get("aircraft", [])
        positioned = sum(
            1 for a in aircraft if a.get("lat") is not None and a.get("lon") is not None
        )
        return {
            "total": len(aircraft),
            "positioned": positioned,
            "messages": data.get("messages", 0),
        }
    except (OSError, json.JSONDecodeError):
        return {"total": 0, "positioned": 0, "messages": 0}


def read_readsb_location() -> dict:
    loc = {"lat": None, "lon": None, "alt": None}
    if not READSB_DEFAULT.exists():
        return loc
    text = READSB_DEFAULT.read_text()
    for flag, key in (("--lat", "lat"), ("--lon", "lon"), ("--alt", "alt")):
        m = re.search(rf"{re.escape(flag)}\s+(\S+)", text)
        if m:
            loc[key] = m.group(1).strip('"').strip("'")
    return loc


def locations_match(airplanes: dict, readsb: dict) -> bool | None:
    if not airplanes.get("lat") or not airplanes.get("lon"):
        return None
    if not readsb.get("lat") or not readsb.get("lon"):
        return False
    try:
        lat_ok = abs(float(airplanes["lat"]) - float(readsb["lat"])) < 0.0001
        lon_ok = abs(float(airplanes["lon"]) - float(readsb["lon"])) < 0.0001
        return lat_ok and lon_ok
    except (TypeError, ValueError):
        return False


def append_history(snapshot: dict) -> None:
    now = datetime.now(timezone.utc)
    snapshot["t"] = now.isoformat()
    cutoff = now.timestamp() - 86400
    HISTORY_LOG.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(snapshot) + "\n")
    rows: list[dict] = []
    if HISTORY_LOG.exists():
        try:
            for line in HISTORY_LOG.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                try:
                    ts = datetime.fromisoformat(row["t"].replace("Z", "+00:00")).timestamp()
                except (KeyError, ValueError):
                    continue
                if ts >= cutoff:
                    rows.append(row)
        except OSError:
            rows = []
    if len(rows) > 2880:
        rows = rows[-2880:]
    HISTORY_LOG.write_text("\n".join(json.dumps(r) for r in rows) + ("\n" if rows else ""), encoding="utf-8")
    HISTORY_CHART.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    append_hourly_rollup(snapshot, now)


def append_hourly_rollup(snapshot: dict, now: datetime) -> None:
    hour_start = now.replace(minute=0, second=0, microsecond=0)
    hour_key = hour_start.isoformat()
    cutoff = now.timestamp() - 7 * 86400

    rows: list[dict] = []
    if HISTORY_HOURLY_LOG.exists():
        try:
            for line in HISTORY_HOURLY_LOG.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                try:
                    ts = datetime.fromisoformat(row["t"].replace("Z", "+00:00")).timestamp()
                except (KeyError, ValueError):
                    continue
                if ts >= cutoff:
                    rows.append(row)
        except OSError:
            rows = []

    current = None
    for row in rows:
        if row.get("t") == hour_key:
            current = row
            break

    if current is None:
        current = {
            "t": hour_key,
            "aircraft_total": 0,
            "aircraft_positioned": 0,
            "messages": 0,
            "snr": None,
            "max_distance": 0,
        }
        rows.append(current)

    current["aircraft_total"] = max(int(current.get("aircraft_total") or 0), int(snapshot.get("aircraft_total") or 0))
    current["aircraft_positioned"] = max(
        int(current.get("aircraft_positioned") or 0), int(snapshot.get("aircraft_positioned") or 0)
    )
    current["messages"] = max(int(current.get("messages") or 0), int(snapshot.get("messages") or 0))
    snr = snapshot.get("snr")
    if snr is not None:
        prev = current.get("snr")
        current["snr"] = max(float(prev), float(snr)) if prev is not None else float(snr)
    dist = snapshot.get("max_distance")
    if dist is not None:
        current["max_distance"] = max(float(current.get("max_distance") or 0), float(dist))

    rows.sort(key=lambda r: r.get("t", ""))
    HISTORY_HOURLY_LOG.write_text("\n".join(json.dumps(r) for r in rows) + ("\n" if rows else ""), encoding="utf-8")
    HISTORY_HOURLY_CHART.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def read_watch_state() -> dict:
    if not WATCH_STATE.exists():
        return {"sdr_ok": sdr_present(), "last_recovery": None}
    try:
        state = json.loads(WATCH_STATE.read_text())
        state["sdr_ok"] = sdr_present()
        return state
    except (OSError, json.JSONDecodeError):
        return {"sdr_ok": sdr_present(), "last_recovery": None}


def main() -> None:
    stats = read_stats()
    signal = stats.get("signal")
    noise = stats.get("noise")
    snr = None
    if signal is not None and noise is not None:
        snr = round(signal - noise, 1)

    ac = read_aircraft_counts()
    muninn_meta = parse_muninn_meta()
    loc = read_location()
    readsb_loc = read_readsb_location()
    loc_match = locations_match(loc, readsb_loc)
    max_dist = stats.get("max_distance")
    if not max_dist:
        max_dist = max_distance_from_aircraft(loc)

    append_history({
        "aircraft_total": ac["total"],
        "aircraft_positioned": ac["positioned"],
        "messages": stats.get("messages") or ac["messages"],
        "snr": snr,
        "max_distance": max_dist,
        "upload_ok": muninn_meta.get("last_ok"),
    })

    payload = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "hostname": run("hostname") or "pi",
        "profile": FEED_PROFILE,
        "links": link_info(),
        "services": build_services(service_state),
        "uptime": {
            "readsb": service_uptime("readsb"),
            "host": run("uptime", "-p"),
        },
        "reception": {
            "gain": read_gain(),
            "signal": signal,
            "noise": noise,
            "snr": snr,
            "max_distance": max_dist,
        },
        "feeds": build_feeds(feed_connected, service_state),
        "sdr": sdr_info(),
        "sdr_ok": sdr_present(),
        "watch": read_watch_state(),
        "location": loc,
        "readsb_location": {**readsb_loc, "matches_airplanes": loc_match},
        "muninn": muninn_meta,
        "muninn_log": muninn_log_tail(),
    }
    OUT.write_text(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
