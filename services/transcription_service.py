__all__ = [
    "OPENAI_TRANSCRIPTION_FILE_LIMIT",
    "DEFAULT_TEXT_CHUNK_SIZE",
    "send_text_chunks",
    "split_text_chunks",
    "transcribe_audio_with_openai",
]

import os

from config import OPENAI_API_KEY, OPENAI_TRANSCRIPTION_MODEL
from services.openai_client import post_openai_multipart

OPENAI_TRANSCRIPTION_FILE_LIMIT = 25 * 1024 * 1024
DEFAULT_TEXT_CHUNK_SIZE = 4096


def _validate_chunk_size(chunk_size):
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")


def _split_long_text_piece(text, chunk_size):
    _validate_chunk_size(chunk_size)
    normalized = (text or "").strip()
    if not normalized:
        return []

    if len(normalized) <= chunk_size:
        return [normalized]

    words = normalized.split()
    if len(words) <= 1:
        return [
            normalized[index : index + chunk_size]
            for index in range(0, len(normalized), chunk_size)
            if normalized[index : index + chunk_size]
        ]

    pieces = []
    current = []
    current_len = 0

    for word in words:
        word_len = len(word)
        if word_len > chunk_size:
            if current:
                pieces.append(" ".join(current))
                current = []
                current_len = 0

            pieces.extend(
                word[index : index + chunk_size]
                for index in range(0, word_len, chunk_size)
                if word[index : index + chunk_size]
            )
            continue

        additional = word_len + (1 if current_len else 0)
        if current and current_len + additional > chunk_size:
            pieces.append(" ".join(current))
            current = [word]
            current_len = word_len
            continue

        current.append(word)
        current_len += additional

    if current:
        pieces.append(" ".join(current))

    return pieces


def split_text_chunks(text, chunk_size=DEFAULT_TEXT_CHUNK_SIZE):
    _validate_chunk_size(chunk_size)
    normalized = (text or "").strip()
    if not normalized:
        return []

    chunks = []
    current = []
    current_len = 0
    for paragraph in normalized.split("\n"):
        paragraph_text = paragraph.strip()
        if not paragraph_text:
            continue

        for piece in _split_long_text_piece(paragraph_text, chunk_size):
            piece_len = len(piece)
            if current and current_len + piece_len + 1 > chunk_size:
                chunks.append("\n".join(current))
                current = [piece]
                current_len = piece_len
                continue

            current.append(piece)
            current_len += piece_len + (1 if current_len else 0)

    if current:
        chunks.append("\n".join(current))

    return chunks


def send_text_chunks(bot, chat_id, text, chunk_size=DEFAULT_TEXT_CHUNK_SIZE, **send_kwargs):
    _validate_chunk_size(chunk_size)
    messages = []
    for chunk in split_text_chunks(text, chunk_size=chunk_size):
        messages.append(bot.send_message(chat_id, chunk, **send_kwargs))
    return messages


def transcribe_audio_with_openai(audio_path):
    with open(audio_path, "rb") as audio_file:
        response = post_openai_multipart(
            "audio/transcriptions",
            api_key=OPENAI_API_KEY,
            data={"model": OPENAI_TRANSCRIPTION_MODEL},
            files={"file": (os.path.basename(audio_path), audio_file)},
        )

    payload = response.json()
    return (payload.get("text") or "").strip()
