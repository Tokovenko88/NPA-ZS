"""Тесты конфигурации LLM-бэкендов (``npazs.config.ollama``)."""

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

from npazs.config.ollama import (
    HTTP_BACKENDS,
    SUPPORTED_BACKENDS,
    get_active_llm_config,
    get_cline_config,
    get_deepseek_config,
    get_gemini_config,
    get_llm_backend,
    get_openrouter_config,
)
from npazs.constants import HTTP_BACKEND_DEFS


def test_supported_backends_include_new_ones():
    assert 'oline' not in SUPPORTED_BACKENDS  # typo check
    for backend in ('ollama', 'kilo_gateway', 'cline', 'openrouter', 'deepseek', 'gemini'):
        assert backend in SUPPORTED_BACKENDS


def test_http_backends_all_have_defs():
    """Каждый HTTP-бэкенд из config/ollama.py есть в HTTP_BACKEND_DEFS."""
    for backend in HTTP_BACKENDS:
        assert backend in HTTP_BACKEND_DEFS, f"Бэкенд {backend} отсутствует в HTTP_BACKEND_DEFS"
        defn = HTTP_BACKEND_DEFS[backend]
        assert defn['base_url'], f"Бэкенд {backend} без base_url"
        assert defn['default_model'], f"Бэкенд {backend} без default_model"
        assert defn['free_models'], f"Бэкенд {backend} без free_models"


def test_get_cline_config():
    cfg = get_cline_config()
    assert cfg['base_url'], 'Cline base_url не должен быть пустым'
    assert cfg['model'], 'Cline model не должен быть пустым'


def test_get_openrouter_config():
    cfg = get_openrouter_config()
    assert cfg['base_url'] == 'https://openrouter.ai/api/v1' or cfg['base_url']


def test_get_deepseek_config():
    cfg = get_deepseek_config()
    assert cfg['base_url']
    assert cfg['model']


def test_get_gemini_config():
    cfg = get_gemini_config()
    assert cfg['base_url']
    assert cfg['model']


def test_get_active_llm_config_is_backend(monkeypatch):
    """get_active_llm_config должен вернуть конфиг с полем backend."""
    # Полный фейковый namedtuple-подобный объект с полями, которые читает код.
    class _FakeSettings:
        llm_backend = 'deepseek'
        deepseek_base_url = 'https://api.deepseek.com/v1'
        deepseek_api_key = 'key123'
        deepseek_default_model = 'deepseek-chat'
        # Остальные поля (не используются для deepseek, но нужны для getattr-безопасности)
        kilom_base_url = ''
        kilom_api_key = ''
        kilom_default_model = ''
        cline_base_url = ''
        cline_api_key = ''
        cline_default_model = ''
        openrouter_base_url = ''
        openrouter_api_key = ''
        openrouter_default_model = ''
        gemini_base_url = ''
        gemini_api_key = ''
        gemini_default_model = ''
        ollama_base_url = 'http://localhost:11434'
        default_ollama_model = 'gpt-oss:20b-cloud'
        kilo_gateway_base_url = ''
        kilo_gateway_api_key = ''
        kilo_gateway_default_model = ''

    monkeypatch.setattr(
        'npazs.config.ollama.get_settings',
        lambda: _FakeSettings(),
    )
    cfg = get_active_llm_config()
    assert cfg['backend'] == 'deepseek'
    assert cfg['base_url']
    assert cfg['model']
    assert cfg['api_key'] == 'key123'


def test_get_llm_backend_valid_and_invalid(monkeypatch):
    """Неизвестный бэкенд откатывается к kilo_gateway."""
    monkeypatch.setattr(
        'npazs.config.ollama.get_settings',
        lambda: type('S', (), {'llm_backend': 'bogus'})(),
    )
    assert get_llm_backend() == 'kilo_gateway'

    monkeypatch.setattr(
        'npazs.config.ollama.get_settings',
        lambda: type('S', (), {'llm_backend': 'cline'})(),
    )
    assert get_llm_backend() == 'cline'