#!/usr/bin/env python3
"""Local-only feeder dashboard API (runs as user server)."""
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from feeder_paths import (
    GEN_STATUS as GEN,
    MUNINN_PY,
    SCHEDULE_SH,
    SET_LOCATION,
    STATUS_JSON,
    UPLOAD_HISTORY as HISTORY,
    UPLOAD_READY,
    UPLOAD_SCRIPT as UPLOAD,
    VENV_PYTHON as MUNINN,
)
from feeder_profile import restart_units
from flight_stats import get_flight_stats
from notify import check_gotify, send_alert_with
from settings_config import get_settings, save_settings, validate_alerts

HOST, PORT = "127.0.0.1", 8765
FLIGHT_STATS_CACHE_TTL_S = 60
_flight_stats_cache: dict = {"at": 0.0, "data": None}

GAIN_RE = re.compile(r"^[0-9]+(\.[0-9]+)?$|^auto$")
WHOAMI_USER = re.compile(r"user=(\S+)")
WHOAMI_STATS = re.compile(r"wifi=(\d+)\s+ble=(\d+)\s+aircraft=(\d+)\s+total=(\d+)")


def run_cmd(args: list[str], timeout: int = 90) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def refresh_status() -> None:
    try:
        subprocess.run(
            [sys.executable, str(GEN)],
            capture_output=True,
            timeout=15,
            check=False,
        )
    except OSError:
        pass


def append_upload_history(summary: str, ok: bool) -> None:
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "time": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "ok": ok,
    }
    try:
        hist = json.loads(HISTORY.read_text()) if HISTORY.exists() else []
    except (OSError, json.JSONDecodeError):
        hist = []
    hist.append(entry)
    HISTORY.write_text(json.dumps(hist[-20:], indent=2))


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


def cached_flight_stats() -> dict:
    now = time.time()
    if _flight_stats_cache["data"] is not None and now - _flight_stats_cache["at"] < FLIGHT_STATS_CACHE_TTL_S:
        return _flight_stats_cache["data"]
    data = get_flight_stats()
    _flight_stats_cache["at"] = now
    _flight_stats_cache["data"] = data
    return data


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0].rstrip("/")
        if path == "/dashboard/api/whoami":
            self._whoami()
            return
        if path == "/dashboard/api/flight-stats":
            self._flight_stats()
            return
        if path == "/dashboard/api/settings":
            self._get_settings()
            return
        self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0].rstrip("/")
        routes = {
            "/dashboard/api/push": self._push,
            "/dashboard/api/restart/readsb": self._restart_readsb,
            "/dashboard/api/restart/all": self._restart_all,
            "/dashboard/api/gain": self._set_gain,
            "/dashboard/api/muninn/interval": self._set_interval,
            "/dashboard/api/settings": self._save_settings,
            "/dashboard/api/settings/test-alert": self._test_alert,
            "/dashboard/api/settings/gotify-check": self._gotify_check,
        }
        handler = routes.get(path)
        if not handler:
            self._json(404, {"ok": False, "error": "not found"})
            return
        try:
            handler()
        except subprocess.TimeoutExpired:
            self._json(504, {"ok": False, "error": "operation timed out"})
        except OSError as exc:
            self._json(500, {"ok": False, "error": str(exc)})

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            return {}

    def _whoami(self) -> None:
        proc = run_cmd([str(MUNINN), str(MUNINN_PY), "--whoami", "-q"], timeout=30)
        combined = (proc.stdout + proc.stderr).strip()
        data = parse_whoami(combined)
        data["ok"] = data["ok"] and proc.returncode == 0
        if not data["ok"] and proc.returncode != 0:
            data["error"] = combined.splitlines()[-1] if combined else "whoami failed"
        self._json(200, data)

    def _flight_stats(self) -> None:
        self._json(200, cached_flight_stats())

    def _get_settings(self) -> None:
        self._json(200, get_settings())

    def _save_settings(self) -> None:
        body = self._read_body()
        try:
            result = save_settings(body)
        except ValueError as exc:
            self._json(400, {"ok": False, "error": str(exc)})
            return

        location_msg = None
        if body.get("location"):
            from settings_config import validate_location

            try:
                loc = validate_location(body["location"])
            except ValueError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            if not SET_LOCATION.exists():
                self._json(500, {"ok": False, "error": "location script not found"})
                return
            proc = run_cmd(
                ["sudo", str(SET_LOCATION), loc["lat"], loc["lon"], loc["alt"]],
                timeout=90,
            )
            combined = (proc.stdout + proc.stderr).strip()
            if proc.returncode != 0:
                self._json(
                    500,
                    {"ok": False, "error": combined.splitlines()[-1] if combined else "location update failed"},
                )
                return
            location_msg = combined.splitlines()[-1] if combined else "location updated"
            result = get_settings()
            result["saved"] = list(set((result.get("saved") or []) + ["location"]))

        refresh_status()
        result["ok"] = True
        if location_msg:
            result["location_summary"] = location_msg
        self._json(200, result)

    def _test_alert(self) -> None:
        body = self._read_body()
        alerts = body.get("alerts") if body else None
        if alerts:
            try:
                env = validate_alerts(alerts)
            except ValueError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
        else:
            from settings_config import read_env_values

            env = read_env_values()

        url = env.get("GOTIFY_URL", "").strip()
        app_token = env.get("GOTIFY_APP_TOKEN", "").strip()
        if not url or not app_token:
            self._json(400, {"ok": False, "error": "Gotify URL and app token required"})
            return

        host = "feeder"
        try:
            status = json.loads(STATUS_JSON.read_text(encoding="utf-8"))
            host = status.get("hostname", host)
        except (OSError, json.JSONDecodeError):
            pass

        ok = send_alert_with(
            url,
            app_token,
            "ADS-B feeder test",
            f"Test from {host} dashboard settings.",
            priority=5,
        )
        if not ok:
            self._json(502, {"ok": False, "error": "Gotify send failed — check URL and app token"})
            return
        self._json(200, {"ok": True, "summary": "Test message sent via Gotify"})

    def _gotify_check(self) -> None:
        body = self._read_body()
        alerts = body.get("alerts") if body else None
        if alerts:
            try:
                env = validate_alerts(alerts)
            except ValueError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
        else:
            from settings_config import read_env_values

            env = read_env_values()

        url = env.get("GOTIFY_URL", "").strip()
        app_token = env.get("GOTIFY_APP_TOKEN", "").strip()
        try:
            app = check_gotify(url, app_token)
        except ValueError as exc:
            self._json(400, {"ok": False, "error": str(exc)})
            return
        self._json(200, {"ok": True, "app": app, "summary": f"Connected to Gotify app “{app.get('name', 'app')}”"})

    def _push(self) -> None:
        target = UPLOAD_READY if UPLOAD_READY.exists() else UPLOAD
        proc = run_cmd([str(target)], timeout=90)
        combined = (proc.stdout + proc.stderr).strip()
        lines = [ln for ln in combined.splitlines() if ln.strip()]
        summary = lines[-1] if lines else "No output"
        ok = proc.returncode == 0 and "skip:" not in summary
        if "skip:" in summary:
            ok = True
        if "upload accepted" in summary or "nothing to upload" in summary:
            append_upload_history(summary, ok)
        refresh_status()
        self._json(
            200,
            {
                "ok": ok,
                "exit_code": proc.returncode,
                "summary": summary,
                "output": lines[-20:],
            },
        )

    def _restart_readsb(self) -> None:
        results = []
        for unit in restart_units("readsb"):
            proc = run_cmd(["sudo", "systemctl", "restart", unit], timeout=30)
            results.append(f"{unit}: {'ok' if proc.returncode == 0 else proc.stderr.strip()}")
        refresh_status()
        ok = all("ok" in r for r in results)
        self._json(200, {"ok": ok, "summary": "; ".join(results), "output": results})

    def _restart_all(self) -> None:
        results = []
        for unit in restart_units("all"):
            proc = run_cmd(["sudo", "systemctl", "restart", unit], timeout=30)
            results.append(f"{unit}: {'ok' if proc.returncode == 0 else proc.stderr.strip()}")
        refresh_status()
        ok = all("ok" in r for r in results)
        self._json(200, {"ok": ok, "summary": "; ".join(results), "output": results})

    def _set_gain(self) -> None:
        body = self._read_body()
        gain = str(body.get("gain", "")).strip()
        if not GAIN_RE.match(gain):
            self._json(400, {"ok": False, "error": "invalid gain (use number or auto)"})
            return
        proc = run_cmd(["sudo", "/usr/local/bin/readsb-gain", gain], timeout=30)
        combined = (proc.stdout + proc.stderr).strip()
        refresh_status()
        ok = proc.returncode == 0
        self._json(
            200,
            {
                "ok": ok,
                "summary": combined or f"gain set to {gain}",
                "output": combined.splitlines() if combined else [],
            },
        )

    def _set_interval(self) -> None:
        body = self._read_body()
        try:
            minutes = int(body.get("minutes", 5))
        except (TypeError, ValueError):
            self._json(400, {"ok": False, "error": "minutes must be an integer"})
            return
        if minutes < 1 or minutes > 60:
            self._json(400, {"ok": False, "error": "minutes must be 1–60"})
            return
        proc = run_cmd(["bash", str(SCHEDULE_SH), str(minutes)], timeout=60)
        combined = (proc.stdout + proc.stderr).strip()
        refresh_status()
        ok = proc.returncode == 0
        self._json(
            200,
            {
                "ok": ok,
                "summary": combined.splitlines()[-1] if combined else f"interval set to {minutes} min",
                "minutes": minutes,
            },
        )

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
