#!/usr/bin/env bash
# Source repo paths for feeder shell scripts.
set -euo pipefail

_feeder_script_dir() {
  cd "$(dirname "${BASH_SOURCE[1]}")" && pwd
}

if [[ -z "${REPO_ROOT:-}" ]]; then
  _src="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  REPO_ROOT="${FEEDER_REPO_ROOT:-$_src}"
fi

MUNINN_ROOT="${FEEDER_MUNINN_ROOT:-$REPO_ROOT/muninn}"
DASHBOARD_DIR="$REPO_ROOT/dashboard"
SCRIPTS_DIR="$REPO_ROOT/scripts"
LOG_DIR="$REPO_ROOT/logs"

if [[ -f "$REPO_ROOT/feeder.env" ]]; then
  # shellcheck disable=SC1090
  set -a && source "$REPO_ROOT/feeder.env" && set +a
fi

export REPO_ROOT MUNINN_ROOT DASHBOARD_DIR SCRIPTS_DIR LOG_DIR
