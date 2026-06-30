#!/usr/bin/env bash
# Deploy split-stack dashboard on a Docker host.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DOCKER_DIR="$(cd "$SCRIPT_DIR/../docker" && pwd)"
cd "$DOCKER_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required." >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created docker/.env — edit PI_HOST, PI_AGENT_URL, PI_AGENT_TOKEN, Gotify, then re-run."
  exit 0
fi

# shellcheck disable=SC1091
source .env
for var in PI_HOST PI_AGENT_URL PI_AGENT_TOKEN; do
  if [[ -z "${!var:-}" || "${!var}" == *change-me* ]]; then
    echo "Set $var in docker/.env first." >&2
    exit 1
  fi
done

REPO_ROOT="$(cd "$DOCKER_DIR/.." && pwd)"
if [[ ! -f "$REPO_ROOT/feeder.env" ]]; then
  cp "$REPO_ROOT/feeder.env.example" "$REPO_ROOT/feeder.env"
fi

# Sync split-mode vars into feeder.env for the API container
set_env() {
  local key="$1" val="$2"
  if grep -q "^${key}=" "$REPO_ROOT/feeder.env"; then
    sed -i "s|^${key}=.*|${key}=${val}|" "$REPO_ROOT/feeder.env"
  else
    echo "${key}=${val}" >> "$REPO_ROOT/feeder.env"
  fi
}
set_env FEEDER_DEPLOY_MODE split
set_env PI_AGENT_URL "$PI_AGENT_URL"
set_env PI_AGENT_TOKEN "$PI_AGENT_TOKEN"
[[ -n "${GOTIFY_URL:-}" ]] && set_env GOTIFY_URL "$GOTIFY_URL"
[[ -n "${GOTIFY_APP_TOKEN:-}" ]] && set_env GOTIFY_APP_TOKEN "$GOTIFY_APP_TOKEN"

if [[ -n "${DASHBOARD_AUTH_HASH:-}" && -n "${DASHBOARD_AUTH_USER:-}" ]]; then
  cp Caddyfile.auth Caddyfile.active
  echo "Dashboard login: enabled (user ${DASHBOARD_AUTH_USER})"
else
  cp Caddyfile Caddyfile.active
  echo "Dashboard login: disabled (LAN-only). Run ../scripts/set-dashboard-password.sh to enable."
fi

if docker compose version >/dev/null 2>&1; then
  docker compose up -d --build
else
  docker-compose up -d --build
fi

echo
echo "Dashboard: http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo localhost):${DASHBOARD_PORT:-8080}/dashboard/"
echo "Live map proxied from Pi at /tar1090/"
