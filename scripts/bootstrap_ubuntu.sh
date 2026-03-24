#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
INSTALL_DEV="${INSTALL_DEV:-0}"

if command -v sudo >/dev/null 2>&1; then
  SUDO="sudo"
else
  SUDO=""
fi

echo "[tg_download] Installing system packages..."
$SUDO apt-get update
$SUDO apt-get install -y git python3 python3-venv ffmpeg

echo "[tg_download] Creating virtual environment..."
"$PYTHON_BIN" -m venv "$PROJECT_DIR/.venv"

echo "[tg_download] Installing Python dependencies..."
"$PROJECT_DIR/.venv/bin/pip" install --upgrade pip
"$PROJECT_DIR/.venv/bin/pip" install -r "$PROJECT_DIR/requirements.txt"

if [ "$INSTALL_DEV" = "1" ]; then
  echo "[tg_download] Installing development dependencies..."
  "$PROJECT_DIR/.venv/bin/pip" install -r "$PROJECT_DIR/requirements-dev.txt"
fi

if [ ! -f "$PROJECT_DIR/.env" ]; then
  echo "[tg_download] Creating .env from .env.example..."
  cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
fi

cat <<EOF

[tg_download] Bootstrap complete.

Next steps:
  1. Edit $PROJECT_DIR/.env
  2. Set BOT_TOKEN
  3. Optional for OpenAI flows:
     - OPENAI_API_KEY
  4. For better Instagram reliability set:
     - INSTAGRAM_USERNAME
     - INSTAGRAM_PASSWORD
  5. Optional advanced yt-dlp fallback override:
     - INSTAGRAM_COOKIES_FILE=/absolute/path/to/cookies.txt
  6. Start bot:
     cd "$PROJECT_DIR"
     source .venv/bin/activate
     python main.py
  7. Optional Linux service:
     sudo cp "$PROJECT_DIR/deploy/tg_download_bot.service" /etc/systemd/system/tg_download_bot.service
     sudo systemctl daemon-reload
     sudo systemctl enable --now tg_download_bot.service

EOF
