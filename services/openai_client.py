"""Низкоуровневые helper'ы для запросов к OpenAI API."""

__all__ = [
    "DEFAULT_OPENAI_TIMEOUT",
    "OpenAITemporaryError",
    "post_openai_json",
    "post_openai_multipart",
]

import time

import requests

from config import get_outbound_requests_proxies
from utils.logging_utils import log_event

DEFAULT_OPENAI_TIMEOUT = (30, 600)
OPENAI_API_BASE = "https://api.openai.com/v1"
OPENAI_MAX_ATTEMPTS = 3
OPENAI_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
OPENAI_RETRY_BASE_DELAY = 1


class OpenAITemporaryError(RuntimeError):
    """Временная ошибка связи с OpenAI или временный ответ OpenAI."""

    def __init__(self, context, detail=None):
        self.context = context
        self.detail = str(detail or "").strip()
        message = self.detail or f"Temporary OpenAI failure for {context}"
        super().__init__(message)


def _build_headers(api_key, extra_headers=None):
    if not api_key:
        raise RuntimeError("Не задан OPENAI_API_KEY")

    headers = {
        "Authorization": f"Bearer {api_key}",
    }
    if extra_headers:
        headers.update(extra_headers)
    return headers


def _response_error_message(response, context):
    response_body = (response.text or "").strip()
    body_preview = response_body[:1000] if response_body else "empty"
    return f"{response.status_code} Client Error for {context}: {body_preview}"


def _raise_for_status_with_body(response, context):
    if response.ok:
        return

    raise requests.HTTPError(
        _response_error_message(response, context),
        response=response,
    )


def _sleep_before_retry(attempt):
    time.sleep(OPENAI_RETRY_BASE_DELAY * attempt)


def _request_with_retry(request_func, context):
    for attempt in range(1, OPENAI_MAX_ATTEMPTS + 1):
        try:
            response = request_func()
        except (requests.Timeout, requests.ConnectionError) as error:
            if attempt < OPENAI_MAX_ATTEMPTS:
                log_event(
                    "openai_request_retry",
                    level="WARNING",
                    context=context,
                    attempt=attempt,
                    reason=error.__class__.__name__,
                )
                _sleep_before_retry(attempt)
                continue
            raise OpenAITemporaryError(context, error) from error

        if response.ok:
            return response

        if response.status_code in OPENAI_RETRYABLE_STATUS_CODES:
            detail = _response_error_message(response, context)
            if attempt < OPENAI_MAX_ATTEMPTS:
                log_event(
                    "openai_request_retry",
                    level="WARNING",
                    context=context,
                    attempt=attempt,
                    status_code=response.status_code,
                )
                _sleep_before_retry(attempt)
                continue
            raise OpenAITemporaryError(context, detail)

        _raise_for_status_with_body(response, context)

    raise OpenAITemporaryError(context, "retry loop exhausted")


def post_openai_json(endpoint, payload, *, api_key, timeout=DEFAULT_OPENAI_TIMEOUT):
    headers = _build_headers(
        api_key,
        extra_headers={"Content-Type": "application/json"},
    )
    context = endpoint.lstrip("/")

    return _request_with_retry(
        lambda: requests.post(
            f"{OPENAI_API_BASE}/{context}",
            headers=headers,
            json=payload,
            timeout=timeout,
            proxies=get_outbound_requests_proxies() or None,
        ),
        context=context,
    )


def post_openai_multipart(endpoint, *, api_key, data, files, timeout=DEFAULT_OPENAI_TIMEOUT):
    headers = _build_headers(api_key)
    context = endpoint.lstrip("/")

    return _request_with_retry(
        lambda: requests.post(
            f"{OPENAI_API_BASE}/{context}",
            headers=headers,
            data=data,
            files=files,
            timeout=timeout,
            proxies=get_outbound_requests_proxies() or None,
        ),
        context=context,
    )
