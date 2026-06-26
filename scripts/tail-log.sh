#!/usr/bin/env bash
# Follow Muninn upload logs (use when user journalctl is empty).
set -euo pipefail
source "$(dirname "$0")/feeder-env.sh"
LOG="$LOG_DIR/upload.log"
mkdir -p "$LOG_DIR"
touch "$LOG"
tail -f "$LOG"
