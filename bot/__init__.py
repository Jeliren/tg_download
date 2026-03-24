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


def create_bot():
    """Создание и настройка экземпляра бота."""
    import telebot
    from telebot import apihelper

    from config import BOT_TOKEN, CONNECT_TIMEOUT, READ_TIMEOUT, validate_config
    from services.converter_service import check_ffmpeg

    validate_config()

    apihelper.CONNECT_TIMEOUT = CONNECT_TIMEOUT
    apihelper.READ_TIMEOUT = READ_TIMEOUT
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


__all__ = ["create_bot", "ExceptionHandler"]
