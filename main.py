import os
import signal
import sys
from threading import Event

import yt_dlp

from bot import create_bot
from config import (
    LONG_POLLING_TIMEOUT,
    MAX_POLLING_RESTARTS,
    POLLING_RESTART_DELAY,
    POLLING_TIMEOUT,
    TEMP_DIR,
    get_runtime_warnings,
)
from utils.file_utils import cleanup_temp_folder
from utils.logging_utils import log, log_event, setup_logging


class ShutdownController:
    """Координирует graceful shutdown без import-side effects."""

    def __init__(self):
        self._requested = Event()
        self._bot = None

    def attach_bot(self, bot):
        self._bot = bot

    def request_shutdown(self, reason):
        if not self._requested.is_set():
            log(reason, level="WARNING")
        self._requested.set()

        stop_polling = getattr(self._bot, "stop_polling", None)
        if callable(stop_polling):
            try:
                stop_polling()
            except Exception as exc:
                log(f"Не удалось корректно остановить polling: {exc}", level="WARNING")

    def is_requested(self):
        return self._requested.is_set()

    def wait(self, timeout):
        return self._requested.wait(timeout)


def _yt_dlp_version():
    try:
        return yt_dlp.version.__version__
    except Exception:
        return "unknown"


def register_signal_handlers(shutdown_controller):
    def _handle_signal(sig, _frame):
        signal_name = signal.Signals(sig).name
        shutdown_controller.request_shutdown(
            f"Получен сигнал {signal_name}. Завершение работы бота...",
        )

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)


def _ensure_runtime_directories():
    os.makedirs(TEMP_DIR, exist_ok=True)


def main():
    shutdown_controller = ShutdownController()

    try:
        _ensure_runtime_directories()
        setup_logging()
        register_signal_handlers(shutdown_controller)

        cleanup_temp_folder()
        for warning in get_runtime_warnings():
            log(warning, level="WARNING")

        bot = create_bot()
        shutdown_controller.attach_bot(bot)

        log_event(
            "runtime_started",
            yt_dlp_version=_yt_dlp_version(),
            temp_dir=TEMP_DIR,
        )
        log("Бот запущен и готов к работе!")
        log("Нажмите Ctrl+C для остановки")

        restart_count = 0
        while not shutdown_controller.is_requested() and restart_count < MAX_POLLING_RESTARTS:
            try:
                bot.infinity_polling(
                    timeout=POLLING_TIMEOUT,
                    long_polling_timeout=LONG_POLLING_TIMEOUT,
                    allowed_updates=["message", "callback_query"],
                )
                if shutdown_controller.is_requested():
                    break

                restart_count += 1
                log(
                    f"Polling завершился без сигнала остановки. Перезапуск {restart_count}/{MAX_POLLING_RESTARTS}",
                    level="WARNING",
                )
            except Exception as e:
                if shutdown_controller.is_requested():
                    break

                restart_count += 1
                log(
                    f"Критическая ошибка polling (попытка {restart_count}/{MAX_POLLING_RESTARTS}): {e}",
                    level="ERROR",
                )

            if restart_count < MAX_POLLING_RESTARTS and not shutdown_controller.is_requested():
                log(f"Перезапуск бота через {POLLING_RESTART_DELAY} секунд...")
                shutdown_controller.wait(POLLING_RESTART_DELAY)

        if shutdown_controller.is_requested():
            log("Остановка бота завершена.")
            return 0

        if restart_count >= MAX_POLLING_RESTARTS:
            log("Достигнуто максимальное количество попыток перезапуска. Завершение работы.", level="ERROR")
            return 1

        return 0
    except Exception as e:
        log(f"Не удалось инициализировать бота: {e}", level="ERROR")
        return 1
    finally:
        cleanup_temp_folder()

if __name__ == "__main__":
    sys.exit(main())
