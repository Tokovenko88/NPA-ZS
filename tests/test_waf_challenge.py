"""Тесты WAF-челленджа chat.qwen.ai (``HTTP 502 upstream_waf_challenge``).

``npazs.revision.ai_utils``: при капче Aliyun WAF NPA-ZS больше НЕ ждёт
слепые 330 с — он запрашивает у прокси Qwen2API статус аккаунтов
(``GET /api/accountStats``), логирует, на каком именно аккаунте проблема,
и повторяет запрос сразу через следующий свободный аккаунт. Пауза до
выхода ближайшего из cooldown — только когда свободных аккаунтов нет;
если статус получить не удалось — обычный бэк-офф (docs/qwen2api.md).
"""

import importlib.util
import json
import time
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
    WAF_BODY_LIMIT_BYTES,
    WAF_CHALLENGE_WAIT_SECONDS,
    is_waf_challenge_error,
    retry_wait_seconds,
    waf_body_size_hint,
    waf_challenge_hint,
)

WAF502 = (
    'HTTP 502: {"error":{"message":"Qwen \u7f51\u9875\u4e0a\u6e38\u89e6\u53d1 WAF/captcha\uff1b'
    'Agent \u4e0a\u4e0b\u6587\u53ef\u80fd\u8fc7\u5927\u6216\u8d26\u53f7\u9700\u8981\u9a8c\u8bc1",'
    '"type":"upstream_error","code":"upstream_waf_challenge"}}'
)


def _stats_response(records):
    """Заглушка ``GET /api/accountStats``: [(email, kind, cooldownEndsAt, code)]."""
    class _Resp:
        status_code = 200
        text = ''

        def json(self):
            return {
                'accounts': [
                    {'email': email,
                     'status': {'kind': kind, 'cooldownEndsAt': ends,
                                'lastErrorCode': code}}
                    for email, kind, ends, code in records
                ]
            }
    return _Resp()


def test_hint_for_qwen2api_waf_challenge():
    """502/WAF от qwen2api → подсказка про паузу и капчу в браузере."""
    hint = waf_challenge_hint('qwen2api', WAF502)
    assert 'chat.qwen.ai' in hint
    assert 'капч' in hint.lower()


def test_detects_raw_waf_markers_without_code_field():
    """Маркеры ловятся и по одиночеству (тело апстрима без поля code)."""
    assert is_waf_challenge_error('qwen2api', 'FAIL_SYS_USER_VALIDATE')
    assert is_waf_challenge_error('QWEN2API', 'RGV587_ERROR::SM')
    assert is_waf_challenge_error('qwen2api', 'HTTP 502: WAF/captcha triggered')


def test_no_hint_for_other_backends_or_unrelated_errors():
    """Чужой бэкенд и не-WAF ошибки (401/10061) подсказку не получают."""
    assert waf_challenge_hint('openrouter', WAF502) == ''
    assert waf_challenge_hint('qwen2api', 'HTTP 401: {"error":"Unauthorized"}') == ''
    assert waf_challenge_hint('qwen2api', 'WinError 10061 connection refused') == ''
    # TLS-подсказка (HTTP 500 会话) не пересекается с WAF.
    assert waf_challenge_hint('qwen2api', 'HTTP 500: {"error":"无法创建或续接 Qwen 会话"}') == ''


def test_retry_wait_zero_when_free_account_exists(monkeypatch):
    """Есть свободный аккаунт → 0 с: ротация прокси уводит запрос на следующий."""
    from npazs.revision import ai_utils

    now = time.time() * 1000
    monkeypatch.setattr(ai_utils.requests, 'get', lambda *a, **k: _stats_response([
        ('bad@example.com', 'cooldown', now + 300_000, 'upstream_waf_challenge'),
        ('good@example.com', 'active', None, None),
    ]))
    logs = []
    wait = ai_utils.retry_wait_seconds(
        1, 15, 2, 'qwen2api', WAF502,
        base_url='http://127.0.0.1:3000/v1', api_key='k',
        log_callback=lambda *entry: logs.append(entry))
    assert wait == 0  # никаких 330 с: свободный аккаунт есть
    text = '\n'.join(str(entry) for entry in logs)
    assert 'bad@example.com' in text  # какой именно аккаунт в проблеме
    assert 'upstream_waf_challenge' in text
    assert 'свободных аккаунтов 1 из 2' in text


def test_retry_wait_until_earliest_cooldown_when_all_cooling(monkeypatch):
    """Все аккаунты в cooldown → до выхода ближайшего, но не дольше лимита."""
    from npazs.revision import ai_utils

    now = time.time() * 1000
    monkeypatch.setattr(ai_utils.requests, 'get', lambda *a, **k: _stats_response([
        ('a@example.com', 'cooldown', now + 60_000, 'upstream_waf_challenge'),
        ('b@example.com', 'cooldown', now + 120_000, 'upstream_waf_challenge'),
    ]))
    wait = ai_utils.retry_wait_seconds(
        1, 15, 2, 'qwen2api', WAF502,
        base_url='http://127.0.0.1:3000', api_key='k')
    assert 60 <= wait <= 70  # 60 с до выхода ближайшего + буфер
    assert wait <= WAF_CHALLENGE_WAIT_SECONDS


def test_retry_wait_regular_backoff_when_status_unavailable(monkeypatch):
    """Прокси недоступен или ключ не admin → обычный бэк-офф, а не 330 с."""
    from npazs.revision import ai_utils

    def _refused(*args, **kwargs):
        raise OSError('connection refused')

    monkeypatch.setattr(ai_utils.requests, 'get', _refused)
    assert ai_utils.retry_wait_seconds(
        1, 15, 2, 'qwen2api', WAF502,
        base_url='http://127.0.0.1:3000', api_key='k') == 15

    class _Resp403:
        status_code = 403
        text = 'Admin access required'

        def json(self):
            return {}

    monkeypatch.setattr(ai_utils.requests, 'get', lambda *a, **k: _Resp403())
    # На 3-й попытке бэк-офф по исторической формуле: 15 * 2**2 = 60.
    assert ai_utils.retry_wait_seconds(
        3, 15, 2, 'qwen2api', WAF502,
        base_url='http://127.0.0.1:3000', api_key='k') == 60


def test_retry_wait_regular_backoff_unchanged():
    """Не-WAF ошибки и чужие бэкенды идут по исторической формуле."""
    assert retry_wait_seconds(1, 15, 2, 'qwen2api', 'HTTP 500: boom') == 15
    assert retry_wait_seconds(3, 15, 2, 'qwen2api', 'HTTP 500: boom') == 60
    assert retry_wait_seconds(1, 15, 2, 'openrouter', WAF502) == 15


def test_ask_gateway_rotates_account_after_waf(monkeypatch):
    """502/WAF → статус прокси: свободный аккаунт есть → повтор без паузы."""
    from npazs.revision import ai_utils

    class _Resp502:
        status_code = 502
        text = WAF502

    class _Resp200:
        status_code = 200
        text = ''

        def json(self):
            return {'choices': [{'message': {'content': '{"ok": true}'}}]}

    responses = [_Resp502(), _Resp200()]
    monkeypatch.setattr(ai_utils.requests, 'post', lambda *a, **k: responses.pop(0))
    now = time.time() * 1000
    monkeypatch.setattr(ai_utils.requests, 'get', lambda *a, **k: _stats_response([
        ('bad@example.com', 'cooldown', now + 300_000, 'upstream_waf_challenge'),
        ('good@example.com', 'active', None, None),
    ]))
    sleeps = []
    monkeypatch.setattr(ai_utils.time, 'sleep', lambda s: sleeps.append(s))
    logs = []
    answer = ai_utils.ask_kilo_gateway(
        '{"ping": 1}', 'qwen3.8-max', lambda *a: logs.append(a),
        backend='qwen2api', base_url='http://127.0.0.1:3000', api_key='k',
        max_retries=2, retry_delay=15,
    )
    assert answer == '{"ok": true}'
    assert sleeps == []  # ни одного ожидания: ротация на свободный аккаунт
    text = '\n'.join(str(entry) for entry in logs)
    assert 'WAF' in text
    assert 'bad@example.com' in text
    assert 'Повтор без паузы' in text


def test_ask_gateway_retries_invalid_json_answer(monkeypatch):
    """Мусор вместо JSON («User Safety: safe») → повтор, а не пропуск/FAILED.

    Кейс из прогона 27.09.2026: ``openrouter/free`` вернул «User Safety: safe»,
    ``_repair_json_answer`` вернул ``None``. Такое нельзя «пропускать
    программно» — запрос повторяется в общем цикле ретраев, и при успехе
    второй попытки возвращается её валидный JSON.
    """
    from npazs.revision import ai_utils

    class _Resp200:
        def __init__(self, content):
            self.status_code = 200
            self.text = ''
            self._content = content

        def json(self):
            return {'choices': [{'message': {'content': self._content}}]}

    responses = [_Resp200('User Safety: safe'), _Resp200('{"ok": true}')]
    monkeypatch.setattr(ai_utils.requests, 'post', lambda *a, **k: responses.pop(0))
    monkeypatch.setattr(ai_utils.time, 'sleep', lambda s: None)
    logs = []
    answer = ai_utils.ask_kilo_gateway(
        '{"ping": 1}', 'openrouter/free', lambda *a: logs.append(a),
        backend='openrouter', base_url='https://openrouter.ai/api/v1', api_key='k',
        max_retries=2, retry_delay=0,
    )
    assert answer == '{"ok": true}'
    text = '\n'.join(str(entry) for entry in logs)
    assert 'Невалидный JSON-ответ ИИ' in text
    assert 'User Safety' in text  # превью мусорного ответа — в причине повтора


def test_ask_gateway_invalid_json_exhausts_retries(monkeypatch):
    """Мусор на всех попытках → исчерпание ретраев (None), а не тихий пропуск."""
    from npazs.revision import ai_utils

    class _Resp200:
        status_code = 200
        text = ''

        def json(self):
            return {'choices': [{'message': {'content': 'User Safety: safe'}}]}

    monkeypatch.setattr(ai_utils.requests, 'post', lambda *a, **k: _Resp200())
    monkeypatch.setattr(ai_utils.time, 'sleep', lambda s: None)
    logs = []
    answer = ai_utils.ask_kilo_gateway(
        '{"ping": 1}', 'openrouter/free', lambda *a: logs.append(a),
        backend='openrouter', base_url='https://openrouter.ai/api/v1', api_key='k',
        max_retries=2, retry_delay=0,
    )
    assert answer is None
    text = '\n'.join(str(entry) for entry in logs)
    assert 'Все попытки (2) исчерпаны' in text
    assert 'невалидный JSON-ответ ИИ' in text


def test_gateway_sends_utf8_body_without_ascii_escapes(monkeypatch):
    """Тело уходит UTF-8-байтами: кириллица не раздувается в \\uXXXX.

    ``requests.post(json=payload)`` экранирует не-ASCII, из-за чего промпт
    stage 3 (87.7 KB) уходил телом 124.3 KiB — у порога капчи WAF (~128 KiB).
    """
    from npazs.revision import ai_utils

    captured = {}

    class _Resp200:
        status_code = 200
        text = ''

        def json(self):
            return {'choices': [{'message': {'content': '{"ok": true}'}}]}

    def _post(url, **kwargs):
        captured.update(kwargs)
        return _Resp200()

    monkeypatch.setattr(ai_utils.requests, 'post', _post)
    prompt = 'в пункте 2 слово «ребенка» заменить словом «детей»; ' * 100
    ai_utils.ask_kilo_gateway(
        prompt, 'qwen3.8-max', lambda *a: None, backend='qwen2api',
        base_url='http://127.0.0.1:3000', api_key='k', max_retries=1,
    )
    body = captured['data']
    assert isinstance(body, bytes)
    text = body.decode('utf-8')
    assert '\\u' not in text
    assert json.loads(text)['messages'][0]['content'] == prompt
    # Дешевле, чем ``json=payload`` (там каждые 2 байта кириллицы → 6).
    escaped = json.dumps({'content': prompt}).encode('utf-8')
    assert len(body) < len(escaped)


def test_body_size_hint_near_waf_limit():
    """Подсказка о размере тела — только для qwen2api и только у порога."""
    assert waf_body_size_hint(40 * 1024) == ''
    hint = waf_body_size_hint(124 * 1024)
    assert 'WAF' in hint
    assert f'{WAF_BODY_LIMIT_BYTES // 1024}' in hint
    assert waf_body_size_hint(124 * 1024, 'openrouter') == ''