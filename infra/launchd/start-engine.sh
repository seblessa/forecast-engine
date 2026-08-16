#!/bin/zsh

set -euo pipefail

set -a
source /Users/seb/.config/forecast-engine.env
set +a

export HOST=0.0.0.0
export PORT=8000

cd /Users/seb/Projects/forecast-engine
exec /opt/homebrew/bin/uv run python server.py
