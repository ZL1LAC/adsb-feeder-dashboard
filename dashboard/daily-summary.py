#!/usr/bin/env python3
"""Send daily ADS-B feeder summary via Gotify."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from feeder_paths import ALERT_STATE, HISTORY_LOG, UPLOAD_HISTORY as UPLOAD_HISTORY_FILE
from notify import alerts_enabled, send_alert

UPLOAD_HISTORY = UPLOAD_HISTORY_FILE
STATE_FILE = ALERT_STATE


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def parse_ts(raw: str) -> datetime | None:
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def aggregate_history(cutoff: datetime) -> dict:
    peak_aircraft = 0
    max_range = 0.0
    snr_vals: list[float] = []
    if not HISTORY_LOG.exists():
        return {"peak_aircraft": 0, "max_range_km": 0, "avg_snr": None}
    try:
        for line in HISTORY_LOG.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            ts = parse_ts(row.get("t", ""))
            if ts is None or ts < cutoff:
                continue
            peak_aircraft = max(peak_aircraft, int(row.get("aircraft_total") or 0))
            dist = row.get("max_distance")
            if dist is not None:
                max_range = max(max_range, float(dist))
            snr = row.get("snr")
            if snr is not None:
                snr_vals.append(float(snr))
    except OSError:
        pass
    avg_snr = round(sum(snr_vals) / len(snr_vals), 1) if snr_vals else None
    return {
        "peak_aircraft": peak_aircraft,
        "max_range_km": round(max_range / 1000) if max_range > 0 else 0,
        "avg_snr": avg_snr,
    }


def aggregate_uploads(cutoff: datetime) -> dict:
    ok = 0
    skipped = 0
    history = load_json(UPLOAD_HISTORY, [])
    if not isinstance(history, list):
        return {"ok": 0, "skipped": 0}
    for entry in history:
        raw_time = entry.get("time")
        if not raw_time:
            continue
        ts = parse_ts(raw_time)
        if ts is None or ts < cutoff:
            continue
        summary = str(entry.get("summary", "")).lower()
        if entry.get("ok") is False or "error" in summary or "failed" in summary:
            continue
        if "skip" in summary or "nothing to upload" in summary:
            skipped += 1
        elif "upload accepted" in summary or entry.get("ok") is True:
            ok += 1
    return {"ok": ok, "skipped": skipped}


def main() -> int:
    if not alerts_enabled():
        return 0

    today = datetime.now(timezone.utc).date().isoformat()
    state = load_json(STATE_FILE, {})
    if state.get("last_daily_summary") == today:
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    hist = aggregate_history(cutoff)
    uploads = aggregate_uploads(cutoff)

    snr_part = f", avg SNR {hist['avg_snr']} dB" if hist["avg_snr"] is not None else ""
    msg = (
        f"Peak {hist['peak_aircraft']} aircraft, max range {hist['max_range_km']} km"
        f"{snr_part}, {uploads['ok']} uploads OK, {uploads['skipped']} skipped"
    )
    if send_alert("ADS-B daily summary", msg):
        state["last_daily_summary"] = today
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
