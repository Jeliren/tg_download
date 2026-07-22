# Deploy Guide

> Фактическая конфигурация текущего production, прямой SSH-доступ, GitHub
> Actions, безопасная работа с секретами, проверка версии и откат описаны в
> [docs/OPERATIONS.md](docs/OPERATIONS.md). Этот файл оставлен как общий гайд для
> развёртывания на новой машине.

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

Ограничьте доступ к секретам:

```bash
chmod 600 .env .instagram-account-session.json .instagram-session-cookies.txt 2>/dev/null || true
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
mkdir -p data
chmod 700 data
docker compose up -d --build
```

Docker Compose сохраняет Instagram session file в `./data/`, поэтому пересоздание контейнера не вызывает новый login.

Остановить контейнер:

```bash
docker compose down
```

Посмотреть логи:

```bash
docker compose logs -f
```

## Как получить актуальные логи на сервере

Сначала определите, чем запущен бот:

```bash
sudo systemctl status tg_download_bot --no-pager
docker compose ps
```

Для systemd:

```bash
sudo journalctl -u tg_download_bot -n 300 --no-pager
sudo journalctl -u tg_download_bot --since "24 hours ago" --no-pager
```

Для Docker Compose:

```bash
docker compose logs --tail=300 bot
docker compose logs --since=24h bot
```

Проверить версию развёрнутого кода и `yt-dlp`, не раскрывая секреты:

```bash
cat /opt/tg_download/.deployed-revision
./.venv/bin/python -c "import yt_dlp; print(yt_dlp.version.__version__)"
```

Production-каталог текущего проекта разворачивается через `rsync` и не содержит
`.git`, поэтому `git log` там не является способом проверки версии.

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
- с Docker: выполнить `docker compose up -d --build`.

## Автоматический production deploy через GitHub Actions

Workflow `.github/workflows/check.yml` после каждого push в `main`:

1. устанавливает зависимости и запускает линтер, тесты и compile-check;
2. передаёт только код в `/opt/tg_download` через SSH/rsync;
3. обновляет production-зависимости;
4. перезапускает `tg_download_bot.service` и проверяет его состояние.

Файлы `.env`, `.env.*`, `data/`, `.venv/`, `logs/` и `temp/` исключены из rsync и не удаляются при деплое.

В GitHub Environment `production` должны быть заданы secrets:

- `PROD_HOST` — IP или hostname сервера;
- `PROD_PORT` — SSH-порт, обычно `22`;
- `PROD_USER` — отдельный deploy-пользователь `tgdownload`;
- `PROD_SSH_PRIVATE_KEY` — приватный ключ этого deploy-пользователя;
- `PROD_KNOWN_HOSTS` — закреплённая строка host key сервера для проверки подлинности.

Deploy-пользователю нужен доступ на запись в `/opt/tg_download` и ограниченный passwordless sudo только для команд перезапуска и проверки `tg_download_bot.service`. Root-пароль в GitHub хранить не нужно.
