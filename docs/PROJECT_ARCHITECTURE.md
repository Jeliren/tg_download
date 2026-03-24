# Project Architecture

Этот документ даёт целостную картину проекта и связывает между собой остальные более узкие документы.

## Что это за проект

`tg_download` — Telegram-бот для media-oriented сценариев:

- YouTube video/audio download;
- music search with YouTube audio download reuse;
- YouTube summary;
- Instagram video/audio best-effort download;
- Instagram description;
- transcription/summary для uploaded audio/video/voice;
- format conversion в video note и voice message.

## Архитектурная идея

Проект сознательно не построен как “framework”.

Вместо этого структура держится на нескольких простых слоях:

1. `main.py` и infrastructure для жизненного цикла процесса;
2. `bot/` для Telegram routing и orchestration;
3. `services/` для domain-specific execution;
4. `core/` и `utils/` для небольших shared primitives.

Это делает код достаточно прямым для чтения и отладки, но уже без ad-hoc хаоса.

## Основные слои

### `main.py` и `config.py`

Этот слой отвечает за:

- startup/shutdown;
- polling lifecycle;
- runtime config;
- logging bootstrap.

Подробности: [docs/CORE_AND_INFRASTRUCTURE.md](/Users/shemetov/Projects/tg_download/docs/CORE_AND_INFRASTRUCTURE.md)

### `bot/`

Это Telegram-facing слой.

Он отвечает за:

- входящие messages;
- callback payload routing;
- клавиатуры;
- orchestration сценариев;
- лёгкое in-memory состояние для краткоживущих сценариев вроде music search;
- user locking и запуск background tasks.

Ключевой принцип:

`bot/handlers.py` координирует сценарии, но не должен тащить в себя низкоуровневую media/OpenAI логику.

Подробности: [docs/ROUTING_AND_UPLOADED_MEDIA.md](/Users/shemetov/Projects/tg_download/docs/ROUTING_AND_UPLOADED_MEDIA.md)

### `services/`

Это основной execution layer.

Тут лежат:

- YouTube flow;
- music search flow;
- Instagram flow;
- OpenAI transcription/summary;
- uploaded media processing;
- conversion helpers.

Service layer делится на domain-specific модули, а не на одну “универсальную pipeline system”.

Подробности:

- [docs/OPENAI_AND_TEXT_PROCESSING.md](/Users/shemetov/Projects/tg_download/docs/OPENAI_AND_TEXT_PROCESSING.md)
- [docs/YOUTUBE_FLOWS.md](/Users/shemetov/Projects/tg_download/docs/YOUTUBE_FLOWS.md)
- [docs/INSTAGRAM_FLOWS.md](/Users/shemetov/Projects/tg_download/docs/INSTAGRAM_FLOWS.md)
- [docs/UPLOADED_MEDIA_SERVICES.md](/Users/shemetov/Projects/tg_download/docs/UPLOADED_MEDIA_SERVICES.md)

### `core/` и `utils/`

Это маленькие shared building blocks:

- TTL cache;
- user task registry;
- bounded background task runner;
- logging;
- file/retry helpers.

Они не должны становиться вторым application layer.

Подробности: [docs/CORE_AND_INFRASTRUCTURE.md](/Users/shemetov/Projects/tg_download/docs/CORE_AND_INFRASTRUCTURE.md)

## End-to-end user flows

### URL flow

1. пользователь присылает ссылку;
2. `bot/input_router.py` определяет platform;
3. `bot/handlers.py` показывает нужные кнопки;
4. callback идёт через `bot/callback_router.py`;
5. handler запускает соответствующий service;
6. service скачивает/обрабатывает media и отвечает пользователю.

### Uploaded media flow

1. пользователь присылает audio/video/voice/document;
2. input router определяет тип;
3. handler показывает action buttons;
4. callback registry хранит payload;
5. service получает `file_id` и выполняет conversion / transcription / summary.

### Background execution

Тяжёлые операции не выполняются прямо в Telegram callback/message handler thread.

Для них используется bounded `BackgroundTaskRunner`, а на пользователя накладывается lock через `UserTaskRegistry`.

Это защищает бота от:

- бесконтрольного роста очередей;
- параллельных тяжёлых действий от одного пользователя;
- более хаотичного runtime behavior.

## Ключевые проектные принципы

### 1. Honest behavior over fake guarantees

Это особенно важно для Instagram и OpenAI.

Если внешний сервис:

- rate-limited;
- требует login;
- недоступен по сети;
- не отдал transcript;

бот должен говорить именно об этом, а не маскировать проблему под абстрактное “что-то пошло не так”.

### 2. Focused abstractions

Повторяемые технические части выносятся:

- OpenAI HTTP client;
- uploaded media helpers;
- infrastructure primitives.

Но проект сознательно не уходит в generic mega-abstraction layer.

### 3. Orchestration separate from execution

`bot/handlers.py` решает, какой сценарий нужен.

`services/...` решают, как этот сценарий реально выполнить.

### 4. Docs follow architecture

Документация строится по тем же границам, что и код:

- infrastructure;
- routing/orchestration;
- OpenAI/text processing;
- YouTube;
- Instagram;
- uploaded media.

Это помогает не только читать проект, но и безопасно менять его по частям.

## Документационная карта

Если нужен общий вход:

- начните с [README.md](/Users/shemetov/Projects/tg_download/README.md)

Если нужен общий архитектурный обзор:

- читайте этот документ

Если нужен конкретный слой:

- infrastructure: [docs/CORE_AND_INFRASTRUCTURE.md](/Users/shemetov/Projects/tg_download/docs/CORE_AND_INFRASTRUCTURE.md)
- routing/uploaded media orchestration: [docs/ROUTING_AND_UPLOADED_MEDIA.md](/Users/shemetov/Projects/tg_download/docs/ROUTING_AND_UPLOADED_MEDIA.md)
- OpenAI/text layer: [docs/OPENAI_AND_TEXT_PROCESSING.md](/Users/shemetov/Projects/tg_download/docs/OPENAI_AND_TEXT_PROCESSING.md)
- YouTube: [docs/YOUTUBE_FLOWS.md](/Users/shemetov/Projects/tg_download/docs/YOUTUBE_FLOWS.md)
- Instagram: [docs/INSTAGRAM_FLOWS.md](/Users/shemetov/Projects/tg_download/docs/INSTAGRAM_FLOWS.md)
- uploaded media services: [docs/UPLOADED_MEDIA_SERVICES.md](/Users/shemetov/Projects/tg_download/docs/UPLOADED_MEDIA_SERVICES.md)

## Что сознательно не делалось

- не строился DI container;
- не делалась command bus / event bus architecture;
- не делался generic media workflow framework;
- не добавлялся persistence layer ради internal runtime state.

Для текущего размера проекта это было бы дороже по сложности, чем полезно по качеству.
