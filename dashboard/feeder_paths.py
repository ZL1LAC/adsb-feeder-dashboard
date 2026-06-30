"""Resolve feeder repo paths from feeder.env or install layout."""
from __future__ import annotations

import os
from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(os.environ.get("FEEDER_REPO_ROOT", DASHBOARD_DIR.parent))
MUNINN_ROOT = Path(os.environ.get("FEEDER_MUNINN_ROOT", REPO_ROOT / "muninn"))


def _load_env_file() -> None:
    env_path = REPO_ROOT / "feeder.env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env_file()

if os.environ.get("FEEDER_REPO_ROOT"):
    REPO_ROOT = Path(os.environ["FEEDER_REPO_ROOT"])
if os.environ.get("FEEDER_MUNINN_ROOT"):
    MUNINN_ROOT = Path(os.environ["FEEDER_MUNINN_ROOT"])

from feeder_profile import FEED_PROFILE  # noqa: E402

DEPLOY_MODE = os.environ.get("FEEDER_DEPLOY_MODE", "").strip().lower()
SPLIT_MODE = DEPLOY_MODE == "split"
DATA_DIR = Path(os.environ.get("FEEDER_DATA_DIR", REPO_ROOT / "data" if SPLIT_MODE else REPO_ROOT))

_default_location = (
    "/opt/adsb/config/.env" if FEED_PROFILE == "adsbim" else "/etc/default/airplanes"
)
_default_aircraft = (
    DATA_DIR / "cache" / "aircraft.json" if SPLIT_MODE else Path("/run/readsb/aircraft.json")
)
_default_stats = DATA_DIR / "cache" / "stats.json" if SPLIT_MODE else Path("/run/readsb/stats.json")

AIRCRAFT_JSON = Path(os.environ.get("FEEDER_AIRCRAFT_JSON", str(_default_aircraft)))
LOCATION_FILE = Path(os.environ.get("FEEDER_LOCATION_FILE", _default_location))
READSB_DEFAULT = Path(os.environ.get("FEEDER_READSB_DEFAULT", "/etc/default/readsb"))
STATS_JSON = Path(os.environ.get("FEEDER_STATS_JSON", str(_default_stats)))
LOG_DIR = DATA_DIR / "logs" if SPLIT_MODE else REPO_ROOT / "logs"
DASHBOARD_DATA = DATA_DIR / "dashboard" if SPLIT_MODE else DASHBOARD_DIR
ALERT_STATE = DASHBOARD_DATA / "alert-state.json"
UPLOAD_LOG = LOG_DIR / "upload.log"
UPLOAD_HISTORY = LOG_DIR / "upload-history.json"
VENV_PYTHON = MUNINN_ROOT / ".venv" / "bin" / "python"
MUNINN_PY = MUNINN_ROOT / "muninn.py"
UPLOAD_SCRIPT = REPO_ROOT / "scripts" / "readsb-upload.sh"
UPLOAD_READY = DASHBOARD_DIR / "upload-if-ready.sh"
SCHEDULE_SH = DASHBOARD_DIR / "apply-muninn-schedule.sh"
GEN_STATUS = DASHBOARD_DIR / "gen-status.py"
SET_LOCATION = REPO_ROOT / "scripts" / "set-station-location.sh"
STATUS_JSON = DASHBOARD_DATA / "status.json"
HISTORY_LOG = DASHBOARD_DATA / "history.jsonl"
HISTORY_CHART = DASHBOARD_DATA / "history.json"
HISTORY_HOURLY_LOG = DASHBOARD_DATA / "history-hourly.jsonl"
HISTORY_HOURLY_CHART = DASHBOARD_DATA / "history-hourly.json"
WATCH_STATE = DASHBOARD_DATA / "watch-state.json"
UPLOAD_SCHEDULE = DATA_DIR / "upload-schedule.json"
