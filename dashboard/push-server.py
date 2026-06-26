#!/usr/bin/env python3
"""Local-only feeder dashboard API (runs as user server)."""
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from feeder_paths import (
    GEN_STATUS as GEN,
    MUNINN_PY,
    SCHEDULE_SH,
    UPLOAD_HISTORY as HISTORY,
    UPLOAD_READY,
    UPLOAD_SCRIPT as UPLOAD,
    VENV_PYTHON as MUNINN,
)

HOST, PORT = "127.0.0.1", 8765

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


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0].rstrip("/")
        if path == "/dashboard/api/whoami":
            self._whoami()
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
        for unit in ("readsb", "tar1090"):
            proc = run_cmd(["sudo", "systemctl", "restart", unit], timeout=30)
            results.append(f"{unit}: {'ok' if proc.returncode == 0 else proc.stderr.strip()}")
        refresh_status()
        ok = all("ok" in r for r in results)
        self._json(200, {"ok": ok, "summary": "; ".join(results), "output": results})

    def _restart_all(self) -> None:
        results = []
        for unit in ("readsb", "tar1090", "airplanes-feed", "airplanes-mlat"):
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
