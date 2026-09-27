"""Тесты WAF-челленджа chat.qwen.ai (``HTTP 502 upstream_waf_challenge``).

``npazs.revision.ai_utils.waf_challenge_hint`` / ``retry_wait_seconds``: при
капче Aliyun WAF NPA-ZS ждёт перед повтором дольше 5-минутного охлаждения
аккаунта в прокси Qwen2API и объясняет причину в логе (docs/qwen2api.md).
"""

import importlib.util
import json
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


def test_retry_wait_stretches_past_proxy_cooldown():
    """WAF-челлендж → пауза ≥ 330 с; обычный бэк-офф не трогаем."""
    # Первый бэк-офф 15 с поднимается до WAF-паузы (охлаждение прокси 300 с).
    assert retry_wait_seconds(1, 15, 2, 'qwen2api', WAF502) == WAF_CHALLENGE_WAIT_SECONDS
    # Не-WAF ошибки и чужие бэкенды идут по исторической формуле.
    assert retry_wait_seconds(1, 15, 2, 'qwen2api', 'HTTP 500: boom') == 15
    assert retry_wait_seconds(3, 15, 2, 'qwen2api', 'HTTP 500: boom') == 60
    assert retry_wait_seconds(1, 15, 2, 'openrouter', WAF502) == 15


def test_ask_gateway_waits_full_waf_cooldown(monkeypatch):
    """Первая попытка 502/WAF → суммарный sleep ровно WAF_CHALLENGE_WAIT_SECONDS."""
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
    sleeps = []
    monkeypatch.setattr(ai_utils.time, 'sleep', lambda s: sleeps.append(s))
    logs = []
    answer = ai_utils.ask_kilo_gateway(
        '{"ping": 1}', 'qwen3.8-max', lambda *a: logs.append(a),
        backend='qwen2api', base_url='http://127.0.0.1:3000', api_key='k',
        max_retries=2, retry_delay=15,
    )
    assert answer == '{"ok": true}'
    assert sum(sleeps) == WAF_CHALLENGE_WAIT_SECONDS
    assert any('WAF' in str(entry) for entry in logs)


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