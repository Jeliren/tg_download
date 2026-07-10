#!/usr/bin/env python3
"""Локальная smoke-проверка YouTube download flows без отправки в Telegram."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_DIR = Path(__file__).resolve().parents[1]
class LocalBot:
    """Минимальный Telegram adapter: проверяет, что файл дошёл до send_* API."""

    def __init__(self):
        self.events = []

    def send_message(self, *_args, **_kwargs):
        self.events.append("message")
        return SimpleNamespace(message_id=1)

    def edit_message_text(self, *_args, **_kwargs):
        self.events.append("edit")
        return True

    def send_audio(self, _chat_id, audio, **_kwargs):
        assert audio.read(1), "audio file is empty"
        audio.seek(0)
        self.events.append("audio")
        return SimpleNamespace(message_id=2)

    def send_video(self, _chat_id, video, **_kwargs):
        assert video.read(1), "video file is empty"
        video.seek(0)
        self.events.append("video")
        return SimpleNamespace(message_id=3)


def main():
    if str(PROJECT_DIR) not in sys.path:
        sys.path.insert(0, str(PROJECT_DIR))

    from services.youtube_service import download_youtube_audio, download_youtube_video

    parser = argparse.ArgumentParser()
    parser.add_argument("--youtube", required=True, help="Public YouTube URL for a short smoke test")
    args = parser.parse_args()

    bot = LocalBot()
    download_youtube_audio(bot, 1, args.youtube, message_id=1)
    download_youtube_video(bot, 1, args.youtube, message_id=1, format_id="best")

    if "audio" not in bot.events or "video" not in bot.events:
        raise RuntimeError(f"YouTube flow did not reach both media sends: {bot.events}")
    print(f"YouTube audio and video flows passed ({', '.join(bot.events)})")


if __name__ == "__main__":
    main()
