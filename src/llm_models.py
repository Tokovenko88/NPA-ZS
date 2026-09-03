"""Общие функции работы со списками моделей ИИ-бэкендов.

Используются и модулем внесения изменений (``npazs.ui.revision_app``),
и модулем сравнения документов (``npazs.compare.gui``), чтобы логика
отбора free-моделей Kilo Gateway и whitelist-фильтра Ollama жила в одном
месте, а не дублировалась в двух GUI.

Модуль намеренно не зависит от Tkinter: всё — чистые функции с ``requests``.
"""

from __future__ import annotations

from collections.abc import Iterable

import requests
from npazs.constants import (
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
    response = requests.get(f'{base}/models', headers=headers, timeout=10)
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
    response = requests.get(f'{base}/api/tags', timeout=5)
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