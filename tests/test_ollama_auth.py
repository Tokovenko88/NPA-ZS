"""Авторизация Ollama cloud: HTTP 403 → fail-fast без повторов + подсказка signin."""

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

from npazs.revision.ai_utils import ask_ollama


class _Resp:
    def __init__(self, status_code, text='', payload=None):
        self.status_code = status_code
        self.text = text
        self._payload = payload or {'response': 'ok'}

    def json(self):
        return self._payload


def test_ask_ollama_403_fails_fast_with_signin_hint(monkeypatch):
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append(url)
        return _Resp(403, '<html>403 Forbidden</html>')

    monkeypatch.setattr('npazs.revision.ai_utils.requests.post', fake_post)
    logs = []
    result = ask_ollama(
        'промпт', 'gpt-oss:20b-cloud', lambda msg, level='info': logs.append((level, msg)),
        max_retries=3, retry_delay=0, repair_json=False, change_info='Изменение 1')
    assert result is None
    assert len(calls) == 1, 'HTTP 403 не должен повторяться (пока нет `ollama signin`)'
    assert any('ollama signin' in msg for _level, msg in logs)
    assert any('Изменение 1' in msg for _level, msg in logs)


def test_ask_ollama_success_still_works(monkeypatch):
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append(url)
        return _Resp(200, 'done', {'response': '  ответ модели  '})

    monkeypatch.setattr('npazs.revision.ai_utils.requests.post', fake_post)
    result = ask_ollama(
        'промпт', 'gpt-oss:20b-cloud', lambda msg, level='info': None,
        max_retries=3, retry_delay=0, repair_json=False)
    assert result == 'ответ модели'
    assert len(calls) == 1
