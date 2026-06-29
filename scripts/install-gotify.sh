#!/usr/bin/env bash
# Run Gotify on this Pi via Docker (host port 8090).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/gotify-docker-compose.yml"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required. Install: sudo apt install -y docker.io docker-compose-v2" >&2
  echo "Then: sudo usermod -aG docker $USER  (log out and back in)" >&2
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose -f "$COMPOSE_FILE")
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose -f "$COMPOSE_FILE")
else
  echo "docker compose or docker-compose not found" >&2
  exit 1
fi

"${COMPOSE[@]}" pull
"${COMPOSE[@]}" up -d

HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo ""
echo "Gotify is running."
echo "  Web UI:  http://${HOST_IP:-127.0.0.1}:8090"
echo "  Login:   admin / admin  (change password on first visit)"
echo ""
echo "Next steps:"
echo "  1. Open the web UI → Apps → Create Application (e.g. ADS-B Feeder)"
echo "  2. Copy the app token into Dashboard → Settings → Gotify"
echo "  3. Install Gotify app on your phone → add server http://${HOST_IP:-YOUR_PI_IP}:8090"
echo ""
