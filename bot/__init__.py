from utils.logging_utils import log


class ExceptionHandler:
    def __init__(self, logger_func):
        self.logger = logger_func

    def handle(self, exception):
        try:
            from telebot import apihelper
        except Exception:
            apihelper = None

        if apihelper and isinstance(exception, apihelper.ApiTelegramException):
            self.logger(f"Telegram API ошибка: {exception}", level="WARNING")
        elif isinstance(exception, TimeoutError) or "timeout" in str(exception).lower():
            self.logger(f"Таймаут соединения: {exception}", level="WARNING")
        else:
            self.logger(f"Необработанное исключение: {exception}", level="ERROR")
        return True


def _configure_telegram_transport(apihelper):
    from config import (
        TELEGRAM_PROXY_HOST,
        TELEGRAM_PROXY_PORT,
        TELEGRAM_PROXY_SCHEME,
        get_telegram_proxy_url,
        is_proxy_enabled,
    )

    apihelper.proxy = {}

    if not is_proxy_enabled():
        log("Proxy отключен. Запуск без proxy.")
        return "direct"

    proxy_url = get_telegram_proxy_url()
    if not proxy_url:
        log(
            "Proxy включен, но Telegram proxy не настроен. Запуск без proxy.",
            level="WARNING",
        )
        return "unavailable"

    apihelper.proxy = {"http": proxy_url, "https": proxy_url}
    log(
        f"Для Telegram включен {TELEGRAM_PROXY_SCHEME} proxy {TELEGRAM_PROXY_HOST}:{TELEGRAM_PROXY_PORT}.",
        level="INFO",
    )
    return "proxy"


def create_bot():
    """Создание и настройка экземпляра бота."""
    import telebot
    from telebot import apihelper

    from config import BOT_TOKEN, CONNECT_TIMEOUT, READ_TIMEOUT, validate_config
    from services.converter_service import check_ffmpeg

    validate_config()

    apihelper.CONNECT_TIMEOUT = CONNECT_TIMEOUT
    apihelper.READ_TIMEOUT = READ_TIMEOUT
    _configure_telegram_transport(apihelper)
    telebot.logger.setLevel(telebot.logging.INFO)

    bot = telebot.TeleBot(BOT_TOKEN)
    bot.exception_handler = ExceptionHandler(log)

    if not check_ffmpeg():
        log("⚠️ ВНИМАНИЕ: ffmpeg не установлен в системе. Необходимо установить ffmpeg.", level="WARNING")
        log("MacOS: brew install ffmpeg")
        log("Linux: sudo apt-get install ffmpeg")
        log("Windows: скачайте с https://ffmpeg.org/download.html")

    from bot.handlers import register_handlers

    register_handlers(bot)
    return bot


__all__ = [
    "create_bot",
    "ExceptionHandler",
    "_configure_telegram_transport",
]
