__all__ = [
    "check_ffmpeg",
    "convert_audio_file_to_voice_message",
    "convert_video_file_to_video_note",
]

import json
import os
import subprocess
import time

from config import MAX_FILE_SIZE, TEMP_DIR
from services.uploaded_media_service import download_telegram_file
from utils.file_utils import send_with_retry
from utils.logging_utils import (
    log,
    log_event,
    log_memory_usage,
    log_perf,
    measure_time,
    new_operation_id,
    perf_monitor,
)

VIDEO_NOTE_TARGET_SIZE = 512
VIDEO_NOTE_SAFE_MAX_SIZE_MB = 8
VOICE_MESSAGE_BITRATE = "48k"
VIDEO_NOTE_ENCODING_PROFILES = (
    {"scale": 512, "crf": 21, "preset": "medium", "audio": True, "audio_bitrate": "112k"},
    {"scale": 512, "crf": 24, "preset": "medium", "audio": True, "audio_bitrate": "96k"},
    {"scale": 384, "crf": 26, "preset": "fast", "audio": True, "audio_bitrate": "80k"},
    {"scale": 384, "crf": 28, "preset": "fast", "audio": False, "audio_bitrate": "0"},
)


@perf_monitor
def check_ffmpeg():
    """Проверка наличия ffmpeg в системе"""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


@perf_monitor
def get_video_info(input_path):
    """Получение информации о видео через ffprobe"""
    try:
        cmd = [
            'ffprobe', 
            '-v', 'quiet', 
            '-print_format', 'json', 
            '-show_format', 
            '-show_streams', 
            input_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        info = json.loads(result.stdout)
        
        # Проверяем наличие аудио и получаем размеры видео
        has_audio = any(stream['codec_type'] == 'audio' for stream in info['streams'])
        video_stream = next((stream for stream in info['streams'] if stream['codec_type'] == 'video'), None)
        
        if not video_stream:
            return None, False, 0, 0, 0
            
        width = int(video_stream.get('width', 0))
        height = int(video_stream.get('height', 0))
        
        # Получаем длительность в секундах
        duration = 0
        if 'duration' in video_stream:
            duration = float(video_stream['duration'])
        elif 'duration' in info.get('format', {}):
            duration = float(info['format']['duration'])
            
        return info, has_audio, width, height, duration
    except Exception as e:
        log(f"Ошибка при получении информации о видео: {e}", level="ERROR")
        return None, False, 0, 0, 0


def _build_video_note_ffmpeg_command(input_path, output_path, crop_cmd, profile):
    scale_cmd = f"scale={profile['scale']}:{profile['scale']}:flags=lanczos"
    cmd = [
        'ffmpeg',
        '-i', input_path,
        '-vf', f"{crop_cmd},{scale_cmd}",
        '-c:v', 'libx264',
        '-preset', profile['preset'],
        '-crf', str(profile['crf']),
        '-profile:v', 'high',
        '-level', '4.0',
        '-pix_fmt', 'yuv420p',
        '-movflags', '+faststart',
    ]

    if profile["audio"]:
        cmd.extend([
            '-c:a', 'aac',
            '-b:a', profile['audio_bitrate'],
            '-ar', '44100',
        ])
    else:
        cmd.append('-an')

    cmd.extend([
        '-y',
        output_path
    ])
    return cmd


def _build_voice_message_ffmpeg_command(input_path, output_path):
    return [
        "ffmpeg",
        "-i",
        input_path,
        "-vn",
        "-ac",
        "1",
        "-c:a",
        "libopus",
        "-b:a",
        VOICE_MESSAGE_BITRATE,
        "-vbr",
        "on",
        "-compression_level",
        "10",
        "-application",
        "voip",
        "-ar",
        "48000",
        "-y",
        output_path,
    ]


def _encode_video_note(input_path, output_path, crop_cmd, profiles):
    last_error = None

    for index, profile in enumerate(profiles, 1):
        cmd = _build_video_note_ffmpeg_command(input_path, output_path, crop_cmd, profile)
        log(
            "Пробую профиль video note "
            f"#{index}: scale={profile['scale']} crf={profile['crf']} "
            f"audio={'on' if profile['audio'] else 'off'}"
        )

        with measure_time(f"CONVERT|video_note_profile_{index}"):
            process = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if process.returncode != 0:
            last_error = process.stderr or "ffmpeg завершился с ошибкой"
            log(f"Профиль video note #{index} не сработал: {last_error}", level="WARNING")
            continue

        file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
        log_perf(f"FILE_SIZE|video_note_profile_{index}|{file_size_mb:.2f}MB")
        if file_size_mb <= VIDEO_NOTE_SAFE_MAX_SIZE_MB:
            return profile, file_size_mb

        log(
            f"Профиль video note #{index} дал слишком большой файл ({file_size_mb:.2f} MB), "
            "пробую более компактный вариант",
            level="INFO",
        )

    raise RuntimeError(last_error or "Не удалось подобрать профиль для video note")


def _safe_remove_file(path, description):
    if not path or not os.path.exists(path):
        return

    try:
        os.remove(path)
    except Exception as error:
        log(f"Ошибка при удалении {description}: {error}", level="ERROR")


@perf_monitor
def convert_audio_file_to_voice_message(bot, chat_id, user_id, audio_file_id):
    input_path = None
    output_path = None
    op_id = new_operation_id("convert-audio")

    try:
        if not check_ffmpeg():
            bot.send_message(chat_id, "❌ Для обработки аудио нужен ffmpeg.")
            return False

        os.makedirs(TEMP_DIR, exist_ok=True)
        file_id = f"{user_id or chat_id}_{int(time.time())}"
        input_path = download_telegram_file(
            bot,
            audio_file_id,
            TEMP_DIR,
            f"temp_audio_{file_id}",
            default_extension=".mp3",
        )
        output_path = os.path.join(TEMP_DIR, f"voice_message_{file_id}.ogg")

        log_event("voice_message_started", op=op_id, chat_id=chat_id, user_id=user_id)

        cmd = _build_voice_message_ffmpeg_command(input_path, output_path)
        with measure_time("CONVERT|voice_message"):
            process = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if process.returncode != 0:
            raise RuntimeError(process.stderr or "ffmpeg завершился с ошибкой")

        file_size = os.path.getsize(output_path)
        file_size_mb = file_size / (1024 * 1024)
        log_perf(f"FILE_SIZE|voice_message|{file_size_mb:.2f}MB")

        if file_size > MAX_FILE_SIZE:
            log_event("voice_message_rejected_large", op=op_id, chat_id=chat_id, size_mb=f"{file_size_mb:.2f}")
            bot.send_message(
                chat_id,
                f"⚠️ Аудиосообщение получилось слишком большим для Telegram ({file_size_mb:.2f} МБ > 50 МБ).",
            )
            return False

        with measure_time("UPLOAD|voice_message_upload"):
            with open(output_path, "rb") as voice_file:
                sent_message = send_with_retry(
                    bot.send_voice,
                    chat_id,
                    voice_file,
                    caption="✅ Ваше аудиосообщение",
                    timeout=180,
                    max_retries=3,
                )

        if sent_message is None:
            log_event("voice_message_upload_failed", level="ERROR", op=op_id, chat_id=chat_id, user_id=user_id)
            bot.send_message(chat_id, "❌ Не удалось отправить аудиосообщение в Telegram.")
            return False

        bot.send_message(chat_id, "✅ Аудиосообщение успешно создано!")
        log_event("voice_message_finished", op=op_id, chat_id=chat_id, user_id=user_id)
        return True
    except subprocess.TimeoutExpired:
        log("Превышено время ожидания ffmpeg при обработке аудио", level="ERROR")
        log_event("voice_message_timeout", level="ERROR", op=op_id, chat_id=chat_id, user_id=user_id)
        bot.send_message(chat_id, "❌ Превышено время обработки аудио. Попробуйте файл покороче.")
        return False
    except Exception as e:
        log(f"Ошибка при конвертации аудио: {e}", level="ERROR")
        log_event("voice_message_failed", level="ERROR", op=op_id, chat_id=chat_id, user_id=user_id, error=e)
        bot.send_message(
            chat_id,
            "❌ Не удалось подготовить аудиосообщение. Попробуйте ещё раз с другим файлом.",
        )
        return False
    finally:
        if input_path and os.path.exists(input_path):
            try:
                os.remove(input_path)
            except Exception as e:
                log(f"Ошибка при удалении временного аудио-файла: {e}", level="ERROR")
        if output_path and os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception as e:
                log(f"Ошибка при удалении временного voice-файла: {e}", level="ERROR")


@perf_monitor
def convert_video_file_to_video_note(bot, chat_id, user_id, video_file_id):
    """Конвертация видео в кружок Telegram"""
    input_path = None
    output_path = None
    op_id = new_operation_id("convert")
    
    try:
        if not check_ffmpeg():
            bot.send_message(chat_id, "❌ Для обработки видео нужен ffmpeg.")
            return False

        os.makedirs(TEMP_DIR, exist_ok=True)
        # Создаем уникальные пути для входного и выходного файлов
        file_id = f"{user_id or chat_id}_{int(time.time())}"
        output_path = os.path.join(TEMP_DIR, f"video_note_{file_id}.mp4")
        
        log_event("converter_started", op=op_id, chat_id=chat_id, user_id=user_id)
        
        # Скачиваем видео
        with measure_time("DOWNLOAD|video_download"):
            input_path = download_telegram_file(
                bot,
                video_file_id,
                TEMP_DIR,
                f"temp_video_{file_id}",
                default_extension=".mp4",
            )
        
        log(f"Видео скачано, начинаю конвертацию для пользователя {user_id}")
        
        # Получаем информацию о видео, включая длительность
        _, has_audio, width, height, duration = get_video_info(input_path)
        log(f"Видео {'имеет' if has_audio else 'не имеет'} аудиодорожку, длительность: {duration:.2f} сек")
        
        # Проверяем длительность и обрезаем до 59 секунд, если превышает
        trim_duration = False
        if duration > 59:
            trim_duration = True
            log(f"Видео слишком длинное ({duration:.2f} сек), обрезаем до 59 секунд")
            # Создаем временный файл для обрезанного видео
            trimmed_path = os.path.join(TEMP_DIR, f"trimmed_{file_id}.mp4")
            
            with measure_time("TRIM|video_trim"):
                trim_cmd = [
                    'ffmpeg',
                    '-i', input_path,
                    '-t', '59',  # Ограничиваем длительность до 59 секунд
                    '-c', 'copy',  # Быстрое копирование без перекодирования
                    '-y',
                    trimmed_path
                ]
                process = subprocess.run(trim_cmd, capture_output=True, text=True, timeout=180)
            
            if process.returncode != 0:
                log(f"Ошибка при обрезке видео: {process.stderr}", level="ERROR")
                log_event("converter_trim_failed", level="ERROR", op=op_id, user_id=user_id)
                bot.send_message(chat_id, "❌ Не удалось обрезать видео. Попробуйте видео короче 1 минуты.")
                return False
                
            # Заменяем исходный файл обрезанным
            os.remove(input_path)
            input_path = trimmed_path
            
            # Обновляем информацию о видео после обрезки
            _, has_audio, width, height, duration = get_video_info(input_path)
        
        # Вычисляем параметры для обрезки в квадрат
        if width > height:
            # Горизонтальное видео
            x_offset = (width - height) // 2
            y_offset = 0
            crop_size = height
        else:
            # Вертикальное видео
            x_offset = 0
            y_offset = (height - width) // 2
            crop_size = width
        
        # Обрезаем к квадрату, а качество подбираем адаптивно, чтобы не мылить кружки заранее.
        crop_cmd = f"crop={crop_size}:{crop_size}:{x_offset}:{y_offset}"
        
        try:
            profile_chain = tuple(
                profile for profile in VIDEO_NOTE_ENCODING_PROFILES
                if profile["audio"] or not has_audio
            )
            selected_profile, file_size_mb = _encode_video_note(
                input_path,
                output_path,
                crop_cmd,
                profile_chain,
            )
            has_audio = has_audio and selected_profile["audio"]
            log_perf(f"FILE_SIZE|video_note|{file_size_mb:.2f}MB")
        except Exception as e:
            log(f"Ошибка ffmpeg: {e}", level="ERROR")
            log_event("converter_second_pass_failed", level="ERROR", op=op_id, user_id=user_id)
            bot.send_message(
                chat_id,
                "❌ Не удалось подготовить видео-кружок. Попробуйте другое видео или файл покороче.",
            )
            return False
        
        # Отправляем видео-кружок
        log("Отправка видео-кружка в Telegram")
        with measure_time("UPLOAD|video_note_upload"):
            with open(output_path, 'rb') as video_note:
                sent_message = send_with_retry(
                    bot.send_video_note,
                    chat_id,
                    video_note,
                    timeout=180,
                    max_retries=3
                )

        if sent_message is None:
            log_event("converter_upload_failed", level="ERROR", op=op_id, user_id=user_id)
            bot.send_message(chat_id, "❌ Не удалось отправить видео-кружок в Telegram.")
            return False
        
        # Отправляем сообщение о результате с информацией об обрезке
        if trim_duration:
            bot.send_message(chat_id, "✅ Видео-кружок создан! Исходное видео было обрезано до 59 секунд.")
        else:
            bot.send_message(chat_id, "✅ Видео-кружок успешно создан!")
        log_event("converter_finished", op=op_id, user_id=user_id)
        return True
            
    except subprocess.TimeoutExpired:
        log("Превышено время ожидания ffmpeg", level="ERROR")
        log_event("converter_timeout", level="ERROR", op=op_id, user_id=user_id)
        bot.send_message(chat_id, "❌ Превышено время обработки видео. Возможно, видео слишком длинное.")
        return False
    except Exception as e:
        log(f"Ошибка при конвертации видео: {e}", level="ERROR")
        log_event("converter_failed", level="ERROR", op=op_id, user_id=user_id, error=e)
        bot.send_message(
            chat_id,
            "❌ Не удалось обработать видео. Попробуйте ещё раз с другим файлом.",
        )
        return False
    finally:
        # Очистка временных файлов
        log(f"Очистка временных файлов для пользователя {user_id}")
        _safe_remove_file(input_path, "временного видео-файла")
        _safe_remove_file(output_path, "временного video note файла")
                
        # Логируем использование памяти в конце операции
        log_memory_usage("После конвертации видео")
