"""Параметры LLM-бэкендов: локальная Ollama и HTTP-бэкенды.

NPA-ZS поддерживает несколько взаимозаменяемых бэкендов для этапов 1-4
AI-пайплайна:

``ollama``
    Локальный/сетевой сервер Ollama. Адрес — ``OLLAMA_BASE_URL``,
    модель по умолчанию — ``OLLAMA_DEFAULT_MODEL``.

``kilo_gateway``, ``cline``, ``openrouter``, ``deepseek``, ``gemini``
    HTTP-шлюзы, использующие OpenAI-compatible ``/chat/completions``.
    Конфигурация (URL, ключ, модель) берётся из :class:`npazs.config.settings.Settings`
    или из :data:`npazs.constants.HTTP_BACKEND_DEFS` как fallback.

Выбор бэкенда: ``LLM_BACKEND`` (по умолчанию ``kilo_gateway``).
"""

from __future__ import annotations

from typing import Any

from npazs.config.settings import get_settings

#: Допустимые значения ``LLM_BACKEND``.  ``ollama`` — локальный сервер;
#: остальные — HTTP-бэкенды с OpenAI-compatible API.
SUPPORTED_BACKENDS = ('ollama', 'kilo_gateway', 'cline', 'openrouter', 'deepseek', 'gemini')

#: HTTP-бэкенды, для которых используется единый ``ask_http_backend`.
HTTP_BACKENDS = frozenset(SUPPORTED_BACKENDS) - {'ollama'}

#: Детерминированные параметры генерации: пайплайн обязан быть воспроизводимым.
DETERMINISTIC_OPTIONS = {
    'temperature': 0.0,
    'top_p': 0.1,
}


def get_llm_backend() -> str:
    """Вернуть выбранный бэкенд; при неизвестном значении — ``kilo_gateway``."""
    backend = (get_settings().llm_backend or '').strip().lower()
    return backend if backend in SUPPORTED_BACKENDS else 'kilo_gateway'


def _get_http_config(backend: str) -> dict[str, Any]:
    """Универсальная конфигурация HTTP-бэкенда из настроек + fallback-констант."""
    from npazs.constants import HTTP_BACKEND_DEFS
    s = get_settings()
    # mapping backend -> (settings.base_url_attr, settings.api_key_attr, settings.model_attr)
    attr_map = {
        'kilo_gateway': ('kilo_gateway_base_url', 'kilo_gateway_api_key', 'kilo_gateway_default_model'),
        'cline':        ('cline_base_url',         'cline_api_key',          'cline_default_model'),
        'openrouter':   ('openrouter_base_url',    'openrouter_api_key',     'openrouter_default_model'),
        'deepseek':     ('deepseek_base_url',      'deepseek_api_key',       'deepseek_default_model'),
        'gemini':       ('gemini_base_url',        'gemini_api_key',         'gemini_default_model'),
    }
    base_url_attr, key_attr, model_attr = attr_map.get(backend, attr_map['kilo_gateway'])
    base_url = getattr(s, base_url_attr) or ''
    api_key = getattr(s, key_attr) or ''
    default_model = getattr(s, model_attr) or ''
    # fallback на константы, если env-переменные пусты
    defn = HTTP_BACKEND_DEFS.get(backend, HTTP_BACKEND_DEFS['kilo_gateway'])
    base_url = base_url or defn['base_url']
    api_key = api_key or defn['api_key']
    default_model = default_model or defn['default_model']
    return {
        'base_url': base_url,
        'api_key': api_key,
        'model': default_model,
        'options': dict(DETERMINISTIC_OPTIONS),
    }


def get_ollama_config() -> dict[str, Any]:
    """Параметры Ollama."""
    s = get_settings()
    return {
        'base_url': s.ollama_base_url,
        'model': s.default_ollama_model,
        'options': dict(DETERMINISTIC_OPTIONS),
    }


def get_kilo_gateway_config() -> dict[str, Any]:
    """Параметры Kilo Gateway."""
    return _get_http_config('kilo_gateway')


def get_cline_config() -> dict[str, Any]:
    """Параметры Cline API."""
    return _get_http_config('cline')


def get_openrouter_config() -> dict[str, Any]:
    """Параметры OpenRouter API."""
    return _get_http_config('openrouter')


def get_deepseek_config() -> dict[str, Any]:
    """Параметры DeepSeek API."""
    return _get_http_config('deepseek')


def get_gemini_config() -> dict[str, Any]:
    """Параметры Gemini API."""
    return _get_http_config('gemini')


def get_active_llm_config() -> dict[str, Any]:
    """Параметры активного бэкенда + поле ``backend`` с его именем."""
    backend = get_llm_backend()
    if backend == 'ollama':
        config = get_ollama_config()
    else:
        config = _get_http_config(backend)
    config['backend'] = backend
    return config


__all__ = [
    'DETERMINISTIC_OPTIONS',
    'HTTP_BACKENDS',
    'SUPPORTED_BACKENDS',
    'get_active_llm_config',
    'get_cline_config',
    'get_deepseek_config',
    'get_gemini_config',
    'get_kilo_gateway_config',
    'get_llm_backend',
    'get_ollama_config',
    'get_openrouter_config',
]
