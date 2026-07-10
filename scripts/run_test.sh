#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec env -u BOT_TOKEN \
  TG_DOWNLOAD_ENV=test \
  TG_DOWNLOAD_ENV_FILE="$PROJECT_DIR/.env.test" \
  "$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/main.py"
