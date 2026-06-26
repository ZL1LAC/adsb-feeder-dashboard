#!/usr/bin/env bash
# Upload to WDGoWars only when positioned aircraft exist (scheduled timer).
set -euo pipefail
source "$(dirname "$0")/../scripts/feeder-env.sh"

INPUT="${FEEDER_AIRCRAFT_JSON:-/run/readsb/aircraft.json}"
mkdir -p "$LOG_DIR"

if [[ ! -f "$INPUT" ]]; then
  echo "$(date -Iseconds) skip: no aircraft.json" >> "$LOG_DIR/upload.log"
  exit 0
fi

count="$(python3 -c "
import json, os
p = os.environ.get('FEEDER_AIRCRAFT_JSON', '$INPUT')
with open(p) as f:
    d = json.load(f)
print(sum(1 for a in d.get('aircraft', []) if a.get('lat') is not None and a.get('lon') is not None))
")"

if [[ "$count" -eq 0 ]]; then
  echo "$(date -Iseconds) skip: 0 positioned aircraft" >> "$LOG_DIR/upload.log"
  exit 0
fi

exec "$SCRIPTS_DIR/readsb-upload.sh"
