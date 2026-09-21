"""Параметры LLM-бэкендов: локальная Ollama и HTTP-бэкенды.

NPA-ZS поддерживает несколько взаимозаменяемых бэкендов для этапов 1-4
AI-пайплайна:

``ollama``
    Локальный/сетевой сервер Ollama. Адрес — ``OLLAMA_BASE_URL``,
    модель по умолчанию — ``OLLAMA_DEFAULT_MODEL``.

``kilo_gateway``, ``cline``, ``openrouter``, ``cerebras``, ``together``, ``mistral``, ``gemini``,
``free_deepseek``
    HTTP-шлюзы, использующие OpenAI-compatible ``/chat/completions``.
    Конфигурация (URL, ключ, модель) берётся из :class:`npazs.config.settings.Settings`
    или из :data:`npazs.constants.HTTP_BACKEND_DEFS` как fallback.
    ``free_deepseek`` — локальный прокси FreeDeepseekAPI
    (https://github.com/dekrezz/FreeDeepseekAPI): ``npm start`` поднимает
    OpenAI-совместимый сервер на ``http://127.0.0.1:9655`` поверх
    web-сессии chat.deepseek.com; API-ключ прокси опционален
    (``PROXY_API_KEY``), сессии агентов — через ``x-agent-session``.

    Выбор бэкенда: ``LLM_BACKEND`` (по умолчанию ``kilo_gateway``).
    Пост-анализ может работать на другом провайдере: ``POST_ANALYSIS_BACKEND``
    + ``POST_ANALYSIS_MODEL`` (см. :func:`get_post_analysis_llm_config`).
    Ключ/URL пост-анализа берутся из ``*_API_KEY`` / ``*_BASE_URL``
    выбранного пост-бэкенда — тех же переменных, что и для основного прогона.
    """

from __future__ import annotations

from typing import Any

from npazs.config.settings import get_settings

#: Допустимые значения ``LLM_BACKEND``.  ``ollama`` — локальный сервер;
#: остальные — HTTP-бэкенды с OpenAI-compatible API.
#: Cerebras, Together, Mistral — платные pay-per-token API, но с generous
#: free tier'ом (без карты при регистрации), контекст до 128K.
SUPPORTED_BACKENDS = (
    'ollama',
    'kilo_gateway',
    'cline',
    'openrouter',
    'cerebras',
    'together',
    'mistral',
    'gemini',
    'free_deepseek',
)

#: HTTP-бэкенды, для которых используется единый ``ask_http_backend`.
HTTP_BACKENDS = frozenset(SUPPORTED_BACKENDS) - {'ollama'}

#: Детерминированные параметры генерации: пайплайн обязан быть воспроизводимым.
DETERMINISTIC_OPTIONS = {
    'temperature': 0.0,
    'top_p': 0.1,
}


def get_llm_backend() -> str:
    """Вернуть выбранный бэкенд; при неизвестном значении — ``free_deepseek``."""
    backend = (get_settings().llm_backend or '').strip().lower()
    return backend if backend in SUPPORTED_BACKENDS else 'free_deepseek'


def get_post_analysis_backend(fallback: str | None = None) -> str:
    """Вернуть бэкенд пост-анализа (``POST_ANALYSIS_BACKEND``).

    Если переменная не задана — возвращается ``fallback`` (обычно основной
    бэкенд), иначе ``kilo_gateway``. Неизвестные значения тоже откатываются
    к ``fallback``.
    """
    raw = (get_settings().post_analysis_backend or '').strip().lower()
    if raw and raw in SUPPORTED_BACKENDS:
        return raw
    if fallback and fallback.strip().lower() in SUPPORTED_BACKENDS:
        return fallback.strip().lower()
    return get_llm_backend()


def get_llm_config(backend: str) -> dict[str, Any]:
    """Параметры произвольного бэкенда + поле ``backend`` с его именем."""
    name = (backend or '').strip().lower()
    if name not in SUPPORTED_BACKENDS:
        name = 'free_deepseek'
    if name == 'ollama':
        config = get_ollama_config()
    else:
        config = _get_http_config(name)
    config['backend'] = name
    return config


def get_post_analysis_llm_config() -> dict[str, Any]:
    """Параметры бэкенда пост-анализа + поле ``backend``.

    Модель подставляется из ``POST_ANALYSIS_MODEL`` (если задана), иначе —
    дефолтная модель выбранного пост-бэкенда. Ключ/URL подставляются из
    ``POST_ANALYSIS_API_KEY`` / ``POST_ANALYSIS_BASE_URL`` (если заданы) —
    эти отдельные креды пост-анализа имеют приоритет над ключом/URL самого
    пост-бэкенда. Для локальной Ollama креды не переопределяются.
    """
    s = get_settings()
    backend = get_post_analysis_backend()
    config = get_llm_config(backend)
    if backend != 'ollama':
        pa_key = (getattr(s, 'post_analysis_api_key', '') or '').strip()
        pa_url = (getattr(s, 'post_analysis_base_url', '') or '').strip()
        if pa_key:
            config['api_key'] = pa_key
        if pa_url:
            config['base_url'] = pa_url
    pa_model = (s.post_analysis_model or '').strip()
    if pa_model:
        config['model'] = pa_model
    return config


def _get_http_config(backend: str) -> dict[str, Any]:
    """Универсальная конфигурация HTTP-бэкенда из настроек + fallback-констант."""
    from npazs.constants import HTTP_BACKEND_DEFS
    s = get_settings()
    # mapping backend -> (settings.base_url_attr, settings.api_key_attr, settings.model_attr)
    attr_map = {
        'kilo_gateway': ('kilo_gateway_base_url', 'kilo_gateway_api_key', 'kilo_gateway_default_model'),
        'cline':        ('cline_base_url',         'cline_api_key',          'cline_default_model'),
        'openrouter':   ('openrouter_base_url',    'openrouter_api_key',     'openrouter_default_model'),
        'cerebras':     ('cerebras_base_url',      'cerebras_api_key',       'cerebras_default_model'),
        'together':     ('together_base_url',      'together_api_key',       'together_default_model'),
        'mistral':      ('mistral_base_url',       'mistral_api_key',        'mistral_default_model'),
        'gemini':       ('gemini_base_url',        'gemini_api_key',         'gemini_default_model'),
        'free_deepseek': (
            'free_deepseek_base_url', 'free_deepseek_api_key', 'free_deepseek_default_model',
        ),
    }
    base_url_attr, key_attr, model_attr = attr_map.get(backend, attr_map['free_deepseek'])
    base_url = getattr(s, base_url_attr) or ''
    api_key = getattr(s, key_attr) or ''
    default_model = getattr(s, model_attr) or ''
    # fallback на константы, если env-переменные пусты
    defn = HTTP_BACKEND_DEFS.get(backend, HTTP_BACKEND_DEFS['free_deepseek'])
    base_url = base_url or defn['base_url']
    api_key = api_key or defn['api_key']
    default_model = default_model or defn['default_model']
    config: dict[str, Any] = {
        'base_url': base_url,
        'api_key': api_key,
        'model': default_model,
        'options': dict(DETERMINISTIC_OPTIONS),
    }
    # free_deepseek — sticky-сессии прокси через x-agent-session.
    if backend == 'free_deepseek':
        session = (getattr(s, 'free_deepseek_session', '') or '').strip()
        if not session:
            session = str(defn.get('session') or 'npazs-main').strip() or 'npazs-main'
        config['session'] = session
    return config


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


def get_cerebras_config() -> dict[str, Any]:
    """Параметры Cerebras API."""
    return _get_http_config('cerebras')


def get_together_config() -> dict[str, Any]:
    """Параметры Together AI API."""
    return _get_http_config('together')


def get_mistral_config() -> dict[str, Any]:
    """Параметры Mistral AI API."""
    return _get_http_config('mistral')


def get_gemini_config() -> dict[str, Any]:
    """Параметры Gemini API."""
    return _get_http_config('gemini')


def get_free_deepseek_config() -> dict[str, Any]:
    """Параметры локального прокси FreeDeepseekAPI (OpenAI-compatible)."""
    return _get_http_config('free_deepseek')


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
        'get_cerebras_config',
        'get_cline_config',
        'get_free_deepseek_config',
        'get_gemini_config',
        'get_kilo_gateway_config',
        'get_llm_backend',
        'get_llm_config',
        'get_mistral_config',
        'get_ollama_config',
        'get_openrouter_config',
        'get_post_analysis_backend',
        'get_post_analysis_llm_config',
        'get_together_config',
    ]
