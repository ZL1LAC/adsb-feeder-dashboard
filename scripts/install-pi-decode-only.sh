#!/usr/bin/env bash
# Pi decode-only setup: pi-agent + feeder-watch, no local dashboard.
set -euo pipefail
source "$(dirname "$0")/feeder-env.sh"

FEEDER_USER="${FEEDER_USER:-$(whoami)}"

echo "Installing Pi decode-only profile (split stack)..."
bash "$SCRIPTS_DIR/install-pi-agent.sh"

# Disable local dashboard stack if present
for unit in feeder-api feeder-push-api feeder-dashboard.timer feeder-alerts.timer feeder-flight-log.timer feeder-daily-summary.timer muninn-upload.timer; do
  systemctl --user disable --now "$unit" 2>/dev/null || true
done

if command -v lighttpd >/dev/null 2>&1 && [[ -f /etc/lighttpd/conf-enabled/89-feeder-dashboard.conf ]]; then
  echo "Tip: remove local dashboard from lighttpd if moving UI to Docker:"
  echo "  sudo rm /etc/lighttpd/conf-enabled/89-feeder-dashboard.conf && sudo systemctl reload lighttpd"
fi

echo
echo "Pi is ready as decode host. Deploy dashboard on Docker:"
echo "  cd docker && cp .env.example .env && docker compose up -d --build"
