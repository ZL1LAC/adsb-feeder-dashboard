#!/usr/bin/env bash
# Upload readsb aircraft.json to WDGoWars via Muninn.
set -euo pipefail
source "$(dirname "$0")/feeder-env.sh"

INPUT="${FEEDER_AIRCRAFT_JSON:-/run/readsb/aircraft.json}"
PY="$MUNINN_ROOT/.venv/bin/python"

if [[ ! -x "$PY" ]]; then
  echo "Run ./scripts/install-muninn.sh first to create the Muninn virtual environment." >&2
  exit 1
fi

if [[ ! -f "$INPUT" ]]; then
  if ! systemctl is-active --quiet readsb; then
    echo "readsb is not running — SDR may be unplugged or USB failed." >&2
    echo "Check: lsusb  (look for RTL-SDR / 0bda:2832)" >&2
    echo "Then: sudo systemctl restart readsb" >&2
  else
    echo "No aircraft data yet at $INPUT (readsb still starting?)." >&2
  fi
  exit 1
fi

exec "$PY" "$MUNINN_ROOT/muninn.py" "$INPUT" --upload --no-save "$@"
