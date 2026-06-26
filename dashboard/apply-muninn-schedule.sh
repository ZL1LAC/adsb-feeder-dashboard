#!/usr/bin/env bash
set -euo pipefail
INTERVAL="${1:-5}"
source "$(dirname "$0")/../scripts/feeder-env.sh"
cd "$MUNINN_ROOT"

"$MUNINN_ROOT/.venv/bin/python" muninn.py --schedule \
  --schedule-mode periodic \
  --schedule-input "${FEEDER_AIRCRAFT_JSON:-/run/readsb/aircraft.json}" \
  --schedule-interval "$INTERVAL"

python3 - "$HOME/.config/systemd/user/muninn-upload.service" "$DASHBOARD_DIR/upload-if-ready.sh" "$LOG_DIR/upload.log" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
upload = sys.argv[2]
log = sys.argv[3]
text = path.read_text() if path.exists() else ""
desc = "Muninn ADS-B upload (one-shot)"
for line in text.splitlines():
    if line.startswith("Description="):
        desc = line.split("=", 1)[1]
        break
path.write_text(
    "[Unit]\n"
    f"Description={desc}\n"
    "# managed-by-feeder-dashboard\n"
    "\n"
    "[Service]\n"
    "Type=oneshot\n"
    "StandardInput=null\n"
    "TimeoutStartSec=60\n"
    f"StandardOutput=append:{log}\n"
    f"StandardError=append:{log}\n"
    f"ExecStart={upload}\n"
)
PY

systemctl --user daemon-reload
systemctl --user enable muninn-upload.timer
systemctl --user restart muninn-upload.timer
echo "Muninn schedule: every ${INTERVAL} min via upload-if-ready.sh"
