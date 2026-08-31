"""Параметры LLM-бэкендов: локальная Ollama и Kilo Gateway.

NPA-ZS поддерживает два взаимозаменяемых бэкенда для этапов 1-4 AI-пайплайна:

``ollama``
    Локальный/сетевой сервер Ollama. Адрес — ``OLLAMA_BASE_URL``,
    модель по умолчанию — ``OLLAMA_DEFAULT_MODEL``.

``kilo_gateway``
    HTTP-шлюз Kilo. Адрес — ``KILO_GATEWAY_BASE_URL``, ключ —
    ``KILO_GATEWAY_API_KEY``, модель — ``KILO_GATEWAY_DEFAULT_MODEL``.

Выбор бэкенда: ``LLM_BACKEND`` (по умолчанию ``kilo_gateway``).

Оба бэкенда вызываются из :func:`npazs.revision.ai_utils.ask_ollama`, которая
принимает параметр ``backend`` и сама маршрутизирует запрос.
"""

from __future__ import annotations

from typing import Any, Dict

from npazs.config.settings import get_settings

#: Допустимые значения ``LLM_BACKEND``.
SUPPORTED_BACKENDS = ('ollama', 'kilo_gateway')

#: Детерминированные параметры генерации: пайплайн обязан быть воспроизводимым.
DETERMINISTIC_OPTIONS = {
    'temperature': 0.0,
    'top_p': 0.1,
}


def get_llm_backend() -> str:
    """Вернуть выбранный бэкенд; при неизвестном значении — ``kilo_gateway``."""
    backend = (get_settings().llm_backend or '').strip().lower()
    return backend if backend in SUPPORTED_BACKENDS else 'kilo_gateway'


def get_ollama_config() -> Dict[str, Any]:
    """Параметры Ollama."""
    s = get_settings()
    return {
        'base_url': s.ollama_base_url,
        'model': s.default_ollama_model,
        'options': dict(DETERMINISTIC_OPTIONS),
    }


def get_kilo_gateway_config() -> Dict[str, Any]:
    """Параметры Kilo Gateway."""
    s = get_settings()
    return {
        'base_url': s.kilo_gateway_base_url,
        'api_key': s.kilo_gateway_api_key,
        'model': s.kilo_gateway_default_model,
        'options': dict(DETERMINISTIC_OPTIONS),
    }


def get_active_llm_config() -> Dict[str, Any]:
    """Параметры активного бэкенда + поле ``backend`` с его именем."""
    backend = get_llm_backend()
    config = get_ollama_config() if backend == 'ollama' else get_kilo_gateway_config()
    config['backend'] = backend
    return config


__all__ = [
    'SUPPORTED_BACKENDS',
    'DETERMINISTIC_OPTIONS',
    'get_llm_backend',
    'get_ollama_config',
    'get_kilo_gateway_config',
    'get_active_llm_config',
]
