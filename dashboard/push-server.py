#!/usr/bin/env python3
"""Local-only feeder dashboard API (runs as user server)."""
import json
import re
import subprocess
import sys
import time
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from feeder_paths import (
    GEN_STATUS as GEN,
    SET_LOCATION,
    SPLIT_MODE,
    STATUS_JSON,
    UPLOAD_HISTORY as HISTORY,
    UPLOAD_READY,
    UPLOAD_SCRIPT as UPLOAD,
)
from feeder_profile import restart_units
from feeder_pi import configured as pi_configured, restart_all as pi_restart_all
from feeder_pi import restart_readsb as pi_restart_readsb
from feeder_pi import set_gain as pi_set_gain
from feeder_pi import set_location as pi_set_location
from flight_stats import get_flight_stats
from muninn_config import (
    muninn_api_key_set,
    muninn_status_dict,
    run_whoami,
    save_api_key,
    sync_upload_timer,
    upload_history,
)
from notify import check_gotify, send_alert_with
from settings_config import (
    get_settings,
    read_env_values,
    save_settings,
    validate_alerts,
    validate_wdgwars,
    _wdgwars_enabled,
    _wdgwars_interval,
)

HOST = os.environ.get("FEEDER_API_HOST", "127.0.0.1")
PORT = int(os.environ.get("FEEDER_API_PORT", "8765"))
FLIGHT_STATS_CACHE_TTL_S = 60
_flight_stats_cache: dict = {"at": 0.0, "data": None}

GAIN_RE = re.compile(r"^[0-9]+(\.[0-9]+)?$|^auto$")


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
    HISTORY.write_text(json.dumps(hist[-50:], indent=2))


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
        if path == "/dashboard/api/muninn/config":
            self._muninn_config()
            return
        if path == "/dashboard/api/muninn/history":
            self._muninn_history()
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
            "/dashboard/api/muninn/test-key": self._muninn_test_key,
            "/dashboard/api/muninn/save-key": self._muninn_save_key,
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
        data = run_whoami()
        self._json(200, data)

    def _muninn_config(self) -> None:
        env = read_env_values()
        api_key_set = muninn_api_key_set()
        enabled = _wdgwars_enabled(env, api_key_set)
        interval = _wdgwars_interval(env)
        self._json(200, {"ok": True, **muninn_status_dict(enabled, interval)})

    def _muninn_history(self) -> None:
        self._json(200, upload_history())

    def _muninn_test_key(self) -> None:
        body = self._read_body()
        api_key = str(body.get("key", "")).strip()
        if not api_key:
            if not muninn_api_key_set():
                self._json(400, {"ok": False, "error": "API key required"})
                return
            data = run_whoami()
        else:
            data = run_whoami(api_key)
        if not data.get("ok"):
            self._json(400, {"ok": False, "error": data.get("error", "invalid API key")})
            return
        user = data.get("user") or "player"
        self._json(200, {"ok": True, "user": user, "summary": f"API key OK for {user}"})

    def _muninn_save_key(self) -> None:
        body = self._read_body()
        api_key = str(body.get("key", "")).strip()
        if not api_key:
            self._json(400, {"ok": False, "error": "API key required"})
            return
        try:
            save_api_key(api_key)
            data = run_whoami()
        except ValueError as exc:
            self._json(400, {"ok": False, "error": str(exc)})
            return
        if not data.get("ok"):
            self._json(400, {"ok": False, "error": data.get("error", "key saved but whoami failed")})
            return
        env = read_env_values()
        enabled = _wdgwars_enabled(env, True)
        interval = _wdgwars_interval(env)
        timer_msg = None
        if enabled:
            try:
                timer_msg = sync_upload_timer(True, interval, True)
            except ValueError as exc:
                self._json(500, {"ok": False, "error": str(exc)})
                return
        refresh_status()
        self._json(
            200,
            {
                "ok": True,
                "user": data.get("user"),
                "summary": f"API key saved for {data.get('user', 'player')}",
                "timer_summary": timer_msg,
                "wdgwars": muninn_status_dict(enabled, interval),
            },
        )

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
            if not SET_LOCATION.exists() and not (SPLIT_MODE and pi_configured()):
                self._json(500, {"ok": False, "error": "location script not found"})
                return
            if SPLIT_MODE and pi_configured():
                proc_data = pi_set_location(loc["lat"], loc["lon"], loc["alt"])
                if not proc_data.get("ok"):
                    self._json(500, {"ok": False, "error": proc_data.get("error", "location update failed")})
                    return
                location_msg = proc_data.get("summary", "location updated")
            else:
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
        if SPLIT_MODE and pi_configured():
            data = pi_restart_readsb()
            refresh_status()
            self._json(200, data)
            return
        results = []
        for unit in restart_units("readsb"):
            proc = run_cmd(["sudo", "systemctl", "restart", unit], timeout=30)
            results.append(f"{unit}: {'ok' if proc.returncode == 0 else proc.stderr.strip()}")
        refresh_status()
        ok = all("ok" in r for r in results)
        self._json(200, {"ok": ok, "summary": "; ".join(results), "output": results})

    def _restart_all(self) -> None:
        if SPLIT_MODE and pi_configured():
            data = pi_restart_all()
            refresh_status()
            self._json(200, data)
            return
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
        if SPLIT_MODE and pi_configured():
            data = pi_set_gain(gain)
            refresh_status()
            self._json(200, data)
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
        from muninn_config import apply_upload_interval

        try:
            summary = apply_upload_interval(minutes)
        except ValueError as exc:
            self._json(500, {"ok": False, "error": str(exc)})
            return
        from settings_config import write_env_values

        write_env_values({"WDGWARS_UPLOAD_INTERVAL_MIN": str(minutes)})
        refresh_status()
        self._json(200, {"ok": True, "summary": summary, "minutes": minutes})

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
