# Instagram Flows

Этот документ описывает Instagram-часть проекта:

- service account mode;
- public fallback через `yt-dlp`;
- metadata и description flow;
- video/audio extraction;
- границы между “описания нет” и “доступ к рилсу не получен”.

## Почему это выделено отдельно

Instagram здесь самый нестабильный внешний источник:

- правила доступа меняются;
- public scraping периодически ломается;
- часть ссылок работает только с авторизацией;
- часть сценариев ломается не из-за кода, а из-за challenge / rate limit / audience restrictions.

Поэтому Instagram-слой должен быть не “магическим”, а честным и хорошо задокументированным.

## Основные модули

- `services/instagram_service.py`
- `services/instagram_account_service.py`

Связанные части:

- `services/platforms.py`
- `bot/keyboards.py`
- `bot/handlers.py`

## Два режима доступа

### 1. Service account mode

`instagram_account_service.py` использует `instagrapi` и серверную сессию.

Он нужен как основной более стабильный путь для:

- metadata;
- video download;
- video->audio fallback для account mode.

### 2. Public fallback

Если service account path не дал результат или не подходит для конкретной ссылки, сервис переходит к public strategy:

- `yt-dlp` без browser cookies;
- optional `cookiefile` override, если он явно задан;
- HTML/meta/direct-media fallback там, где это оправдано.

Это best-effort путь, а не гарантированный API.

## Границы account mode

### Поддерживаемые URL в account mode

Server-side account path поддерживает shortcode-based media URLs:

- `/reel/<id>/`
- `/reels/<id>/`
- `/p/<id>/`
- `/tv/<id>/`

Story URLs вида `/stories/<username>/<id>/` через этот путь не поддерживаются.

### Что происходит для stories

Если ссылка story-like:

- account mode пропускается;
- дальше работают только public fallback strategies.

Это честнее и технически корректнее.

## `instagram_account_service.py`

### Что он делает

- создаёт и хранит singleton-like `instagrapi.Client`;
- восстанавливает и сохраняет session settings;
- получает media metadata;
- скачивает video по `video_url`;
- кеширует metadata по shortcode.

### Что важно

- timeout client использует сумму `EXTERNAL_CONNECT_TIMEOUT` и `EXTERNAL_READ_TIMEOUT`;
- account mode явно отвергает unsupported URL types;
- metadata cache привязан к shortcode, чтобы одинаковый reel с разными `?igsh=` не тянулся заново.

### Когда account mode должен считаться неуспешным

Критичные account-specific причины:

- bad credentials;
- challenge required;
- 2FA required.

Если это произошло и public fallback тоже не помог, наружу нужно поднимать именно эту причину, а не безликий `unknown`.

## `instagram_service.py`

Это orchestration-слой Instagram.

### Что он делает

- классифицирует и интерпретирует ошибки;
- выбирает между account mode и public mode;
- скачивает video/audio;
- нормализует video под Telegram;
- строит description;
- запускает OpenAI transcription для reel audio.

## Video flow

Поток:

1. если account mode применим для URL, сначала пробуем его;
2. потом `yt-dlp`;
3. если `yt-dlp` дал нетерминальную `unknown`-ошибку, пробуем direct media fallback;
4. при необходимости нормализуем видео под Telegram-safe MP4/H.264/AAC;
5. отправляем результат в Telegram.

### Почему direct media fallback ограниченный

Он нужен не как основной путь, а как дополнительный шанс, когда extractor path не дал результат по нетерминальной причине.

Это сознательное ограничение: direct-media scraping слишком хрупок, чтобы считать его главным слоем.

## Audio flow

Поток:

1. если account mode применим, сначала пытаемся получить video через account и извлечь из него audio;
2. затем пробуем `yt-dlp` audio path;
3. если audio path не сработал по `unknown` / `auth_required` / `rate_limited`, разрешаем fallback через video download + ffmpeg audio extraction.

Это pragmatic strategy:

- прямой audio path дешевле;
- но video->audio fallback иногда спасает кейсы, где extractor не смог отдать готовый audio stream.

## Description flow

### Источники описания

Приоритет такой:

1. metadata из account mode;
2. metadata из `yt-dlp`;
3. HTML/meta fallback со страницы.

### Важная граница

Бот различает два разных случая:

1. описание реально отсутствует;
2. описание не удалось получить, потому что сам рилс/пост недоступен.

Если metadata path упал с осмысленной причиной и description так и не удалось достать, пользователю показывается честная причина недоступности.

## Error model

### Public-mode причины

`instagram_service.py` различает как минимум:

- `auth_required`
- `rate_limited`
- `audience_restricted`
- `not_found`
- `network`
- `unknown`

### Account-mode причины

Дополнительно различаются:

- `account_auth_failed`
- `account_challenge_required`
- `account_two_factor_required`
- `unsupported_url`

`unsupported_url` чаще всего не должен доходить до пользователя как финальная причина, потому что это скорее routing-решение: такой URL надо просто не гнать в account mode.

## Честное поведение

Важный принцип Instagram-слоя:

бот не должен выдавать “описание отсутствует”, “видео плохое” или “что-то пошло не так”, если реальная причина в том, что Instagram:

- требует логин;
- выдал challenge;
- включил rate limit;
- ограничил аудиторию;
- не отдал страницу/медиа по сети.

То есть Instagram-нестабильность не должна маскироваться под внутренние проблемы бота.

## Что здесь сознательно не делалось

### Не делалась попытка превратить stories в полноценный account-mode сценарий

Для текущего проекта это было бы отдельной веткой сложности и не выглядит как безопасное маленькое улучшение.

### Не вводился тяжёлый state machine для fallback orchestration

Текущая явная цепочка `account -> ytdlp -> direct/html fallback` читается лучше и проще отлаживается.

### Не обещалась гарантированная поддержка всех Instagram media types

Проект остаётся best-effort решением, а не официальным Instagram API.

## Когда этот слой стоит менять дальше

Хорошие причины:

- нужен отдельный story-specific product flow;
- появились новые repeatable extractor failures;
- нужно улучшить metadata extraction quality;
- хочется добавить более точную классификацию новых Instagram failure modes.

Плохие причины:

- “давайте перепишем весь Instagram слой в generic fallback engine”;
- “давайте скрывать причины недоступности, чтобы UX выглядел мягче”;
- “давайте считать любой HTML fallback достаточно хорошим независимо от риска”.

Для текущего проекта Instagram-слой должен быть практичным, осторожным и максимально честным к пользователю.
