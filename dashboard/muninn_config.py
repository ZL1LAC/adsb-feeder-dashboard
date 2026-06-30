"""WDGoWars / Muninn configuration helpers."""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from feeder_paths import MUNINN_PY, SCHEDULE_SH, SPLIT_MODE, UPLOAD_HISTORY as HISTORY, UPLOAD_SCHEDULE, VENV_PYTHON

WHOAMI_USER = re.compile(r"user=(\S+)")
WHOAMI_STATS = re.compile(r"wifi=(\d+)\s+ble=(\d+)\s+aircraft=(\d+)\s+total=(\d+)")


def _run(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def _truthy(raw: str | None, default: bool = False) -> bool:
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def parse_muninn_config_output(text: str) -> dict:
    api_key_set = False
    for line in text.splitlines():
        if line.lower().startswith("api key:"):
            api_key_set = "set" in line.lower() and "not set" not in line.lower()
            break
    return {"api_key_set": api_key_set}


def muninn_api_key_set() -> bool:
    if not VENV_PYTHON.exists() or not MUNINN_PY.exists():
        return False
    proc = _run([str(VENV_PYTHON), str(MUNINN_PY), "--config"], timeout=30)
    return parse_muninn_config_output(proc.stdout + proc.stderr).get("api_key_set", False)


def read_upload_schedule() -> dict:
    if not UPLOAD_SCHEDULE.exists():
        return {"enabled": False, "minutes": 5}
    try:
        data = json.loads(UPLOAD_SCHEDULE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"enabled": False, "minutes": 5}
    return {
        "enabled": bool(data.get("enabled")),
        "minutes": int(data.get("minutes") or 5),
        "last_run": data.get("last_run"),
        "next_run": data.get("next_run"),
    }


def write_upload_schedule(enabled: bool, minutes: int) -> None:
    UPLOAD_SCHEDULE.parent.mkdir(parents=True, exist_ok=True)
    existing = read_upload_schedule()
    UPLOAD_SCHEDULE.write_text(
        json.dumps(
            {
                "enabled": enabled,
                "minutes": minutes,
                "last_run": existing.get("last_run"),
                "next_run": existing.get("next_run"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def muninn_timer_active() -> bool:
    if SPLIT_MODE:
        return read_upload_schedule().get("enabled", False)
    proc = _run(["systemctl", "--user", "is-active", "muninn-upload.timer"], timeout=15)
    return proc.stdout.strip() == "active"


def parse_whoami(text: str) -> dict:
    result: dict = {
        "ok": False,
        "user": None,
        "wifi": None,
        "ble": None,
        "aircraft": None,
        "total": None,
    }
    for line in text.splitlines():
        if "key OK" in line:
            result["ok"] = True
            m = WHOAMI_USER.search(line)
            if m:
                result["user"] = m.group(1)
        m = WHOAMI_STATS.search(line)
        if m:
            result["wifi"] = int(m.group(1))
            result["ble"] = int(m.group(2))
            result["aircraft"] = int(m.group(3))
            result["total"] = int(m.group(4))
    return result


def run_whoami(api_key: str | None = None) -> dict:
    if not VENV_PYTHON.exists() or not MUNINN_PY.exists():
        return {"ok": False, "error": "Muninn not installed"}
    args = [str(VENV_PYTHON), str(MUNINN_PY), "--whoami", "-q"]
    if api_key:
        args.extend(["--key", api_key])
    proc = _run(args, timeout=30)
    combined = (proc.stdout + proc.stderr).strip()
    data = parse_whoami(combined)
    data["ok"] = data["ok"] and proc.returncode == 0
    if not data["ok"]:
        data["error"] = combined.splitlines()[-1] if combined else "whoami failed"
    return data


def save_api_key(api_key: str) -> None:
    key = api_key.strip()
    if len(key) < 8:
        raise ValueError("API key looks too short")
    if not VENV_PYTHON.exists():
        raise ValueError("Muninn not installed — run install-muninn.sh")
    proc = _run([str(VENV_PYTHON), str(MUNINN_PY), "--save-key", key], timeout=30)
    if proc.returncode != 0:
        err = (proc.stdout + proc.stderr).strip()
        raise ValueError(err.splitlines()[-1] if err else "failed to save API key")


def apply_upload_interval(minutes: int) -> str:
    if minutes < 1 or minutes > 60:
        raise ValueError("interval must be 1–60 minutes")
    if SPLIT_MODE:
        sched = read_upload_schedule()
        write_upload_schedule(sched.get("enabled", True), minutes)
        return f"interval set to {minutes} min (docker upload loop)"
    if not SCHEDULE_SH.exists():
        raise ValueError("schedule script not found")
    proc = _run(["bash", str(SCHEDULE_SH), str(minutes)], timeout=60)
    combined = (proc.stdout + proc.stderr).strip()
    if proc.returncode != 0:
        raise ValueError(combined.splitlines()[-1] if combined else "failed to set interval")
    return combined.splitlines()[-1] if combined else f"interval set to {minutes} min"


def stop_upload_timer() -> None:
    if SPLIT_MODE:
        sched = read_upload_schedule()
        write_upload_schedule(False, int(sched.get("minutes") or 5))
        return
    _run(["systemctl", "--user", "stop", "muninn-upload.timer"], timeout=30)
    _run(["systemctl", "--user", "disable", "muninn-upload.timer"], timeout=30)


def sync_upload_timer(enabled: bool, interval_min: int, api_key_set: bool) -> str | None:
    if enabled and api_key_set:
        if SPLIT_MODE:
            write_upload_schedule(True, interval_min)
            return f"WDGoWars uploads enabled every {interval_min} min (docker loop)"
        return apply_upload_interval(interval_min)
    if not enabled:
        stop_upload_timer()
        return "WDGoWars uploads disabled (timer stopped)"
    return None


def upload_history(limit: int = 50) -> dict:
    entries: list[dict] = []
    if HISTORY.exists():
        try:
            entries = json.loads(HISTORY.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            entries = []
    entries = entries[-limit:]
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    ok_24h = skip_24h = fail_24h = 0
    for entry in entries:
        try:
            ts = datetime.fromisoformat(str(entry.get("time", "")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if ts < cutoff:
            continue
        summary = str(entry.get("summary", "")).lower()
        if "skip" in summary or "nothing to upload" in summary:
            skip_24h += 1
        elif entry.get("ok") is True or "upload accepted" in summary:
            ok_24h += 1
        else:
            fail_24h += 1
    return {
        "ok": True,
        "entries": list(reversed(entries)),
        "stats_24h": {"ok": ok_24h, "skip": skip_24h, "fail": fail_24h},
    }


def muninn_status_dict(enabled: bool, interval_min: int) -> dict:
    api_key_set = muninn_api_key_set()
    return {
        "enabled": enabled,
        "api_key_set": api_key_set,
        "configured": bool(enabled and api_key_set),
        "upload_interval_min": interval_min,
        "timer_active": muninn_timer_active(),
    }
