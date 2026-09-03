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

from npazs.llm_models import (
    fetch_kilo_gateway_free_models,
    fetch_ollama_models,
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