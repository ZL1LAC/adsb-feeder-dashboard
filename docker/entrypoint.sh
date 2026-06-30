#!/usr/bin/env bash
set -euo pipefail

cd /app
mkdir -p /data/cache /data/dashboard /data/logs

if [[ ! -f /app/feeder.env ]]; then
  cp /app/feeder.env.example /app/feeder.env 2>/dev/null || true
fi

export FEEDER_REPO_ROOT=/app
export FEEDER_MUNINN_ROOT=/app/muninn
export FEEDER_DEPLOY_MODE=split
export FEEDER_DATA_DIR=/data
export FEEDER_AIRCRAFT_JSON=/data/cache/aircraft.json
export FEEDER_STATS_JSON=/data/cache/stats.json

run_loop() {
  local name="$1"
  local interval="$2"
  shift 2
  (
    while true; do
      if "$@"; then
        :
      else
        echo "[$name] failed" >&2
      fi
      sleep "$interval"
    done
  ) &
}

# shellcheck source=/dev/null
[[ -f /app/feeder.env ]] && set -a && source /app/feeder.env && set +a

echo "Starting split-stack feeder dashboard..."
python3 /app/dashboard/sync-from-pi.py &
python3 /app/dashboard/push-server.py &

run_loop gen-status 30 python3 /app/dashboard/gen-status.py
run_loop feeder-alerts 60 python3 /app/dashboard/feeder-alerts.py
run_loop flight-log 30 python3 /app/dashboard/flight-log.py

(
  while true; do
  now_hour=$(date -u +%H)
  now_min=$(date -u +%M)
  if [[ "$now_hour" == "08" && "$now_min" == "00" ]]; then
    python3 /app/dashboard/daily-summary.py || true
    sleep 120
  fi
  sleep 30
  done
) &

(
  while true; do
    sched=$(python3 - <<'PY'
import json
from pathlib import Path
p = Path("/data/upload-schedule.json")
if not p.exists():
    print("5|0")
else:
    d = json.loads(p.read_text())
    print(f"{int(d.get('minutes') or 5)}|{1 if d.get('enabled') else 0}")
PY
)
    minutes=${sched%%|*}
    enabled=${sched##*|}
    if [[ "$enabled" == "1" ]]; then
      if [[ -x /app/dashboard/upload-if-ready.sh ]]; then
        /app/dashboard/upload-if-ready.sh >> /data/logs/upload.log 2>&1 || true
      fi
      python3 - <<'PY'
import json
from datetime import datetime, timezone
from pathlib import Path
p = Path("/data/upload-schedule.json")
d = json.loads(p.read_text()) if p.exists() else {"enabled": True, "minutes": 5}
d["last_run"] = datetime.now(timezone.utc).isoformat()
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps(d, indent=2))
PY
    fi
    sleep $((minutes * 60))
  done
) &

wait
