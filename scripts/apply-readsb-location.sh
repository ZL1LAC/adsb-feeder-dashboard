#!/usr/bin/env bash
# Sync lat/lon from /etc/default/airplanes into readsb RECEIVER_OPTIONS.
# Note: readsb supports --lat and --lon only (no --alt).
set -euo pipefail

AIRPLANES="${FEEDER_LOCATION_FILE:-/etc/default/airplanes}"
READSB="${FEEDER_READSB_DEFAULT:-/etc/default/readsb}"

if [[ ! -f "$AIRPLANES" ]]; then
  echo "Missing $AIRPLANES — set airplanes.live feeder location first." >&2
  exit 1
fi
if [[ ! -f "$READSB" ]]; then
  echo "Missing $READSB" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$AIRPLANES"

LAT="${LATITUDE:-}"
LON="${LONGITUDE:-}"

if [[ -z "$LAT" || -z "$LON" ]]; then
  echo "LATITUDE/LONGITUDE not set in $AIRPLANES" >&2
  exit 1
fi

sudo python3 - "$READSB" "$LAT" "$LON" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
lat, lon = sys.argv[2], sys.argv[3]
text = path.read_text(encoding="utf-8")
lines = text.splitlines()

opts = []
for line in lines:
    if "RECEIVER_OPTIONS" in line and "=" in line:
        _, _, val = line.partition("=")
        val = val.strip().strip('"').strip("'")
        opts = val.split()
        break

def drop_flag(args, flag):
    out = []
    skip = False
    for a in args:
        if skip:
            skip = False
            continue
        if a == flag:
            skip = True
            continue
        out.append(a)
    return out

opts = drop_flag(opts, "--lat")
opts = drop_flag(opts, "--lon")
opts = drop_flag(opts, "--alt")
opts += ["--lat", lat, "--lon", lon]

new_opts = " ".join(opts)
found = False
out_lines = []
for line in lines:
    if "RECEIVER_OPTIONS" in line and "=" in line:
        key, _, _ = line.partition("=")
        out_lines.append(f'{key}="{new_opts}"')
        found = True
    else:
        out_lines.append(line)

if not found:
    out_lines.append(f'RECEIVER_OPTIONS="{new_opts}"')

path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
print(f"Updated RECEIVER_OPTIONS: --lat {lat} --lon {lon}")
PY

echo "Restarting readsb and tar1090..."
sudo systemctl restart readsb tar1090
echo "Done."
