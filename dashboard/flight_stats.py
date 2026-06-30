"""Shared flight log analytics from flights.sqlite."""
from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from feeder_paths import LOG_DIR, STATUS_JSON, STATUS_JSON

DB_PATH = LOG_DIR / "flights.sqlite"
STATUS_FILE = STATUS_JSON


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p = math.pi / 180
    a = (
        math.sin((lat2 - lat1) * p / 2) ** 2
        + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def load_station_location() -> tuple[float, float] | None:
    if not STATUS_FILE.exists():
        return None
    try:
        data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    loc = data.get("location") or {}
    try:
        lat = float(loc["lat"])
        lon = float(loc["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    return lat, lon


def cutoff_iso(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def today_start_iso() -> str:
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.isoformat()


def db_connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"flight log not found: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_flight_stats() -> dict:
    if not DB_PATH.exists():
        return {
            "ok": False,
            "error": "flight log database not found",
            "db_path": str(DB_PATH),
        }

    cutoff_24h = cutoff_iso(1)
    cutoff_7d = cutoff_iso(7)
    cutoff_today = today_start_iso()
    db_size = DB_PATH.stat().st_size

    try:
        conn = db_connect()
    except FileNotFoundError as exc:
        return {"ok": False, "error": str(exc), "db_path": str(DB_PATH)}

    try:
        unique_24h = conn.execute(
            "SELECT COUNT(DISTINCT hex) FROM sightings WHERE ts >= ?",
            (cutoff_24h,),
        ).fetchone()[0]
        unique_7d = conn.execute(
            "SELECT COUNT(DISTINCT hex) FROM sightings WHERE ts >= ?",
            (cutoff_7d,),
        ).fetchone()[0]
        sightings_today = conn.execute(
            "SELECT COUNT(*) FROM sightings WHERE ts >= ?",
            (cutoff_today,),
        ).fetchone()[0]
        oldest = conn.execute("SELECT MIN(ts) FROM sightings").fetchone()[0]
        total_rows = conn.execute("SELECT COUNT(*) FROM sightings").fetchone()[0]
        top_rows = conn.execute(
            """SELECT flight, COUNT(*) AS cnt
               FROM sightings
               WHERE ts >= ? AND flight IS NOT NULL AND TRIM(flight) != ''
               GROUP BY UPPER(TRIM(flight))
               ORDER BY cnt DESC
               LIMIT 5""",
            (cutoff_7d,),
        ).fetchall()
    finally:
        conn.close()

    return {
        "ok": True,
        "unique_hex_24h": int(unique_24h or 0),
        "unique_hex_7d": int(unique_7d or 0),
        "sightings_today": int(sightings_today or 0),
        "total_rows": int(total_rows or 0),
        "top_callsigns_7d": [
            {"flight": row["flight"].strip(), "count": int(row["cnt"])} for row in top_rows
        ],
        "oldest_record": oldest,
        "db_size_bytes": db_size,
        "db_path": str(DB_PATH),
        "updated": datetime.now(timezone.utc).isoformat(),
    }


def query_callsign(callsign: str, days: float) -> dict:
    conn = db_connect()
    try:
        pattern = f"%{callsign.strip().upper()}%"
        cutoff = cutoff_iso(days)
        row = conn.execute(
            """SELECT COUNT(*) AS cnt,
                      COUNT(DISTINCT hex) AS unique_hex,
                      MIN(ts) AS first_seen,
                      MAX(ts) AS last_seen
               FROM sightings
               WHERE UPPER(TRIM(flight)) LIKE ? AND ts >= ?""",
            (pattern, cutoff),
        ).fetchone()
        return {
            "callsign": callsign.strip().upper(),
            "days": days,
            "sightings": int(row["cnt"] or 0),
            "unique_hex": int(row["unique_hex"] or 0),
            "first_seen": row["first_seen"],
            "last_seen": row["last_seen"],
        }
    finally:
        conn.close()


def query_summary(today_only: bool) -> dict:
    conn = db_connect()
    try:
        cutoff = today_start_iso() if today_only else cutoff_iso(1)
        label = "today" if today_only else "24h"
        unique_hex = conn.execute(
            "SELECT COUNT(DISTINCT hex) FROM sightings WHERE ts >= ?",
            (cutoff,),
        ).fetchone()[0]
        sightings = conn.execute(
            "SELECT COUNT(*) FROM sightings WHERE ts >= ?",
            (cutoff,),
        ).fetchone()[0]
        positioned = conn.execute(
            "SELECT COUNT(*) FROM sightings WHERE ts >= ? AND lat IS NOT NULL AND lon IS NOT NULL",
            (cutoff,),
        ).fetchone()[0]
        return {
            "period": label,
            "unique_hex": int(unique_hex or 0),
            "sightings": int(sightings or 0),
            "positioned_sightings": int(positioned or 0),
        }
    finally:
        conn.close()


def query_top(days: float, limit: int) -> list[dict]:
    conn = db_connect()
    try:
        cutoff = cutoff_iso(days)
        rows = conn.execute(
            """SELECT UPPER(TRIM(flight)) AS flight, COUNT(*) AS cnt,
                      COUNT(DISTINCT hex) AS unique_hex
               FROM sightings
               WHERE ts >= ? AND flight IS NOT NULL AND TRIM(flight) != ''
               GROUP BY UPPER(TRIM(flight))
               ORDER BY cnt DESC
               LIMIT ?""",
            (cutoff, limit),
        ).fetchall()
        return [
            {
                "flight": row["flight"],
                "sightings": int(row["cnt"]),
                "unique_hex": int(row["unique_hex"]),
            }
            for row in rows
        ]
    finally:
        conn.close()


def query_overhead(km: float, days: float) -> list[dict]:
    station = load_station_location()
    if not station:
        raise ValueError("station location not available in status.json")
    lat0, lon0 = station
    max_m = km * 1000

    conn = db_connect()
    try:
        cutoff = cutoff_iso(days)
        rows = conn.execute(
            """SELECT hex, flight, lat, lon, alt_baro, ts
               FROM sightings
               WHERE ts >= ? AND lat IS NOT NULL AND lon IS NOT NULL""",
            (cutoff,),
        ).fetchall()
    finally:
        conn.close()

    best: dict[str, dict] = {}
    for row in rows:
        hex_id = str(row["hex"]).lower()
        try:
            dist_m = haversine_m(lat0, lon0, float(row["lat"]), float(row["lon"]))
        except (TypeError, ValueError):
            continue
        if dist_m > max_m:
            continue
        flight = (row["flight"] or "").strip() or hex_id.upper()
        prev = best.get(hex_id)
        if prev is None or dist_m < prev["min_distance_m"]:
            best[hex_id] = {
                "hex": hex_id.upper(),
                "flight": flight,
                "min_distance_m": dist_m,
                "min_distance_km": round(dist_m / 1000, 2),
                "alt_baro": row["alt_baro"],
                "closest_at": row["ts"],
            }

    results = sorted(best.values(), key=lambda r: r["min_distance_km"])
    return results
