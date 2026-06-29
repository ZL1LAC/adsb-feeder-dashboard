"""Send feeder alerts via Gotify (self-hosted, free, unlimited)."""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

import feeder_paths  # noqa: F401 — load feeder.env

GOTIFY_URL_RE = re.compile(r"^https?://[^\s/]+(?::\d+)?(?:/.*)?$", re.IGNORECASE)


def _normalize_app_token(raw: str) -> str:
    token = raw.strip().strip('"').strip("'")
    if token.lower().startswith("token="):
        token = token.split("=", 1)[1].strip()
    return token


def _validate_app_token(app_token: str) -> None:
    if not app_token:
        return
    if " " in app_token or "\n" in app_token or "\t" in app_token:
        raise ValueError("app token must not contain spaces — paste only the token from Gotify → Apps")
    if len(app_token) < 4 or len(app_token) > 256:
        raise ValueError("app token length looks wrong — copy from Gotify → Apps")
    if not app_token.startswith("A"):
        raise ValueError(
            "use an application token from Gotify → Apps (starts with A), not a client/phone token"
        )


def _url() -> str:
    return os.environ.get("GOTIFY_URL", "").strip().rstrip("/")


def _app_token() -> str:
    return _normalize_app_token(os.environ.get("GOTIFY_APP_TOKEN", ""))


def alerts_enabled() -> bool:
    return bool(_url() and _app_token())


def validate_gotify_config(url: str, app_token: str) -> tuple[str, str]:
    url = url.strip().rstrip("/")
    app_token = _normalize_app_token(app_token)
    if not url and not app_token:
        return "", ""
    if url and not GOTIFY_URL_RE.match(url):
        raise ValueError("Gotify URL must start with http:// or https:// (e.g. http://alerts.lacdh.live)")
    _validate_app_token(app_token)
    if bool(url) != bool(app_token):
        raise ValueError("set both Gotify URL and app token, or leave both empty to disable alerts")
    return url, app_token


def send_alert(title: str, message: str, priority: int = 5) -> bool:
    if not alerts_enabled():
        return False
    return send_alert_with(_url(), _app_token(), title, message, priority)


def send_alert_with(
    url: str,
    app_token: str,
    title: str,
    message: str,
    priority: int = 5,
) -> bool:
    url = url.strip().rstrip("/")
    app_token = _normalize_app_token(app_token)
    if not url or not app_token:
        return False
    priority = max(1, min(10, int(priority)))
    endpoint = f"{url}/message?token={urllib.parse.quote(app_token, safe='')}"
    payload = json.dumps(
        {
            "title": title[:250],
            "message": message[:5000],
            "priority": priority,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, OSError):
        return False


def check_gotify(url: str, app_token: str) -> dict:
    """Verify Gotify is reachable (app tokens may only POST /message)."""
    url = url.strip().rstrip("/")
    app_token = _normalize_app_token(app_token)
    validate_gotify_config(url, app_token)
    endpoint = f"{url}/message?token={urllib.parse.quote(app_token, safe='')}"
    payload = json.dumps(
        {
            "title": "ADS-B feeder",
            "message": "Connection test from feeder dashboard.",
            "priority": 1,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise ValueError("Gotify rejected the app token — use Apps → your app → token (not client token)") from exc
        raise ValueError(f"Gotify HTTP {exc.code}") from exc
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not reach Gotify at {url}: {exc}") from exc
    return {
        "name": data.get("title", "connected"),
        "id": data.get("id"),
    }
