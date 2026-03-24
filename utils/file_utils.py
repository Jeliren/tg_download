import os
import shutil
import threading
import time

from requests.exceptions import ConnectionError, ReadTimeout
from telebot.apihelper import ApiTelegramException

from config import TEMP_DIR
from utils.logging_utils import log


def send_with_retry(send_func, *args, timeout=180, max_retries=3, **kwargs):
    """
    Отправка сообщения с автоматическими повторами при ошибках
    
    Args:
        send_func: Функция отправки Telegram
        *args: Аргументы для функции отправки
        timeout: Таймаут для отправки (увеличено до 180 секунд)
        max_retries: Максимальное количество попыток
        **kwargs: Дополнительные именованные аргументы
    
    Returns:
        Объект сообщения Telegram или None в случае ошибки
    """
    kwargs["timeout"] = timeout
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            return send_func(*args, **kwargs)
        except ApiTelegramException as e:
            last_error = e
            # Проверяем специфические ошибки Telegram
            if "Failed to get HTTP URL content" in str(e):
                log(f"Ошибка получения контента: {e}. Повтор {attempt}/{max_retries}", level="WARNING")
            elif "Too big file" in str(e):
                log("Файл слишком большой для Telegram", level="ERROR")
                return None  # Не повторяем для слишком больших файлов
            elif "timed out" in str(e).lower():
                log(f"Таймаут соединения: {e}. Повтор {attempt}/{max_retries}", level="WARNING")
            else:
                log(f"Ошибка API Telegram: {e}. Повтор {attempt}/{max_retries}", level="WARNING")
        except (ReadTimeout, ConnectionError) as e:
            last_error = e
            log(f"Сетевая ошибка при отправке: {e}. Повтор {attempt}/{max_retries}", level="WARNING")
        except Exception as e:
            last_error = e
            log(f"Общая ошибка при отправке: {e}. Повтор {attempt}/{max_retries}", level="WARNING")

        if attempt < max_retries:
            # Экспоненциальное ожидание: 1, 2, 4 секунды
            wait_time = 2 ** (attempt - 1)
            time.sleep(wait_time)

    log(f"Не удалось отправить после {max_retries} попыток: {last_error}", level="ERROR")
    return None

def show_progress_message(bot, chat_id, action_text, message_id, interval=5, max_time=120, stop_event=None):
    """
    Показывает прогресс загрузки, обновляя сообщение с эмодзи индикатором
    
    Args:
        bot: Объект бота
        chat_id: ID чата
        action_text: Текст действия (например, "Загрузка видео")
        message_id: ID сообщения для обновления
        interval: Интервал между обновлениями (секунды)
        max_time: Максимальное время ожидания (секунды)
    """
    indicators = ["⏳", "⌛"]
    start_time = time.time()
    index = 0
    
    while time.time() - start_time < max_time:
        if stop_event and stop_event.is_set():
            break

        try:
            elapsed = int(time.time() - start_time)
            minutes = elapsed // 60
            seconds = elapsed % 60
            
            # Формируем текст с индикатором времени
            progress_text = f"{indicators[index]} {action_text}... {minutes}:{seconds:02d}"
            
            bot.edit_message_text(
                progress_text,
                chat_id=chat_id,
                message_id=message_id
            )
            
            # Изменяем индекс для анимации
            index = (index + 1) % len(indicators)
            
            # Ждем интервал
            if stop_event:
                if stop_event.wait(interval):
                    break
            else:
                time.sleep(interval)
        except ApiTelegramException as e:
            # Игнорируем ошибку "сообщение не изменилось"
            if "message is not modified" not in str(e):
                log(f"Ошибка при обновлении прогресс-сообщения: {e}", level="DEBUG")
                # Увеличиваем интервал, чтобы уменьшить количество ошибок
                interval += 1
        except Exception as e:
            log(f"Ошибка в прогресс-сообщении: {e}", level="DEBUG")
            # Делаем паузу при ошибке
            if stop_event:
                stop_event.wait(interval)
            else:
                time.sleep(interval)

def start_progress_message(bot, chat_id, action_text, message_id, interval=5, max_time=120):
    """Запускает фоновое обновление progress-сообщения и возвращает stop event."""
    stop_event = threading.Event()
    thread = threading.Thread(
        target=show_progress_message,
        args=(bot, chat_id, action_text, message_id),
        kwargs={"interval": interval, "max_time": max_time, "stop_event": stop_event},
        daemon=True,
    )
    thread.start()
    return stop_event

def cleanup_temp_folder(temp_dir=TEMP_DIR):
    """
    Очистка временной папки от старых файлов
    """
    if not temp_dir:
        log("Пропускаю очистку временной папки: путь не задан", level="WARNING")
        return

    resolved_temp_dir = os.path.realpath(temp_dir)
    if resolved_temp_dir in {os.path.realpath(os.sep), os.path.realpath(os.path.expanduser("~"))}:
        log(f"Пропускаю очистку небезопасной временной директории: {resolved_temp_dir}", level="ERROR")
        return

    if not os.path.exists(temp_dir):
        return

    try:
        log("Очистка временных файлов")
        for item in os.listdir(temp_dir):
            item_path = os.path.join(temp_dir, item)
            try:
                if os.path.isfile(item_path):
                    os.remove(item_path)
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)
            except Exception as e:
                log(f"Не удалось удалить {item_path}: {e}", level="WARNING")
    except Exception as e:
        log(f"Ошибка при очистке временной папки: {e}", level="ERROR")

__all__ = ["send_with_retry", "show_progress_message", "start_progress_message", "cleanup_temp_folder"]
