#!/usr/bin/env bash
# Update station lat/lon/alt in /etc/default/airplanes and sync readsb.
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "Usage: $0 LAT LON [ALT]" >&2
  exit 1
fi

LAT="$1"
LON="$2"
ALT="${3:-12m}"

AIRPLANES="${FEEDER_LOCATION_FILE:-/etc/default/airplanes}"
READSB="${FEEDER_READSB_DEFAULT:-/etc/default/readsb}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python3 - "$AIRPLANES" "$LAT" "$LON" "$ALT" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
lat, lon, alt = sys.argv[2], sys.argv[3], sys.argv[4]

try:
    float(lat)
    float(lon)
except ValueError:
    raise SystemExit("LAT and LON must be numbers")

if not path.exists():
    raise SystemExit(f"Missing {path}")

text = path.read_text(encoding="utf-8")
updates = {
    "LATITUDE": f'"{lat}"',
    "LONGITUDE": f'"{lon}"',
    "ALTITUDE": f'"{alt}"',
}

out_lines = []
seen = set()
for line in text.splitlines():
    matched = False
    for key, value in updates.items():
        if line.strip().startswith(f"{key}="):
            out_lines.append(f"{key}={value}")
            seen.add(key)
            matched = True
            break
    if not matched:
        out_lines.append(line)

for key, value in updates.items():
    if key not in seen:
        out_lines.append(f"{key}={value}")

path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
print(f"Updated {path}: {lat}, {lon}, {alt}")
PY

export FEEDER_LOCATION_FILE="$AIRPLANES"
export FEEDER_READSB_DEFAULT="$READSB"
bash "$SCRIPT_DIR/apply-readsb-location.sh"
