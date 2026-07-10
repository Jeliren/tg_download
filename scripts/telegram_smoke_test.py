#!/usr/bin/env python3
"""Безопасная проверка Telegram-токена без запуска polling."""

from __future__ import annotations

import sys
from pathlib import Path

import requests

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from config import BOT_TOKEN  # noqa: E402


def main():
    token = BOT_TOKEN.strip()
    if not token or ":" not in token:
        print("BOT_TOKEN is not configured", file=sys.stderr)
        return 2

    base_url = f"https://api.telegram.org/bot{token}"
    try:
        me_response = requests.get(f"{base_url}/getMe", timeout=(10, 30))
        me_response.raise_for_status()
        me = me_response.json()

        webhook_response = requests.get(f"{base_url}/getWebhookInfo", timeout=(10, 30))
        webhook_response.raise_for_status()
        webhook = webhook_response.json().get("result") or {}
    except requests.RequestException as error:
        detail = str(error).replace(token, "<redacted-bot-token>")
        print(f"Telegram API check failed: {detail}", file=sys.stderr)
        return 1

    result = me.get("result") or {}
    if not me.get("ok") or not result.get("username"):
        print("Telegram rejected BOT_TOKEN", file=sys.stderr)
        return 1

    pending = webhook.get("pending_update_count", 0)
    has_webhook = bool(webhook.get("url"))
    print(f"Telegram bot is available: @{result['username']}")
    print(f"Webhook configured: {'yes' if has_webhook else 'no'}; pending updates: {pending}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
