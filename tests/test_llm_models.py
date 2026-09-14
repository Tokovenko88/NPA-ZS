"""Тесты общего модуля списков моделей ИИ-бэкендов (``npazs.llm_models``)."""

import importlib.util
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
    fetch_cline_models,
    fetch_deepseek_models,
    fetch_gemini_models,
    fetch_kilo_gateway_free_models,
    fetch_ollama_models,
    fetch_openrouter_free_models,
    get_free_models_for_backend,
)


class _FakeResponse:
    def __init__(self, status_code=200, text='', data=None):
        self.status_code = status_code
        self.text = text
        self._data = data

    def json(self):
        return self._data


def test_fetch_kilo_gateway_filters_and_sends_auth(monkeypatch):
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append((url, headers, timeout))
        return _FakeResponse(data={'data': [
            {'id': 'provider:paid', 'name': 'Paid'},
            {'id': 'google/gemini-2.5-flash:free', 'name': 'Gemini Flash'},
            {'id': 'openrouter/auto:free', 'name': 'Auto Free'},
        ]})

    monkeypatch.setattr('npazs.llm_models.requests.get', fake_get)
    result = fetch_kilo_gateway_free_models('https://kg.example/', 'secret')
    assert result == ['google/gemini-2.5-flash:free', 'openrouter/auto:free']
    url, headers, _timeout = calls[0]
    assert url == 'https://kg.example/models'
    assert headers == {'Authorization': 'Bearer secret'}


def test_fetch_kilo_gateway_raises_on_http_error(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        return _FakeResponse(status_code=500, text='boom')

    monkeypatch.setattr('npazs.llm_models.requests.get', fake_get)
    with pytest.raises(RuntimeError, match='500'):
        fetch_kilo_gateway_free_models('https://kg.example', '')


def test_fetch_ollama_filters_whitelist(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        assert url == 'http://localhost:11434/api/tags'
        return _FakeResponse(data={'models': [
            {'name': 'some-other-model'},
            {'name': 'gpt-oss:20b-cloud'},
            {'name': 'gemma4:31b'},
        ]})

    monkeypatch.setattr('npazs.llm_models.requests.get', fake_get)
    result = fetch_ollama_models('http://localhost:11434')
    assert result == ['gemma4:31b', 'gpt-oss:20b-cloud']


def test_fetch_ollama_raises_on_http_error(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        return _FakeResponse(status_code=503, text='unavailable')

    monkeypatch.setattr('npazs.llm_models.requests.get', fake_get)
    with pytest.raises(RuntimeError, match='503'):
        fetch_ollama_models('http://localhost:11434')


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

    monkeypatch.setattr('npazs.llm_models.requests.get', fake_get)
    result = _fetch_openai_compat_models('https://fake.example', 'key', 'free')
    assert result == ['google/gemini-2.5-flash:free', 'openai/gpt-4o:free']
    url, headers, _ = calls[0]
    assert url == 'https://fake.example/models'
    assert headers == {'Content-Type': 'application/json', 'Authorization': 'Bearer key'}


def test_fetch_openrouter_free_models(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        assert url == 'https://openrouter.ai/api/v1/models'
        return _FakeResponse(data={'data': [
            {'id': 'openai/gpt-4o:free', 'name': 'Free'},
            {'id': 'openai/gpt-4o', 'name': 'Paid'},
        ]})

    monkeypatch.setattr('npazs.llm_models.requests.get', fake_get)
    result = fetch_openrouter_free_models('secret')
    assert result == ['openai/gpt-4o:free']


def test_fetch_cline_models_fallback_on_error(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        return _FakeResponse(status_code=401, text='no auth')

    monkeypatch.setattr('npazs.llm_models.requests.get', fake_get)
    # На 401 _fetch_openai_compat_models бросает RuntimeError,
    # fetch_cline_models перехватывает и возвращает fallback из констант.
    result = fetch_cline_models('')
    assert result == sorted(HTTP_BACKEND_DEFS['cline']['free_models'])


def test_fetch_deepseek_models_fallback_on_error(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        raise RuntimeError('network down')

    monkeypatch.setattr('npazs.llm_models.requests.get', fake_get)
    result = fetch_deepseek_models('')
    assert result == sorted(HTTP_BACKEND_DEFS['deepseek']['free_models'])


def test_fetch_gemini_models_fallback_on_error(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        return _FakeResponse(status_code=500, text='boom')

    monkeypatch.setattr('npazs.llm_models.requests.get', fake_get)
    result = fetch_gemini_models('')
    assert result == sorted(HTTP_BACKEND_DEFS['gemini']['free_models'])


def test_get_free_models_for_backend_all_backends():
    """Каждый HTTP-бэкенд из констант имеет непустой fallback-список."""
    for backend in HTTP_BACKENDS:
        models = get_free_models_for_backend(backend)
        assert len(models) > 0, f"Бэкенд {backend} не имеет free-моделей"


def test_get_free_models_for_backend_unknown():
    assert get_free_models_for_backend('nonexistent') == sorted(
        HTTP_BACKEND_DEFS['kilo_gateway']['free_models']
    )


def test_get_free_models_for_backend_kilo_gateway():
    result = get_free_models_for_backend('kilo_gateway')
    assert result == sorted(HTTP_BACKEND_DEFS['kilo_gateway']['free_models'])