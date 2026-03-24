__all__ = [
    "create_inline_markup",
    "create_main_reply_markup",
    "create_format_selection_markup",
    "create_music_results_markup",
    "create_transcription_confirmation_markup",
    "create_uploaded_audio_markup",
    "create_uploaded_voice_markup",
    "create_uploaded_video_markup",
]

from telebot import types

from bot.texts import HELP_BUTTON, MUSIC_BUTTON


def _human_size(size_bytes):
    if not size_bytes:
        return ""

    units = ["B", "KB", "MB", "GB"]
    size = float(size_bytes)
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1

    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    return f"{size:.1f} {units[unit_index]}"


def create_inline_markup(
    url_id,
    include_description=False,
    include_summary=False,
    include_transcription=False,
):
    """Создает инлайн-клавиатуру для выбора действия"""
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("📹 Скачать видео", callback_data=f"v:{url_id}"),
        types.InlineKeyboardButton("🎵 Скачать аудио", callback_data=f"a:{url_id}")
    )
    if include_summary:
        markup.row(types.InlineKeyboardButton("🧠 Саммари", callback_data=f"s:{url_id}"))
    extra_buttons = []
    if include_description:
        extra_buttons.append(types.InlineKeyboardButton("📝 Описание", callback_data=f"d:{url_id}"))
    if include_transcription:
        extra_buttons.append(types.InlineKeyboardButton("🎙 Расшифровка", callback_data=f"tr:{url_id}"))
    if extra_buttons:
        markup.row(*extra_buttons)
    return markup


def create_main_reply_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(types.KeyboardButton(MUSIC_BUTTON), types.KeyboardButton(HELP_BUTTON))
    return markup


def create_transcription_confirmation_markup(url_id):
    """Кнопки для подтверждения платной расшифровки аудио."""
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton(
            "🎙 Расшифровать и суммаризовать",
            callback_data=f"t:{url_id}",
        )
    )
    markup.row(types.InlineKeyboardButton("✖️ Отмена", callback_data=f"x:{url_id}"))
    return markup


def create_uploaded_video_markup(video_id):
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("⭕ Кружок", callback_data=f"vn:{video_id}"))
    markup.row(
        types.InlineKeyboardButton("🎙 Расшифровка", callback_data=f"vt:{video_id}"),
        types.InlineKeyboardButton("🧠 Саммари", callback_data=f"vs:{video_id}"),
    )
    return markup


def create_uploaded_audio_markup(audio_id):
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("🎙 Аудиосообщение", callback_data=f"an:{audio_id}"))
    markup.row(
        types.InlineKeyboardButton("📝 Расшифровка", callback_data=f"at:{audio_id}"),
        types.InlineKeyboardButton("🧠 Саммари", callback_data=f"as:{audio_id}"),
    )
    return markup


def create_uploaded_voice_markup(voice_id):
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("📝 Расшифровка", callback_data=f"at:{voice_id}"),
        types.InlineKeyboardButton("🧠 Саммари", callback_data=f"as:{voice_id}"),
    )
    return markup


def create_music_results_markup(search_id, results, page, total_pages):
    markup = types.InlineKeyboardMarkup()

    start_index = page * 5
    for offset, result in enumerate(results):
        markup.row(
            types.InlineKeyboardButton(
                result["button_label"],
                callback_data=f"ms:{search_id}:{start_index + offset}",
            )
        )

    pagination_buttons = []
    if page > 0:
        pagination_buttons.append(
            types.InlineKeyboardButton("⬅️ Назад", callback_data=f"mp:{search_id}:{page - 1}")
        )
    if page + 1 < total_pages:
        pagination_buttons.append(
            types.InlineKeyboardButton("Дальше ➡️", callback_data=f"mp:{search_id}:{page + 1}")
        )
    if pagination_buttons:
        markup.row(*pagination_buttons)

    return markup

def _validate_callback_data(callback_data):
    if len(callback_data.encode("utf-8")) > 64:
        raise ValueError("callback_data exceeds Telegram limit")


def create_format_selection_markup(formats, best_callback_data=None):
    """Создает инлайн-клавиатуру для выбора формата видео с YouTube"""
    markup = types.InlineKeyboardMarkup(row_width=2)  # Делаем кнопки в два ряда для компактности

    # Создаем кнопки для форматов, добавляя по 2 в ряд для форматов с близкими разрешениями
    buttons = []
    
    # Группируем близкие по качеству форматы вместе
    hd_formats = []  # HD и выше (720p+)
    sd_formats = []  # SD (360p, 480p)
    low_formats = [] # Низкое качество (240p и ниже)
    
    for format_info in formats:
        height = format_info.get('height', 0)
        format_name = format_info['format_name']
        size_bytes = format_info.get("filesize") or format_info.get("filesize_approx")
        size_label = _human_size(size_bytes)
        button_text = format_name if not size_label else f"{format_name} ~{size_label}"

        callback_data = format_info['callback_data']
        _validate_callback_data(callback_data)
        button = types.InlineKeyboardButton(button_text, callback_data=callback_data)

        # Распределяем по группам качества
        if height >= 720:
            hd_formats.append(button)
        elif height >= 360:
            sd_formats.append(button)
        else:
            low_formats.append(button)
    
    # Добавляем кнопки по группам (сначала HD, затем SD, затем низкое качество)
    for button in hd_formats:
        buttons.append(button)
    
    for button in sd_formats:
        buttons.append(button)
    
    for button in low_formats:
        buttons.append(button)
    
    # Добавляем кнопки в разметку по 2 в ряд (если возможно)
    for i in range(0, len(buttons), 2):
        if i + 1 < len(buttons):
            markup.row(buttons[i], buttons[i+1])
        else:
            markup.row(buttons[i])

    # Добавляем кнопку "Наилучшее качество" отдельно в конце
    if best_callback_data:
        _validate_callback_data(best_callback_data)
        markup.row(types.InlineKeyboardButton("🔄 Наилучшее качество", callback_data=best_callback_data))

    return markup
