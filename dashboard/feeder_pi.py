"""HTTP client for Pi agent in split-stack deployments."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

PI_AGENT_URL = os.environ.get("PI_AGENT_URL", "").rstrip("/")
PI_AGENT_TOKEN = os.environ.get("PI_AGENT_TOKEN", "").strip()


def split_mode() -> bool:
    return os.environ.get("FEEDER_DEPLOY_MODE", "").strip().lower() == "split"


def configured() -> bool:
    return split_mode() and bool(PI_AGENT_URL)


def _headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if PI_AGENT_TOKEN:
        headers["Authorization"] = f"Bearer {PI_AGENT_TOKEN}"
    return headers


def _request(method: str, path: str, body: dict | None = None, timeout: int = 15) -> dict[str, Any]:
    if not PI_AGENT_URL:
        return {"ok": False, "error": "PI_AGENT_URL not set"}
    url = f"{PI_AGENT_URL}{path}"
    data = None
    headers = _headers()
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode())
        except (OSError, json.JSONDecodeError, ValueError):
            payload = {"ok": False, "error": exc.reason}
        payload.setdefault("ok", False)
        return payload
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": str(exc)}


def get_probe() -> dict[str, Any]:
    return _request("GET", "/v1/probe")


def get_aircraft() -> dict[str, Any]:
    return _request("GET", "/v1/aircraft")


def get_stats() -> dict[str, Any]:
    return _request("GET", "/v1/stats")


def get_receiver() -> dict[str, Any]:
    return _request("GET", "/v1/receiver")


def restart_readsb() -> dict[str, Any]:
    return _request("POST", "/v1/ops/restart/readsb", {}, timeout=60)


def restart_all() -> dict[str, Any]:
    return _request("POST", "/v1/ops/restart/all", {}, timeout=60)


def set_gain(gain: str) -> dict[str, Any]:
    return _request("POST", "/v1/ops/gain", {"gain": gain}, timeout=60)


def set_location(lat: str, lon: str, alt: str) -> dict[str, Any]:
    return _request("POST", "/v1/ops/location", {"lat": lat, "lon": lon, "alt": alt}, timeout=90)
