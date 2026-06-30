#!/usr/bin/env bash
# Remove local dashboard/Muninn cruft after split-stack (Pi = decode + pi-agent only).
set -euo pipefail
source "$(dirname "$0")/feeder-env.sh"

KEEP_UNITS=(pi-agent.service feeder-watch.service feeder-watch.timer)

stop_disable() {
  local unit="$1"
  systemctl --user disable --now "$unit" 2>/dev/null || true
}

remove_unit() {
  local unit="$1"
  local path="$HOME/.config/systemd/user/$unit"
  stop_disable "$unit"
  [[ -f "$path" ]] && rm -f "$path"
}

echo "Stopping and removing unused dashboard systemd units..."
for unit in \
  feeder-api.service \
  feeder-push-api.service \
  feeder-dashboard.timer feeder-dashboard-update.service \
  feeder-alerts.timer feeder-alerts.service \
  feeder-flight-log.timer feeder-flight-log.service \
  feeder-daily-summary.timer feeder-daily-summary.service \
  muninn-upload.timer muninn-upload.service; do
  remove_unit "$unit"
done

systemctl --user daemon-reload
echo "Active units:"
systemctl --user list-units 'pi-agent*' 'feeder-watch*' --no-pager

echo
echo "Removing Pi-only deploy artifacts..."
rm -f /tmp/adsb-feeder-dashboard-docker.tar.gz
rm -rf "$REPO_ROOT/docker"

echo
echo "Clearing local dashboard runtime data (now on Docker)..."
rm -f \
  "$DASHBOARD_DIR/status.json" \
  "$DASHBOARD_DIR/history.json" \
  "$DASHBOARD_DIR/history.jsonl" \
  "$DASHBOARD_DIR/history-hourly.json" \
  "$DASHBOARD_DIR/history-hourly.jsonl" \
  "$DASHBOARD_DIR/alert-state.json" \
  "$DASHBOARD_DIR/watch-state.json" \
  "$DASHBOARD_DIR/watchlist.json" 2>/dev/null || true

if [[ -d "$LOG_DIR" ]]; then
  echo "Clearing local logs (flight DB + upload log on Docker now)..."
  rm -f "$LOG_DIR/flights.sqlite" "$LOG_DIR/upload.log" "$LOG_DIR/upload-history.json" 2>/dev/null || true
fi

if [[ -d "$REPO_ROOT/.venv" ]]; then
  echo "Removing Muninn venv on Pi (uploads run on Docker)..."
  rm -rf "$REPO_ROOT/.venv"
fi

if [[ -d /home/server/adsb-feeder-dashboard && "$REPO_ROOT" != /home/server/adsb-feeder-dashboard ]]; then
  echo
  echo "Note: /home/server/adsb-feeder-dashboard is a duplicate of the GitHub repo."
  echo "  Remove manually to save ~30M: rm -rf /home/server/adsb-feeder-dashboard"
fi

echo
echo "Pi cleanup done. Kept: pi-agent, feeder-watch, $REPO_ROOT"
