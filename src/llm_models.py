"""Общие функции работы со списками моделей ИИ-бэкендов.

Используются и модулем внесения изменений (``npazs.ui.revision_app``),
и модулем сравнения документов (``npazs.compare.gui``).

Строгое правило: списки моделей — ТОЛЬКО live из API провайдера
(``GET {base_url}/models``, для Ollama — ``GET {base_url}/api/tags``).
Никаких захардкоженных списков и fallback-наборов здесь нет:
при недоступности API функции бросают ``RuntimeError``/``requests``-исключение,
а GUI показывает пустой список + честную ошибку. ``base_url`` всегда
передаётся параметром (из ``.env`` через ``load_backend_settings``),
внутри функций URL не зашиты.

Модуль намеренно не зависит от Tkinter: всё — чистые функции с ``requests``.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterable

import requests


def filter_free_models(payload, known: Iterable[str] = ()) -> list:
    """Отобрать реально существующие free-модели из ответа ``GET /models``.

    ``payload`` — объект из ответа (словарь с ключом ``data``). Отбираются
    только модели, в id/названии которых есть признак ``free`` — это реальный
    тарифный признак в ответах Kilo/OpenRouter/Cline, а не выдуманный список.
    ``known`` оставлен для совместимости и по умолчанию пуст (не используется).
    Возвращается отсортированный список без дубликатов.
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
        if 'free' in low:
            selected.append(model_id)
    if not selected:
        for expected in known:
            lower = str(expected).lower()
            if lower in ids_lower:
                selected.append(ids_lower[lower])
    return sorted(set(selected))


def fetch_kilo_gateway_free_models(url: str, api_key: str = '') -> list:
    """Получить реально существующие free-модели Kilo Gateway через API.

    Выполняет ``GET {url}/models`` и возвращает список моделей через
    :func:`filter_free_models`. Бросает ``RuntimeError`` при HTTP-ошибке;
    исключения ``requests`` уходят вызывающей стороне (GUI показывает
    пустой список + честную ошибку, без выдуманных моделей).
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


def fetch_ollama_models(base_url: str = '', cloud_only: bool = False) -> list:
    """Получить установленные модели из локального Ollama.

    Выполняет ``GET {base_url}/api/tags`` и возвращает отсортированный
    список имён. Никакого whitelist-фильтра: что реально установлено,
    то и показывается. Бросает ``RuntimeError`` при HTTP-ошибке.
    ``base_url`` обязан прийти из ``.env`` (``OLLAMA_BASE_URL``).

    ``cloud_only=True`` — только облачные модели Ollama (признак
    ``remote_host``/``remote_model`` в ``/api/tags`` либо ``cloud``-суффикс
    в имени); локальные модели в выборку не попадают (см.
    :func:`is_ollama_cloud_model`).
    """
    base = (base_url or '').rstrip('/')
    if not base:
        raise RuntimeError('OLLAMA_BASE_URL is not configured in .env')
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
        if not name:
            continue
        if cloud_only and not is_ollama_cloud_model(m):
            continue
        models.append(name)
    return sorted(set(models))


#: Подсказка при отсутствии авторизации Ollama cloud (HTTP 403 от ollama.com).
OLLAMA_SIGNIN_HINT = (
    'Облачным моделям Ollama нужен вход на ollama.com: выполните в терминале '
    '`ollama signin` (откроется браузер для входа) или откройте '
    'https://ollama.com, затем обновите список моделей.'
)

#: Текст диалога «Авторизоваться сейчас?» (GUI).
OLLAMA_SIGNIN_DIALOG_TEXT = (
    'Облачные модели Ollama недоступны: нет авторизации ollama.com (HTTP 403).\n\n'
    'Авторизоваться сейчас? Будет запущен `ollama signin` и откроется браузер '
    'для входа на ollama.com.\n\n'
    'Позже авторизацию можно выполнить вручную командой `ollama signin` '
    'в терминале, затем нажать «Обновить модели».'
)


def is_ollama_cloud_model(entry) -> bool:
    """Признак облачной модели Ollama.

    ``entry`` — словарь из ``GET /api/tags`` или имя строки. Облачная модель:
    в ответе есть ``remote_host``/``remote_model`` (авторитетный признак
    remote-модели Ollama) либо тег имени равен/оканчивается на ``cloud``
    (``gpt-oss:20b-cloud``, ``minimax-m3:cloud``).
    """
    if isinstance(entry, dict):
        if str(entry.get('remote_host') or '').strip() or str(entry.get('remote_model') or '').strip():
            return True
        name = str(entry.get('name') or '')
    else:
        name = str(entry or '')
    tag = name.split(':', 1)[1] if ':' in name else name
    return tag == 'cloud' or tag.endswith('-cloud')


def check_ollama_cloud_access(base_url: str, model: str) -> str:
    """Проверить доступ к облачной модели Ollama (проба авторизации).

    Дёшево выполняет ``POST {base_url}/api/show`` (без генерации токенов):
    если облако Ollama отвечает ``HTTP 403`` — входа на ollama.com нет
    (или нет прав на модель). Возвращает пустую строку при успехе либо
    текст причины; при 403 причина содержит подсказку ``ollama signin``.
    Прочие ошибки тоже возвращаются текстом (403 — не единственная причина
    недоступности). ``RuntimeError`` — только при незаданном ``base_url``.
    """
    base = (base_url or '').rstrip('/')
    if not base:
        raise RuntimeError('OLLAMA_BASE_URL is not configured in .env')
    session = _ssl_session()
    try:
        response = session.post(f'{base}/api/show', json={'name': model}, timeout=10)
    finally:
        session.close()
    if response.status_code == 403:
        return f'HTTP 403 (нет авторизации ollama.com). {OLLAMA_SIGNIN_HINT}'
    if response.status_code == 401:
        return f'HTTP 401 (требуется авторизация ollama.com). {OLLAMA_SIGNIN_HINT}'
    if response.status_code != 200:
        return f'HTTP {response.status_code}'
    return ''


def verify_ollama_cloud_models(base_url: str, models) -> dict:
    """Проверить доступность облачных моделей Ollama.

    Возвращает ``{model: reason}`` только для недоступных моделей:
    пустой словарь = авторизация есть, все модели доступны.
    """
    blocked = {}
    for name in models:
        try:
            reason = check_ollama_cloud_access(base_url, name)
        except requests.RequestException as e:
            # Сеть/таймаут — не «нет авторизации», но модель тоже недоступна.
            reason = f'Проверка доступа не удалась: {e}'
        if reason:
            blocked[str(name)] = reason
    return blocked


def run_ollama_signin() -> None:
    """Запустить ``ollama signin`` (открывает браузер для входа на ollama.com)."""
    subprocess.Popen(['ollama', 'signin'])


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
    (``free`` для OpenRouter/Cline). При ``free_marker=None`` фильтр
    отключается и возвращаются ВСЕ модели из ответа (Cerebras,
    Mistral, Gemini, локальные прокси).
    Ошибки НЕ глотаются: ``RuntimeError`` уходит в GUI.
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


def fetch_openrouter_free_models(base_url: str, api_key: str = '') -> list:
    """РЕАЛЬНЫЕ free-модели OpenRouter: ``GET {base_url}/models``, фильтр 'free'.

    ``base_url`` — строго из ``.env`` (``OPENROUTER_BASE_URL``). Ошибки
    не глотаются: уходят в GUI (пустой список + честная ошибка).
    """
    return _fetch_openai_compat_models(base_url, api_key, 'free')


def fetch_cline_models(base_url: str, api_key: str = '') -> list:
    """РЕАЛЬНЫЕ free-модели Cline API: ``GET {base_url}/models``, фильтр 'free'.

    ``base_url`` — строго из ``.env`` (``CLINE_BASE_URL``). Ошибки не глотаются.
    """
    return _fetch_openai_compat_models(base_url, api_key, 'free')


def fetch_cerebras_models(base_url: str, api_key: str = '') -> list:
    """РЕАЛЬНЫЙ список моделей Cerebras: ``GET {base_url}/models`` без фильтра.

    ``base_url`` — строго из ``.env`` (``CEREBRAS_BASE_URL``). Ошибки не глотаются.
    """
    return _fetch_openai_compat_models(base_url, api_key, free_marker=None)


def fetch_mistral_models(base_url: str, api_key: str = '') -> list:
    """РЕАЛЬНЫЙ список моделей Mistral AI: ``GET {base_url}/models`` без фильтра.

    ``base_url`` — строго из ``.env`` (``MISTRAL_BASE_URL``). Ошибки не глотаются.
    """
    return _fetch_openai_compat_models(base_url, api_key, free_marker=None)


def fetch_gemini_models(base_url: str, api_key: str = '') -> list:
    """РЕАЛЬНЫЙ список моделей Gemini: ``GET {base_url}/models`` без фильтра.

    ``base_url`` — строго из ``.env`` (``GEMINI_BASE_URL``). Возвращаются все
    доступные по ключу модели (фильтра по тарифу нет — его знает только
    провайдер/ключ). Ошибки не глотаются.
    """
    return _fetch_openai_compat_models(base_url, api_key, free_marker=None)


def fetch_free_deepseek_models(base_url: str, api_key: str = '') -> list:
    """РЕАЛЬНЫЙ список моделей локального прокси FreeDeepseekAPI.

    ``base_url`` — строго из ``.env`` (``FREE_DEEPSEEK_BASE_URL``, хранится
    с суффиксом ``/v1``; bare-host дополняется до ``/v1``). Без фильтра:
    возвращается всё, что отдал ``GET /v1/models``. Ошибки не глотаются.
    """
    base = (base_url or '').rstrip('/')
    if not base:
        raise RuntimeError('FREE_DEEPSEEK_BASE_URL is not configured in .env')
    # base_url хранится с суффиксом /v1, bare-host дополняем так же.
    root = base if base.endswith('/v1') else f'{base}/v1'
    return _fetch_openai_compat_models(root, api_key, free_marker=None)


def fetch_qwen2api_models(base_url: str, api_key: str = '') -> list:
    """РЕАЛЬНЫЙ список моделей локального прокси Qwen2API (Qwen-Proxy).

    ``base_url`` — строго из ``.env`` (``QWEN2API_BASE_URL``, хранится
    с суффиксом ``/v1``; bare-host дополняется до ``/v1``). Без фильтра:
    список зависит от подключённых аккаунтов chat.qwen.ai.
    Ошибки не глотаются (401 = неверный ``QWEN2API_API_KEY`` в ``.env`` NPA-ZS
    относительно ``API_KEY`` в ``.env`` самого прокси).
    """
    base = (base_url or '').rstrip('/')
    if not base:
        raise RuntimeError('QWEN2API_BASE_URL is not configured in .env')
    # base_url хранится с суффиксом /v1, bare-host дополняем так же.
    root = base if base.endswith('/v1') else f'{base}/v1'
    return _fetch_openai_compat_models(root, api_key, free_marker=None)


def get_free_models_for_backend(backend: str) -> list:
    """Совместимость: выдуманных fallback-списков больше нет — всегда [].

    Оставлена, чтобы старый код не падал с ImportError: при недоступности
    API GUI показывает пустой список + честную ошибку.
    """
    return []
