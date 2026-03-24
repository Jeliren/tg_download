# OpenAI And Text Processing

Этот документ описывает слой, который отвечает за:

- OpenAI HTTP-запросы;
- транскрипцию аудио;
- разбиение текста на chunk'и;
- суммаризацию транскриптов;
- правила fallback между субтитрами, аудио и финальным summary.

## Зачем это выделено отдельно

В проекте уже есть несколько user-facing сценариев, которые выглядят по-разному, но под капотом используют один и тот же текстовый pipeline:

- YouTube summary по субтитрам;
- YouTube paid transcription + summary;
- Instagram reel transcription;
- transcription/summary для uploaded audio;
- transcription/summary для uploaded video.

Если этот слой описан плохо, код быстро начинает расходиться:

- одни сценарии по-разному режут длинный текст;
- одни повторяют OpenAI-запросы, а другие нет;
- одни считают пустой ответ ошибкой, а другие молча продолжают;
- временные сетевые проблемы начинают выглядеть как “непонятная ошибка бота”.

## Основные модули

- `services/openai_client.py`
- `services/transcription_service.py`
- `services/summary_service.py`

Связанные caller'ы:

- `services/youtube_service.py`
- `services/instagram_service.py`
- `services/uploaded_audio_service.py`
- `services/uploaded_video_service.py`

## `openai_client.py`

Это низкоуровневый HTTP helper для OpenAI.

### Что он делает

- собирает headers с Bearer token;
- выполняет `POST` в OpenAI;
- повторяет запрос для действительно временных проблем;
- превращает временные деградации в отдельную ошибку `OpenAITemporaryError`.

### Что считается временной проблемой

- `requests.Timeout`
- `requests.ConnectionError`
- HTTP `429`
- HTTP `500`
- HTTP `502`
- HTTP `503`
- HTTP `504`

### Почему это полезно

Раньше summary и transcription сервисы сами руками делали `requests.post(...)` и каждый раз по сути решали одну и ту же задачу заново.

Теперь низкоуровневый контракт единый:

- временные проблемы retry'ятся ограниченное число раз;
- если даже после retry не получилось, caller получает `OpenAITemporaryError`;
- неretryable HTTP ошибки остаются честными `HTTPError`.

Это даёт более предсказуемое поведение и уменьшает дублирование.

## `transcription_service.py`

Этот модуль отвечает за две вещи:

- отправку аудиофайла в OpenAI transcription endpoint;
- разбиение длинного текста на Telegram-safe chunk'и.

### `transcribe_audio_with_openai(...)`

Функция:

- принимает локальный путь к аудиофайлу;
- отправляет файл в OpenAI;
- возвращает только итоговый текст.

Она не занимается:

- temp directory lifecycle;
- скачиванием файлов из Telegram / YouTube / Instagram;
- user-facing сообщениями;
- summary logic.

Это важно: transcription service — технический building block, а не orchestration-слой.

### Chunking для отправки в Telegram

`split_text_chunks(...)` и `send_text_chunks(...)` используются для длинных транскриптов.

Инварианты:

- chunk size должен быть положительным;
- длинные слова режутся, а не ломают pipeline;
- короткие абзацы стараются группироваться в один chunk;
- пустой текст возвращает пустой список, а не фиктивный chunk.

По умолчанию используется `4096`, то есть безопасный лимит для Telegram text message.

## `summary_service.py`

Этот модуль работает уже не с аудио, а с готовым transcript text.

### Что он делает

- считает, на сколько summary-chunk'ов развалится текст;
- строит prompt для single-pass summary;
- строит prompt для chunk summary;
- строит merge prompt для финальной сборки.

### Single-pass vs chunked summary

Если транскрипт короткий, используется один OpenAI-запрос.

Если длинный:

1. текст режется на крупные части;
2. для каждой части делается компактное partial summary;
3. из partial summaries собирается финальное summary.

### Почему это правильный компромисс

Для этого проекта важно не “идеально токен-оптимально”, а:

- достаточно надёжно;
- достаточно читаемо;
- без излишне сложного token accounting слоя;
- с понятной отладкой и прогнозируемым поведением.

Поэтому сейчас используется character-based chunking с отдельным merge-pass, а не более тяжёлый generic summarization framework.

## Caller flows

## YouTube summary

Поток:

1. загрузить метаданные видео;
2. попробовать получить субтитры;
3. если субтитры есть, отдать текст в `summary_service`;
4. если субтитров нет или они непригодны, предложить отдельный paid fallback;
5. только по явному подтверждению скачать аудио, отдать его в transcription, потом в summary.

### Почему это важно

Это сохраняет правильную product boundary:

- бесплатный путь использует уже доступный текст;
- платный путь запускается только по подтверждению;
- бот не делает вид, что умеет “саммаризировать YouTube URL напрямую”.

## Uploaded audio / video

Поток:

1. caller готовит локальный аудиофайл;
2. transcription service получает текст;
3. текст либо отправляется пользователю chunk'ами, либо уходит в summary service;
4. user-facing тексты и status messages остаются на стороне caller'а.

Это позволяет держать orchestration отдельно от OpenAI-логики.

## Instagram transcription

Поток похожий, но без summary:

1. достать audio asset рилса;
2. проверить размер;
3. отправить в transcription;
4. отдать пользователю текст кусками.

Instagram тут intentionally не делит flow на subtitles и paid fallback, потому что продуктово это другой сценарий.

## Error model

### Missing OpenAI config

Caller'ы проверяют `OPENAI_API_KEY` заранее и дают понятный user-facing ответ.

Это сделано специально, чтобы пользователь видел проблему конфигурации как проблему конфигурации, а не как безликий `401`.

### Temporary OpenAI failures

После bounded retry низкоуровневый слой поднимает `OpenAITemporaryError`.

Caller'ы обрабатывают его отдельно и отвечают честно:

- OpenAI временно недоступен;
- попробуйте ещё раз чуть позже.

Это лучше, чем маскировать деградацию сети/API под “не удалось подготовить файл”.

### Permanent API errors

Если OpenAI вернул нерetryable HTTP error, наружу идёт `requests.HTTPError`.

Caller сообщает, что OpenAI API вернул ошибку, не подменяя её на “видео плохое” или “ссылка сломана”.

### Пустые результаты

Слой считает это ошибкой, а не успехом:

- пустая транскрипция не отправляется как “готово”;
- пустое partial summary ломает merge flow;
- пустое итоговое summary не скрывается.

Это делает поведение production-friendly и честным.

## Что здесь сознательно не делалось

### Не вводился отдельный token-accounting framework

Сейчас это было бы дороже по сложности, чем полезно проекту.

### Не добавлялась единая super-абстракция для всех media/text workflows

Хотя YouTube, Instagram и uploaded media используют общий OpenAI слой, user-facing orchestration у них всё равно разная.

### Не убиралось всё дублирование до нуля

Некоторая часть повторения на стороне caller'ов нормальна:

- разные тексты ошибок;
- разные статусы;
- разные fallback rules;
- разные product expectations.

## Когда этот слой стоит менять дальше

Хорошие причины:

- появились новые OpenAI use cases;
- нужно расширить retry policy;
- нужно улучшить observability и usage logging;
- chunking начал реально ломать длинные сценарии.

Плохие причины:

- “давайте сделаем универсальный AI workflow engine”;
- “давайте перепишем всё под generic agents pipeline без конкретной боли”;
- “давайте спрячем все различия между YouTube и Instagram”.

Для текущего проекта этот слой уже должен быть аккуратным и надёжным, но всё ещё оставаться достаточно прямым для чтения и отладки.
