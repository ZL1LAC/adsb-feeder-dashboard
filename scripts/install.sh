#!/usr/bin/env bash
# Top-level installer for the ADS-B feeder dashboard.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
export FEEDER_REPO_ROOT="$REPO_ROOT"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/feeder-env.sh"

FEEDER_USER="$(whoami)"
FEED_PROFILE="airplanes"
SKIP_MUNINN=0
SKIP_DASHBOARD=0
RUN_AIRPLANES=0

usage() {
  cat <<EOF
Usage: $0 [options]

Options:
  --user NAME          Feeder Linux user (default: current user)
  --profile PROFILE    airplanes | adsbim | readsb-only  (default: airplanes)
  --skip-muninn        Skip Muninn/WDGoWars setup
  --skip-dashboard     Skip dashboard systemd/lighttpd install
  --install-airplanes  Run airplanes.live feed installer (requires sudo)
  -h, --help           Show this help

Examples:
  ./scripts/install.sh --profile airplanes
  sudo ./scripts/install.sh --install-airplanes
  ./scripts/go-live.sh YOUR_WDGOWARS_API_KEY
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --user) FEEDER_USER="$2"; shift 2 ;;
    --profile) FEED_PROFILE="$2"; shift 2 ;;
    --skip-muninn) SKIP_MUNINN=1; shift ;;
    --skip-dashboard) SKIP_DASHBOARD=1; shift ;;
    --install-airplanes) RUN_AIRPLANES=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

export FEEDER_USER FEED_PROFILE

check_prereq() {
  local missing=0
  for cmd in python3 git; do
    command -v "$cmd" >/dev/null || { echo "Missing: $cmd" >&2; missing=1; }
  done
  for svc in readsb tar1090; do
    systemctl is-enabled "$svc" &>/dev/null || echo "Note: $svc not enabled yet"
  done
  [[ $missing -eq 0 ]] || exit 1
}

check_prereq

if [[ $RUN_AIRPLANES -eq 1 ]]; then
  sudo "$SCRIPT_DIR/install-airplanes.sh"
fi

if [[ "$FEED_PROFILE" == "airplanes" ]]; then
  echo "Profile: airplanes.live (ensure airplanes-feed and airplanes-mlat are running)"
  if ! systemctl is-active airplanes-feed &>/dev/null; then
    echo "  Tip: sudo ./scripts/install-airplanes.sh"
  fi
elif [[ "$FEED_PROFILE" == "adsbim" ]]; then
  echo "Profile: adsb.im (ensure adsb-docker is running)"
  if ! systemctl is-active adsb-docker &>/dev/null; then
    echo "  Tip: install adsb.im first — see docs/INSTALL-adsbim.md"
  fi
else
  echo "Profile: readsb-only (airplanes.live feed optional)"
fi

if [[ $SKIP_MUNINN -eq 0 ]]; then
  bash "$SCRIPT_DIR/install-muninn.sh"
fi

if [[ $SKIP_DASHBOARD -eq 0 ]]; then
  FEEDER_USER="$FEEDER_USER" bash "$SCRIPT_DIR/install-dashboard.sh"
fi

echo
echo "Next steps:"
echo "  1. ./scripts/go-live.sh <WDGoWars-api-key>   # enable WDGoWars uploads"
echo "  2. Open http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo localhost)/dashboard/"
echo "  Docs: docs/INSTALL-airplanes-live.md, docs/INSTALL-adsbim.md, or docs/INSTALL-readsb-only.md"
