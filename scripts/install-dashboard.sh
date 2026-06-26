#!/usr/bin/env bash
# Install systemd units, lighttpd config, and sudoers for the feeder dashboard.
set -euo pipefail
source "$(dirname "$0")/feeder-env.sh"

FEEDER_USER="${FEEDER_USER:-$(whoami)}"
MUNINN_ROOT="${FEEDER_MUNINN_ROOT:-$REPO_ROOT/muninn}"
INSTALL_DIR="$REPO_ROOT/install"
USER_SYSTEMD="$HOME/.config/systemd/user"
LIGHTTPD_DEST="/etc/lighttpd/conf-enabled/89-feeder-dashboard.conf"
SUDOERS_DEST="/etc/sudoers.d/feeder-ops"

subst() {
  local infile="$1" outfile="$2"
  sed \
    -e "s|@REPO_ROOT@|$REPO_ROOT|g" \
    -e "s|@MUNINN_ROOT@|$MUNINN_ROOT|g" \
    -e "s|@FEEDER_USER@|$FEEDER_USER|g" \
    "$infile" > "$outfile"
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "Missing required command: $1" >&2; exit 1; }
}

need_cmd python3
need_cmd systemctl

mkdir -p "$USER_SYSTEMD" "$LOG_DIR" "$DASHBOARD_DIR"
chmod +x "$SCRIPTS_DIR"/*.sh "$DASHBOARD_DIR"/*.sh 2>/dev/null || true

# Write feeder.env if missing
if [[ ! -f "$REPO_ROOT/feeder.env" ]]; then
  cp "$REPO_ROOT/feeder.env.example" "$REPO_ROOT/feeder.env"
  sed -i "s|^REPO_ROOT=.*|REPO_ROOT=$REPO_ROOT|" "$REPO_ROOT/feeder.env"
  sed -i "s|^FEEDER_USER=.*|FEEDER_USER=$FEEDER_USER|" "$REPO_ROOT/feeder.env"
  sed -i "s|^FEEDER_MUNINN_ROOT=.*|FEEDER_MUNINN_ROOT=$MUNINN_ROOT|" "$REPO_ROOT/feeder.env"
fi

echo "Installing systemd user units..."
for unit in feeder-api.service feeder-dashboard-update.service feeder-dashboard.timer feeder-watch.service feeder-watch.timer; do
  subst "$INSTALL_DIR/systemd/${unit}.in" "$USER_SYSTEMD/${unit}"
done

systemctl --user daemon-reload
systemctl --user enable --now feeder-api.service
systemctl --user enable --now feeder-dashboard.timer
systemctl --user enable --now feeder-watch.timer

if command -v lighttpd >/dev/null 2>&1; then
  echo "Installing lighttpd dashboard config..."
  if [[ "$(id -u)" -eq 0 ]]; then
    subst "$INSTALL_DIR/lighttpd/89-feeder-dashboard.conf.in" "$LIGHTTPD_DEST"
    systemctl reload lighttpd || systemctl restart lighttpd
  else
    subst "$INSTALL_DIR/lighttpd/89-feeder-dashboard.conf.in" "/tmp/89-feeder-dashboard.conf"
    echo "Run: sudo cp /tmp/89-feeder-dashboard.conf $LIGHTTPD_DEST && sudo systemctl reload lighttpd"
  fi
else
  echo "lighttpd not found — install it or proxy /dashboard/ manually." >&2
fi

if [[ "$(id -u)" -eq 0 ]]; then
  subst "$INSTALL_DIR/sudoers/feeder-ops.in" "$SUDOERS_DEST"
  chmod 440 "$SUDOERS_DEST"
  visudo -c -f "$SUDOERS_DEST"
else
  subst "$INSTALL_DIR/sudoers/feeder-ops.in" "/tmp/feeder-ops"
  echo "Run: sudo cp /tmp/feeder-ops $SUDOERS_DEST && sudo chmod 440 $SUDOERS_DEST"
fi

# Initial status.json
if [[ -x "$MUNINN_ROOT/.venv/bin/python" ]]; then
  FEEDER_REPO_ROOT="$REPO_ROOT" FEEDER_MUNINN_ROOT="$MUNINN_ROOT" \
    "$MUNINN_ROOT/.venv/bin/python" "$DASHBOARD_DIR/gen-status.py" || true
fi

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo "Dashboard installed."
echo "  UI:  http://${IP:-localhost}/dashboard/"
echo "  Map: http://${IP:-localhost}/tar1090/"
