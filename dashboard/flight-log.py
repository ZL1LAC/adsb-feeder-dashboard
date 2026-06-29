#!/usr/bin/env python3
"""Log aircraft sightings to SQLite for long-term queries."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from feeder_paths import AIRCRAFT_JSON, LOG_DIR

DB_PATH = LOG_DIR / "flights.sqlite"
RETENTION_DAYS = 30

SCHEMA = """
CREATE TABLE IF NOT EXISTS sightings (
  id INTEGER PRIMARY KEY,
  ts TEXT NOT NULL,
  hex TEXT NOT NULL,
  flight TEXT,
  lat REAL,
  lon REAL,
  alt_baro INTEGER,
  gs REAL,
  track REAL,
  squawk TEXT,
  rssi REAL
);
CREATE INDEX IF NOT EXISTS idx_hex_ts ON sightings(hex, ts);
CREATE INDEX IF NOT EXISTS idx_ts ON sightings(ts);
"""


def ensure_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def prune_old(conn: sqlite3.Connection) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).isoformat()
    conn.execute("DELETE FROM sightings WHERE ts < ?", (cutoff,))
    conn.commit()


def insert_sightings(conn: sqlite3.Connection, aircraft: list, ts: str) -> int:
    rows = []
    for ac in aircraft:
        hex_id = str(ac.get("hex", "")).strip().lower()
        if not hex_id:
            continue
        rows.append(
            (
                ts,
                hex_id,
                (ac.get("flight") or "").strip() or None,
                ac.get("lat"),
                ac.get("lon"),
                ac.get("alt_baro"),
                ac.get("gs"),
                ac.get("track"),
                str(ac.get("squawk", "")).strip() or None,
                ac.get("rssi"),
            )
        )
    if not rows:
        return 0
    conn.executemany(
        """INSERT INTO sightings
           (ts, hex, flight, lat, lon, alt_baro, gs, track, squawk, rssi)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    return len(rows)


def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if not AIRCRAFT_JSON.exists():
        return 0
    try:
        data = json.loads(AIRCRAFT_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0

    ts = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(DB_PATH)
    try:
        ensure_db(conn)
        insert_sightings(conn, data.get("aircraft", []), ts)
        prune_old(conn)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
