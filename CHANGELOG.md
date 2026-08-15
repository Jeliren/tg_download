# Changelog

Здесь фиксируются заметные изменения проекта. Формат — даты, потому что у
репозитория пока нет версионных тегов и GitHub Releases.

## Unreleased

### Changed

- Подтверждено и зафиксировано фактическое SSH-ограничение production: root
  принимает только ключи, а password и keyboard-interactive аутентификация
  отключены. Проверены новый вход операторским ключом и чтение systemd journal.

## 2026-07-22

### Added

- Полный production runbook: доступы, секреты, GitHub Actions, диагностика,
  обновление и откат.
- `AGENTS.md` как обязательная точка входа для новой модели или разработчика.
- Маркер `/opt/tg_download/.deployed-revision` с SHA развернутого коммита.
- Конвертация загруженных Telegram audio/voice в mono MP3 перед отправкой в
  OpenAI.
- Регрессионные тесты для Telegram `.oga` audio.
- Живой приоритетный backlog вместо завершённого плана рефакторинга.

### Changed

- Runtime cache (`__pycache__`, `*.pyc`) исключён из production `rsync`.
- Telegram smoke test на production запускается от runtime-пользователя, чтобы
  не создавать root-owned файлы.
- Документация приведена к фактической схеме GitHub → Actions → `rsync` →
  systemd.

### Fixed

- Исправлена ошибка OpenAI `Unsupported file format oga`.
- Исправлен автодеплой, которому мешал root-owned Python cache на сервере.

### Removed

- Завершённый и частично устаревший `PROJECT_REWORK_PLAN.md`.
- Неиспользуемый `READY_FOR_MORE_TEXT` и локальные cache/log-артефакты.

## 2026-07-10

### Added

- Отдельные локальные test и production контуры через `.env.test`/`.env` и
  `scripts/run_test.sh`/`scripts/run_prod.sh`.
- Автоматические lint, unit test, compile и production deploy jobs в GitHub
  Actions.
- Telegram и media smoke-скрипты.
- Instagram account mode, session/cookies support и public fallback.

### Changed

- YouTube и Instagram download flows переведены на актуальный `yt-dlp` с
  ограниченными fallback-путями и понятной классификацией ошибок.
- Сценарии Telegram упрощены: media отправляются без лишних captions, а
  завершение Instagram download показывается отдельным коротким сообщением.
- Polling и graceful shutdown ускорены и стабилизированы.
- OpenAI summary/transcription, uploaded media и Telegram routing разделены на
  отдельные сервисные слои.

### Fixed

- Обработка недоступных Instagram/YouTube ссылок, rate limits, слишком больших
  файлов и ошибок отправки в Telegram.
- Маскирование Telegram token в логах и очистка временных файлов.

## 2026-03-24

### Added

- Первая рабочая версия Telegram media bot.
- Базовая конфигурация, Docker/systemd deployment, логирование и тестовый
  фундамент.

### Changed

- Экспериментальные Telegram proxy-настройки были проверены и затем полностью
  отменены, чтобы не оставлять ненужную сетевую сложность.

## Правило ведения

- Любое заметное пользовательское, production или security-изменение добавлять
  сначала в `Unreleased`.
- При формальном релизе переносить пункты из `Unreleased` в раздел с датой или
  версией и при необходимости создавать соответствующий Git tag/Release.
- Не добавлять сюда токены, IP-пароли, cookies и другие секреты.
