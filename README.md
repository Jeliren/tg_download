# tg_download Bot

`tg_download` — Telegram-бот для работы с медиа по ссылкам и с файлами, присланными прямо в чат.

Бот поддерживает три основных класса сценариев:

- ссылки на YouTube: скачивание видео, скачивание аудио, саммари;
- сценарий `Музыка`: поиск по текстовому запросу на YouTube, пагинация результатов и скачивание выбранного варианта как аудио;
- ссылки на Instagram: скачивание видео, скачивание аудио, описание, расшифровка;
- загруженные в Telegram видео, аудио, `voice` и `document`: конвертация, расшифровка и саммари.

Проект рассчитан на запуск как обычный polling-бот на сервере Linux или на локальной машине с `ffmpeg` и Python.

## Что умеет бот

### YouTube

- показывает кнопки `📹 Скачать видео`, `🎵 Скачать аудио`, `🧠 Саммари`;
- для видео предлагает выбор качества и умеет предлагать более компактный вариант, если файл не помещается в ограничения Telegram;
- для саммари использует субтитры, если они доступны;
- если субтитров нет, запрашивает подтверждение на расшифровку аудио через OpenAI.

### Музыка

- кнопка `Музыка` переводит бота в короткий режим ожидания текстового запроса;
- поиск идёт через `yt-dlp` YouTube search без отдельного внешнего API;
- результаты выдаются по 5 на страницу, максимум 15 результатов;
- выбранный вариант скачивается через тот же YouTube audio flow, что и обычная YouTube-ссылка.

### Instagram

- показывает кнопки `📹 Скачать видео`, `🎵 Скачать аудио`, `📝 Описание`, `🎙 Расшифровка`;
- принимает публичные ссылки на публикации формата `/reel/`, `/reels/`, `/p/`, `/tv/` и story-like URL;
- при наличии сервисного аккаунта использует account mode для shortcode-based ссылок;
- для остальных случаев использует public fallback через `yt-dlp`, HTML/meta parsing и прямой media URL там, где это уместно;
- честно сообщает, если контент недоступен из-за логина, challenge, rate limit, ограничений аудитории или проблем доступа к странице.

### Загруженные файлы

- `video` и video-документы: `⭕ Кружок`, `🎙 Расшифровка`, `🧠 Саммари`;
- `audio` и audio-документы: `🎙 Аудиосообщение`, `📝 Расшифровка`, `🧠 Саммари`;
- `voice`: `📝 Расшифровка`, `🧠 Саммари`.

## Как устроен проект

Код разделён на несколько простых слоёв:

- `main.py` и `config.py` отвечают за старт процесса, polling, сигналы, базовую конфигурацию и runtime warnings;
- `bot/` содержит Telegram-роутинг, callback-обработку, клавиатуры и orchestration пользовательских сценариев;
- `services/` реализует прикладную логику YouTube, Instagram, OpenAI и uploaded media;
- `core/` и `utils/` дают общие примитивы: TTL-кеш, ограничение фоновых задач, логирование, retry и работу с временными файлами.

Подробная архитектурная карта: [docs/PROJECT_ARCHITECTURE.md](docs/PROJECT_ARCHITECTURE.md).

## Требования

- Python 3.11+;
- `ffmpeg` в `PATH`;
- доступ в интернет для Telegram, YouTube, Instagram и OpenAI, если используются summary/transcription-сценарии.

Проверка `ffmpeg`:

```bash
ffmpeg -version
```

## Быстрый старт

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Минимальная конфигурация:

```env
BOT_TOKEN=1234567890:replace_with_real_token
LOG_LEVEL=INFO
```

Запуск:

```bash
./.venv/bin/python main.py
```

Для Ubuntu есть bootstrap-скрипт:

```bash
./scripts/bootstrap_ubuntu.sh
```

Он устанавливает системные зависимости, создаёт `.venv`, ставит Python-зависимости и подготавливает `.env`.

## Запуск через Docker

Если нужен одинаковый запуск на Linux и Windows, можно использовать Docker:

```bash
cp .env.example .env
docker compose up -d --build
```

Логи контейнера:

```bash
docker compose logs -f
```

Остановка:

```bash
docker compose down
```

Подробная инструкция по переносу проекта между машинами: [DEPLOY.md](DEPLOY.md).

## Конфигурация

Полный пример лежит в [.env.example](.env.example). Ниже перечислены переменные, которые реально участвуют в runtime.

### Обязательная переменная

- `BOT_TOKEN` — токен Telegram-бота.

### Proxy для всего проекта

Проект умеет использовать один proxy для всего внешнего трафика:

- Telegram Bot API;
- YouTube и `yt-dlp`;
- Instagram public fallback;
- Instagram service account;
- OpenAI API.

Логика теперь простая:

- если proxy включен, проект пускает весь внешний трафик через proxy;
- если proxy выключен, проект работает без proxy;
- автоматической проверки прямого доступа перед стартом больше нет.

Главный переключатель:

- `PROXY_ENABLED=true` — включить proxy;
- `PROXY_ENABLED=false` — выключить proxy.

Для всего проекта можно использовать два варианта:

- `TELEGRAM_PROXY_SCHEME` — например, `socks5`;
- `TELEGRAM_PROXY_HOST` — адрес proxy;
- `TELEGRAM_PROXY_PORT` — порт proxy;
- `TELEGRAM_PROXY_USERNAME` — логин, если нужен;
- `TELEGRAM_PROXY_PASSWORD` — пароль, если нужен.

По умолчанию эти же значения используются и для остального внешнего трафика.

Если нужно задать отдельный proxy именно для YouTube / Instagram / OpenAI, используйте optional override:

- `OUTBOUND_PROXY_SCHEME`
- `OUTBOUND_PROXY_HOST`
- `OUTBOUND_PROXY_PORT`
- `OUTBOUND_PROXY_USERNAME`
- `OUTBOUND_PROXY_PASSWORD`

Пример:

```env
PROXY_ENABLED=true
TELEGRAM_PROXY_SCHEME=socks5
TELEGRAM_PROXY_HOST=127.0.0.1
TELEGRAM_PROXY_PORT=1080
TELEGRAM_PROXY_USERNAME=
TELEGRAM_PROXY_PASSWORD=
```

Если `OUTBOUND_PROXY_*` пустые, проект автоматически переиспользует `TELEGRAM_PROXY_*` для всего внешнего трафика.

### OpenAI-сценарии

- `OPENAI_API_KEY` — нужен для саммари и расшифровки;
- `OPENAI_SUMMARY_MODEL` — модель для саммари, по умолчанию `gpt-5-mini`;
- `OPENAI_TRANSCRIPTION_MODEL` — модель для транскрипции, по умолчанию `gpt-4o-mini-transcribe`.

Если `OPENAI_API_KEY` не задан, бот продолжит работать, но OpenAI-сценарии будут недоступны.

### Instagram

- `INSTAGRAM_USERNAME` и `INSTAGRAM_PASSWORD` — учётные данные сервисного аккаунта для `instagrapi`;
- `INSTAGRAM_ACCOUNT_SESSION_FILE` — путь к файлу сохранённой сессии сервисного аккаунта;
- `INSTAGRAM_COOKIES_FILE` — необязательный `cookiefile` для `yt-dlp` public path.

Если заданы `INSTAGRAM_USERNAME` и `INSTAGRAM_PASSWORD`, бот сначала пробует account mode для shortcode-based ссылок и сохраняет рабочую сессию в `INSTAGRAM_ACCOUNT_SESSION_FILE`. Если account mode не подходит для URL или не даёт результата, сервис продолжает обработку через public fallback.

`INSTAGRAM_COOKIES_FILE` полезен как дополнительный override для `yt-dlp`, но не является обязательной частью развёртывания.

### Таймауты, лимиты и логи

- `CONNECT_TIMEOUT`, `READ_TIMEOUT` — таймауты Telegram API;
- `EXTERNAL_CONNECT_TIMEOUT`, `EXTERNAL_READ_TIMEOUT` — таймауты внешних HTTP-запросов;
- `POLLING_TIMEOUT`, `LONG_POLLING_TIMEOUT`, `MAX_POLLING_RESTARTS`, `POLLING_RESTART_DELAY` — параметры polling loop;
- `RETRY_COUNT`, `RETRY_DELAY` — повторные попытки для части операций;
- `MAX_FILE_SIZE`, `MAX_CONCURRENT_DOWNLOADS`, `MAX_DOWNLOAD_ATTEMPTS`, `URL_CACHE_TTL` — лимиты и runtime-cache;
- `LOGGING_ENABLED`, `LOG_LEVEL`, `PERFORMANCE_LOGGING`, `LOG_MEMORY_USAGE` — поведение логирования.

## Поведение по платформам

### YouTube

- summary flow сначала ищет субтитры;
- если субтитров нет, бот просит подтвердить расшифровку аудио;
- для транскрипции действует лимит OpenAI на размер входного файла `25 MB`.

### Instagram

- скачивание и описание работают в best-effort режиме;
- часть ссылок может быть недоступна из-за ограничений самой платформы;
- story-like URL обрабатываются через public path;
- отсутствие описания и недоступность самого поста рассматриваются как разные случаи и показываются пользователю по-разному.

## Запуск в фоне

Шаблон systemd unit лежит в [deploy/tg_download_bot.service](deploy/tg_download_bot.service).

Типовой порядок:

```bash
sudo cp deploy/tg_download_bot.service /etc/systemd/system/tg_download_bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now tg_download_bot.service
```

Перед запуском проверьте `User`, `WorkingDirectory`, `EnvironmentFile` и `ExecStart` в unit-файле.

## Проверки

Быстрая проверка:

```bash
./.venv/bin/python -m unittest discover -s tests -v
```

Полный локальный набор:

```bash
./.venv/bin/python -m unittest discover -s tests -v
./.venv/bin/python -m compileall main.py bot services utils core config.py tests
./.venv/bin/ruff check .
```

## Документация

- [docs/PROJECT_ARCHITECTURE.md](docs/PROJECT_ARCHITECTURE.md) — обзор проекта и карта остальных документов.
- [docs/CORE_AND_INFRASTRUCTURE.md](docs/CORE_AND_INFRASTRUCTURE.md) — конфигурация, lifecycle процесса, logging, concurrency и temp files.
- [docs/ROUTING_AND_UPLOADED_MEDIA.md](docs/ROUTING_AND_UPLOADED_MEDIA.md) — Telegram routing, callback payloads и uploaded media flows.
- [docs/UPLOADED_MEDIA_SERVICES.md](docs/UPLOADED_MEDIA_SERVICES.md) — сервисы для видео, аудио и `voice`, присланных в чат.
- [docs/YOUTUBE_FLOWS.md](docs/YOUTUBE_FLOWS.md) — download, выбор формата, subtitles и summary pipeline.
- [docs/INSTAGRAM_FLOWS.md](docs/INSTAGRAM_FLOWS.md) — account mode, public fallback, description и media extraction.
- [docs/OPENAI_AND_TEXT_PROCESSING.md](docs/OPENAI_AND_TEXT_PROCESSING.md) — OpenAI client, chunking, transcription и summary flows.

## Практические замечания

- не коммитьте `.env` и не публикуйте токены;
- после добавления новых переменных из `.env.example` переносите их в локальный `.env` вручную, потому что `.env` не хранится в Git;
- при запуске на сервере полезно периодически обновлять `yt-dlp` внутри `.venv`;
- после обновления зависимостей имеет смысл прогнать проверки и сделать короткий smoke test на реальных YouTube и Instagram ссылках.
