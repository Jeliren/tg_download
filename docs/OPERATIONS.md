# Production Operations Runbook

Этот документ позволяет обслуживать проект в новом чате без истории переписки.
Он описывает фактическую конфигурацию на 22 июля 2026 года. Значения секретов
здесь намеренно отсутствуют.

## 1. Что является источником истины

| Объект | Источник истины |
|---|---|
| Код | GitHub `Jeliren/tg_download`, ветка `main` |
| Production-конфигурация | `/opt/tg_download/.env` на сервере |
| Локальная production-конфигурация | `.env` в рабочей папке, Git её игнорирует |
| Локальная test-конфигурация | `.env.test`, Git её игнорирует |
| Instagram cookies/session | локальные игнорируемые файлы и `/opt/tg_download/data/` либо путь из production `.env` |
| CI SSH-доступ | GitHub Actions secrets |
| Процесс бота | systemd unit `tg_download_bot.service` |

Production-каталог не является Git-клоном: `.git` там нет. GitHub Actions
передаёт файлы через `rsync`. Поэтому на сервере нельзя использовать `git pull`
или считать вывод `git log` способом определения production-версии.

## 2. Точная production-конфигурация

- Host: `195.63.161.180`
- SSH port: `22`
- Hostname: `v877274.hosted-by-vdsina.com`
- Operator SSH user: `root`
- Deploy/runtime user: `tgdownload`
- Project directory: `/opt/tg_download`
- Virtualenv: `/opt/tg_download/.venv`
- Environment file: `/opt/tg_download/.env`
- systemd unit: `tg_download_bot.service`
- Application log: `/opt/tg_download/logs/bot.log`
- Server size: 1 vCPU / 1 GB RAM
- `sing-box` работает на этом же сервере и должен оставаться активным.

Unit запускает:

```text
/opt/tg_download/.venv/bin/python /opt/tg_download/main.py
```

от пользователя `tgdownload`, с рабочей папкой `/opt/tg_download` и
`EnvironmentFile=/opt/tg_download/.env`.

## 3. Два независимых SSH-маршрута

### Прямой операторский доступ с этого Mac

Для диагностики и администрирования используется локальный ключ
`~/.ssh/id_ed25519`:

```bash
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes \
  -o ConnectTimeout=10 root@195.63.161.180 'id -u; hostname'
```

Ожидается UID `0` и hostname сервера. Этот путь уже проверен и позволяет читать
systemd journal, проверять файлы и выполнять административные действия.

### Доступ GitHub Actions

Workflow подключается как `tgdownload` отдельным deploy-ключом. Его приватная
часть хранится только в GitHub secret и не обязана существовать на Mac.

Поэтому `Permission denied (publickey)` для
`tgdownload@195.63.161.180` не доказывает отсутствие доступа к серверу. Сначала
нужно проверить описанный выше root-маршрут.

Пользователь `tgdownload` владеет `/opt/tg_download` и имеет passwordless sudo
только для:

```text
/usr/bin/systemctl restart tg_download_bot.service
/usr/bin/systemctl is-active --quiet tg_download_bot.service
```

Это ограничение намеренное. Для журналов используется прямой root SSH.

## 4. Где лежат секреты

Никогда не печатать значения этих файлов и переменных целиком.

Локально:

- `.env` — production-настройки;
- `.env.test` — переопределение токена тестового бота;
- `data/`, `.instagram-account-session.json`,
  `.instagram-session-cookies.txt` — cookies/session данные.

На production:

- `/opt/tg_download/.env`, права `600`, владелец `tgdownload`;
- `/opt/tg_download/data/instagram-cookies.txt` и другие runtime session-файлы,
  если их пути заданы в `.env`.

В GitHub Actions должны существовать secrets:

- `PROD_HOST`
- `PROD_PORT`
- `PROD_USER`
- `PROD_SSH_PRIVATE_KEY`
- `PROD_KNOWN_HOSTS`

GitHub remote настроен как
`https://github.com/Jeliren/tg_download.git`. GitHub connector установлен,
авторизован и должен работать с репозиторием `Jeliren/tg_download`. Терминальный
HTTPS `git push` на этом Mac может не иметь отдельной сессии и вернуть
`could not read Username ... Device not configured`; это не означает отсутствие
доступа у connector. После connector-write выполнить `git fetch origin` и
синхронизировать рабочую ветку с новым `origin/main`.

Токены, пароли и приватные ключи нельзя добавлять в Git, issue, PR, Actions log
или сообщение чата. Для проверки конфигурации выводить только наличие ключей,
права файлов и безопасные метаданные.

## 5. Локальные test и production контуры

Установить зависимости:

```bash
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements-dev.txt
```

Запуск тестового бота:

```bash
./scripts/run_test.sh
```

Запуск основного бота локально:

```bash
./scripts/run_prod.sh
```

Нельзя одновременно держать локальный и серверный polling одного production
бота: Telegram updates начнут конкурировать. Для локальной разработки
использовать `.env.test` и тестового бота.

Остановка — `Ctrl+C`. Перед production-деплоем убедиться, что локальный
production-процесс не запущен.

## 6. Проверки перед отправкой изменений

Сначала сохранить и не затирать чужую работу:

```bash
git fetch origin
git status -sb
git log --oneline --decorate -8 --all
```

`origin/main` — актуальная основа. Если локальный `main` разошёлся с remote,
создавать рабочую ветку прямо от `origin/main`, не делать destructive reset:

```bash
git switch -c codex/<короткое-имя-задачи> origin/main
```

Полная проверка:

```bash
./.venv/bin/ruff check .
./.venv/bin/python -m unittest discover -s tests -v
./.venv/bin/python -m compileall main.py bot services utils core config.py tests
```

Также проверить diff и отсутствие секретов:

```bash
git diff --check
git status --short
git diff --stat
```

## 7. Нормальный путь обновления GitHub и production

Workflow `.github/workflows/check.yml` делает следующее:

1. На любом push/PR запускает lint, unit tests и compile-check.
2. Только для `main` после успешной проверки запускает production deploy.
3. Передаёт код в `/opt/tg_download` через `rsync --delete`.
4. Не трогает `.env`, `.env.*`, `.venv/`, `__pycache__/`, `*.pyc`, `data/`,
   `logs/`, `temp/` и `.git/`.
5. Пересоздаёт/обновляет `.venv`, устанавливает `requirements.txt`.
6. Записывает SHA развернутого коммита в
   `/opt/tg_download/.deployed-revision`.
7. Перезапускает сервис и проверяет, что он active.

Обычный порядок после готовой правки:

```bash
git add <только-нужные-файлы>
git commit -m "Краткое описание изменения"
git push origin HEAD:main
```

Прямой push в `main` принят в текущем проекте. Если политика репозитория позже
потребует PR, создать PR в `main` и дождаться merge; deploy произойдёт после
появления коммита в `main`.

Не добавлять в commit незнакомые untracked-файлы автоматически. Особенно
осторожно относиться к временным workflow, ключам и экспортам cookies.

## 8. Проверка после деплоя

Сначала проверить GitHub Actions: job `verify` и `deploy-production` должны быть
зелёными. Затем проверить сервер напрямую:

```bash
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes root@195.63.161.180 \
  'cat /opt/tg_download/.deployed-revision; systemctl is-active tg_download_bot.service; systemctl status tg_download_bot.service --no-pager -l'
```

SHA в `.deployed-revision` должен совпадать с коммитом в `origin/main`.

Telegram smoke test на сервере:

```bash
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes root@195.63.161.180 \
  'cd /opt/tg_download && runuser -u tgdownload -- .venv/bin/python scripts/telegram_smoke_test.py'
```

Smoke test должен показать доступное имя бота, отсутствие webhook и нормальное
число pending updates. Он читает production token через `config.py`, но не
выводит токен.

Важно запускать Python-проверки от `tgdownload`, а не от root: иначе в каталоге
проекта могут появиться root-owned `__pycache__`, мешающие следующему `rsync`.

После этого просмотреть свежие ошибки:

```bash
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes root@195.63.161.180 \
  'journalctl -u tg_download_bot.service --since "15 minutes ago" --no-pager -l'
```

## 9. Логи и диагностика production

Состояние сервиса:

```bash
ssh root@195.63.161.180 \
  'systemctl status tg_download_bot.service --no-pager -l'
```

Последние 300 строк journal:

```bash
ssh root@195.63.161.180 \
  'journalctl -u tg_download_bot.service -n 300 --no-pager -l'
```

Логи за период:

```bash
ssh root@195.63.161.180 \
  'journalctl -u tg_download_bot.service --since "3 hours ago" --no-pager -l'
```

Файловый лог:

```bash
ssh root@195.63.161.180 \
  'tail -n 300 /opt/tg_download/logs/bot.log'
```

Для быстрого поиска причин:

```bash
ssh root@195.63.161.180 \
  'journalctl -u tg_download_bot.service --since "24 hours ago" --no-pager -l | grep -Ei "error|exception|traceback|failed|instagram|youtube|openai|transcri|file is too big"'
```

Сначала читать полный контекст вокруг ошибки, затем определять причину. Не
перезапускать сервис только ради того, чтобы «проверить, поможет ли» — рестарт
может стереть полезный runtime-контекст.

## 10. Изменение production `.env` или cookies

Push в GitHub не переносит секреты. Если меняется production-токен, OpenAI key,
Instagram пароль, proxy или путь к cookies, нужно отдельно обновить сервер.

Перед заменой проверить локальный файл без печати значений:

```bash
test -s .env
stat -f '%Sp %N' .env
```

Безопасный способ заменить production `.env`:

```bash
scp -p .env root@195.63.161.180:/tmp/tg_download.env.new
ssh root@195.63.161.180 \
  'cp -p /opt/tg_download/.env /opt/tg_download/.env.backup && install -o tgdownload -g tgdownload -m 600 /tmp/tg_download.env.new /opt/tg_download/.env && rm -f /tmp/tg_download.env.new && systemctl restart tg_download_bot.service && systemctl is-active --quiet tg_download_bot.service'
```

После проверки удалить backup вручную либо оставить один последний защищённый
backup. Не скачивать production `.env` в новые незашифрованные места.

Cookies передаются аналогично, с владельцем `tgdownload`, правами `600` и точным
путём из `INSTAGRAM_COOKIES_FILE`. После замены cookies перезапустить сервис и
проверить реальную публичную Instagram-ссылку.

## 11. Обновление зависимостей

Python-зависимости закреплены в `requirements.txt`; dev tooling — в
`requirements-dev.txt`. Обновлять версию нужно в Git, затем запускать полный
набор проверок и обычный deploy через `main`.

Для YouTube особенно важен актуальный `yt-dlp[default]`: YouTube регулярно
меняет extraction-механизмы. Перед обновлением сверять текущий официальный
release, менять pin осознанно и проверять как минимум:

- получение metadata;
- скачивание видео;
- скачивание аудио и ffmpeg conversion;
- сценарий без субтитров;
- размер итогового файла для Telegram.

На production Actions сам выполнит `pip install -r requirements.txt`. Ручное
обновление пакета только на сервере создаёт незадокументированный drift и не
должно быть постоянным решением.

Текущие запланированные инфраструктурные улучшения и их безопасный порядок
описаны в [`BACKLOG.md`](../BACKLOG.md). В частности, SSH-вход по паролю нельзя
отключать до проверки второго одновременного входа по ключу и доступности
recovery console провайдера.

## 12. Аварийный откат

Предпочтительный откат — новый Git commit, отменяющий проблемное изменение:

```bash
git fetch origin
git switch -c codex/rollback-<причина> origin/main
git revert <плохой-commit-sha>
git push origin HEAD:main
```

После этого GitHub Actions развернёт отмену обычным способом. Не применять
`git reset --hard` к общей ветке и не force-push в `main`.

Если сервис падает и ждать CI нельзя, допустимо временно восстановить конкретный
файл на сервере из известной хорошей версии и перезапустить сервис, но затем
обязательно оформить тот же откат в Git. Сервер без `.git`, поэтому полноценный
rollback всё равно должен исходить из GitHub.

## 13. Известные эксплуатационные ограничения

- На обычном облачном Telegram Bot API бот не может скачать входящий файл больше
  лимита `getFile` (около 20 MB). Ошибка возникает до OpenAI и выглядит как
  `400 Bad Request: file is too big`.
- Локальный Telegram Bot API технически снимает это ограничение, но для сервера
  1 vCPU / 1 GB вместе с `ffmpeg`, ботом и `sing-box` он не рекомендован из-за
  риска нехватки памяти. Практичный вариант — попросить пользователя прислать
  меньший файл либо увеличить сервер минимум примерно до 2 vCPU / 2 GB.
- Серверный IP может быть ограничен Instagram. Ошибка авторизации не всегда
  означает неправильный пароль. Public `yt-dlp` fallback и cookies могут
  продолжать работать даже при проблеме account mode.
- Instagram cookies могут протухать; их обновление не требует изменения кода,
  но требует безопасно заменить runtime-файл на сервере.
- `MAX_FILE_SIZE` проекта и лимиты OpenAI не отменяют более ранние ограничения
  Telegram на получение входящего файла.

## 14. Минимальный чек-лист завершённой задачи

- Изменение находится в Git, секретов в diff нет.
- Lint, tests и compile-check прошли.
- Commit появился в `origin/main`.
- GitHub Actions `verify` и `deploy-production` успешны.
- `.deployed-revision` совпадает с нужным SHA.
- `tg_download_bot.service` active.
- Telegram smoke test успешен.
- В свежих production-логах нет нового traceback/error.
- `sing-box` active.

Если все пункты выполнены, изменение действительно находится в production, а не
только локально или только в GitHub.
