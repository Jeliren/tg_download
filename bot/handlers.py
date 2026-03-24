from dataclasses import dataclass, field

from telebot.apihelper import ApiTelegramException

import services.converter_service as converter_service
import services.instagram_service as instagram_service
import services.music_service as music_service
import services.uploaded_audio_service as uploaded_audio_service
import services.uploaded_video_service as uploaded_video_service
import services.youtube_service as youtube_service
from bot.callback_registry import callback_registry
from bot.callback_router import (
    CALLBACK_ROUTE_DOWNLOAD,
    CALLBACK_ROUTE_FORMAT,
    CALLBACK_ROUTE_MUSIC,
    CALLBACK_ROUTE_UPLOADED_AUDIO,
    CALLBACK_ROUTE_UPLOADED_VIDEO,
    classify_callback_data,
)
from bot.input_router import (
    ROUTE_INSTAGRAM_URL,
    ROUTE_UNKNOWN,
    ROUTE_UPLOADED_AUDIO,
    ROUTE_UPLOADED_VIDEO,
    ROUTE_UPLOADED_VOICE,
    ROUTE_YOUTUBE_URL,
    classify_message,
)
from bot.keyboards import (
    create_inline_markup,
    create_main_reply_markup,
    create_music_results_markup,
    create_uploaded_audio_markup,
    create_uploaded_video_markup,
    create_uploaded_voice_markup,
)
from bot.texts import (
    BROKEN_CALLBACK_TEXT,
    EXPIRED_CALLBACK_TEXT,
    HELP_BUTTON,
    HELP_TEXT,
    INVALID_UPLOADED_MEDIA_TEXT,
    MUSIC_BUTTON,
    MUSIC_DOWNLOAD_FAILED_TEXT,
    MUSIC_DOWNLOAD_STATUS_TEXT,
    MUSIC_EMPTY_QUERY_TEXT,
    MUSIC_NO_RESULTS_TEXT,
    MUSIC_PROMPT_TEXT,
    MUSIC_RESULTS_FOREIGN_USER_TEXT,
    MUSIC_SEARCHING_TEXT,
    READY_FOR_MORE_TEXT,
    SERVICE_BUSY_TEXT,
    UNKNOWN_COMMAND_TEXT,
    WAIT_PREVIOUS_OPERATION_TEXT,
    WELCOME_TEXT,
)
from config import MAX_CONCURRENT_DOWNLOADS
from core.cache import ExpiringStore
from core.task_registry import UserTaskRegistry
from core.task_runner import BackgroundTaskRunner
from services.platforms import (
    is_instagram_url,
    is_youtube_url,
)
from utils.logging_utils import log, log_event, new_operation_id

URL_AVAILABILITY_CACHE_TIME = 60 * 10  # 10 минут
MUSIC_QUERY_STATE_TTL = 60 * 10
MUSIC_RESULTS_PAGE_SIZE = 5


@dataclass
class HandlerRuntime:
    availability_cache: ExpiringStore = field(default_factory=lambda: ExpiringStore(ttl=URL_AVAILABILITY_CACHE_TIME))
    music_query_state: ExpiringStore = field(default_factory=lambda: ExpiringStore(ttl=MUSIC_QUERY_STATE_TTL))
    active_users: UserTaskRegistry = field(default_factory=UserTaskRegistry)
    task_runner: BackgroundTaskRunner = field(
        default_factory=lambda: BackgroundTaskRunner(
            max_workers=MAX_CONCURRENT_DOWNLOADS,
            max_queue_size=MAX_CONCURRENT_DOWNLOADS * 2,
            logger=log,
        )
    )


class BotHandlerCoordinator:
    def __init__(self, bot):
        self.bot = bot
        self.runtime = HandlerRuntime()

    def register(self):
        @self.bot.message_handler(commands=["start"])
        def send_welcome(message):
            self.send_welcome(message)

        @self.bot.message_handler(commands=["help"])
        def send_help(message):
            self.send_help(message)

        @self.bot.message_handler(content_types=["video", "audio", "voice", "document", "text"])
        def handle_message(message):
            self.handle_incoming_message(message)

        @self.bot.callback_query_handler(func=lambda call: True)
        def handle_callback(call):
            self.handle_callback(call)

    def send_welcome(self, message):
        self.bot.reply_to(message, WELCOME_TEXT, reply_markup=self._help_markup())

    def send_help(self, message):
        self.bot.reply_to(message, HELP_TEXT, reply_markup=self._help_markup())

    def handle_video(self, message):
        self.handle_incoming_message(message)

    def handle_audio(self, message):
        self.handle_incoming_message(message)

    def handle_voice(self, message):
        self.handle_incoming_message(message)

    def handle_document(self, message):
        self.handle_incoming_message(message)

    def handle_text_message(self, message):
        self.handle_incoming_message(message)

    def handle_incoming_message(self, message):
        if self._is_music_button_message(message):
            self._enter_music_mode(message)
            return

        route = classify_message(message)

        if route.kind in {ROUTE_UPLOADED_VIDEO, ROUTE_UPLOADED_AUDIO, ROUTE_UPLOADED_VOICE} and not route.file_id:
            log("Не удалось определить file_id для входящего медиа", level="WARNING")
            self.bot.reply_to(message, INVALID_UPLOADED_MEDIA_TEXT)
            return

        if route.kind == ROUTE_UPLOADED_VIDEO:
            self._show_uploaded_video_actions(message, route.file_id)
            return

        if route.kind == ROUTE_UPLOADED_AUDIO:
            self._show_uploaded_audio_actions(message, route.file_id)
            return

        if route.kind == ROUTE_UPLOADED_VOICE:
            self._show_uploaded_voice_actions(message, route.file_id)
            return

        if route.kind == ROUTE_YOUTUBE_URL:
            self._handle_youtube_url(message, route.text)
            return

        if route.kind == ROUTE_INSTAGRAM_URL:
            self._handle_generic_media_url(message, route.text)
            return

        if self._should_treat_as_music_query(message, route.kind):
            self._handle_music_query(message)
            return

        self.bot.reply_to(message, UNKNOWN_COMMAND_TEXT)

    def handle_callback(self, call):
        try:
            route = classify_callback_data(getattr(call, "data", None))

            if route.kind == CALLBACK_ROUTE_DOWNLOAD:
                self._handle_download_callback(call, route.action)
                return

            if route.kind == CALLBACK_ROUTE_UPLOADED_VIDEO:
                self._handle_uploaded_video_callback(call, route.action)
                return

            if route.kind == CALLBACK_ROUTE_UPLOADED_AUDIO:
                self._handle_uploaded_audio_callback(call, route.action)
                return

            if route.kind == CALLBACK_ROUTE_FORMAT:
                self._handle_format_callback(call)
                return

            if route.kind == CALLBACK_ROUTE_MUSIC:
                self._handle_music_callback(call, route.action)
                return

            self.safe_answer_callback(call.id, BROKEN_CALLBACK_TEXT)
        except Exception as e:
            log(f"Ошибка в обработке callback: {e}", level="ERROR")
            self.safe_answer_callback(call.id, "❌ Произошла ошибка при обработке запроса")

    def safe_answer_callback(self, callback_id, text=None):
        """Безопасный ответ на callback запрос с обработкой ошибок."""
        try:
            self.bot.answer_callback_query(callback_id, text=text)
        except ApiTelegramException as e:
            if "query is too old" in str(e) or "query ID is invalid" in str(e):
                log("Ignoring expired callback query", level="DEBUG")
            else:
                log(f"Ошибка при ответе на callback: {e}", level="WARNING")

    def _is_music_button_message(self, message):
        text = (getattr(message, "text", None) or "").strip()
        return text == MUSIC_BUTTON

    def _enter_music_mode(self, message):
        user_id = self._resolve_user_id_from_message(message)
        self.runtime.music_query_state.set(user_id, True)
        self.bot.reply_to(message, MUSIC_PROMPT_TEXT, reply_markup=self._help_markup())

    def _should_treat_as_music_query(self, message, route_kind):
        if route_kind != ROUTE_UNKNOWN:
            return False
        text = (getattr(message, "text", None) or "").strip()
        if not text or text == HELP_BUTTON:
            return False

        user_id = self._resolve_user_id_from_message(message)
        return self.runtime.music_query_state.contains(user_id)

    def _handle_music_query(self, message):
        query = (getattr(message, "text", None) or "").strip()
        user_id = self._resolve_user_id_from_message(message)

        if len(query) < 2:
            self.bot.reply_to(message, MUSIC_EMPTY_QUERY_TEXT)
            self.runtime.music_query_state.set(user_id, True)
            return

        if self.runtime.active_users.is_active(user_id):
            self.bot.reply_to(message, WAIT_PREVIOUS_OPERATION_TEXT)
            return

        status_message = self.bot.reply_to(message, MUSIC_SEARCHING_TEXT)
        self.runtime.music_query_state.set(user_id, True)
        if not self._submit_background_task(
            "music_search",
            self._perform_music_search,
            message.chat.id,
            user_id,
            query,
            status_message.message_id,
        ):
            self._try_edit_message(
                status_message.chat.id,
                status_message.message_id,
                SERVICE_BUSY_TEXT,
            )

    def _perform_music_search(self, chat_id, user_id, query, message_id):
        try:
            results = music_service.search_music(query, max_results=music_service.MAX_MUSIC_RESULTS)
        except music_service.MusicSearchError as exc:
            self.runtime.music_query_state.set(user_id, True)
            self._try_edit_message(chat_id, message_id, exc.user_message)
            return
        except Exception as exc:
            log(f"Ошибка во время music search: {exc}", level="ERROR")
            self.runtime.music_query_state.set(user_id, True)
            self._try_edit_message(chat_id, message_id, SERVICE_BUSY_TEXT)
            return

        if not results:
            self.runtime.music_query_state.set(user_id, True)
            self._try_edit_message(chat_id, message_id, MUSIC_NO_RESULTS_TEXT)
            return

        self.runtime.music_query_state.pop(user_id, None)
        search_id = callback_registry.register_music_search(user_id, query, results)
        text, markup = self._build_music_results_view(search_id, query, results, page=0)

        if not self._try_edit_message(chat_id, message_id, text, reply_markup=markup):
            self.bot.send_message(chat_id, text, reply_markup=markup)

    def _handle_youtube_url(self, message, url):
        status_message = self.bot.reply_to(message, "⏳ Загружаю информацию о видео...")
        url_id = callback_registry.register_action_url(url)

        self._try_edit_message(
            status_message.chat.id,
            status_message.message_id,
            "✅ Выберите действие:",
            reply_markup=create_inline_markup(url_id, include_summary=True),
        )

        future = self._submit_background_task(
            "youtube_availability_check",
            self._check_youtube_availability_thread,
            message.chat.id,
            url,
            status_message.message_id,
        )
        if future is None:
            log("Пропускаем фоновую проверку YouTube доступности из-за перегруженной очереди", level="WARNING")

    def _handle_generic_media_url(self, message, url):
        status_message = self.bot.reply_to(message, "🔍 Проверяю ссылку...")
        if not self._submit_background_task(
            "generic_url_processing",
            self._process_url,
            message.chat.id,
            url,
            status_message.message_id,
        ):
            self._try_edit_message(
                status_message.chat.id,
                status_message.message_id,
                SERVICE_BUSY_TEXT,
            )

    def _handle_download_callback(self, call, action):
        parts = call.data.split(":", 1)
        if len(parts) != 2:
            self.safe_answer_callback(call.id, BROKEN_CALLBACK_TEXT)
            return

        _, url_id = parts
        url = callback_registry.resolve_action_url(url_id)
        if not url:
            self.safe_answer_callback(call.id, EXPIRED_CALLBACK_TEXT)
            return

        log(f"Callback обработка: {action} для {url}")
        if action == "x":
            self.bot.send_message(
                call.message.chat.id,
                "Ок, платную расшифровку не запускаю. Можете отправить другую ссылку.",
            )
            return

        user_id = self._resolve_user_id_from_call(call)
        if not self.runtime.active_users.try_start(user_id):
            self.safe_answer_callback(call.id, WAIT_PREVIOUS_OPERATION_TEXT)
            return

        self.safe_answer_callback(call.id, "⏳ Начинаю обработку...")
        if action == "v":
            status_message = self.bot.send_message(
                call.message.chat.id,
                "⏳ Начинаю загрузку видео... Это может занять немного времени.",
            )
            if not self._submit_locked_user_task(
                user_id,
                "video_download",
                self._handle_video_download,
                call.message.chat.id,
                url,
                status_message.message_id,
            ):
                self._try_edit_message(
                    status_message.chat.id,
                    status_message.message_id,
                    SERVICE_BUSY_TEXT,
                )
            return

        if action == "a":
            status_message = self.bot.send_message(
                call.message.chat.id,
                "⏳ Начинаю извлечение аудио... Это может занять немного времени.",
            )
            if not self._submit_locked_user_task(
                user_id,
                "audio_download",
                self._handle_audio_download,
                call.message.chat.id,
                url,
                status_message.message_id,
            ):
                self._try_edit_message(
                    status_message.chat.id,
                    status_message.message_id,
                    SERVICE_BUSY_TEXT,
                )
            return

        if action == "s":
            status_message = self.bot.send_message(
                call.message.chat.id,
                "⏳ Готовлю саммари видео... Сначала попробую получить субтитры.",
            )
            if not self._submit_locked_user_task(
                user_id,
                "youtube_summary",
                self._handle_summary_download,
                call.message.chat.id,
                url,
                status_message.message_id,
            ):
                self._try_edit_message(
                    status_message.chat.id,
                    status_message.message_id,
                    SERVICE_BUSY_TEXT,
                )
            return

        if action == "t":
            status_message = self.bot.send_message(
                call.message.chat.id,
                "⏳ Запускаю расшифровку аудио и саммари... Это платный и более медленный сценарий.",
            )
            if not self._submit_locked_user_task(
                user_id,
                "youtube_summary_with_transcription",
                self._handle_summary_with_transcription_download,
                call.message.chat.id,
                url,
                status_message.message_id,
            ):
                self._try_edit_message(
                    status_message.chat.id,
                    status_message.message_id,
                    SERVICE_BUSY_TEXT,
                )
            return

        if action == "tr":
            status_message = self.bot.send_message(
                call.message.chat.id,
                "⏳ Запускаю расшифровку рилса... Это может занять немного времени.",
            )
            if not self._submit_locked_user_task(
                user_id,
                "instagram_transcription",
                self._handle_transcription_download,
                call.message.chat.id,
                url,
                status_message.message_id,
            ):
                self._try_edit_message(
                    status_message.chat.id,
                    status_message.message_id,
                    SERVICE_BUSY_TEXT,
                )
            return

        status_message = self.bot.send_message(
            call.message.chat.id,
            "⏳ Получаю описание рилса...",
        )
        if not self._submit_locked_user_task(
            user_id,
            "description_download",
            self._handle_description_download,
            call.message.chat.id,
            url,
            status_message.message_id,
        ):
            self._try_edit_message(
                status_message.chat.id,
                status_message.message_id,
                SERVICE_BUSY_TEXT,
            )

    def _handle_format_callback(self, call):
        parts = call.data.split(":", 2)
        url = None
        format_id = None

        if len(parts) == 2 and parts[0] == "f":
            selection = callback_registry.resolve_format_selection(parts[1])
            if not selection:
                self.safe_answer_callback(call.id, EXPIRED_CALLBACK_TEXT)
                return
            url = selection["url"]
            format_id = selection["format_id"]
        elif len(parts) == 3 and parts[0] == "f":
            _, url_hash, format_id = parts
            url = callback_registry.resolve_format_url(url_hash)
            if not url:
                self.safe_answer_callback(call.id, EXPIRED_CALLBACK_TEXT)
                return
        else:
            self.safe_answer_callback(call.id, BROKEN_CALLBACK_TEXT)
            return

        log(f"Выбран формат {format_id} для {url}")
        user_id = self._resolve_user_id_from_call(call)
        if not self.runtime.active_users.try_start(user_id):
            self.safe_answer_callback(call.id, WAIT_PREVIOUS_OPERATION_TEXT)
            return

        self.safe_answer_callback(call.id, "⏳ Загружаю видео в выбранном качестве...")
        self._try_edit_message(
            call.message.chat.id,
            call.message.message_id,
            "⏳ Начинаю скачивание видео в выбранном качестве...",
        )

        if not self._submit_locked_user_task(
            user_id,
            "youtube_format_download",
            youtube_service.download_youtube_video,
            self.bot,
            call.message.chat.id,
            url,
            call.message.message_id,
            format_id,
        ):
            self.bot.send_message(call.message.chat.id, SERVICE_BUSY_TEXT)

    def _handle_music_callback(self, call, action):
        if action == "mp":
            self._handle_music_page_callback(call)
            return
        if action == "ms":
            self._handle_music_selection_callback(call)
            return
        self.safe_answer_callback(call.id, BROKEN_CALLBACK_TEXT)

    def _handle_music_page_callback(self, call):
        payload, target_page = self._resolve_music_callback_payload(call, expected_parts=3)
        if payload is None or target_page is None:
            return

        self.safe_answer_callback(call.id)
        text, markup = self._build_music_results_view(
            self._extract_music_search_id(call.data),
            payload["query"],
            payload["results"],
            page=target_page,
        )

        if not self._try_edit_message(
            call.message.chat.id,
            call.message.message_id,
            text,
            reply_markup=markup,
        ):
            log("Не удалось обновить сообщение с музыкальной выдачей", level="WARNING")

    def _handle_music_selection_callback(self, call):
        payload, result_index = self._resolve_music_callback_payload(call, expected_parts=3)
        if payload is None or result_index is None:
            return

        results = payload.get("results") or []
        if result_index < 0 or result_index >= len(results):
            self.safe_answer_callback(call.id, BROKEN_CALLBACK_TEXT)
            return

        user_id = self._resolve_user_id_from_call(call)
        if not self.runtime.active_users.try_start(user_id):
            self.safe_answer_callback(call.id, WAIT_PREVIOUS_OPERATION_TEXT)
            return

        self.safe_answer_callback(call.id, "⏳ Начинаю скачивание...")
        status_message = self.bot.send_message(
            call.message.chat.id,
            MUSIC_DOWNLOAD_STATUS_TEXT,
        )
        if not self._submit_locked_user_task(
            user_id,
            "music_audio_download",
            youtube_service.download_youtube_audio,
            self.bot,
            call.message.chat.id,
            results[result_index]["url"],
            status_message.message_id,
            MUSIC_DOWNLOAD_FAILED_TEXT,
        ):
            self._try_edit_message(
                status_message.chat.id,
                status_message.message_id,
                SERVICE_BUSY_TEXT,
            )

    def _resolve_music_callback_payload(self, call, expected_parts):
        parts = (getattr(call, "data", None) or "").split(":")
        if len(parts) != expected_parts:
            self.safe_answer_callback(call.id, BROKEN_CALLBACK_TEXT)
            return None, None

        search_id = parts[1]
        payload = callback_registry.resolve_music_search(search_id)
        if not payload:
            self.safe_answer_callback(call.id, EXPIRED_CALLBACK_TEXT)
            return None, None

        user_id = self._resolve_user_id_from_call(call)
        if payload.get("user_id") != user_id:
            self.safe_answer_callback(call.id, MUSIC_RESULTS_FOREIGN_USER_TEXT)
            return None, None

        try:
            target_value = int(parts[2])
        except (TypeError, ValueError):
            self.safe_answer_callback(call.id, BROKEN_CALLBACK_TEXT)
            return None, None

        return payload, target_value

    def _extract_music_search_id(self, callback_data):
        parts = (callback_data or "").split(":")
        if len(parts) < 2:
            return None
        return parts[1]

    def _handle_uploaded_video_callback(self, call, action):
        parts = call.data.split(":", 1)
        if len(parts) != 2:
            self.safe_answer_callback(call.id, BROKEN_CALLBACK_TEXT)
            return

        _, video_id = parts
        payload = callback_registry.resolve_uploaded_video(video_id)
        if not payload:
            self.safe_answer_callback(call.id, EXPIRED_CALLBACK_TEXT)
            return

        user_id = self._resolve_user_id_from_call(call)
        if not self.runtime.active_users.try_start(user_id):
            self.safe_answer_callback(call.id, WAIT_PREVIOUS_OPERATION_TEXT)
            return

        self.safe_answer_callback(call.id, "⏳ Начинаю обработку...")
        if action == "vn":
            status_message = self.bot.send_message(
                call.message.chat.id,
                "⏳ Делаю кружок из видео...",
            )
            submitted = self._submit_locked_user_task(
                user_id,
                "uploaded_video_note",
                self._handle_uploaded_video_note,
                payload,
                status_message.message_id,
            )
        elif action == "vt":
            status_message = self.bot.send_message(
                call.message.chat.id,
                "⏳ Запускаю расшифровку видео... Это может занять немного времени.",
            )
            submitted = self._submit_locked_user_task(
                user_id,
                "uploaded_video_transcription",
                self._handle_uploaded_video_transcription,
                payload,
                status_message.message_id,
            )
        else:
            status_message = self.bot.send_message(
                call.message.chat.id,
                "⏳ Готовлю саммари видео... Сначала сделаю расшифровку.",
            )
            submitted = self._submit_locked_user_task(
                user_id,
                "uploaded_video_summary",
                self._handle_uploaded_video_summary,
                payload,
                status_message.message_id,
            )

        if not submitted:
            self._try_edit_message(
                status_message.chat.id,
                status_message.message_id,
                SERVICE_BUSY_TEXT,
            )

    def _handle_uploaded_audio_callback(self, call, action):
        parts = call.data.split(":", 1)
        if len(parts) != 2:
            self.safe_answer_callback(call.id, BROKEN_CALLBACK_TEXT)
            return

        _, audio_id = parts
        payload = callback_registry.resolve_uploaded_audio(audio_id)
        if not payload:
            self.safe_answer_callback(call.id, EXPIRED_CALLBACK_TEXT)
            return

        user_id = self._resolve_user_id_from_call(call)
        if not self.runtime.active_users.try_start(user_id):
            self.safe_answer_callback(call.id, WAIT_PREVIOUS_OPERATION_TEXT)
            return

        self.safe_answer_callback(call.id, "⏳ Начинаю обработку...")
        if action == "an":
            status_message = self.bot.send_message(
                call.message.chat.id,
                "⏳ Делаю аудиосообщение из аудио...",
            )
            submitted = self._submit_locked_user_task(
                user_id,
                "uploaded_audio_voice_message",
                self._handle_uploaded_audio_voice_message,
                payload,
                status_message.message_id,
            )
        elif action == "at":
            status_message = self.bot.send_message(
                call.message.chat.id,
                "⏳ Запускаю расшифровку аудио... Это может занять немного времени.",
            )
            submitted = self._submit_locked_user_task(
                user_id,
                "uploaded_audio_transcription",
                self._handle_uploaded_audio_transcription,
                payload,
                status_message.message_id,
            )
        else:
            status_message = self.bot.send_message(
                call.message.chat.id,
                "⏳ Готовлю саммари аудио... Сначала сделаю расшифровку.",
            )
            submitted = self._submit_locked_user_task(
                user_id,
                "uploaded_audio_summary",
                self._handle_uploaded_audio_summary,
                payload,
                status_message.message_id,
            )

        if not submitted:
            self._try_edit_message(
                status_message.chat.id,
                status_message.message_id,
                SERVICE_BUSY_TEXT,
            )

    def _check_youtube_availability_thread(self, chat_id, url, message_id):
        """Фоновая проверка доступности YouTube видео с уведомлением только при ошибке."""
        try:
            is_available = youtube_service.check_youtube_availability(url)
            if not is_available:
                self._try_edit_message(
                    chat_id,
                    message_id,
                    "❌ Видео недоступно или ограничено. Проверьте ссылку.",
                )
        except Exception as e:
            log(f"Ошибка при проверке YouTube: {e}", level="WARNING")

    def _process_url(self, chat_id, url, message_id):
        """Обработка URL в отдельном потоке."""
        op_id = new_operation_id("url")
        log_event("url_processing_started", op=op_id, chat_id=chat_id, url=url)
        try:
            cached_result = self.runtime.availability_cache.get(url)
            if cached_result is True:
                log_event("url_processing_cache_hit", op=op_id, chat_id=chat_id, available=True)
                self._create_and_show_buttons(chat_id, url, message_id)
                return
            if cached_result is False:
                log_event("url_processing_cache_hit", op=op_id, chat_id=chat_id, available=False)
                self._notify_invalid_url(chat_id, message_id)
                return

            is_available = self._check_content_availability(url)
            self.runtime.availability_cache.set(url, is_available)
            log_event("url_processing_checked", op=op_id, chat_id=chat_id, available=is_available)

            if is_available:
                self._create_and_show_buttons(chat_id, url, message_id)
                return

            self._notify_invalid_url(chat_id, message_id)
        except Exception as e:
            log_event("url_processing_failed", level="ERROR", op=op_id, chat_id=chat_id, error=e)
            error_text = "❌ Не удалось проверить ссылку. Попробуйте ещё раз чуть позже."
            if not self._try_edit_message(chat_id, message_id, error_text):
                self.bot.send_message(chat_id, error_text)

    def _create_and_show_buttons(self, chat_id, url, message_id):
        url_id = callback_registry.register_action_url(url)
        include_description = is_instagram_url(url)
        include_summary = is_youtube_url(url)
        include_transcription = is_instagram_url(url)

        if not self._try_edit_message(
            chat_id,
            message_id,
            "✅ Контент доступен для скачивания. Выберите действие:",
            reply_markup=create_inline_markup(
                url_id,
                include_description=include_description,
                include_summary=include_summary,
                include_transcription=include_transcription,
            ),
        ):
            self.bot.send_message(
                chat_id,
                "✅ Контент доступен для скачивания. Выберите действие:",
                reply_markup=create_inline_markup(
                    url_id,
                    include_description=include_description,
                    include_summary=include_summary,
                    include_transcription=include_transcription,
                ),
            )

    def _notify_invalid_url(self, chat_id, message_id):
        text = "❌ К сожалению, не могу обработать эту ссылку. Проверьте её правильность."
        if not self._try_edit_message(chat_id, message_id, text):
            self.bot.send_message(chat_id, text)

    def _check_content_availability(self, url):
        if is_youtube_url(url):
            return youtube_service.check_youtube_availability(url)
        if is_instagram_url(url):
            return instagram_service.check_instagram_availability(url)
        return False

    def _handle_uploaded_video_note(self, payload, status_message_id=None):
        chat_id = payload["chat_id"]
        user_id = payload.get("user_id")
        op_id = new_operation_id("video-note")
        try:
            if status_message_id:
                self._try_edit_message(
                    chat_id,
                    status_message_id,
                    "⏳ Обработка видео... Это займет некоторое время.",
                )

            log_event("video_note_started", op=op_id, chat_id=chat_id, user_id=user_id)
            success = converter_service.convert_video_file_to_video_note(
                self.bot,
                chat_id,
                user_id,
                payload["file_id"],
            )

            if success and status_message_id:
                self._try_edit_message(
                    chat_id,
                    status_message_id,
                    "✅ Видео-кружок успешно создан!",
                )

            if success:
                self.bot.send_message(chat_id, READY_FOR_MORE_TEXT)
                log_event("video_note_finished", op=op_id, chat_id=chat_id, user_id=user_id)
        except Exception as e:
            log_event("video_note_failed", level="ERROR", op=op_id, chat_id=chat_id, user_id=user_id, error=e)
            try:
                self.bot.send_message(
                    chat_id,
                    "❌ Произошла ошибка при конвертации. Возможно, видео слишком длинное или большое.",
                )
            except Exception as send_error:
                log(f"Не удалось отправить сообщение об ошибке: {send_error}", level="ERROR")
        finally:
            log_event("video_note_cleanup", op=op_id, user_id=user_id)

    def _handle_video_download(self, chat_id, url, message_id=None):
        if is_youtube_url(url):
            youtube_service.download_youtube_video(self.bot, chat_id, url, message_id)
        elif is_instagram_url(url):
            instagram_service.download_instagram_video(self.bot, chat_id, url, message_id)
        else:
            self.bot.send_message(chat_id, "❌ Неподдерживаемый тип ссылки")

    def _handle_audio_download(self, chat_id, url, message_id=None):
        if is_youtube_url(url):
            youtube_service.download_youtube_audio(self.bot, chat_id, url, message_id)
        elif is_instagram_url(url):
            instagram_service.download_instagram_audio(self.bot, chat_id, url, message_id)
        else:
            self.bot.send_message(
                chat_id,
                "❌ Извлечение аудио поддерживается только для YouTube и Instagram",
            )

    def _handle_description_download(self, chat_id, url, message_id=None):
        if is_instagram_url(url):
            instagram_service.download_instagram_description(self.bot, chat_id, url, message_id)
        else:
            self.bot.send_message(chat_id, "❌ Описание сейчас поддерживается только для Instagram.")

    def _handle_transcription_download(self, chat_id, url, message_id=None):
        if is_instagram_url(url):
            instagram_service.transcribe_instagram_reel(self.bot, chat_id, url, message_id)
        else:
            self.bot.send_message(chat_id, "❌ Расшифровка сейчас поддерживается только для Instagram.")

    def _handle_summary_download(self, chat_id, url, message_id=None):
        if is_youtube_url(url):
            youtube_service.summarize_youtube_video(self.bot, chat_id, url, message_id)
        else:
            self.bot.send_message(chat_id, "❌ Саммари сейчас поддерживается только для YouTube.")

    def _handle_summary_with_transcription_download(self, chat_id, url, message_id=None):
        if is_youtube_url(url):
            youtube_service.transcribe_and_summarize_youtube_video(self.bot, chat_id, url, message_id)
        else:
            self.bot.send_message(chat_id, "❌ Расшифровка и саммари сейчас поддерживаются только для YouTube.")

    def _handle_uploaded_video_transcription(self, payload, status_message_id=None):
        uploaded_video_service.transcribe_uploaded_video(
            self.bot,
            payload["chat_id"],
            payload.get("user_id"),
            payload["file_id"],
            message_id=status_message_id,
        )

    def _handle_uploaded_video_summary(self, payload, status_message_id=None):
        uploaded_video_service.summarize_uploaded_video(
            self.bot,
            payload["chat_id"],
            payload.get("user_id"),
            payload["file_id"],
            message_id=status_message_id,
        )

    def _handle_uploaded_audio_voice_message(self, payload, status_message_id=None):
        chat_id = payload["chat_id"]
        user_id = payload.get("user_id")
        op_id = new_operation_id("audio-message")
        try:
            if status_message_id:
                self._try_edit_message(
                    chat_id,
                    status_message_id,
                    "⏳ Обработка аудио... Это займет некоторое время.",
                )

            log_event("audio_message_started", op=op_id, chat_id=chat_id, user_id=user_id)
            success = converter_service.convert_audio_file_to_voice_message(
                self.bot,
                chat_id,
                user_id,
                payload["file_id"],
            )

            if success and status_message_id:
                self._try_edit_message(
                    chat_id,
                    status_message_id,
                    "✅ Аудиосообщение успешно создано!",
                )

            if success:
                self.bot.send_message(chat_id, READY_FOR_MORE_TEXT)
                log_event("audio_message_finished", op=op_id, chat_id=chat_id, user_id=user_id)
        except Exception as e:
            log_event("audio_message_failed", level="ERROR", op=op_id, chat_id=chat_id, user_id=user_id, error=e)
            try:
                self.bot.send_message(chat_id, "❌ Произошла ошибка при подготовке аудиосообщения.")
            except Exception as send_error:
                log(f"Не удалось отправить сообщение об ошибке: {send_error}", level="ERROR")
        finally:
            log_event("audio_message_cleanup", op=op_id, user_id=user_id)

    def _handle_uploaded_audio_transcription(self, payload, status_message_id=None):
        uploaded_audio_service.transcribe_uploaded_audio(
            self.bot,
            payload["chat_id"],
            payload.get("user_id"),
            payload["file_id"],
            message_id=status_message_id,
        )

    def _handle_uploaded_audio_summary(self, payload, status_message_id=None):
        uploaded_audio_service.summarize_uploaded_audio(
            self.bot,
            payload["chat_id"],
            payload.get("user_id"),
            payload["file_id"],
            message_id=status_message_id,
        )

    def _show_uploaded_video_actions(self, message, file_id):
        payload = self._build_uploaded_payload(message, file_id)
        video_id = callback_registry.register_uploaded_video(payload)
        prompt = (
            "🎬 Что сделать с этим видеофайлом?"
            if getattr(message, "document", None) is not None
            else "🎬 Что сделать с этим видео?"
        )
        self.bot.reply_to(
            message,
            prompt,
            reply_markup=create_uploaded_video_markup(video_id),
        )

    def _show_uploaded_audio_actions(self, message, file_id):
        payload = self._build_uploaded_payload(message, file_id)
        audio_id = callback_registry.register_uploaded_audio(payload)
        prompt = (
            "🎵 Что сделать с этим аудиофайлом?"
            if getattr(message, "document", None) is not None
            else "🎵 Что сделать с этим аудио?"
        )
        self.bot.reply_to(
            message,
            prompt,
            reply_markup=create_uploaded_audio_markup(audio_id),
        )

    def _show_uploaded_voice_actions(self, message, file_id):
        payload = self._build_uploaded_payload(message, file_id)
        voice_id = callback_registry.register_uploaded_voice(payload)
        self.bot.reply_to(
            message,
            "🎙 Что сделать с этим голосовым сообщением?",
            reply_markup=create_uploaded_voice_markup(voice_id),
        )

    def _build_music_results_view(self, search_id, query, results, page):
        total_results = len(results)
        total_pages = max(1, (total_results + MUSIC_RESULTS_PAGE_SIZE - 1) // MUSIC_RESULTS_PAGE_SIZE)
        page = max(0, min(page, total_pages - 1))
        start_index = page * MUSIC_RESULTS_PAGE_SIZE
        end_index = start_index + MUSIC_RESULTS_PAGE_SIZE
        page_results = results[start_index:end_index]

        lines = [
            f"🎵 Найдено результатов: {total_results}. Страница {page + 1} из {total_pages}. Выбери трек.",
            f"Запрос: {query}",
        ]
        for offset, result in enumerate(page_results, start=start_index + 1):
            duration = f" ({result['duration_label']})" if result.get("duration_label") else ""
            lines.append(f"{offset}. {result['display_title']}{duration}")

        return "\n".join(lines), create_music_results_markup(search_id, page_results, page, total_pages)

    def _help_markup(self):
        return create_main_reply_markup()

    def _build_uploaded_payload(self, message, file_id):
        return {
            "chat_id": getattr(getattr(message, "chat", None), "id", None),
            "message_id": getattr(message, "message_id", None),
            "file_id": file_id,
            "user_id": self._resolve_user_id_from_message(message),
        }

    def _resolve_user_id_from_message(self, message):
        from_user = getattr(message, "from_user", None)
        user_id = getattr(from_user, "id", None)
        if user_id is not None:
            return user_id
        return getattr(getattr(message, "chat", None), "id", None)

    def _resolve_user_id_from_call(self, call):
        from_user = getattr(call, "from_user", None)
        user_id = getattr(from_user, "id", None)
        if user_id is not None:
            return user_id
        message = getattr(call, "message", None)
        return self._resolve_user_id_from_message(message)

    def _submit_locked_user_task(self, user_id, task_name, target, *args):
        future = self._submit_background_task(task_name, target, *args)
        if future is None:
            self.runtime.active_users.finish(user_id)
            return None

        if hasattr(future, "add_done_callback"):
            future.add_done_callback(lambda _: self.runtime.active_users.finish(user_id))
        return future

    def _submit_background_task(self, task_name, target, *args):
        return self.runtime.task_runner.submit(task_name, target, *args)

    def _try_edit_message(self, chat_id, message_id, text, reply_markup=None):
        try:
            self.bot.edit_message_text(
                text=text,
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=reply_markup,
            )
            return True
        except ApiTelegramException as e:
            if "message is not modified" not in str(e):
                log(f"Ошибка при обновлении сообщения: {e}", level="WARNING")
            return False


def register_handlers(bot):
    """Регистрация всех обработчиков бота."""
    BotHandlerCoordinator(bot).register()
