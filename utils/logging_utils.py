import functools
import logging
import os
import re
import time
import uuid
from logging.handlers import RotatingFileHandler

from config import (
    BOT_TOKEN,
    LOG_LEVEL,
    LOG_MEMORY_USAGE,
    LOGGING_ENABLED,
    LOGS_DIR,
    PERFORMANCE_LOGGING,
)

TOKEN_PATTERNS = (
    re.compile(r"bot\d{8,}:[A-Za-z0-9_-]{20,}"),
    re.compile(r"\b\d{8,}:[A-Za-z0-9_-]{20,}\b"),
)


def _sanitize_text(value):
    if not isinstance(value, str):
        return value

    sanitized = value
    if BOT_TOKEN:
        sanitized = sanitized.replace(BOT_TOKEN, "<redacted-bot-token>")

    for pattern in TOKEN_PATTERNS:
        sanitized = pattern.sub(
            lambda match: "bot<redacted-bot-token>"
            if match.group(0).startswith("bot")
            else "<redacted-bot-token>",
            sanitized,
        )

    return sanitized


def _format_context_value(value):
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "true" if value else "false"

    text = _sanitize_text(str(value))
    return text.replace("\n", "\\n")


def new_operation_id(prefix="op"):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def log_event(event, level="INFO", **fields):
    """Структурированный лог событий в формате key=value."""
    payload = [f"event={event}"]
    for key in sorted(fields):
        payload.append(f"{key}={_format_context_value(fields[key])}")
    log(" ".join(payload), level=level)


class SensitiveDataFormatter(logging.Formatter):
    """Formatter, который маскирует токены и другие чувствительные значения."""

    def format(self, record):
        formatted = super().format(record)
        return _sanitize_text(formatted)

# Настройка логирования
def setup_logging():
    """Настройка логирования"""
    if not LOGGING_ENABLED:
        return

    os.makedirs(LOGS_DIR, exist_ok=True)
    logging.addLevelName(15, "PERF")

    resolved_level = getattr(logging, LOG_LEVEL, logging.INFO)
    if PERFORMANCE_LOGGING and resolved_level > 15:
        resolved_level = 15

    formatter = SensitiveDataFormatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        os.path.join(LOGS_DIR, "bot.log"),
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    logging.basicConfig(
        level=resolved_level,
        handlers=[stream_handler, file_handler],
        force=True,
    )

    # Настраиваем логирование внешних библиотек
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("telebot").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)

def log(message, level="INFO"):
    """Логирование сообщений"""
    if not LOGGING_ENABLED:
        return

    logger = logging.getLogger("tg_download_bot")
    level_method = getattr(logger, level.lower(), logger.info)
    level_method(_sanitize_text(message))

# Новые функции для мониторинга производительности

def log_perf(message):
    """Логирование производительности"""
    if not LOGGING_ENABLED or not PERFORMANCE_LOGGING:
        return

    logger = logging.getLogger("tg_download_bot")
    logger.log(15, f"[PERF] {message}")

def perf_monitor(func):
    """Декоратор для мониторинга производительности функций"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Получаем имя функции для логирования
        func_name = func.__name__
        
        # Логируем начало выполнения
        log(f"Начало выполнения {func_name}", "DEBUG")
        
        # Замеряем время выполнения
        start_time = time.perf_counter()
        
        # Выполняем функцию
        try:
            result = func(*args, **kwargs)
            success = True
        except Exception as e:
            success = False
            log(f"Ошибка при выполнении {func_name}: {e}", "ERROR")
            raise
        finally:
            # Замеряем время окончания и логируем результат
            end_time = time.perf_counter()
            duration = end_time - start_time
            
            # Определяем тип операции по имени функции
            if 'download' in func_name:
                op_type = "DOWNLOAD"
            elif 'convert' in func_name:
                op_type = "CONVERT"
            elif 'check' in func_name:
                op_type = "CHECK"
            else:
                op_type = "OTHER"
            
            status = "SUCCESS" if success else "FAILED"
            
            # Логируем с меткой времени для удобного анализа
            log_perf(f"{op_type}|{func_name}|{status}|{duration:.3f}s")
        
        return result
    
    return wrapper

def measure_time(message=None):
    """Контекстный менеджер для измерения времени выполнения блока кода"""
    class Timer:
        def __init__(self, message):
            self.message = message
            self.start_time = None
            
        def __enter__(self):
            self.start_time = time.perf_counter()
            return self
            
        def __exit__(self, exc_type, exc_val, exc_tb):
            end_time = time.perf_counter()
            duration = end_time - self.start_time
            
            if self.message:
                log_perf(f"{self.message}|{duration:.3f}s")
            else:
                log_perf(f"Блок кода выполнен за {duration:.3f}s")
    
    return Timer(message)

# Логирование использования памяти (для более глубокой отладки)
def log_memory_usage(message=None):
    """Логирование использования памяти"""
    if not LOG_MEMORY_USAGE:
        return

    try:
        import psutil
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        
        memory_mb = memory_info.rss / (1024 * 1024)
        
        if message:
            log_perf(f"MEMORY|{message}|{memory_mb:.2f}MB")
        else:
            log_perf(f"MEMORY|Использование памяти: {memory_mb:.2f}MB")
    except ImportError:
        log("Для логирования памяти установите psutil: pip install psutil", "WARNING")

__all__ = [
    "setup_logging",
    "log",
    "log_event",
    "log_perf",
    "perf_monitor",
    "measure_time",
    "log_memory_usage",
    "new_operation_id",
] 
