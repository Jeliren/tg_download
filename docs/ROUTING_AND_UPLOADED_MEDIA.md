# Routing And Uploaded Media

Этот документ описывает слой маршрутизации входящих сообщений и callback'ов, а также обработку загруженных пользователем видео, аудио и голосовых сообщений.

## Зачем это вынесено

В боте есть два отдельных, но похожих по задаче механизма:

1. Нужно понять, что прислал пользователь:
   - ссылку на YouTube;
   - ссылку на Instagram;
   - обычное видео;
   - обычное аудио;
   - голосовое сообщение;
   - аудио- или видеофайл, присланный как `document`.
2. Нужно понять, что означает нажатый callback:
   - скачать видео или аудио по ссылке;
   - получить описание или расшифровку;
   - обработать загруженный медиафайл;
   - выбрать формат YouTube;
   - перелистнуть или выбрать результат music search.

Раньше эта логика постепенно расползалась по `bot/handlers.py`. Сейчас она вынесена в отдельные роутеры, а `BotHandlerCoordinator` остался координатором сценариев.

## Ключевые модули

- `bot/input_router.py` — классификация входящих Telegram message.
- `bot/callback_router.py` — классификация Telegram callback payload.
- `bot/handlers.py` — orchestration: показ кнопок, запуск background tasks, вызов сервисов.
- `bot/callback_registry.py` — хранение коротких payload-ов для callback-кнопок.
- `bot/keyboards.py` — сборка Telegram inline keyboard.
- `services/music_service.py` — поиск по YouTube и нормализация музыкальной выдачи.
- `services/uploaded_media_service.py` — общие helper'ы для загруженных медиа.
- `services/uploaded_video_service.py` — расшифровка и саммари загруженного видео.
- `services/uploaded_audio_service.py` — расшифровка и саммари загруженного аудио.
- `services/converter_service.py` — video note и voice message конвертация.

Подробное описание service layer лежит отдельно в:

- `docs/UPLOADED_MEDIA_SERVICES.md`

## Входящие сообщения

`bot/input_router.py` возвращает `IncomingMessageRoute` со следующими route kind:

- `uploaded_video`
- `uploaded_audio`
- `uploaded_voice`
- `youtube_url`
- `instagram_url`
- `unknown`

### Как определяется тип

Порядок проверки такой:

1. `message.video`
2. `message.audio`
3. `message.voice`
4. `message.document`
5. `message.text`

Это важно, потому что `document` может нести и аудио, и видео, но нативные Telegram media-типы должны иметь приоритет.

### Документы

Для `message.document` используются две эвристики:

- `mime_type`
- расширение `file_name`

Аудиодокумент определяется по:

- `audio/*`
- `.aac`, `.aiff`, `.alac`, `.flac`, `.m4a`, `.mp3`, `.oga`, `.ogg`, `.opus`, `.wav`, `.wma`

Видеодокумент определяется по:

- `video/*`
- `.3gp`, `.avi`, `.m4v`, `.mkv`, `.mov`, `.mp4`, `.mpeg`, `.mpg`, `.webm`

Приоритет у аудиодокумента выше, чем у видеодокумента, чтобы файл с `audio/*` не уехал в видео-ветку из-за расширения.

### URL

Для текста используется `services.platforms.detect_platform`, который распознает:

- YouTube
- Instagram reel / post / story media links

Если текст не является поддержанной ссылкой, route становится `unknown`.

Это используется и для сценария `Музыка`: вход в режим делает сам `BotHandlerCoordinator`, а следующий обычный `unknown` text временно трактуется как music query, если для пользователя активен краткоживущий in-memory state.

## Callback routing

`bot/callback_router.py` возвращает `CallbackRoute` со следующими route kind:

- `download`
- `uploaded_video`
- `uploaded_audio`
- `format`
- `music`
- `unknown`

### Группы callback-префиксов

`download`:

- `v` — скачать видео по ссылке
- `a` — скачать аудио по ссылке
- `d` — описание Instagram
- `s` — саммари YouTube
- `t` — платная расшифровка + саммари YouTube
- `tr` — расшифровка Instagram reel
- `x` — отмена

`uploaded_video`:

- `vn` — video note из загруженного видео
- `vt` — расшифровка загруженного видео
- `vs` — саммари загруженного видео

`uploaded_audio`:

- `an` — voice message из загруженного аудио
- `at` — расшифровка загруженного аудио или voice
- `as` — саммари загруженного аудио или voice

`format`:

- `f` — выбранный формат YouTube

`music`:

- `mp` — перелистывание страницы музыкальной выдачи
- `ms` — выбор конкретного результата

## Callback registry

`bot/callback_registry.py` хранит четыре типа данных:

- action URL для ссылочных сценариев
- format selections для YouTube
- uploaded media payload для локально присланных файлов
- music search payload с `user_id`, `query` и нормализованными результатами

### Что важно про uploaded media payload

Сейчас `handlers.py` передаёт в registry уже нормализованный payload:

- `chat_id`
- `message_id`
- `file_id`
- `user_id`

Registry всё ещё умеет собрать payload из сырого Telegram message для обратной совместимости и тестов, но основной runtime-путь теперь использует уже подготовленные данные. Это уменьшает риск повторной “угадайки” и ошибок вроде `file_id not specified`.

## Роль BotHandlerCoordinator

`bot/handlers.py` теперь отвечает не за распознавание типа входа, а за orchestration.

### Что он делает

- регистрирует Telegram handlers;
- вызывает `classify_message(...)` для входящих сообщений;
- вызывает `classify_callback_data(...)` для callback'ов;
- показывает нужные клавиатуры;
- запускает background tasks;
- следит за user lock через `UserTaskRegistry`;
- держит короткое user state ожидания music query через `ExpiringStore`;
- прокидывает управление в service layer.

### Что он не делает

- не парсит URL вручную;
- не определяет тип `document` по расширению самостоятельно;
- не решает по callback-префиксам через большой набор `if action in {...}` на верхнем уровне.

## Uploaded media flows

### Загруженное видео

Поток:

1. `input_router` классифицирует сообщение как `uploaded_video`
2. `handlers` показывает кнопки `Кружок / Расшифровка / Саммари`
3. callback идёт в `uploaded_video` route
4. `handlers` вызывает:
   - `converter_service.convert_video_file_to_video_note`
   - `uploaded_video_service.transcribe_uploaded_video`
   - `uploaded_video_service.summarize_uploaded_video`

### Загруженное аудио

Поток:

1. `input_router` классифицирует сообщение как `uploaded_audio`
2. `handlers` показывает кнопки `Аудиосообщение / Расшифровка / Саммари`
3. callback идёт в `uploaded_audio` route
4. `handlers` вызывает:
   - `converter_service.convert_audio_file_to_voice_message`
   - `uploaded_audio_service.transcribe_uploaded_audio`
   - `uploaded_audio_service.summarize_uploaded_audio`

### Голосовое сообщение

Поток:

1. `input_router` классифицирует сообщение как `uploaded_voice`
2. `handlers` показывает только `Расшифровка / Саммари`
3. используются те же `uploaded_audio_service.*` сценарии

Кнопка создания voice message не показывается, потому что исходный формат уже является голосовым сообщением.

## Shared service helpers

`services/uploaded_media_service.py` содержит общие примитивы:

- создание/очистка temp dir
- безопасное обновление status message
- скачивание файла из Telegram по `file_id`
- извлечение аудио из видео
- подготовка audio track для uploaded video

Это уменьшает дублирование между `uploaded_video_service.py` и `uploaded_audio_service.py`.

## Защита от плохих входов

В `BotHandlerCoordinator.handle_incoming_message` есть защита от случая, когда route определён как uploaded media, но `file_id` не удалось получить. В этом случае бот честно отвечает пользователю, что файл не удалось определить, вместо того чтобы падать позже на `bot.get_file(None)`.

## Как расширять дальше

### Если нужно добавить новый тип входящего сообщения

1. Добавить классификацию в `bot/input_router.py`
2. Добавить user-facing prompt и keyboard в `bot/handlers.py` / `bot/keyboards.py`
3. При необходимости добавить новый service
4. Добавить тесты на router и handler

### Если нужно добавить новый callback

1. Добавить action prefix в `bot/callback_router.py`
2. Добавить кнопку в `bot/keyboards.py`
3. Подключить исполнение в `bot/handlers.py`
4. Добавить тесты на router и orchestration

## Почему архитектура сейчас считается удачной

Для текущего размера проекта это хорошая компромиссная точка:

- есть отдельные точки принятия решений;
- нет тяжёлой “framework-like” архитектуры;
- `handlers.py` остаётся читаемым;
- новые действия добавляются локально;
- логика хорошо покрывается unit-тестами.

Иными словами, это уже не набор ad-hoc условий, но ещё и не переусложнённая система команд/шины/DI-контейнеров.
