import os
from urllib.parse import quote

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_dotenv(dotenv_path):
    if not os.path.exists(dotenv_path):
        return

    with open(dotenv_path, "r", encoding="utf-8") as dotenv_file:
        for raw_line in dotenv_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            if line.startswith("export "):
                line = line[len("export "):].lstrip()

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'\"")

            if key and key not in os.environ:
                os.environ[key] = value


def _get_bool(name, default):
    value = os.getenv(name)
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _get_int(name, default, minimum=None):
    value = os.getenv(name)
    if value is None:
        return default

    try:
        parsed = int(value)
    except ValueError:
        return default

    if minimum is not None and parsed < minimum:
        return default
    return parsed


# Секреты и основные пути
_load_dotenv(os.path.join(BASE_DIR, ".env"))

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
TEMP_DIR = os.path.join(BASE_DIR, "temp")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

# Таймауты для Telegram API
CONNECT_TIMEOUT = _get_int("CONNECT_TIMEOUT", 30, minimum=1)
READ_TIMEOUT = _get_int("READ_TIMEOUT", 60, minimum=1)
POLLING_TIMEOUT = _get_int("POLLING_TIMEOUT", 60, minimum=1)
LONG_POLLING_TIMEOUT = _get_int("LONG_POLLING_TIMEOUT", 40, minimum=1)
MAX_POLLING_RESTARTS = _get_int("MAX_POLLING_RESTARTS", 5, minimum=1)
POLLING_RESTART_DELAY = _get_int("POLLING_RESTART_DELAY", 5, minimum=0)

# Таймауты для внешних сервисов
EXTERNAL_CONNECT_TIMEOUT = _get_int("EXTERNAL_CONNECT_TIMEOUT", 15, minimum=1)
EXTERNAL_READ_TIMEOUT = _get_int("EXTERNAL_READ_TIMEOUT", 30, minimum=1)
RETRY_COUNT = _get_int("RETRY_COUNT", 3, minimum=1)
RETRY_DELAY = _get_int("RETRY_DELAY", 2, minimum=0)

# Максимальный размер файла (в байтах) - 50MB для Telegram
MAX_FILE_SIZE = _get_int("MAX_FILE_SIZE", 50 * 1024 * 1024, minimum=1024)
INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME", "").strip()
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD", "").strip()
INSTAGRAM_COOKIES_FILE = os.getenv("INSTAGRAM_COOKIES_FILE", "").strip()
INSTAGRAM_ACCOUNT_SESSION_FILE = os.getenv(
    "INSTAGRAM_ACCOUNT_SESSION_FILE",
    os.path.join(BASE_DIR, ".instagram-account-session.json"),
).strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_SUMMARY_MODEL = os.getenv("OPENAI_SUMMARY_MODEL", "gpt-5-mini").strip() or "gpt-5-mini"
OPENAI_TRANSCRIPTION_MODEL = os.getenv(
    "OPENAI_TRANSCRIPTION_MODEL",
    "gpt-4o-mini-transcribe",
).strip() or "gpt-4o-mini-transcribe"
PROXY_ENABLED = _get_bool("PROXY_ENABLED", False)
TELEGRAM_PROXY_SCHEME = os.getenv("TELEGRAM_PROXY_SCHEME", "").strip().lower()
TELEGRAM_PROXY_HOST = os.getenv("TELEGRAM_PROXY_HOST", "").strip()
TELEGRAM_PROXY_PORT = _get_int("TELEGRAM_PROXY_PORT", 0, minimum=1)
TELEGRAM_PROXY_USERNAME = os.getenv("TELEGRAM_PROXY_USERNAME", "").strip()
TELEGRAM_PROXY_PASSWORD = os.getenv("TELEGRAM_PROXY_PASSWORD", "").strip()
OUTBOUND_PROXY_SCHEME = os.getenv("OUTBOUND_PROXY_SCHEME", "").strip().lower()
OUTBOUND_PROXY_HOST = os.getenv("OUTBOUND_PROXY_HOST", "").strip()
OUTBOUND_PROXY_PORT = _get_int("OUTBOUND_PROXY_PORT", 0, minimum=1)
OUTBOUND_PROXY_USERNAME = os.getenv("OUTBOUND_PROXY_USERNAME", "").strip()
OUTBOUND_PROXY_PASSWORD = os.getenv("OUTBOUND_PROXY_PASSWORD", "").strip()

# Настройки логирования
LOGGING_ENABLED = _get_bool("LOGGING_ENABLED", True)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
PERFORMANCE_LOGGING = _get_bool("PERFORMANCE_LOGGING", True)
LOG_MEMORY_USAGE = _get_bool("LOG_MEMORY_USAGE", False)

# Очистка кеша
URL_CACHE_TTL = _get_int("URL_CACHE_TTL", 3600, minimum=1)

# Настройки для оптимизации
MAX_CONCURRENT_DOWNLOADS = _get_int("MAX_CONCURRENT_DOWNLOADS", 3, minimum=1)
MAX_DOWNLOAD_ATTEMPTS = _get_int("MAX_DOWNLOAD_ATTEMPTS", 3, minimum=1)


def validate_config():
    """Базовая валидация конфигурации перед запуском приложения."""
    errors = []

    if not BOT_TOKEN:
        errors.append("Не задан BOT_TOKEN. Укажите токен бота в переменной окружения.")
    elif ":" not in BOT_TOKEN:
        errors.append("BOT_TOKEN имеет неожиданный формат.")

    if errors:
        raise RuntimeError("Ошибка конфигурации:\n- " + "\n- ".join(errors))


def _is_proxy_configured(scheme, host, port, username, password):
    if not scheme or not host or not port:
        return False

    if bool(username) != bool(password):
        return False

    return True


def _build_proxy_url(scheme, host, port, username, password):
    if not _is_proxy_configured(scheme, host, port, username, password):
        return ""

    credentials = ""
    if username and password:
        credentials = (
            f"{quote(username, safe='')}:{quote(password, safe='')}@"
        )

    return f"{scheme}://{credentials}{host}:{port}"


def is_telegram_proxy_configured():
    return _is_proxy_configured(
        TELEGRAM_PROXY_SCHEME,
        TELEGRAM_PROXY_HOST,
        TELEGRAM_PROXY_PORT,
        TELEGRAM_PROXY_USERNAME,
        TELEGRAM_PROXY_PASSWORD,
    )


def get_telegram_proxy_url():
    if not is_proxy_enabled():
        return ""

    return _build_proxy_url(
        TELEGRAM_PROXY_SCHEME,
        TELEGRAM_PROXY_HOST,
        TELEGRAM_PROXY_PORT,
        TELEGRAM_PROXY_USERNAME,
        TELEGRAM_PROXY_PASSWORD,
    )


def is_outbound_proxy_configured():
    return _is_proxy_configured(
        OUTBOUND_PROXY_SCHEME,
        OUTBOUND_PROXY_HOST,
        OUTBOUND_PROXY_PORT,
        OUTBOUND_PROXY_USERNAME,
        OUTBOUND_PROXY_PASSWORD,
    )


def get_outbound_proxy_url():
    if not is_proxy_enabled():
        return ""

    outbound_proxy_url = _build_proxy_url(
        OUTBOUND_PROXY_SCHEME,
        OUTBOUND_PROXY_HOST,
        OUTBOUND_PROXY_PORT,
        OUTBOUND_PROXY_USERNAME,
        OUTBOUND_PROXY_PASSWORD,
    )
    if outbound_proxy_url:
        return outbound_proxy_url

    return get_telegram_proxy_url()


def get_outbound_requests_proxies():
    proxy_url = get_outbound_proxy_url()
    if not proxy_url:
        return {}

    return {
        "http": proxy_url,
        "https": proxy_url,
    }


def is_proxy_enabled():
    if PROXY_ENABLED:
        return True

    return any(
        [
            TELEGRAM_PROXY_SCHEME,
            TELEGRAM_PROXY_HOST,
            TELEGRAM_PROXY_PORT,
            TELEGRAM_PROXY_USERNAME,
            TELEGRAM_PROXY_PASSWORD,
            OUTBOUND_PROXY_SCHEME,
            OUTBOUND_PROXY_HOST,
            OUTBOUND_PROXY_PORT,
            OUTBOUND_PROXY_USERNAME,
            OUTBOUND_PROXY_PASSWORD,
        ]
    )


def get_runtime_warnings():
    warnings = []

    if bool(INSTAGRAM_USERNAME) != bool(INSTAGRAM_PASSWORD):
        warnings.append(
            "Для серверного Instagram login должны быть заданы и INSTAGRAM_USERNAME, и "
            "INSTAGRAM_PASSWORD одновременно."
        )

    proxy_configs = [
        (
            "Telegram proxy",
            "TELEGRAM_PROXY",
            TELEGRAM_PROXY_SCHEME,
            TELEGRAM_PROXY_HOST,
            TELEGRAM_PROXY_PORT,
            TELEGRAM_PROXY_USERNAME,
            TELEGRAM_PROXY_PASSWORD,
        ),
        (
            "outbound proxy",
            "OUTBOUND_PROXY",
            OUTBOUND_PROXY_SCHEME,
            OUTBOUND_PROXY_HOST,
            OUTBOUND_PROXY_PORT,
            OUTBOUND_PROXY_USERNAME,
            OUTBOUND_PROXY_PASSWORD,
        ),
    ]

    for label, prefix, scheme, host, port, username, password in proxy_configs:
        if not any([scheme, host, port, username, password]):
            continue

        missing_required_proxy_fields = []
        if not scheme:
            missing_required_proxy_fields.append(f"{prefix}_SCHEME")
        if not host:
            missing_required_proxy_fields.append(f"{prefix}_HOST")
        if not port:
            missing_required_proxy_fields.append(f"{prefix}_PORT")

        if missing_required_proxy_fields:
            warnings.append(
                f"Для {label} должны быть заданы "
                + ", ".join(missing_required_proxy_fields)
                + "."
            )
        elif bool(username) != bool(password):
            warnings.append(
                f"Для {label} должны быть заданы и {prefix}_USERNAME, и "
                f"{prefix}_PASSWORD одновременно."
            )

    return warnings

__all__ = [
    "BOT_TOKEN",
    "BASE_DIR",
    "TEMP_DIR",
    "LOGS_DIR",
    "CONNECT_TIMEOUT",
    "READ_TIMEOUT",
    "POLLING_TIMEOUT",
    "LONG_POLLING_TIMEOUT",
    "MAX_POLLING_RESTARTS",
    "POLLING_RESTART_DELAY",
    "EXTERNAL_CONNECT_TIMEOUT",
    "EXTERNAL_READ_TIMEOUT",
    "RETRY_COUNT",
    "RETRY_DELAY",
    "MAX_FILE_SIZE",
    "INSTAGRAM_USERNAME",
    "INSTAGRAM_PASSWORD",
    "INSTAGRAM_COOKIES_FILE",
    "INSTAGRAM_ACCOUNT_SESSION_FILE",
    "OPENAI_API_KEY",
    "OPENAI_SUMMARY_MODEL",
    "OPENAI_TRANSCRIPTION_MODEL",
    "TELEGRAM_PROXY_SCHEME",
    "TELEGRAM_PROXY_HOST",
    "TELEGRAM_PROXY_PORT",
    "TELEGRAM_PROXY_USERNAME",
    "TELEGRAM_PROXY_PASSWORD",
    "OUTBOUND_PROXY_SCHEME",
    "OUTBOUND_PROXY_HOST",
    "OUTBOUND_PROXY_PORT",
    "OUTBOUND_PROXY_USERNAME",
    "OUTBOUND_PROXY_PASSWORD",
    "PROXY_ENABLED",
    "LOGGING_ENABLED",
    "LOG_LEVEL",
    "PERFORMANCE_LOGGING",
    "LOG_MEMORY_USAGE",
    "URL_CACHE_TTL",
    "MAX_CONCURRENT_DOWNLOADS",
    "MAX_DOWNLOAD_ATTEMPTS",
    "validate_config",
    "is_proxy_enabled",
    "is_telegram_proxy_configured",
    "get_telegram_proxy_url",
    "is_outbound_proxy_configured",
    "get_outbound_proxy_url",
    "get_outbound_requests_proxies",
    "get_runtime_warnings",
]
