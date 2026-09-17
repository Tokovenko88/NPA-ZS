"""Общие функции работы со списками моделей ИИ-бэкендов.

Используются и модулем внесения изменений (``npazs.ui.revision_app``),
и модулем сравнения документов (``npazs.compare.gui``), чтобы логика
отбора free-моделей Kilo Gateway и whitelist-фильтра Ollama жила в одном
месте, а не дублировалась в двух GUI.

Модуль намеренно не зависит от Tkinter: всё — чистые функции с ``requests``.
"""

from __future__ import annotations

from collections.abc import Iterable
import os

import requests
from npazs.constants import (
    HTTP_BACKEND_DEFS,
    KILO_GATEWAY_FREE_MODELS,
    OLLAMA_MODELS_WHITELIST,
    _ollama_base_url,
)


def filter_free_models(
    payload, known: Iterable[str] = KILO_GATEWAY_FREE_MODELS
) -> list:
    """Отобрать реально существующие free-модели из ответа Kilo Gateway.

    ``payload`` — объект из ответа ``GET /models`` (словарь с ключом
    ``data``). Сначала отбираются все модели, в id/названии которых есть
    признак ``free`` (или ``auto free``); если таких нет — по известным
    id из ``known``. Возвращается отсортированный список без дубликатов.
    """
    candidates = []
    for m in payload.get('data', []) if isinstance(payload, dict) else []:
        if not isinstance(m, dict):
            continue
        model_id = str(m.get('id') or '').strip()
        name = str(m.get('name') or '').strip()
        if model_id:
            candidates.append((model_id, name))
    ids_lower = {model_id.lower(): model_id for model_id, _ in candidates}
    selected = []
    for model_id, name in candidates:
        low = f"{model_id} {name}".lower()
        if 'free' in low or 'auto free' in low:
            selected.append(model_id)
    if not selected:
        for expected in known:
            lower = expected.lower()
            if lower in ids_lower:
                selected.append(ids_lower[lower])
    return sorted(set(selected))


def fetch_kilo_gateway_free_models(url: str, api_key: str = '') -> list:
    """Получить реально существующие free-модели Kilo Gateway через API.

    Выполняет ``GET {url}/models`` и возвращает список моделей через
    :func:`filter_free_models`. Бросает ``RuntimeError`` при HTTP-ошибке;
    исключения ``requests`` уходят вызывающей стороне — она решает, как
    показать fallback-список.
    """
    base = url.rstrip('/') if url else ''
    headers = {}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'
    session = _ssl_session()
    try:
        response = session.get(f'{base}/models', headers=headers, timeout=10)
    finally:
        session.close()
    if response.status_code != 200:
        raise RuntimeError(
            f'HTTP {response.status_code}: {response.text}'
        )
    data = response.json()
    return filter_free_models(data)


def fetch_ollama_models(base_url: str = _ollama_base_url) -> list:
    """Получить разрешённые модели из локального Ollama.

    Выполняет ``GET {base_url}/api/tags`` и возвращает отсортированный
    список моделей, прошедших ``OLLAMA_MODELS_WHITELIST``. Бросает
    ``RuntimeError`` при HTTP-ошибке.
    """
    base = base_url.rstrip('/') if base_url else ''
    session = _ssl_session()
    try:
        response = session.get(f'{base}/api/tags', timeout=5)
    finally:
        session.close()
    if response.status_code != 200:
        raise RuntimeError(f'HTTP {response.status_code}')
    data = response.json()
    models = []
    for m in data.get('models', []):
        if not isinstance(m, dict):
            continue
        name = str(m.get('name') or '').strip()
        if name and name in OLLAMA_MODELS_WHITELIST:
            models.append(name)
    return sorted(models)


# ---------------------------------------------------------------------------
# Generic OpenAI-compatible model fetching (OpenRouter, Cline, DeepSeek, Gemini)
# ---------------------------------------------------------------------------

def _ssl_session() -> requests.Session:
    """Вернуть ``requests.Session`` с учётом настроек SSL.

    При ``NPAZ_DISABLE_SSL_VERIFY=1`` проверка сертификата отключается —
    нужно для корпоративных прокси с самоподписанными сертификатами.
    Переменная ``REQUESTS_CA_BUNDLE`` (стандартная для ``requests``)
    позволяет указать путь к кастомному CA-бандлу.
    """
    session = requests.Session()
    if os.environ.get('NPAZ_DISABLE_SSL_VERIFY', '0').strip() in ('1', 'true', 'yes'):
        session.verify = False
    return session


def _fetch_openai_compat_models(
    base_url: str,
    api_key: str = '',
    free_marker: str | None = 'free',
) -> list:
    """Получить список моделей из OpenAI-compatible ``GET /models``.

    ``free_marker`` — маркер, по которому отбираются free-модели
    (например, ``free`` для OpenRouter/Cline или ``flash`` для Gemini).
    При ``free_marker=None`` фильтр отключается и возвращаются все модели
    (используется для бэкендов без free-тарифа, например DeepSeek).
    Если API недоступен или не возвращает моделей, выбрасывается
    ``RuntimeError`` — вызывающий код решает, как использовать fallback-список.
    """
    base = (base_url or '').rstrip('/')
    if not base:
        raise RuntimeError('Base URL is not configured')
    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'
    session = _ssl_session()
    try:
        response = session.get(f'{base}/models', headers=headers, timeout=15)
    finally:
        session.close()
    if response.status_code != 200:
        raise RuntimeError(
            f'HTTP {response.status_code}: {response.text[:200]}'
        )
    data = response.json()
    selected = []
    for m in data.get('data', []):
        if not isinstance(m, dict):
            continue
        model_id = str(m.get('id') or '').strip()
        name = str(m.get('name') or str(m.get('id') or '')).strip()
        if not model_id:
            continue
        if free_marker is None or free_marker in f'{model_id} {name}'.lower():
            selected.append(model_id)
    return sorted(set(selected))


def fetch_openrouter_free_models(api_key: str = '') -> list:
    """Получить free-модели OpenRouter через ``GET /models``.

    Если API недоступен (SSL, сеть, ключ), используется fallback из констант
    (``HTTP_BACKEND_DEFS['openrouter']['free_models']``) — как у остальных
    HTTP-бэкендов.
    """
    try:
        return _fetch_openai_compat_models(
            'https://openrouter.ai/api/v1', api_key, 'free'
        )
    except RuntimeError:
        return sorted(HTTP_BACKEND_DEFS['openrouter']['free_models'])


def fetch_cline_models(api_key: str = '') -> list:
    """Получить только и только free-модели Cline API через ``GET /models``.

    Отбираются модели с признаком ``free`` (у Cline это суффикс ``:free``).
    Если API недоступен, используется fallback из констант
    (``HTTP_BACKEND_DEFS['cline']['free_models']``).
    """
    try:
        return _fetch_openai_compat_models(
            'https://api.cline.bot/api/v1', api_key, 'free'
        )
    except RuntimeError:
        return sorted(HTTP_BACKEND_DEFS['cline']['free_models'])


def fetch_cerebras_models(api_key: str = '') -> list:
    """Получить список моделей Cerebras через ``GET /models``.

    Cerebras — платный pay-per-token, но с generous free tier'ом при регистрации
    (без карты), контекст до 128K. Если API недоступен, используется fallback
    из констант.
    """
    try:
        return _fetch_openai_compat_models(
            'https://api.cerebras.ai/v1', api_key, free_marker=None
        )
    except RuntimeError:
        return sorted(HTTP_BACKEND_DEFS['cerebras']['free_models'])


def fetch_together_models(api_key: str = '') -> list:
    """Получить список моделей Together AI через ``GET /models``.

    Together AI — платный pay-per-token, но с free tier'ом при регистрации
    (без карты), контекст до 128K. Если API недоступен, используется fallback
    из констант.
    """
    try:
        return _fetch_openai_compat_models(
            'https://api.together.xyz/v1', api_key, free_marker=None
        )
    except RuntimeError:
        return sorted(HTTP_BACKEND_DEFS['together']['free_models'])


def fetch_mistral_models(api_key: str = '') -> list:
    """Получить список моделей Mistral AI через ``GET /models``.

    Mistral AI — платный pay-per-token, но с free tier'ом при регистрации
    (без карты), контекст до 128K. Если API недоступен, используется fallback
    из констант.
    """
    try:
        return _fetch_openai_compat_models(
            'https://api.mistral.ai/v1', api_key, free_marker=None
        )
    except RuntimeError:
        return sorted(HTTP_BACKEND_DEFS['mistral']['free_models'])


def fetch_gemini_models(api_key: str = '') -> list:
    """Получить список free-моделей Gemini через ``GET /models``.

    Если API не доступен, используется fallback из констант.
    """
    try:
        return _fetch_openai_compat_models(
            'https://generativelanguage.googleapis.com/v1beta/openai',
            api_key, 'flash'
        )
    except RuntimeError:
        return sorted(HTTP_BACKEND_DEFS['gemini']['free_models'])


def get_free_models_for_backend(backend: str) -> list:
    """Вернуть fallback-список free-моделей для любого бэкенда.

    Используется как запасной вариант, когда API недоступен.
    """
    if backend == 'kilo_gateway':
        return sorted(KILO_GATEWAY_FREE_MODELS)
    defn = HTTP_BACKEND_DEFS.get(backend)
    if defn:
        return sorted(defn['free_models'])
    return sorted(KILO_GATEWAY_FREE_MODELS)