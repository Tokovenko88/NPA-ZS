"""Тесты исчерпания дневной квоты модели на chat.qwen.ai (``qwen2api``).

Стек (по образцу ``tests/test_waf_challenge.py``):

- ``npazs.revision.ai_utils.is_quota_exhausted_error`` — детектор квоты по
  коду ``RateLimited`` / ``quota_limit`` / ``insufficient_quota`` и тексту
  «upper limit for today's usage» / «已达上限» (см.
  ``tools/Qwen2API/src/utils/upstream-error.js``).
- ``npazs.revision.ai_utils.ask_kilo_gateway`` — при квоте НИКАКИХ повторов:
  ни одного ``sleep``, сразу диалог-предложение переключиться на другой
  бэкенд и возврат ``None`` (работа останавливается, а не «долбится»).
"""

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "npazs_bootstrap", _ROOT / "src" / "bootstrap.py"
)
assert _spec is not None and _spec.loader is not None
_bootstrap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bootstrap)
_bootstrap.bootstrap()

from npazs.revision.ai_utils import (
    QuotaExhaustedError,
    is_quota_exhausted_error,
    quota_exhausted_hint,
)

QUOTA429 = (
    'HTTP 429: {"error":{"message":"You\'ve reached the upper limit for '
    "today's usage. Please wait about 7 hours and try again.\","
    '"type":"insufficient_quota","code":"quota_limit"}}'
)
QUOTA_CN = '已达上限，今日次数已用完'
QUOTA_RATELIMITED = 'HTTP 429: {"error":{"code":"RateLimited"}}'
WAF502 = (
    'HTTP 502: {"error":{"message":"Qwen \\u7f51\\u9875\\u4e0a\\u6e38\\u89e6\\u53d1 '
    'WAF/captcha","type":"upstream_error","code":"upstream_waf_challenge"}}'
)


def test_detects_english_quota_message():
    """EN-текст прокси («upper limit for today») — это квота."""
    assert is_quota_exhausted_error('qwen2api', QUOTA429)


def test_detects_chinese_quota_message_and_ratelimited_code():
    """CN-текст («已达上限») и код RateLimited — тоже квота."""
    assert is_quota_exhausted_error('qwen2api', QUOTA_CN)
    assert is_quota_exhausted_error('QWEN2API', QUOTA_RATELIMITED)
    assert is_quota_exhausted_error('qwen2api', 'HTTP 429: insufficient_quota')


def test_waf_is_not_quota():
    """Капча WAF — отдельная категория, квотой не считается."""
    assert not is_quota_exhausted_error('qwen2api', WAF502)


def test_no_detection_for_other_backends_or_unrelated_errors():
    """Чужой бэкенд и не-квота (401/обрыв/500-TLS) — не квота."""
    assert not is_quota_exhausted_error('openrouter', QUOTA429)
    assert not is_quota_exhausted_error('qwen2api', 'HTTP 401: {"error":"Unauthorized"}')
    assert not is_quota_exhausted_error('qwen2api', 'WinError 10061 connection refused')
    assert not is_quota_exhausted_error('qwen2api', 'HTTP 500: boom')


def test_hint_mentions_switching_backend():
    """Подсказка говорит про переключение бэкенда, а не про повтор."""
    hint = quota_exhausted_hint('qwen2api', QUOTA429, model='qwen3-coder-plus')
    assert 'дневной лимит' in hint.lower()
    assert 'qwen3-coder-plus' in hint
    assert 'Переключитесь' in hint or 'переключите' in hint.lower()
    assert quota_exhausted_hint('openrouter', QUOTA429) == ''
    assert quota_exhausted_hint('qwen2api', 'HTTP 500: boom') == ''


def test_ask_gateway_fails_fast_on_quota(monkeypatch):
    """429/квота → 1 запрос, 0 sleep'ов, диалог «переключитесь», возврат None."""
    import npazs.constants as constants
    from npazs.revision import ai_utils

    class _Resp429:
        status_code = 429
        text = QUOTA429

    calls = []
    monkeypatch.setattr(
        ai_utils.requests, 'post', lambda *a, **k: (calls.append(1), _Resp429())[1]
    )
    sleeps = []
    monkeypatch.setattr(ai_utils.time, 'sleep', lambda s: sleeps.append(s))
    shown = []
    monkeypatch.setattr(
        constants, '_user_retry_callback',
        lambda msg, action='retry': shown.append((msg, action)) or 'stop',
    )
    logs = []
    answer = ai_utils.ask_kilo_gateway(
        '{"ping": 1}', 'qwen3-coder-plus', lambda *a: logs.append(a),
        backend='qwen2api', base_url='http://127.0.0.1:3000', api_key='k',
        max_retries=5, retry_delay=15,
    )
    assert answer is None
    assert len(calls) == 1  # без повторов
    assert sleeps == []  # без пауз backoff
    assert len(shown) == 1  # один диалог пользователю
    assert shown[0][1] == 'switch'
    assert 'исчерпан' in shown[0][0]
    assert any('лимит исчерпан' in str(entry).lower() for entry in logs)
    assert any('Переключитесь' in str(entry) or 'переключите' in str(entry).lower()
               for entry in logs)


def test_quota_error_type_carries_backend_and_model():
    """QuotaExhaustedError несёт backend/model для диалога пользователю."""
    err = QuotaExhaustedError('HTTP 429: x', backend='qwen2api', model='m')
    assert err.backend == 'qwen2api'
    assert err.model == 'm'
