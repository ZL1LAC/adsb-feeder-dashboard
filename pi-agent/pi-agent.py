#!/usr/bin/env python3
"""Lightweight Pi-side API for split-stack deployments (decode host only)."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Allow importing feeder_profile from dashboard when run from repo root.
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO / "dashboard") not in sys.path:
    sys.path.insert(0, str(_REPO / "dashboard"))

from feeder_profile import FEED_PROFILE, apply_location_line, build_feeds, build_services, restart_units  # noqa: E402

HOST = os.environ.get("PI_AGENT_HOST", "0.0.0.0")
PORT = int(os.environ.get("PI_AGENT_PORT", "8780"))
TOKEN = os.environ.get("PI_AGENT_TOKEN", "").strip()
AIRCRAFT_JSON = Path(os.environ.get("FEEDER_AIRCRAFT_JSON", "/run/readsb/aircraft.json"))
STATS_JSON = Path(os.environ.get("FEEDER_STATS_JSON", "/run/readsb/stats.json"))
RECEIVER_JSON = Path(os.environ.get("FEEDER_RECEIVER_JSON", "/run/readsb/receiver.json"))
READSB_DEFAULT = Path(os.environ.get("FEEDER_READSB_DEFAULT", "/etc/default/readsb"))
LOCATION_FILE = Path(os.environ.get("FEEDER_LOCATION_FILE", "/etc/default/airplanes"))
SET_LOCATION = _REPO / "scripts" / "set-station-location.sh"
WATCH_STATE = _REPO / "dashboard" / "watch-state.json"
GAIN_RE = re.compile(r"^[0-9]+(\.[0-9]+)?$|^auto$")


def run(*args: str, timeout: int = 10) -> str:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return ""


def run_cmd(args: list[str], timeout: int = 90) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


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
    iso = run("date", "-d", raw, "-Iseconds")
    return iso if iso else raw


def feed_connected() -> dict:
    ss = run("ss", "-tn")
    return {
        "beast": any(p in ss for p in (":30004", ":64004")),
        "mlat": ":31090" in ss and "78.46.234.18" in ss,
    }


def read_json_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def read_location() -> dict:
    loc = {"lat": None, "lon": None, "alt": None, "user": None}
    if not LOCATION_FILE.exists():
        return loc
    for line in LOCATION_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        apply_location_line(line, loc)
    return loc


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
    data = read_json_file(STATS_JSON)
    total = data.get("total", {})
    local = total.get("local", {})
    return {
        "signal": local.get("signal"),
        "noise": local.get("noise"),
        "max_distance": total.get("max_distance"),
        "messages": total.get("messages"),
    }


def sdr_present() -> bool:
    return any("0bda:" in ln.lower() for ln in run("lsusb").splitlines())


def sdr_info() -> str:
    for line in run("lsusb").splitlines():
        if "0bda:" in line.lower() or "rtl" in line.lower():
            return line.strip()
    return "not detected"


def read_watch_state() -> dict:
    if not WATCH_STATE.exists():
        return {"sdr_ok": sdr_present(), "last_recovery": None}
    try:
        state = json.loads(WATCH_STATE.read_text())
        state["sdr_ok"] = sdr_present()
        return state
    except (OSError, json.JSONDecodeError):
        return {"sdr_ok": sdr_present(), "last_recovery": None}


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


def build_probe() -> dict:
    stats = read_stats()
    signal = stats.get("signal")
    noise = stats.get("noise")
    snr = round(signal - noise, 1) if signal is not None and noise is not None else None
    loc = read_location()
    readsb_loc = read_readsb_location()
    return {
        "hostname": run("hostname") or "pi",
        "profile": FEED_PROFILE,
        "services": build_services(service_state),
        "uptime": {
            "readsb": service_uptime("readsb"),
            "host": run("uptime", "-p"),
        },
        "feeds": build_feeds(feed_connected, service_state),
        "sdr": sdr_info(),
        "sdr_ok": sdr_present(),
        "watch": read_watch_state(),
        "location": loc,
        "readsb_location": {**readsb_loc, "matches_airplanes": locations_match(loc, readsb_loc)},
        "gain": read_gain(),
        "reception": {
            "gain": read_gain(),
            "signal": signal,
            "noise": noise,
            "snr": snr,
            "max_distance": stats.get("max_distance"),
        },
    }


class Handler(BaseHTTPRequestHandler):
    def _authorized(self) -> bool:
        if not TOKEN:
            return True
        auth = self.headers.get("Authorization", "")
        return auth == f"Bearer {TOKEN}"

    def _json(self, code: int, payload: dict | list) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            return {}

    def _file_json(self, path: Path) -> None:
        if not path.exists():
            self._json(404, {"ok": False, "error": f"{path.name} not found"})
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self._json(500, {"ok": False, "error": str(exc)})
            return
        self._json(200, data)

    def do_GET(self) -> None:
        if not self._authorized():
            self._json(401, {"ok": False, "error": "unauthorized"})
            return
        path = self.path.split("?", 1)[0].rstrip("/")
        if path == "/v1/health":
            self._json(200, {"ok": True, "service": "pi-agent"})
            return
        if path == "/v1/probe":
            self._json(200, build_probe())
            return
        if path == "/v1/aircraft":
            self._file_json(AIRCRAFT_JSON)
            return
        if path == "/v1/stats":
            self._file_json(STATS_JSON)
            return
        if path == "/v1/receiver":
            self._file_json(RECEIVER_JSON)
            return
        self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        if not self._authorized():
            self._json(401, {"ok": False, "error": "unauthorized"})
            return
        path = self.path.split("?", 1)[0].rstrip("/")
        body = self._read_body()

        if path == "/v1/ops/restart/readsb":
            results = []
            for unit in restart_units("readsb"):
                proc = run_cmd(["sudo", "systemctl", "restart", unit], timeout=30)
                results.append(f"{unit}: {'ok' if proc.returncode == 0 else proc.stderr.strip()}")
            ok = all("ok" in r for r in results)
            self._json(200, {"ok": ok, "summary": "; ".join(results), "output": results})
            return

        if path == "/v1/ops/restart/all":
            results = []
            for unit in restart_units("all"):
                proc = run_cmd(["sudo", "systemctl", "restart", unit], timeout=30)
                results.append(f"{unit}: {'ok' if proc.returncode == 0 else proc.stderr.strip()}")
            ok = all("ok" in r for r in results)
            self._json(200, {"ok": ok, "summary": "; ".join(results), "output": results})
            return

        if path == "/v1/ops/gain":
            gain = str(body.get("gain", "")).strip()
            if not GAIN_RE.match(gain):
                self._json(400, {"ok": False, "error": "invalid gain (use number or auto)"})
                return
            proc = run_cmd(["sudo", "/usr/local/bin/readsb-gain", gain], timeout=30)
            combined = (proc.stdout + proc.stderr).strip()
            ok = proc.returncode == 0
            self._json(
                200,
                {
                    "ok": ok,
                    "summary": combined or f"gain set to {gain}",
                    "output": combined.splitlines() if combined else [],
                },
            )
            return

        if path == "/v1/ops/location":
            lat = str(body.get("lat", "")).strip()
            lon = str(body.get("lon", "")).strip()
            alt = str(body.get("alt", "12")).strip()
            if not lat or not lon:
                self._json(400, {"ok": False, "error": "lat and lon required"})
                return
            if not SET_LOCATION.exists():
                self._json(500, {"ok": False, "error": "location script not found"})
                return
            proc = run_cmd(["sudo", str(SET_LOCATION), lat, lon, alt], timeout=90)
            combined = (proc.stdout + proc.stderr).strip()
            if proc.returncode != 0:
                self._json(
                    500,
                    {"ok": False, "error": combined.splitlines()[-1] if combined else "location update failed"},
                )
                return
            self._json(
                200,
                {"ok": True, "summary": combined.splitlines()[-1] if combined else "location updated"},
            )
            return

        self._json(404, {"ok": False, "error": "not found"})

    def log_message(self, fmt: str, *args) -> None:
        return


def main() -> None:
    if not TOKEN:
        print("Warning: PI_AGENT_TOKEN is empty — agent accepts unauthenticated requests", file=sys.stderr)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"pi-agent listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
