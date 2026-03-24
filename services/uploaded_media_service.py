"""Общие helper'ы для uploaded media flows."""

__all__ = [
    "UploadedMediaNoAudioError",
    "cleanup_temp_dir",
    "create_temp_dir",
    "download_telegram_file",
    "ensure_status_message",
    "extract_audio_from_video",
    "finalize_status_message",
    "prepare_uploaded_audio",
    "prepare_uploaded_video_audio",
]

import os
import shutil
import subprocess
import time

from telebot.apihelper import ApiTelegramException

from config import TEMP_DIR
from utils.logging_utils import log


class UploadedMediaNoAudioError(RuntimeError):
    pass


def _is_message_not_modified_error(error):
    return "message is not modified" in str(error).lower()


def ensure_status_message(bot, chat_id, message_id, text):
    """Обновляет status message или создаёт новое сообщение, если update не удался."""
    if message_id:
        try:
            bot.edit_message_text(text, chat_id=chat_id, message_id=message_id)
            return message_id
        except ApiTelegramException as error:
            if _is_message_not_modified_error(error):
                return message_id
            log(f"Ошибка при обновлении сообщения: {error}", level="WARNING")
        except Exception as error:
            log(f"Ошибка при обновлении сообщения: {error}", level="WARNING")

    message = bot.send_message(chat_id, text)
    return message.message_id


def finalize_status_message(bot, chat_id, message_id, text):
    """Пытается финализировать status message без выброса исключения наружу."""
    if not message_id:
        return

    try:
        bot.edit_message_text(text, chat_id=chat_id, message_id=message_id)
    except ApiTelegramException as error:
        if _is_message_not_modified_error(error):
            return
        log(f"Не удалось финализировать статусное сообщение: {error}", level="DEBUG")
    except Exception as error:
        log(f"Не удалось финализировать статусное сообщение: {error}", level="DEBUG")


def create_temp_dir(prefix):
    """Создаёт уникальную временную директорию внутри TEMP_DIR."""
    temp_dir = os.path.join(TEMP_DIR, f"{prefix}_{int(time.time() * 1000)}")
    os.makedirs(temp_dir, exist_ok=True)
    return temp_dir


def cleanup_temp_dir(temp_dir):
    """Безопасно удаляет временную директорию со всем содержимым."""
    if temp_dir and os.path.exists(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)


def _resolve_extension(file_path, default_extension):
    extension = os.path.splitext(file_path or "")[1]
    if extension:
        return extension
    return default_extension


def download_telegram_file(bot, telegram_file_id, temp_dir, base_name, default_extension=""):
    """Скачивает файл из Telegram по file_id и возвращает локальный путь."""
    if not telegram_file_id:
        raise ValueError("telegram_file_id is required")

    os.makedirs(temp_dir, exist_ok=True)
    file_info = bot.get_file(telegram_file_id)
    extension = _resolve_extension(getattr(file_info, "file_path", None), default_extension)
    output_path = os.path.join(temp_dir, f"{base_name}{extension}")
    downloaded_file = bot.download_file(file_info.file_path)
    with open(output_path, "wb") as output_file:
        output_file.write(downloaded_file)
    return output_path


def extract_audio_from_video(video_path, audio_path):
    """Извлекает mono MP3-дорожку из видео для транскрипции."""
    cmd = [
        "ffmpeg",
        "-i",
        video_path,
        "-vn",
        "-ac",
        "1",
        "-ar",
        "24000",
        "-b:a",
        "64k",
        "-acodec",
        "mp3",
        "-y",
        audio_path,
    ]
    process = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if process.returncode != 0:
        raise RuntimeError(process.stderr or "ffmpeg завершился с ошибкой при извлечении аудио")
    return audio_path


def prepare_uploaded_video_audio(bot, video_file_id, temp_dir):
    """Скачивает загруженное видео и подготавливает аудио-дорожку для OpenAI."""
    from services.converter_service import get_video_info

    video_path = download_telegram_file(
        bot,
        video_file_id,
        temp_dir,
        "uploaded_video",
        default_extension=".mp4",
    )
    _, has_audio, _, _, _ = get_video_info(video_path)
    if not has_audio:
        raise UploadedMediaNoAudioError("В загруженном видео нет аудиодорожки")

    audio_path = os.path.join(temp_dir, "uploaded_video_audio.mp3")
    return extract_audio_from_video(video_path, audio_path)


def prepare_uploaded_audio(bot, audio_file_id, temp_dir):
    """Скачивает загруженный Telegram audio/voice файл во временную папку."""
    return download_telegram_file(
        bot,
        audio_file_id,
        temp_dir,
        "uploaded_audio",
        default_extension=".mp3",
    )
