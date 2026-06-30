#!/usr/bin/env python3
"""Pull aircraft/stats from Pi agent into local cache (split-stack Docker side)."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from feeder_paths import AIRCRAFT_JSON, STATS_JSON
from feeder_pi import configured, get_aircraft, get_stats

INTERVAL_S = float(__import__("os").environ.get("PI_SYNC_INTERVAL_S", "2"))


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def sync_once() -> bool:
    aircraft = get_aircraft()
    if aircraft.get("aircraft") is not None or aircraft.get("now") is not None:
        write_json(AIRCRAFT_JSON, aircraft)
    stats = get_stats()
    if stats.get("total") is not None:
        write_json(STATS_JSON, stats)
    return True


def main() -> None:
    if not configured():
        print("split mode requires PI_AGENT_URL", file=sys.stderr)
        sys.exit(1)
    while True:
        try:
            sync_once()
        except OSError as exc:
            print(f"sync error: {exc}", file=sys.stderr)
        time.sleep(INTERVAL_S)


if __name__ == "__main__":
    main()
