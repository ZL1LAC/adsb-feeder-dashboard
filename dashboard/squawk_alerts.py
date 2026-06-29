"""Squawk alert configuration from feeder.env."""
from __future__ import annotations

import os
import re

import feeder_paths  # noqa: F401 — load feeder.env

EMERGENCY_SQUAWKS = frozenset({"7500", "7600", "7700"})

SQUAWK_LABELS: dict[str, str] = {
    "7500": "Hijack",
    "7600": "Radio failure",
    "7700": "Emergency",
    "1200": "VFR",
    "2000": "IFR",
    "4000": "Military intercept",
}


def _truthy(raw: str | None, default: bool = True) -> bool:
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def parse_squawk_codes(raw: str) -> list[str]:
    items: list[str] = []
    for part in re.split(r"[\s,]+", raw or ""):
        code = part.strip()
        if not code:
            continue
        if not (len(code) == 4 and code.isdigit()):
            raise ValueError(f"invalid squawk code: {code} (use 4 digits, e.g. 7700)")
        if code == "0000":
            continue
        if code not in items:
            items.append(code)
    return items


def squawk_label(code: str) -> str:
    return SQUAWK_LABELS.get(code, f"Squawk {code}")


def squawk_priority(code: str) -> int:
    if code in EMERGENCY_SQUAWKS:
        return 10
    return 7


def load_squawk_codes() -> set[str]:
    if not _truthy(os.environ.get("ALERT_SQUAWK_ENABLED"), default=True):
        return set()
    codes: set[str] = set()
    if _truthy(os.environ.get("ALERT_SQUAWK_EMERGENCY"), default=True):
        codes.update(EMERGENCY_SQUAWKS)
    extra = os.environ.get("ALERT_SQUAWK_EXTRA", "")
    for code in parse_squawk_codes(extra):
        codes.add(code)
    return codes


def squawk_settings_dict() -> dict:
    return {
        "enabled": _truthy(os.environ.get("ALERT_SQUAWK_ENABLED"), default=True),
        "emergency": _truthy(os.environ.get("ALERT_SQUAWK_EMERGENCY"), default=True),
        "extra_codes": parse_squawk_codes(os.environ.get("ALERT_SQUAWK_EXTRA", "")),
        "active_codes": sorted(load_squawk_codes()),
    }


def validate_squawk_settings(payload: dict) -> dict[str, str]:
    enabled = bool(payload.get("enabled", True))
    emergency = bool(payload.get("emergency", True))
    extra_raw = payload.get("extra_codes", "")
    if isinstance(extra_raw, list):
        extra_raw = "\n".join(str(c) for c in extra_raw)
    extra_codes = parse_squawk_codes(str(extra_raw)) if extra_raw else []
    if not enabled:
        emergency = False
        extra_codes = []
    return {
        "ALERT_SQUAWK_ENABLED": "true" if enabled else "false",
        "ALERT_SQUAWK_EMERGENCY": "true" if emergency else "false",
        "ALERT_SQUAWK_EXTRA": ",".join(extra_codes),
    }
