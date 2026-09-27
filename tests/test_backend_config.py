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
        get_cerebras_config,
        get_gemini_config,
        get_llm_backend,
        get_mistral_config,
        get_openrouter_config,
)
from npazs.constants import HTTP_BACKEND_DEFS


def test_supported_backends_include_new_ones():
        assert 'oline' not in SUPPORTED_BACKENDS  # typo check
        for backend in (
            'ollama', 'kilo_gateway', 'cline', 'openrouter',
            'cerebras', 'mistral', 'gemini',
            'free_deepseek', 'qwen2api',
        ):
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


def test_get_cerebras_config():
        cfg = get_cerebras_config()
        assert cfg['base_url']
        assert cfg['model']


def test_get_mistral_config():
        cfg = get_mistral_config()
        assert cfg['base_url']
        assert cfg['model']


def test_get_gemini_config():
        cfg = get_gemini_config()
        assert cfg['base_url']
        assert cfg['model']


def test_get_qwen2api_config(monkeypatch):
        """Конфиг локального прокси Qwen2API: URL/модель из дефолтов.

        Live-значения из .env пользователя не влияют: env-переменные
        снимаются, проверяются именно дефолты.
        """
        from npazs.config.ollama import get_qwen2api_config

        monkeypatch.delenv('QWEN2API_BASE_URL', raising=False)
        monkeypatch.delenv('QWEN2API_API_KEY', raising=False)
        monkeypatch.delenv('QWEN2API_DEFAULT_MODEL', raising=False)
        cfg = get_qwen2api_config()
        assert cfg['base_url'] == 'http://127.0.0.1:3000/v1'
        assert cfg['model'] == 'qwen3-coder-plus'


def test_get_active_llm_config_is_backend(monkeypatch):
        """get_active_llm_config должен вернуть конфиг с полем backend."""
        # Полный фейковый namedtuple-подобный объект с полями, которые читает код.
        class _FakeSettings:
            llm_backend = 'cerebras'
            cerebras_base_url = 'https://api.cerebras.ai/v1'
            cerebras_api_key = 'key123'
            cerebras_default_model = 'llama3.1-8b'
            # Остальные поля (не используются для cerebras, но нужны для getattr-безопасности)
            kilom_base_url = ''
            kilom_api_key = ''
            kilom_default_model = ''
            cline_base_url = ''
            cline_api_key = ''
            cline_default_model = ''
            openrouter_base_url = ''
            openrouter_api_key = ''
            openrouter_default_model = ''
            mistral_base_url = ''
            mistral_api_key = ''
            mistral_default_model = ''
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
        assert cfg['backend'] == 'cerebras'
        assert cfg['base_url']
        assert cfg['model']
        assert cfg['api_key'] == 'key123'


def test_get_llm_backend_valid_and_invalid(monkeypatch):
        """Неизвестный бэкенд откатывается к free_deepseek (дефолт)."""
        monkeypatch.setattr('npazs.config.ollama.get_settings', lambda: type('S', (), {'llm_backend': 'bogus'})())
        assert get_llm_backend() == 'free_deepseek'
        assert get_llm_backend() == 'free_deepseek'

def test_default_backend_is_free_deepseek(monkeypatch):
    """free_deepseek — бэкенд по умолчанию для обоих селекторов."""
    from npazs.config.settings import get_settings
    from npazs.constants import DEFAULT_BACKEND

    assert DEFAULT_BACKEND == 'free_deepseek'
    monkeypatch.delenv('LLM_BACKEND', raising=False)
    assert get_settings().llm_backend == 'free_deepseek'
    assert get_llm_backend() == 'free_deepseek'


def _fake_settings(**overrides):
    """Минимальный settings-объект для тестов пост-конфига."""
    fields = {
        'llm_backend': 'free_deepseek',
        'post_analysis_backend': '',
        'post_analysis_model': '',
        'post_analysis_api_key': '',
        'post_analysis_base_url': '',
        'free_deepseek_base_url': 'http://127.0.0.1:9655/v1',
        'free_deepseek_api_key': '',
        'free_deepseek_default_model': 'deepseek-v4-flash',
        'free_deepseek_session': 'npazs-main',
        'gemini_base_url': 'https://gemini-url',
        'gemini_api_key': 'K-pa',
        'gemini_default_model': 'gemini-2.5-flash',
    }
    fields.update(overrides)
    return type('S', (), fields)()


def test_post_analysis_llm_config_overrides(monkeypatch):
    """POST_ANALYSIS_API_KEY/_BASE_URL приоритетнее кредов пост-бэкенда."""
    from npazs.config.ollama import get_post_analysis_llm_config

    monkeypatch.setattr(
        'npazs.config.ollama.get_settings',
        lambda: _fake_settings(
            post_analysis_backend='gemini',
            post_analysis_api_key='K-override',
            post_analysis_base_url='https://pa-own-url',
        ),
    )
    config = get_post_analysis_llm_config()
    assert config['backend'] == 'gemini'
    assert config['api_key'] == 'K-override'
    assert config['base_url'] == 'https://pa-own-url'


def test_post_analysis_llm_config_inherits_backend_creds(monkeypatch):
    """Пустые POST_ANALYSIS-оверрайды — наследуются креды пост-бэкенда."""
    from npazs.config.ollama import get_post_analysis_llm_config

    monkeypatch.setattr(
        'npazs.config.ollama.get_settings',
        lambda: _fake_settings(post_analysis_backend='gemini'),
    )
    config = get_post_analysis_llm_config()
    assert config['backend'] == 'gemini'
    assert config['api_key'] == 'K-pa'
    assert config['base_url'] == 'https://gemini-url'


def test_post_analysis_llm_config_ollama_ignores_overrides(monkeypatch):
    """Для ollama креды не переопределяются (нет api_key в конфиге)."""
    from npazs.config.ollama import get_post_analysis_llm_config

    monkeypatch.setattr(
        'npazs.config.ollama.get_settings',
        lambda: _fake_settings(
            post_analysis_backend='ollama',
            post_analysis_api_key='K-override',
            post_analysis_base_url='https://pa-own-url',
            ollama_base_url='http://localhost:11434',
            default_ollama_model='gemini-1.5-flash',
        ),
    )
    config = get_post_analysis_llm_config()
    assert config['backend'] == 'ollama'
    assert 'api_key' not in config
    assert config['base_url'] == 'http://localhost:11434'
