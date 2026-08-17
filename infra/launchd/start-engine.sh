#!/bin/zsh

set -euo pipefail

SCRIPT_DIR="${0:A:h}"
REPO_ROOT="${SCRIPT_DIR:h:h}"

set -a
source "$HOME/.config/forecast-engine.env"
set +a

export HOST=0.0.0.0
export PORT=8000

cd "$REPO_ROOT"
exec /opt/homebrew/bin/uv run python server.py
