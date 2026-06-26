#!/usr/bin/env bash
# Install airplanes.live feed (readsb + tar1090 + upstream feed).
set -euo pipefail

if [[ "$(id -u)" != "0" ]]; then
  echo "Run with sudo: sudo ./scripts/install-airplanes.sh" >&2
  exit 1
fi

IPATH=/usr/local/share/airplanes
REPO="https://github.com/airplanes-live/feed.git"
BRANCH="main"

apt-get update -qq || true
apt-get install -y --no-install-recommends git wget unzip whiptail lighttpd || true

mkdir -p "$IPATH"

if [[ -d "$IPATH/git/.git" ]]; then
  echo "Updating airplanes.live feed installer..."
  cd "$IPATH/git" && git fetch --depth 1 origin "$BRANCH" && git reset --hard FETCH_HEAD
else
  echo "Cloning airplanes.live feed installer..."
  git clone --depth 1 --branch "$BRANCH" "$REPO" "$IPATH/git"
fi

cd "$IPATH/git"
bash "$IPATH/git/setup.sh"

echo
echo "airplanes.live feed installed. Configure /etc/default/airplanes (lat/lon, USER)."
echo "Verify: systemctl status airplanes-feed airplanes-mlat readsb tar1090"
