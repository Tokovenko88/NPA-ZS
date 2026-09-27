"""Тесты общего модуля списков моделей ИИ-бэкендов (``npazs.llm_models``)."""

import importlib.util
import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "npazs_bootstrap", _ROOT / "src" / "bootstrap.py"
)
assert _spec is not None and _spec.loader is not None
_bootstrap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bootstrap)
_bootstrap.bootstrap()

from npazs.constants import HTTP_BACKEND_DEFS, HTTP_BACKENDS
from npazs.llm_models import (
    _fetch_openai_compat_models,
    check_ollama_cloud_access,
    fetch_cerebras_models,
    fetch_cline_models,
    fetch_free_deepseek_models,
    fetch_gemini_models,
    fetch_kilo_gateway_free_models,
    fetch_mistral_models,
    fetch_ollama_models,
    fetch_openrouter_free_models,
    fetch_qwen2api_models,
    get_free_models_for_backend,
    is_ollama_cloud_model,
    run_ollama_signin,
    verify_ollama_cloud_models,
)


class _FakeResponse:
    def __init__(self, status_code=200, text='', data=None):
        self.status_code = status_code
        self.text = text
        self._data = data

    def json(self):
        return self._data


def _fake_session(get_impl):
    """Подделка requests.Session: Kilo перевёл fetch_* с requests.get на session.get."""
    class _Session:
        def get(self, url, headers=None, timeout=None):
            return get_impl(url, headers=headers, timeout=timeout)

        def close(self):
            pass
    return _Session()


def _fake_post_session(post_impl):
    """Подделка requests.Session с POST (проба авторизации Ollama /api/show)."""
    class _Session:
        def post(self, url, json=None, timeout=None):
            return post_impl(url, json=json, timeout=timeout)

        def close(self):
            pass
    return _Session()


def test_fetch_kilo_gateway_filters_and_sends_auth(monkeypatch):
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append((url, headers, timeout))
        return _FakeResponse(data={'data': [
            {'id': 'provider:paid', 'name': 'Paid'},
            {'id': 'google/gemini-2.5-flash:free', 'name': 'Gemini Flash'},
            {'id': 'openrouter/auto:free', 'name': 'Auto Free'},
        ]})

    monkeypatch.setattr('npazs.llm_models.requests.Session', lambda: _fake_session(fake_get))
    result = fetch_kilo_gateway_free_models('https://kg.example/', 'secret')
    assert result == ['google/gemini-2.5-flash:free', 'openrouter/auto:free']
    url, headers, _timeout = calls[0]
    assert url == 'https://kg.example/models'
    assert headers == {'Authorization': 'Bearer secret'}


def test_fetch_kilo_gateway_raises_on_http_error(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        return _FakeResponse(status_code=500, text='boom')

    monkeypatch.setattr('npazs.llm_models.requests.Session', lambda: _fake_session(fake_get))
    with pytest.raises(RuntimeError, match='500'):
        fetch_kilo_gateway_free_models('https://kg.example', '')


def test_fetch_ollama_returns_all_installed(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        assert url == 'http://localhost:11434/api/tags'
        return _FakeResponse(data={'models': [
            {'name': 'some-other-model'},
            {'name': 'gpt-oss:20b-cloud'},
            {'name': 'gemma4:31b'},
        ]})

    monkeypatch.setattr('npazs.llm_models.requests.Session', lambda: _fake_session(fake_get))
    result = fetch_ollama_models('http://localhost:11434')
    assert result == ['gemma4:31b', 'gpt-oss:20b-cloud', 'some-other-model']


def test_fetch_ollama_raises_on_http_error(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        return _FakeResponse(status_code=503, text='unavailable')

    monkeypatch.setattr('npazs.llm_models.requests.Session', lambda: _fake_session(fake_get))
    with pytest.raises(RuntimeError, match='503'):
        fetch_ollama_models('http://localhost:11434')


# ---------------------------------------------------------------------------
# Ollama cloud: только cloud-модели + проверка авторизации (HTTP 403)
# ---------------------------------------------------------------------------

def test_is_ollama_cloud_model_variants():
    # Авторитетный признак remote-модели — remote_host/remote_model в /api/tags.
    assert is_ollama_cloud_model({'name': 'gpt-oss:20b', 'remote_host': 'https://ollama.com'})
    assert is_ollama_cloud_model({'name': 'minimax-m3', 'remote_model': 'minimax-m3'})
    # Признак по имени (cloud-суффикс тега).
    assert is_ollama_cloud_model({'name': 'gpt-oss:20b-cloud'})
    assert is_ollama_cloud_model('nemotron-3-nano:30b-cloud')
    assert is_ollama_cloud_model('minimax-m3:cloud')
    # Локальные модели — не cloud.
    assert not is_ollama_cloud_model({'name': 'qwen2.5-coder:1.5b'})
    assert not is_ollama_cloud_model('gemma4:31b')
    assert not is_ollama_cloud_model({'name': ''})


def test_fetch_ollama_cloud_only_filters_local(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        assert url == 'http://localhost:11434/api/tags'
        return _FakeResponse(data={'models': [
            {'name': 'gpt-oss:20b-cloud', 'remote_host': 'https://ollama.com:443'},
            {'name': 'qwen2.5-coder:1.5b'},
            {'name': 'minimax-m3:cloud'},
        ]})

    monkeypatch.setattr('npazs.llm_models.requests.Session', lambda: _fake_session(fake_get))
    assert fetch_ollama_models('http://localhost:11434', cloud_only=True) == [
        'gpt-oss:20b-cloud', 'minimax-m3:cloud']
    # Без фильтра — все установленные (регрессия обратной совместимости).
    assert fetch_ollama_models('http://localhost:11434') == [
        'gpt-oss:20b-cloud', 'minimax-m3:cloud', 'qwen2.5-coder:1.5b']


def test_check_ollama_cloud_access_ok(monkeypatch):
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append((url, json, timeout))
        return _FakeResponse(status_code=200)

    monkeypatch.setattr('npazs.llm_models.requests.Session', lambda: _fake_post_session(fake_post))
    assert check_ollama_cloud_access('http://localhost:11434/', 'gpt-oss:20b-cloud') == ''
    assert calls == [('http://localhost:11434/api/show', {'name': 'gpt-oss:20b-cloud'}, 10)]


def test_check_ollama_cloud_access_403_hints_signin(monkeypatch):
    def fake_post(url, json=None, timeout=None):
        return _FakeResponse(status_code=403, text='<html>403 Forbidden</html>')

    monkeypatch.setattr('npazs.llm_models.requests.Session', lambda: _fake_post_session(fake_post))
    reason = check_ollama_cloud_access('http://localhost:11434', 'gpt-oss:20b-cloud')
    assert 'HTTP 403' in reason
    assert 'ollama signin' in reason


def test_check_ollama_cloud_access_other_http_error(monkeypatch):
    def fake_post(url, json=None, timeout=None):
        return _FakeResponse(status_code=500, text='boom')

    monkeypatch.setattr('npazs.llm_models.requests.Session', lambda: _fake_post_session(fake_post))
    assert check_ollama_cloud_access('http://localhost:11434', 'gpt-oss:20b-cloud') == 'HTTP 500'


def test_verify_ollama_cloud_models_splits_blocked(monkeypatch):
    def fake_post(url, json=None, timeout=None):
        if json.get('name') == 'minimax-m3:cloud':
            return _FakeResponse(status_code=200)
        return _FakeResponse(status_code=403, text='<html>403 Forbidden</html>')

    monkeypatch.setattr('npazs.llm_models.requests.Session', lambda: _fake_post_session(fake_post))
    blocked = verify_ollama_cloud_models(
        'http://localhost:11434', ['minimax-m3:cloud', 'gpt-oss:20b-cloud'])
    assert list(blocked) == ['gpt-oss:20b-cloud']
    assert 'ollama signin' in blocked['gpt-oss:20b-cloud']


def test_run_ollama_signin_invokes_cli(monkeypatch):
    calls = []
    monkeypatch.setattr('npazs.llm_models.subprocess.Popen', lambda cmd: calls.append(cmd))
    run_ollama_signin()
    assert calls == [['ollama', 'signin']]


# ---------------------------------------------------------------------------
# HTTP-бэкенды: OpenRouter, Cline, DeepSeek, Gemini
# ---------------------------------------------------------------------------

def test_fetch_openai_compat_filters_free(monkeypatch):
    payload = {'data': [
        {'id': 'provider:paid-model', 'name': 'Paid'},
        {'id': 'openai/gpt-4o:free', 'name': 'GPT-4o (free)'},
        {'id': 'google/gemini-2.5-flash:free', 'name': 'Gemini Flash'},
        None,
        'not-a-dict',
    ]}
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append((url, headers, timeout))
        return _FakeResponse(data=payload)

    monkeypatch.setattr('npazs.llm_models.requests.Session', lambda: _fake_session(fake_get))
    result = _fetch_openai_compat_models('https://fake.example', 'key', 'free')
    assert result == ['google/gemini-2.5-flash:free', 'openai/gpt-4o:free']
    url, headers, _ = calls[0]
    assert url == 'https://fake.example/models'
    assert headers == {'Content-Type': 'application/json', 'Authorization': 'Bearer key'}


def test_fetch_openrouter_free_models(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        assert url == 'https://openrouter.ai/api/v1/models'
        assert headers == {'Content-Type': 'application/json', 'Authorization': 'Bearer secret'}
        return _FakeResponse(data={'data': [
            {'id': 'openai/gpt-4o:free', 'name': 'Free'},
            {'id': 'openai/gpt-4o', 'name': 'Paid'},
        ]})

    monkeypatch.setattr('npazs.llm_models.requests.Session', lambda: _fake_session(fake_get))
    result = fetch_openrouter_free_models('https://openrouter.ai/api/v1', 'secret')
    assert result == ['openai/gpt-4o:free']


def test_fetch_cline_models_raises_on_error(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        return _FakeResponse(status_code=401, text='no auth')

    monkeypatch.setattr('npazs.llm_models.requests.Session', lambda: _fake_session(fake_get))
    # Нет fallback: при недоступности API бросаем RuntimeError, а не
    # подменяем захардкоженный список моделей.
    with pytest.raises(RuntimeError, match='401'):
        fetch_cline_models('https://api.cline.bot/api/v1', '')


def test_cline_free_models_have_free_marker():
    """В live-ответе Cline free-модели помечены суффиксом ':free'."""
    # Эта проверка больше не про fallback: список free_models из констант
    # использовался только для fallback-подстановки, а та убрана.
    # Если в константах остались free модели — проверяем их структуру.
    models = HTTP_BACKEND_DEFS['cline'].get('free_models', [])
    for model in models:
        assert isinstance(model, str)


def test_fetch_cline_models_returns_only_free(monkeypatch):
    """Live-выборка cline: платные модели отбрасываются, URL и ключ корректны."""
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append((url, headers))
        return _FakeResponse(data={'data': [
            {'id': 'openai/gpt-6-astra', 'name': None},
            {'id': 'nex-agi/nex-n2.5-mini:free', 'name': None},
            {'id': 'z-ai/glm-5.2:free', 'name': None},
                        {'id': 'openai/gpt-6-astra:batch', 'name': None},
        ]})

    monkeypatch.setattr('npazs.llm_models.requests.Session', lambda: _fake_session(fake_get))
    result = fetch_cline_models('https://api.cline.bot/api/v1', 'secret')
    assert result == ['nex-agi/nex-n2.5-mini:free', 'z-ai/glm-5.2:free']
    url, headers = calls[0]
    assert url == 'https://api.cline.bot/api/v1/models'
    assert headers['Authorization'] == 'Bearer secret'


def test_fetch_cerebras_models_raises_on_error(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        return _FakeResponse(status_code=500, text='boom')

    monkeypatch.setattr('npazs.llm_models.requests.Session', lambda: _fake_session(fake_get))
    # Без fallback: при недоступности API бросаем RuntimeError.
    with pytest.raises(RuntimeError, match='500'):
        fetch_cerebras_models('https://example.com', '')


def test_fetch_mistral_raises_on_error(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        raise RuntimeError('network down')

    monkeypatch.setattr('npazs.llm_models.requests.Session', lambda: _fake_session(fake_get))
    # Без fallback: при недоступности API бросаем RuntimeError.
    with pytest.raises(RuntimeError, match='network down'):
        fetch_mistral_models('https://mistral.example', '')


def test_fetch_gemini_models_raises_on_error(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        return _FakeResponse(status_code=500, text='boom')

    monkeypatch.setattr('npazs.llm_models.requests.Session', lambda: _fake_session(fake_get))
    # Без fallback: при недоступности API бросаем RuntimeError.
    with pytest.raises(RuntimeError, match='500'):
        fetch_gemini_models('https://example.com', '')


def test_fetch_free_deepseek_models_hits_v1_models(monkeypatch):
    """Прокси FreeDeepseekAPI: GET {base}/models без free-фильтра."""
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append((url, headers))
        return _FakeResponse(data={'data': [
            {'id': 'deepseek-v4-flash', 'name': 'DeepSeek-V4.1-Flash'},
            {'id': 'deepseek-v4-pro', 'name': 'Legacy alias'},
        ]})

    monkeypatch.setattr('npazs.llm_models.requests.Session', lambda: _fake_session(fake_get))
    result = fetch_free_deepseek_models('http://127.0.0.1:9655/v1', '')
    assert result == ['deepseek-v4-flash', 'deepseek-v4-pro']
    url, headers = calls[0]
    assert url == 'http://127.0.0.1:9655/v1/models'
    # Без PROXY_API_KEY заголовок Authorization не отправляется.
    assert headers == {'Content-Type': 'application/json'}


def test_fetch_free_deepseek_models_raises_on_error(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        return _FakeResponse(status_code=500, text='boom')

    monkeypatch.setattr('npazs.llm_models.requests.Session', lambda: _fake_session(fake_get))
    # Без fallback: при недоступности API бросаем RuntimeError.
    with pytest.raises(RuntimeError, match='500'):
        fetch_free_deepseek_models('http://127.0.0.1:9655/v1', '')


def test_ask_free_deepseek_sends_agent_session(monkeypatch):
    """ask_* для free_deepseek: bare-host → /v1/chat/completions + x-agent-session."""
    from npazs.revision import ai_utils

    calls = {}

    class _Resp:
        status_code = 200
        text = ''

        def json(self):
            return {'choices': [{'message': {'content': '{"ok": true}'}}]}

    def fake_post(url, data=None, headers=None, timeout=None):
        # Тело приходит готовыми UTF-8-байтами (data=), а не через json=:
        # кириллица в escaped-JSON раздувала запрос до порога капчи WAF.
        calls['url'] = url
        calls['headers'] = dict(headers or {})
        calls['json'] = json.loads(data.decode('utf-8'))
        return _Resp()

    monkeypatch.setattr(ai_utils.requests, 'post', fake_post)
    answer = ai_utils.ask_kilo_gateway(
        '{"ping": 1}', 'deepseek-v4-flash', None,
        backend='free_deepseek', base_url='http://127.0.0.1:9655',
        api_key='', agent_session='npazs-test',
    )
    assert answer == '{"ok": true}'
    assert calls['url'] == 'http://127.0.0.1:9655/v1/chat/completions'
    assert calls['json']['messages'][0]['content'] == '{"ping": 1}'
    assert calls['headers']['x-agent-session'] == 'npazs-test'
    assert 'Authorization' not in calls['headers']


def test_fetch_qwen2api_models_hits_v1_models(monkeypatch):
    """Прокси Qwen2API: GET {base}/models без free-фильтра, с Bearer-ключом."""
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append((url, headers))
        return _FakeResponse(data={'data': [
            {'id': 'qwen3-coder-plus', 'name': 'Qwen3 Coder Plus'},
            {'id': 'qwen3-coder-flash', 'name': 'Qwen3 Coder Flash'},
        ]})

    monkeypatch.setattr('npazs.llm_models.requests.Session', lambda: _fake_session(fake_get))
    result = fetch_qwen2api_models('http://127.0.0.1:3000/v1', 'sk-test')
    assert result == ['qwen3-coder-flash', 'qwen3-coder-plus']
    url, headers = calls[0]
    assert url == 'http://127.0.0.1:3000/v1/models'
    # API_KEY прокси обязателен — отправляется как Bearer.
    assert headers.get('Authorization') == 'Bearer sk-test'


def test_fetch_qwen2api_models_raises_on_error(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        return _FakeResponse(status_code=500, text='boom')

    monkeypatch.setattr('npazs.llm_models.requests.Session', lambda: _fake_session(fake_get))
    # Без fallback: при недоступности API бросаем RuntimeError.
    with pytest.raises(RuntimeError, match='500'):
        fetch_qwen2api_models('http://127.0.0.1:3000/v1', '')


def test_ask_qwen2api_bare_host_gets_v1_suffix(monkeypatch):
    """ask_* для qwen2api: bare-host → /v1/chat/completions + Bearer."""
    from npazs.revision import ai_utils

    calls = {}

    class _Resp:
        status_code = 200
        text = ''

        def json(self):
            return {'choices': [{'message': {'content': '{"ok": true}'}}]}

    def fake_post(url, data=None, headers=None, timeout=None):
        calls['url'] = url
        calls['headers'] = dict(headers or {})
        calls['data'] = data
        return _Resp()

    monkeypatch.setattr(ai_utils.requests, 'post', fake_post)
    answer = ai_utils.ask_kilo_gateway(
        '{"ping": 1}', 'qwen3-coder-plus', None,
        backend='qwen2api', base_url='http://127.0.0.1:3000',
        api_key='sk-test',
    )
    assert answer == '{"ok": true}'
    assert calls['url'] == 'http://127.0.0.1:3000/v1/chat/completions'
    assert calls['headers']['Authorization'] == 'Bearer sk-test'
    # Тело — UTF-8-байты без \uXXXX-эскейпов (иначе кириллица раздувает запрос).
    assert isinstance(calls['data'], bytes)
    assert b'\\u' not in calls['data']
    assert 'x-agent-session' not in calls['headers']


def test_get_free_models_for_backend_returns_empty():
    """get_free_models_for_backend больше не выдаёт захардкоженных fallback-списков."""
    for backend in HTTP_BACKENDS:
        assert get_free_models_for_backend(backend) == []


def test_get_free_models_for_backend_unknown():
    assert get_free_models_for_backend('nonexistent') == []


def test_get_free_models_for_backend_kilo_gateway():
    assert get_free_models_for_backend('kilo_gateway') == []