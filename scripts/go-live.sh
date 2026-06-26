#!/usr/bin/env bash
# Save WDGoWars API key and enable Muninn live uploads from readsb.
set -euo pipefail
source "$(dirname "$0")/feeder-env.sh"

INTERVAL="${2:-5}"

if [[ ! -x "$MUNINN_ROOT/.venv/bin/python" ]]; then
  echo "Run ./scripts/install-muninn.sh first." >&2
  exit 1
fi

if [[ -z "${1:-}" ]]; then
  echo "Usage: $0 <WDGoWars-API-key> [interval-minutes]" >&2
  echo "Get your key from https://wdgwars.pl/ → profile → API Key" >&2
  exit 1
fi

"$MUNINN_ROOT/.venv/bin/python" "$MUNINN_ROOT/muninn.py" --save-key "$1"

bash "$DASHBOARD_DIR/apply-muninn-schedule.sh" "$INTERVAL"

echo
echo "Live uploads enabled (every ${INTERVAL} min, skip when no positioned aircraft)."
echo "  systemctl --user status muninn-upload.timer"
echo "  ./scripts/tail-log.sh"
