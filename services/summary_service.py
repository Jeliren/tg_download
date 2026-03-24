__all__ = [
    "SUMMARY_CHUNK_SIZE",
    "count_summary_chunks",
    "summarize_transcript_text",
]

from config import OPENAI_API_KEY, OPENAI_SUMMARY_MODEL
from services.openai_client import post_openai_json
from services.transcription_service import split_text_chunks
from utils.logging_utils import log_event

SUMMARY_CHUNK_SIZE = 40000
SUMMARY_MAX_OUTPUT_TOKENS = 500
SUMMARY_REASONING_EFFORT = "low"
SUMMARY_VERBOSITY = "low"


def _extract_response_output_text(payload):
    output_text = payload.get("output_text")
    if output_text:
        return output_text.strip()

    texts = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                texts.append(content["text"])

    return "\n".join(texts).strip()


def _log_response_usage(payload, request_type):
    usage = payload.get("usage") or {}
    if not usage:
        return

    output_details = usage.get("output_tokens_details") or {}
    reasoning_tokens = output_details.get("reasoning_tokens")
    log_event(
        "summary_openai_usage",
        request_type=request_type,
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        total_tokens=usage.get("total_tokens"),
        reasoning_tokens=reasoning_tokens if reasoning_tokens is not None else "unknown",
    )


def _responses_create(input_text, *, request_type):
    response = post_openai_json(
        "responses",
        {
            "model": OPENAI_SUMMARY_MODEL,
            "max_output_tokens": SUMMARY_MAX_OUTPUT_TOKENS,
            "reasoning": {
                "effort": SUMMARY_REASONING_EFFORT,
            },
            "text": {
                "verbosity": SUMMARY_VERBOSITY,
            },
            "instructions": (
                "Ты делаешь компактное и качественное саммари видео на русском языке. "
                "Опирайся только на присланный текст, ничего не придумывай и не подтягивай извне. "
                "Сохраняй факты, причинно-следственные связи, цифры, имена и важные оговорки. "
                "Если исходный текст шумный, обрывочный или неполный, прямо скажи об этом. "
                "Пиши коротко, плотно, структурно и без воды."
            ),
            "input": input_text,
        },
        api_key=OPENAI_API_KEY,
    )
    payload = response.json()
    _log_response_usage(payload, request_type=request_type)
    return _extract_response_output_text(payload)


def _source_label(transcript_source):
    source_map = {
        "subtitles": "ручные субтитры YouTube",
        "automatic_captions": "автоматические субтитры YouTube",
        "openai_transcription": "автоматическая расшифровка аудио",
    }
    return source_map.get(transcript_source, "текстовая расшифровка")


def _build_summary_prompt(transcript_text, title=None, transcript_source=None, transcript_language=None):
    return (
        f"Название видео: {title or 'Без названия'}\n"
        f"Источник текста: {_source_label(transcript_source)}\n"
        f"Язык текста: {transcript_language or 'не указан'}\n\n"
        "Сделай итоговое саммари по тексту видео.\n"
        "Требования к ответу:\n"
        "1. Раздел `Коротко`: 2-3 предложения с сутью видео.\n"
        "2. Раздел `Ключевые мысли`: 4-6 коротких пунктов.\n"
        "3. Раздел `Практический вывод`: 1-2 пункта, только если они действительно следуют из текста.\n"
        "4. Если текст неполный, шумный или местами неразборчивый, добавь в конце одну короткую пометку.\n"
        "5. Ответ должен быть компактным.\n\n"
        f"Текст:\n{transcript_text}"
    )


def _build_chunk_summary_prompt(
    chunk_text,
    index,
    total_chunks,
    title=None,
    transcript_source=None,
    transcript_language=None,
):
    return (
        f"Название видео: {title or 'Без названия'}\n"
        f"Источник текста: {_source_label(transcript_source)}\n"
        f"Язык текста: {transcript_language or 'не указан'}\n"
        f"Это часть {index} из {total_chunks}.\n\n"
        "Сделай краткое саммари этой части на русском языке.\n"
        "Формат:\n"
        "1. 1 короткое предложение с сутью.\n"
        "2. 3-5 ключевых пунктов.\n"
        "3. Важные факты, цифры или оговорки только если они есть.\n"
        "4. Будь очень кратким.\n\n"
        f"Текст:\n{chunk_text}"
    )


def _build_merged_summary_prompt(partial_summaries, title=None, transcript_source=None, transcript_language=None):
    merged_input = "\n\n".join(f"Часть {index}:\n{summary}" for index, summary in enumerate(partial_summaries, start=1))
    return (
        f"Название видео: {title or 'Без названия'}\n"
        f"Источник текста: {_source_label(transcript_source)}\n"
        f"Язык текста: {transcript_language or 'не указан'}\n\n"
        "Ниже саммари частей одного видео. Собери цельное итоговое саммари на русском языке.\n"
        "Требования к ответу:\n"
        "1. Раздел `Коротко`: 2-3 предложения.\n"
        "2. Раздел `Ключевые мысли`: 4-6 пунктов.\n"
        "3. Раздел `Практический вывод`: 1-2 пункта, если они есть.\n"
        "4. Если по частям видно, что текст неполный или шумный, добавь короткую пометку.\n"
        "5. Ответ должен быть компактным.\n\n"
        f"{merged_input}"
    )


def summarize_transcript_text(transcript_text, title=None, transcript_source=None, transcript_language=None):
    chunks = split_text_chunks(transcript_text, chunk_size=SUMMARY_CHUNK_SIZE)
    if not chunks:
        raise RuntimeError("Пустая транскрипция для саммари")

    if len(chunks) == 1:
        return _responses_create(
            _build_summary_prompt(
                chunks[0],
                title=title,
                transcript_source=transcript_source,
                transcript_language=transcript_language,
            ),
            request_type="single",
        )

    partial_summaries = []
    for index, chunk in enumerate(chunks, start=1):
        partial_summary = _responses_create(
            _build_chunk_summary_prompt(
                chunk,
                index,
                len(chunks),
                title=title,
                transcript_source=transcript_source,
                transcript_language=transcript_language,
            ),
            request_type=f"chunk_{index}_of_{len(chunks)}",
        )
        if not partial_summary:
            raise RuntimeError(f"OpenAI вернул пустое частичное саммари для chunk {index}")
        partial_summaries.append(partial_summary)

    return _responses_create(
        _build_merged_summary_prompt(
            partial_summaries,
            title=title,
            transcript_source=transcript_source,
            transcript_language=transcript_language,
        ),
        request_type="merge",
    )


def count_summary_chunks(transcript_text):
    return len(split_text_chunks(transcript_text, chunk_size=SUMMARY_CHUNK_SIZE))
