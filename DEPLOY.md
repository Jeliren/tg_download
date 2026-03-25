# Deploy Guide

Ниже два рабочих сценария развёртывания проекта на другой машине.

## Вариант 1. Через GitHub и локальный Python

Подходит, если хотите обычный запуск без Docker.

### Linux (Ubuntu)

```bash
git clone git@github.com:Jeliren/tg_download.git
cd tg_download
./scripts/bootstrap_ubuntu.sh
cp .env.example .env
```

После этого откройте `.env`, заполните как минимум `BOT_TOKEN`, при необходимости добавьте `OPENAI_API_KEY`, затем запустите:

```bash
./.venv/bin/python main.py
```

Для фонового запуска можно использовать systemd unit из `deploy/tg_download_bot.service`.

### Windows

1. Установить Git.
2. Установить Python 3.11+.
3. Установить ffmpeg и добавить его в `PATH`.
4. Клонировать проект:

```powershell
git clone git@github.com:Jeliren/tg_download.git
cd tg_download
py -m venv .venv
.venv\Scripts\pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt
Copy-Item .env.example .env
```

После заполнения `.env` запуск:

```powershell
.venv\Scripts\python main.py
```

## Вариант 2. Через Docker

Подходит, если хотите максимально одинаковый запуск на Linux и Windows.

### Что нужно

1. Установить Git.
2. Установить Docker Desktop на Windows или Docker Engine на Linux.
3. Клонировать проект и создать `.env`.

```bash
git clone git@github.com:Jeliren/tg_download.git
cd tg_download
cp .env.example .env
```

Заполните `.env`, затем выполните:

```bash
docker compose up -d --build
```

Остановить контейнер:

```bash
docker compose down
```

Посмотреть логи:

```bash
docker compose logs -f
```

## Что хранить в GitHub, а что нет

Можно хранить:

- исходный код;
- `README.md`, `DEPLOY.md`, `Dockerfile`, `docker-compose.yml`;
- `.env.example`;
- тесты и workflow.

Нельзя хранить:

- `.env`;
- токены и API-ключи;
- `.venv`;
- логи;
- файлы Instagram session/cookies.

## Как обновлять проект на другой машине

Если проект уже поднят:

```bash
git pull
```

Дальше:

- без Docker: при изменении зависимостей снова выполнить `pip install -r requirements.txt`;
- с Docker: выполнить `docker compose up -d --build`;
- если в репозитории изменился `.env.example`, вручную перенесите новые переменные в ваш локальный `.env`, потому что `.env` не обновляется через Git.

## Proxy для всего проекта

Проект умеет использовать proxy для Telegram API и всего остального внешнего трафика:

- Telegram;
- YouTube / `yt-dlp`;
- Instagram;
- OpenAI.

Для SOCKS5 нужен установленный Python-пакет `PySocks`, он уже входит в `requirements.txt`.

Включение proxy:

```env
PROXY_ENABLED=true
```

Базовые переменные для `.env`:

```env
PROXY_ENABLED=true
TELEGRAM_PROXY_SCHEME=socks5
TELEGRAM_PROXY_HOST=127.0.0.1
TELEGRAM_PROXY_PORT=1080
TELEGRAM_PROXY_USERNAME=
TELEGRAM_PROXY_PASSWORD=
```

Если `OUTBOUND_PROXY_*` не заданы, проект использует эти же значения для YouTube, Instagram и OpenAI.

При необходимости можно задать отдельный proxy для всего остального внешнего трафика:

```env
OUTBOUND_PROXY_SCHEME=socks5
OUTBOUND_PROXY_HOST=127.0.0.1
OUTBOUND_PROXY_PORT=1080
OUTBOUND_PROXY_USERNAME=
OUTBOUND_PROXY_PASSWORD=
```
