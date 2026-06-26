#!/usr/bin/env python3
"""Auto-recover readsb when SDR is present but decoder is down."""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

STATE = Path(__file__).resolve().parent / "watch-state.json"
GEN = Path(__file__).resolve().parent / "gen-status.py"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=30)


def sdr_present() -> bool:
    proc = run("lsusb")
    return any("0bda:" in ln.lower() for ln in proc.stdout.splitlines())


def readsb_active() -> bool:
    proc = run("systemctl", "is-active", "readsb")
    return proc.stdout.strip() == "active"


def load_state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text())
        except json.JSONDecodeError:
            pass
    return {"last_recovery": None, "recoveries": 0}


def save_state(state: dict) -> None:
    STATE.write_text(json.dumps(state, indent=2))


def recover() -> bool:
    ok = True
    for unit in ("readsb", "tar1090"):
        proc = run("sudo", "systemctl", "restart", unit)
        if proc.returncode != 0:
            ok = False
    return ok


def main() -> None:
    state = load_state()
    state["sdr_ok"] = sdr_present()
    state["readsb_active"] = readsb_active()
    state["checked"] = datetime.now(timezone.utc).isoformat()

    if state["sdr_ok"] and not state["readsb_active"]:
        if recover():
            state["last_recovery"] = datetime.now(timezone.utc).isoformat()
            state["recoveries"] = state.get("recoveries", 0) + 1

    save_state(state)
    run("python3", str(GEN))


if __name__ == "__main__":
    main()
