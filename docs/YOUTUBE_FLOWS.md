# YouTube Flows

Этот документ описывает YouTube-часть проекта:

- поиск музыки по текстовому запросу;
- скачивание видео;
- скачивание аудио;
- выбор качества;
- summary по субтитрам;
- paid transcription + summary fallback.

## Почему это выделено отдельно

YouTube в проекте не сводится к одному downloader-сценарию. Здесь есть несколько разных user flows с разными требованиями:

- быстрый download;
- download с выбором качества;
- summary через уже доступные субтитры;
- платный fallback через OpenAI, если субтитров нет.

Если держать всё это только в одном большом сервисе без отдельного описания, быстро теряются:

- product rules;
- различия между UI-quality list и internal fallback;
- границы между subtitle flow и audio-transcription flow.

## Основной модуль

- `services/youtube_service.py`

Связанные части:

- `bot/keyboards.py`
- `bot/callback_router.py`
- `bot/handlers.py`
- `services/music_service.py`
- `services/summary_service.py`
- `services/transcription_service.py`

## User-facing сценарии

### Музыка

Поток:

1. пользователь нажимает кнопку `Музыка`;
2. бот просит текстовый запрос;
3. `services/music_service.py` выполняет `yt-dlp` search и нормализует до компактной выдачи;
4. результаты хранятся в callback registry с TTL и листаются через inline callback'и;
5. выбранный результат передаётся в уже существующий `download_youtube_audio(...)`.

Это важно: music search не вводит новый downloader и не дублирует YouTube audio logic.

### Скачать видео

Поток:

1. пользователь отправляет YouTube URL;
2. бот показывает кнопки `Видео / Аудио / Саммари`;
3. при выборе `Видео` сначала предлагает выбор качества;
4. после выбора качества скачивает видео и отправляет его в Telegram.

### Скачать аудио

Поток проще:

1. скачать audio stream;
2. при необходимости извлечь/конвертировать mp3 через `yt-dlp`;
3. отправить как Telegram audio.

### Саммари

По умолчанию summary для YouTube старается быть “дешёвым” и быстрым:

1. загрузить metadata;
2. найти подходящие субтитры;
3. скачать subtitle text;
4. отдать transcript в summary pipeline.

Если пригодных субтитров нет:

1. бот честно пишет, что subtitle path не сработал;
2. предлагает отдельную кнопку платной расшифровки;
3. только после явного подтверждения идёт в audio transcription + summary.

Это важная product boundary: paid flow не стартует автоматически.

## Выбор качества

### UI-список форматов

Для выбора качества бот показывает компактный список top quality options.

Это именно UI-список, а не полный внутренний набор всех fallback-вариантов.

Список:

- строится по доступным video heights;
- объединяет video+audio через selector вида `bv*[height<=?720]+ba/b[height<=?720]`;
- ограничивается верхними quality options, чтобы клавиатура не становилась слишком длинной.

### Internal fallback для `best`

Важный нюанс: internal fallback теперь не зависит от UI-limit.

Если пользователь выбирает `best`, сервис:

- собирает все реально доступные высоты;
- пробует их по убыванию;
- если очередной вариант не помещается в Telegram, идёт ниже.

Это позволяет не застрять в ситуации, где UI показал только top-6 quality options, а Telegram-safe размер был бы только у более низкого разрешения.

### Что происходит, если выбранное качество слишком большое

Если пользователь выбрал конкретное качество и итоговый файл оказался больше Telegram limit:

- бот не заканчивает flow тупиком;
- вместо этого повторно предлагает более низкие варианты;
- кнопка “best” в таком re-offer не показывается, чтобы не возвращать пользователя в тот же oversized path.

Это делает format-selection flow заметно практичнее.

## Subtitle flow

### Выбор языка

Приоритет такой:

1. manual subtitles на русском;
2. automatic captions на русском;
3. manual subtitles на английском;
4. automatic captions на английском;
5. затем любой manual language;
6. затем любой automatic language.

Это хороший pragmatic default для текущего бота.

### Parsing VTT

Subtitle parsing intentionally остаётся простым, но теперь аккуратнее:

- служебные строки `WEBVTT`, `Kind:`, `Language:`, `NOTE` не попадают в transcript;
- cue identifier lines не попадают в transcript;
- подряд идущие одинаковые caption lines схлопываются;
- повтор фразы позже по видео сохраняется.

Последний пункт важен: глобальная dedupe-логика выглядела аккуратно, но на практике могла выкидывать реальные повторяющиеся фразы из видео.

## Download constraints

### Telegram file limit

YouTube video/audio send path ограничен `MAX_FILE_SIZE`.

Для видео это значит:

- oversized variant для `best` ведёт к попытке более низкого качества;
- oversized explicit quality ведёт к re-offer lower qualities;
- если Telegram-safe вариант не найден, бот честно сообщает об этом.

### OpenAI transcription limit

Paid transcription + summary flow дополнительно ограничен лимитом transcription endpoint.

Если аудио больше лимита:

- бот не пытается “как-нибудь протолкнуть” файл;
- честно пишет, что видео слишком длинное для автоматического сценария.

## Архитектурные границы

### Что делает `youtube_service.py`

- собирает metadata через `yt-dlp`;
- получает format options;
- скачивает media;
- получает subtitles;
- управляет YouTube-specific fallback rules;
- вызывает shared transcription/summary services.

### Что он не делает

- не маршрутизирует callback_data;
- не решает, какой callback относится к YouTube;
- не хранит callback registry state сам по себе;
- не реализует generic OpenAI client.

Эти обязанности остаются в других слоях.

## Что здесь сознательно не делалось

### Не вводился отдельный quality negotiation framework

Для проекта достаточно:

- компактного UI quality list;
- полного internal fallback для `best`;
- lower-quality re-offer при explicit oversized selection.

### Не делалась “магическая” нормализация YouTube video перед Telegram

YouTube path в основном опирается на `yt-dlp` selectors и Telegram size limit, а не на тяжёлую post-processing pipeline как в некоторых Instagram/uploaded video сценариях.

### Не добавлялся автозапуск paid fallback

Это было бы удобнее для кода, но хуже как product behavior.

## Когда этот слой стоит менять дальше

Хорошие причины:

- понадобилось smarter error classification для YouTube restrictions;
- качество/размер selection требует новой эвристики;
- subtitles quality начала часто ломать summary quality;
- появились новые user-facing YouTube actions.

Плохие причины:

- “давайте перепишем весь flow в generic media engine”;
- “давайте спрячем все product rules за универсальным abstraction layer”;
- “давайте автоматически тратить OpenAI на все видео, где нет субтитров”.

Для текущего проекта YouTube слой уже должен быть достаточно надёжным и понятным, но без лишней архитектурной тяжести.
