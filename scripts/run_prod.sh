#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec env -u BOT_TOKEN -u TG_DOWNLOAD_ENV -u TG_DOWNLOAD_ENV_FILE \
  "$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/main.py"
