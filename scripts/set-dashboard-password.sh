#!/usr/bin/env bash
# Enable HTTP basic auth for the Docker dashboard (browser login prompt).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DOCKER_DIR="$(cd "$SCRIPT_DIR/../docker" && pwd)"
cd "$DOCKER_DIR"

USER="${1:-admin}"
PASS="${2:-}"
if [[ -z "$PASS" ]]; then
  read -r -s -p "Dashboard password for $USER: " PASS
  echo
  [[ -n "$PASS" ]] || { echo "Password required." >&2; exit 1; }
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required to hash the password." >&2
  exit 1
fi

HASH=$(docker run --rm caddy:2-alpine caddy hash-password --plaintext "$PASS")

[[ -f .env ]] || cp .env.example .env

set_env() {
  local key="$1" val="$2"
  if grep -q "^${key}=" .env; then
    sed -i "s|^${key}=.*|${key}=${val}|" .env
  else
    echo "${key}=${val}" >> .env
  fi
}

set_env DASHBOARD_AUTH_USER "$USER"
set_env DASHBOARD_AUTH_HASH "$HASH"
cp Caddyfile.auth Caddyfile.active

echo "Dashboard login enabled."
echo "  User: $USER"
echo "  Active Caddy config: docker/Caddyfile.active"
echo
echo "Restart Caddy: cd docker && docker compose up -d caddy"
