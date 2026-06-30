#!/usr/bin/env bash
# Create a tarball to copy to the Docker host and run install-split-docker.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT="${1:-/tmp/adsb-feeder-dashboard-docker.tar.gz}"

cd "$REPO_ROOT/.."
tar czf "$OUT" \
  --exclude='.git' \
  --exclude='logs/*' \
  --exclude='feeder.env' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.venv' \
  adsb-feeder-dashboard/

echo "Created $OUT"
echo
echo "Pi (SDR) = 192.168.50.57   Docker (pocker) = 192.168.50.52"
echo
echo "From Pi — push tarball to Docker:"
echo "  scp $OUT server@192.168.50.52:/tmp/"
echo
echo "From Pi — push updated install script:"
echo "  scp $REPO_ROOT/scripts/install-muninn.sh server@192.168.50.52:/tmp/adsb-feeder-dashboard/scripts/"
echo
echo "On Docker (192.168.50.52) — deploy:"
echo "  cd /tmp/adsb-feeder-dashboard && ./scripts/install-split-docker.sh"
