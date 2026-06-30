#!/usr/bin/env bash
# Install Muninn (WDGoWars uploader) into muninn/ submodule or clone.
set -euo pipefail
source "$(dirname "$0")/feeder-env.sh"

MUNINN_REPO="${MUNINN_REPO:-https://github.com/Yggdrasil-AI-labs/adsb-to-wdgwars.git}"
MUNINN_BRANCH="${MUNINN_BRANCH:-main}"

if [[ -f "$MUNINN_ROOT/muninn.py" ]] || [[ -x "$MUNINN_ROOT/setup.sh" ]]; then
  echo "Using existing Muninn at $MUNINN_ROOT"
elif [[ ! -d "$MUNINN_ROOT/.git" ]]; then
  echo "Cloning Muninn into $MUNINN_ROOT ..."
  mkdir -p "$(dirname "$MUNINN_ROOT")"
  rm -rf "$MUNINN_ROOT"
  git clone --depth 1 --branch "$MUNINN_BRANCH" "$MUNINN_REPO" "$MUNINN_ROOT"
fi

if [[ ! -x "$MUNINN_ROOT/setup.sh" ]]; then
  echo "Muninn setup.sh not found in $MUNINN_ROOT" >&2
  exit 1
fi

echo "Running Muninn setup (venv + dependencies)..."
cd "$MUNINN_ROOT"
if [[ -t 0 ]]; then
  ./setup.sh
else
  # Non-interactive: create venv and install deps without API key prompt
  if [[ ! -x .venv/bin/python ]]; then
    python3 -m venv .venv
  fi
  .venv/bin/python -m pip install --upgrade pip -q
  .venv/bin/python -m pip install --upgrade -r requirements.txt -q
  echo "Muninn venv ready. Save API key with: ./scripts/go-live.sh <key>"
fi

echo "Muninn installed at $MUNINN_ROOT"
