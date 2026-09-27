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


# ---------------------------------------------------------------------------
# Регрессия прогона 27.09.2026: квота qwen3.8-max исчерпана, пользователь
# выбрал ДРУГУЮ МОДЕЛЬ того же бэкенда qwen2api → «Бэкенд не изменён» →
# stop_event.set() → «Обработка прервана пользователем», весь прогон убит.
# ---------------------------------------------------------------------------


def _install_quota(monkeypatch, first_models=('qwen3.8-max',)):
    """Первый запрос — 429 по квоте, последующие отвечают валидным JSON."""
    from npazs.revision import ai_utils

    calls = []

    class _Resp200:
        status_code = 200
        text = ''

        def json(self):
            return {'choices': [{'message': {'content': '{"ok": true}'}}]}

    def fake_post(url, data=None, headers=None, timeout=None):
        import json as _json
        calls.append((url, _json.loads(data.decode('utf-8'))['model']))
        if len(calls) == 1:
            class _Resp429:
                status_code = 429
                text = QUOTA429
            return _Resp429()
        return _Resp200()

    monkeypatch.setattr(ai_utils.requests, 'post', fake_post)
    return calls


def test_quota_switch_to_another_model_keeps_run_alive(monkeypatch):
    """Квота исчерпана → меняем ТОЛЬКО модель (бэкенд тот же) → запрос идёт.

    Раньше смена засчитывалась только при смене бэкенда, поэтому выбор другой
    модели qwen2api отбрасывался и прогон останавливался целиком.
    """
    import threading

    import npazs.constants as constants
    from npazs.revision import ai_utils

    calls = _install_quota(monkeypatch)
    monkeypatch.setattr(
        constants, '_user_retry_callback',
        lambda msg, action='retry': 'switch',
    )
    monkeypatch.setattr(
        constants, '_settings_provider',
        lambda: {
            'backend': 'qwen2api',
            'model': 'qwen3.7-max',          # та же провайдерская семья
            'base_url': 'http://127.0.0.1:3000',
            'api_key': 'k',
            'agent_session': None,
        },
    )
    stop = threading.Event()
    logs = []

    answer = ai_utils.ask_kilo_gateway(
        '{"a": 1}', 'qwen3.8-max', lambda *a: logs.append(str(a)),
        backend='qwen2api', base_url='http://127.0.0.1:3000', api_key='k',
        max_retries=3, retry_delay=0, stop_event=stop,
    )

    assert answer == '{"ok": true}'
    assert not stop.is_set(), 'смена модели не должна останавливать прогон'
    assert [model for _url, model in calls] == ['qwen3.8-max', 'qwen3.7-max']
    joined = '\n'.join(logs)
    assert 'изменено: модель' in joined


def test_quota_switch_dialog_is_requeried_when_nothing_changed(monkeypatch):
    """Пустой «переключатель» переспрашивается и НЕ убивает прогон."""
    import threading

    import npazs.constants as constants
    from npazs.revision import ai_utils

    calls = _install_quota(monkeypatch)
    shown = []
    monkeypatch.setattr(
        constants, '_user_retry_callback',
        lambda msg, action='retry': shown.append(msg) or 'switch',
    )
    monkeypatch.setattr(
        constants, '_settings_provider',
        lambda: {   # пользователь ничего не поменял
            'backend': 'qwen2api',
            'model': 'qwen3.8-max',
            'base_url': 'http://127.0.0.1:3000',
            'api_key': 'k',
            'agent_session': None,
        },
    )
    stop = threading.Event()
    logs = []

    answer = ai_utils.ask_kilo_gateway(
        '{"a": 1}', 'qwen3.8-max', lambda *a: logs.append(str(a)),
        backend='qwen2api', base_url='http://127.0.0.1:3000', api_key='k',
        max_retries=3, retry_delay=0, stop_event=stop,
    )

    assert answer is None
    assert not stop.is_set(), 'пустая смена не должна останавливать прогон'
    assert len(calls) == 1, 'квота = ни одного повтора'
    assert len(shown) == ai_utils.SWITCH_ASK_LIMIT
    assert 'ДРУГУЮ модель' in '\n'.join(logs)
    assert 'прогон продолжается' in '\n'.join(logs)


def test_quota_headless_does_not_stop_pipeline(monkeypatch):
    """Без GUI-диалога (headless) квота не ставит stop_event."""
    import threading

    import npazs.constants as constants
    from npazs.revision import ai_utils

    calls = _install_quota(monkeypatch)
    monkeypatch.setattr(constants, '_user_retry_callback', None)
    stop = threading.Event()
    logs = []

    answer = ai_utils.ask_kilo_gateway(
        '{"a": 1}', 'qwen3.8-max', lambda *a: logs.append(str(a)),
        backend='qwen2api', base_url='http://127.0.0.1:3000', api_key='k',
        max_retries=3, retry_delay=0, stop_event=stop,
    )

    assert answer is None
    assert not stop.is_set(), 'headless-прогон нельзя останавливать из-за квоты'
    assert len(calls) == 1
    assert 'Прогон продолжается' in '\n'.join(logs)


def test_quota_explicit_stop_is_respected(monkeypatch):
    """Только явное «Остановить» останавливает прогон."""
    import threading

    import npazs.constants as constants
    from npazs.revision import ai_utils

    _install_quota(monkeypatch)
    monkeypatch.setattr(
        constants, '_user_retry_callback',
        lambda msg, action='retry': 'stop',
    )
    stop = threading.Event()

    answer = ai_utils.ask_kilo_gateway(
        '{"a": 1}', 'qwen3.8-max', lambda *a: None,
        backend='qwen2api', base_url='http://127.0.0.1:3000', api_key='k',
        max_retries=3, retry_delay=0, stop_event=stop,
    )

    assert answer is None
    assert stop.is_set(), 'явная остановка пользователем обязана работать'
