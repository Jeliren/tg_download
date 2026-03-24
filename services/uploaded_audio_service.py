"""Сценарии расшифровки и саммари для загруженных аудиофайлов и voice."""

__all__ = [
    "summarize_uploaded_audio",
    "transcribe_uploaded_audio",
]

import os

import requests

from bot.texts import READY_FOR_MORE_TEXT
from config import OPENAI_API_KEY
from services.openai_client import OpenAITemporaryError
from services.summary_service import count_summary_chunks, summarize_transcript_text
from services.transcription_service import (
    OPENAI_TRANSCRIPTION_FILE_LIMIT,
    send_text_chunks,
    split_text_chunks,
    transcribe_audio_with_openai,
)
from services.uploaded_media_service import (
    cleanup_temp_dir as _cleanup_temp_dir,
)
from services.uploaded_media_service import (
    create_temp_dir as _create_temp_dir,
)
from services.uploaded_media_service import (
    ensure_status_message as _ensure_status_message,
)
from services.uploaded_media_service import (
    finalize_status_message as _finalize_status_message,
)
from services.uploaded_media_service import (
    prepare_uploaded_audio as _prepare_uploaded_audio,
)
from utils.file_utils import start_progress_message
from utils.logging_utils import log_event, measure_time, new_operation_id, perf_monitor


def _send_summary_result(bot, chat_id, summary, status_message_id):
    _finalize_status_message(bot, chat_id, status_message_id, "✅ Саммари готово.")
    bot.send_message(chat_id, f"🧠 Саммари загруженного аудио\n\n{summary}")
    bot.send_message(chat_id, READY_FOR_MORE_TEXT)


@perf_monitor
def transcribe_uploaded_audio(bot, chat_id, user_id, audio_file_id, message_id=None):
    """Скачивает аудио из Telegram, отправляет его в OpenAI и возвращает транскрипт пользователю."""
    op_id = new_operation_id("tg-audio-transcript")
    status_message_id = _ensure_status_message(bot, chat_id, message_id, "⏳ Запускаю расшифровку аудио...")
    progress_stop = start_progress_message(bot, chat_id, "Расшифровка загруженного аудио", status_message_id)
    temp_dir = _create_temp_dir("uploaded_audio_transcription")
    log_event("uploaded_audio_transcription_started", op=op_id, chat_id=chat_id, user_id=user_id)

    try:
        if not OPENAI_API_KEY:
            _finalize_status_message(bot, chat_id, status_message_id, "❌ Не настроен OpenAI API key.")
            bot.send_message(
                chat_id,
                "❌ Для расшифровки нужен `OPENAI_API_KEY` в конфиге бота.",
                parse_mode="Markdown",
            )
            return

        _ensure_status_message(bot, chat_id, status_message_id, "⏳ Скачиваю аудио из Telegram...")
        with measure_time("DOWNLOAD|uploaded_audio"):
            audio_path = _prepare_uploaded_audio(bot, audio_file_id, temp_dir)

        audio_size = os.path.getsize(audio_path)
        audio_size_mb = audio_size / (1024 * 1024)
        log_event(
            "uploaded_audio_transcription_audio_ready",
            op=op_id,
            chat_id=chat_id,
            size_mb=f"{audio_size_mb:.2f}",
        )
        if audio_size > OPENAI_TRANSCRIPTION_FILE_LIMIT:
            _finalize_status_message(
                bot,
                chat_id,
                status_message_id,
                "⚠️ Аудио слишком длинное для автоматической расшифровки.",
            )
            bot.send_message(
                chat_id,
                "⚠️ Аудио оказалось слишком большим для транскрипции через OpenAI "
                f"({audio_size_mb:.2f} МБ > 25 МБ). "
                "Попробуйте более короткое аудио.",
            )
            return

        _ensure_status_message(bot, chat_id, status_message_id, "⏳ Распознаю речь через OpenAI...")
        with measure_time("OPENAI|uploaded_audio_transcription"):
            transcript_text = transcribe_audio_with_openai(audio_path)

        if not transcript_text:
            raise RuntimeError("Не удалось получить текст из транскрипции загруженного аудио")

        transcript_chunks = split_text_chunks(transcript_text)
        log_event(
            "uploaded_audio_transcription_chunking",
            op=op_id,
            chat_id=chat_id,
            chunks=len(transcript_chunks),
        )
        send_text_chunks(bot, chat_id, transcript_text)
        _finalize_status_message(bot, chat_id, status_message_id, "✅ Расшифровка аудио готова.")
        log_event("uploaded_audio_transcription_finished", op=op_id, chat_id=chat_id, user_id=user_id)
        bot.send_message(chat_id, READY_FOR_MORE_TEXT)
    except OpenAITemporaryError as error:
        log_event(
            "uploaded_audio_transcription_openai_unavailable", level="ERROR", op=op_id, chat_id=chat_id, error=error
        )
        _finalize_status_message(bot, chat_id, status_message_id, "❌ OpenAI временно недоступен.")
        bot.send_message(
            chat_id, "❌ Не удалось связаться с OpenAI при расшифровке аудио. Попробуйте ещё раз чуть позже."
        )
    except requests.HTTPError as error:
        log_event("uploaded_audio_transcription_http_error", level="ERROR", op=op_id, chat_id=chat_id, error=error)
        _finalize_status_message(bot, chat_id, status_message_id, "❌ Не удалось получить расшифровку.")
        bot.send_message(chat_id, "❌ OpenAI API вернул ошибку при расшифровке аудио.")
    except Exception as error:
        log_event("uploaded_audio_transcription_failed", level="ERROR", op=op_id, chat_id=chat_id, error=error)
        _finalize_status_message(bot, chat_id, status_message_id, "❌ Не удалось расшифровать аудио.")
        bot.send_message(chat_id, "❌ Не удалось подготовить расшифровку для этого аудио.")
    finally:
        progress_stop.set()
        _cleanup_temp_dir(temp_dir)


@perf_monitor
def summarize_uploaded_audio(bot, chat_id, user_id, audio_file_id, message_id=None):
    """Скачивает аудио из Telegram, делает транскрипт и строит краткое саммари."""
    op_id = new_operation_id("tg-audio-summary")
    status_message_id = _ensure_status_message(bot, chat_id, message_id, "⏳ Готовлю саммари аудио...")
    progress_stop = start_progress_message(bot, chat_id, "Саммари загруженного аудио", status_message_id)
    temp_dir = _create_temp_dir("uploaded_audio_summary")
    log_event("uploaded_audio_summary_started", op=op_id, chat_id=chat_id, user_id=user_id)

    try:
        if not OPENAI_API_KEY:
            _finalize_status_message(bot, chat_id, status_message_id, "❌ Не настроен OpenAI API key.")
            bot.send_message(
                chat_id,
                "❌ Для саммари нужен `OPENAI_API_KEY` в конфиге бота.",
                parse_mode="Markdown",
            )
            return

        _ensure_status_message(bot, chat_id, status_message_id, "⏳ Скачиваю аудио из Telegram...")
        with measure_time("DOWNLOAD|uploaded_audio"):
            audio_path = _prepare_uploaded_audio(bot, audio_file_id, temp_dir)

        audio_size = os.path.getsize(audio_path)
        audio_size_mb = audio_size / (1024 * 1024)
        log_event(
            "uploaded_audio_summary_audio_ready",
            op=op_id,
            chat_id=chat_id,
            size_mb=f"{audio_size_mb:.2f}",
        )
        if audio_size > OPENAI_TRANSCRIPTION_FILE_LIMIT:
            _finalize_status_message(
                bot,
                chat_id,
                status_message_id,
                "⚠️ Аудио слишком длинное для автоматического саммари.",
            )
            bot.send_message(
                chat_id,
                "⚠️ Аудио оказалось слишком большим для транскрипции через OpenAI "
                f"({audio_size_mb:.2f} МБ > 25 МБ). "
                "Попробуйте более короткое аудио.",
            )
            return

        _ensure_status_message(bot, chat_id, status_message_id, "⏳ Распознаю речь через OpenAI...")
        with measure_time("OPENAI|uploaded_audio_transcription"):
            transcript_text = transcribe_audio_with_openai(audio_path)

        if not transcript_text:
            raise RuntimeError("Не удалось получить текст из транскрипции загруженного аудио")

        chunk_count = count_summary_chunks(transcript_text)
        log_event(
            "uploaded_audio_summary_chunking",
            op=op_id,
            chat_id=chat_id,
            transcript_source="openai_transcription",
            chunks=chunk_count,
        )

        _ensure_status_message(bot, chat_id, status_message_id, "⏳ Собираю саммари...")
        with measure_time("OPENAI|uploaded_audio_summary"):
            summary = summarize_transcript_text(
                transcript_text,
                title="Загруженное аудио",
                transcript_source="openai_transcription",
                transcript_language=None,
            )

        if not summary:
            raise RuntimeError("OpenAI вернул пустое саммари")

        _send_summary_result(bot, chat_id, summary, status_message_id)
        log_event("uploaded_audio_summary_finished", op=op_id, chat_id=chat_id, user_id=user_id)
    except OpenAITemporaryError as error:
        log_event("uploaded_audio_summary_openai_unavailable", level="ERROR", op=op_id, chat_id=chat_id, error=error)
        _finalize_status_message(bot, chat_id, status_message_id, "❌ OpenAI временно недоступен.")
        bot.send_message(
            chat_id, "❌ Не удалось связаться с OpenAI при подготовке саммари. Попробуйте ещё раз чуть позже."
        )
    except requests.HTTPError as error:
        log_event("uploaded_audio_summary_http_error", level="ERROR", op=op_id, chat_id=chat_id, error=error)
        _finalize_status_message(bot, chat_id, status_message_id, "❌ Не удалось получить саммари.")
        bot.send_message(chat_id, "❌ OpenAI API вернул ошибку при построении саммари.")
    except Exception as error:
        log_event("uploaded_audio_summary_failed", level="ERROR", op=op_id, chat_id=chat_id, error=error)
        _finalize_status_message(bot, chat_id, status_message_id, "❌ Не удалось получить саммари.")
        bot.send_message(chat_id, "❌ Не удалось подготовить саммари для этого аудио.")
    finally:
        progress_stop.set()
        _cleanup_temp_dir(temp_dir)
