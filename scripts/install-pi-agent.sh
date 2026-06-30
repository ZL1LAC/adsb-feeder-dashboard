#!/usr/bin/env bash
# Install pi-agent on the decode host (Pi) for split-stack deployments.
set -euo pipefail
source "$(dirname "$0")/feeder-env.sh"

FEEDER_USER="${FEEDER_USER:-$(whoami)}"
INSTALL_DIR="$REPO_ROOT/install"
USER_SYSTEMD="$HOME/.config/systemd/user"
TOKEN="${PI_AGENT_TOKEN:-}"

subst() {
  sed \
    -e "s|@REPO_ROOT@|$REPO_ROOT|g" \
    -e "s|@MUNINN_ROOT@|${FEEDER_MUNINN_ROOT:-$REPO_ROOT/muninn}|g" \
    -e "s|@FEEDER_USER@|$FEEDER_USER|g" \
    "$1" > "$2"
}

if [[ -z "$TOKEN" ]]; then
  TOKEN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
  echo "Generated PI_AGENT_TOKEN=$TOKEN"
fi

set_env_var() {
  local key="$1" value="$2"
  if [[ ! -f "$REPO_ROOT/feeder.env" ]]; then
    cp "$REPO_ROOT/feeder.env.example" "$REPO_ROOT/feeder.env"
  fi
  if grep -q "^${key}=" "$REPO_ROOT/feeder.env"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$REPO_ROOT/feeder.env"
  else
    echo "${key}=${value}" >> "$REPO_ROOT/feeder.env"
  fi
}

set_env_var PI_AGENT_TOKEN "$TOKEN"
set_env_var PI_AGENT_PORT "${PI_AGENT_PORT:-8780}"

chmod +x "$REPO_ROOT/pi-agent/pi-agent.py"

mkdir -p "$USER_SYSTEMD"
subst "$INSTALL_DIR/systemd/pi-agent.service.in" "$USER_SYSTEMD/pi-agent.service"
subst "$INSTALL_DIR/systemd/feeder-watch.service.in" "$USER_SYSTEMD/feeder-watch.service"
subst "$INSTALL_DIR/systemd/feeder-watch.timer.in" "$USER_SYSTEMD/feeder-watch.timer"

systemctl --user daemon-reload
systemctl --user enable --now pi-agent.service
systemctl --user enable --now feeder-watch.timer

if [[ "$(id -u)" -eq 0 ]]; then
  subst "$INSTALL_DIR/sudoers/feeder-ops.in" "/etc/sudoers.d/feeder-ops"
  chmod 440 /etc/sudoers.d/feeder-ops
  visudo -c -f /etc/sudoers.d/feeder-ops
else
  subst "$INSTALL_DIR/sudoers/feeder-ops.in" "/tmp/feeder-ops"
  echo "Run: sudo cp /tmp/feeder-ops /etc/sudoers.d/feeder-ops && sudo chmod 440 /etc/sudoers.d/feeder-ops"
fi

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo "Pi agent installed."
echo "  URL:   http://${IP:-localhost}:${PI_AGENT_PORT:-8780}"
echo "  Token: $TOKEN"
echo "  Put these in docker/.env on your Docker host:"
echo "    PI_AGENT_URL=http://${IP:-pi}:8780"
echo "    PI_AGENT_TOKEN=$TOKEN"
echo "    PI_HOST=${IP:-pi}"
