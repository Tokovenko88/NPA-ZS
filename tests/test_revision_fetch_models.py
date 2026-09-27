"""Регрессионные тесты загрузки списка моделей в GUI внесения изменений.

В ``App._fetch_models_for`` вызовы ``_fetch_http_models`` для ``qwen2api`` и
``free_deepseek`` ранее передавали не тех позиционных аргументов (паттерн до
появления параметра ``base_url`` в сигнатуре): флаг ``try_api`` (bool)
попадал в слот ``api_key``, а лямбда-fetcher получала его вместо URL. В результате
``fetch_qwen2api_models(True, key)`` падал с ``'bool' object has no attribute
'rstrip'``, что GUI показывало как ложную ошибку «прокси не запущен или
неверный ключ». Тесты фиксируют корректные аргументы и отдельно — что при
``try_api=False`` fetcher не вызывается.
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

from npazs.ui import revision_app
from npazs.ui.revision_app import App

_PROXY_URL = 'http://127.0.0.1:3000/v1'
_MODELS = ['qwen3-coder-plus']


class _StubVar:
    """Минимальная замена ``tk.StringVar`` (только ``get``)."""

    def __init__(self, value=''):
        self._value = value

    def get(self):
        return self._value


class _StubRoot:
    """``root.after``, выполняющий колбэк сразу — логи доступны синхронно."""

    def after(self, _delay, callback, *args):
        callback(*args)


def _make_app():
    """Экземпляр ``App`` без Tk-инициализации с заглушками GUI-зависимостей."""
    app = App.__new__(App)
    app.kilo_gateway_url = _StubVar(_PROXY_URL)
    app.post_gateway_url = _StubVar(_PROXY_URL)
    app.backend = _StubVar('qwen2api')
    app.post_analysis_backend = _StubVar('qwen2api')
    app.root = _StubRoot()
    app.logs = []
    app.log = lambda msg, level='info': app.logs.append((level, msg))
    app.set_targets = []
    app._set_models_for_target = (
        lambda models, target: app.set_targets.append((list(models), target))
    )
    app._api_key_for = lambda name, target='main': 'sk-test'
    app._kilo_credentials_for = lambda name, target='main': (_PROXY_URL, 'sk-test')
    return app


def _patch_fetcher(monkeypatch, attr_name):
    """Подменить fetcher в пространстве имён revision_app, вернуть журнал вызовов."""
    calls = []

    def fake_fetch(base_url, api_key=''):
        calls.append((base_url, api_key))
        return list(_MODELS)

    monkeypatch.setattr(revision_app, attr_name, fake_fetch)
    return calls


def test_qwen2api_post_fetcher_gets_url_and_key(monkeypatch):
    """Пост-анализ: fetcher обязан получить (URL: str, ключ: str), не bool."""
    calls = _patch_fetcher(monkeypatch, 'fetch_qwen2api_models')
    app = _make_app()

    app._fetch_models_for('qwen2api', try_api=True, target='post')

    assert calls == [(_PROXY_URL, 'sk-test')]
    assert app.set_targets == [(_MODELS, 'post')]
    assert not any(level == 'error' for level, _msg in app.logs)


def test_qwen2api_main_fetcher_gets_url_and_key(monkeypatch):
    """Основной бэкенд: тот же порядок аргументов (URL, ключ)."""
    calls = _patch_fetcher(monkeypatch, 'fetch_qwen2api_models')
    app = _make_app()

    app._fetch_models_for('qwen2api', try_api=True, target='main')

    assert calls == [(_PROXY_URL, 'sk-test')]
    assert app.set_targets == [(_MODELS, 'main')]


def test_free_deepseek_main_fetcher_gets_url_and_key(monkeypatch):
    """У ``free_deepseek`` был тот же баг аргументов — regress-check."""
    calls = _patch_fetcher(monkeypatch, 'fetch_free_deepseek_models')
    app = _make_app()

    app._fetch_models_for('free_deepseek', try_api=True, target='main')

    assert calls == [(_PROXY_URL, 'sk-test')]
    assert app.set_targets == [(_MODELS, 'main')]


def test_try_api_false_skips_fetcher(monkeypatch):
    """При отключённом live-запросе fetcher не вызывается, список пуст."""
    calls = _patch_fetcher(monkeypatch, 'fetch_qwen2api_models')
    app = _make_app()

    app._fetch_models_for('qwen2api', try_api=False, target='post')

    assert calls == []
    assert app.set_targets == [([], 'post')]
