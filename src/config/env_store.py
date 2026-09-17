"""Запись API-ключей и параметров LLM-бэкендов в ``.env``.

:mod:`npazs.config.settings` только читает переменные окружения, поэтому
ключ, введённый в поле GUI, жил до закрытия окна. Этот модуль добавляет
обратную операцию: аккуратно обновляет файл ``.env``
(:data:`npazs.config.settings.ENV_PATH`), сохраняя комментарии, порядок и
пустые строки, — чтобы API-ключи моделей не приходилось вводить заново
после перезапуска приложения.

Публичный API:

* :data:`BACKEND_ENV_KEYS` — имена переменных окружения по бэкенду;
* :data:`ACTIVE_BACKEND_ENV` — переменная выбора активного бэкенда;
* :func:`env_var_names` — имена переменных одного бэкенда;
* :func:`get_env_value` — значение переменной прямо из файла;
* :func:`load_backend_settings` — прочитать сохранённые параметры бэкенда;
* :func:`load_active_backend` — имя активного бэкенда из ``.env``;
* :func:`save_env_values` — записать произвольный набор ``KEY=VALUE``;
* :func:`save_backend_settings` — сохранить ключ/URL/модель бэкенда.

Пример::

    from npazs.config.env_store import save_backend_settings

    save_backend_settings('gemini', api_key='AIza...', model='gemini-2.0-flash')
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path

from npazs.config.settings import ENV_PATH

__all__ = [
    'ACTIVE_BACKEND_ENV',
    'BACKEND_ENV_KEYS',
    'env_var_names',
    'get_env_value',
    'load_active_backend',
    'load_backend_settings',
    'save_backend_settings',
    'save_env_values',
]

#: Переменная выбора активного LLM-бэкенда (``LLM_BACKEND``).
ACTIVE_BACKEND_ENV = 'LLM_BACKEND'

#: Имена переменных окружения по бэкенду: ``api_key`` / ``base_url`` / ``model``.
#: У локальной Ollama API-ключа нет, поэтому соответствующий ключ отсутствует.
BACKEND_ENV_KEYS: dict[str, dict[str, str]] = {
    'ollama': {
        'base_url': 'OLLAMA_BASE_URL',
        'model': 'OLLAMA_DEFAULT_MODEL',
    },
    'kilo_gateway': {
        'api_key': 'KILO_GATEWAY_API_KEY',
        'base_url': 'KILO_GATEWAY_BASE_URL',
        'model': 'KILO_GATEWAY_DEFAULT_MODEL',
    },
    'cline': {
        'api_key': 'CLINE_API_KEY',
        'base_url': 'CLINE_BASE_URL',
        'model': 'CLINE_DEFAULT_MODEL',
    },
    'openrouter': {
        'api_key': 'OPENROUTER_API_KEY',
        'base_url': 'OPENROUTER_BASE_URL',
        'model': 'OPENROUTER_DEFAULT_MODEL',
    },
    'cerebras': {
        'api_key': 'CEREBRAS_API_KEY',
        'base_url': 'CEREBRAS_BASE_URL',
        'model': 'CEREBRAS_DEFAULT_MODEL',
    },
    'together': {
        'api_key': 'TOGETHER_API_KEY',
        'base_url': 'TOGETHER_BASE_URL',
        'model': 'TOGETHER_DEFAULT_MODEL',
    },
    'mistral': {
        'api_key': 'MISTRAL_API_KEY',
        'base_url': 'MISTRAL_BASE_URL',
        'model': 'MISTRAL_DEFAULT_MODEL',
    },
    'gemini': {
        'api_key': 'GEMINI_API_KEY',
        'base_url': 'GEMINI_BASE_URL',
        'model': 'GEMINI_DEFAULT_MODEL',
    },
}

#: Строка ``KEY=VALUE`` (допускается префикс ``export`` и пробелы вокруг ``=``).
_LINE_RE = re.compile(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=')

#: Символы, из-за которых значение нужно брать в двойные кавычки.
_UNSAFE_VALUE_RE = re.compile(r'[\s#\'"]')


def env_var_names(backend: str) -> dict[str, str]:
    """Имена переменных окружения для бэкенда (копия словаря)."""
    return dict(BACKEND_ENV_KEYS.get((backend or '').strip().lower(), {}))


def _normalize(value: object) -> str:
    """Привести значение к однострочной строке без внешних пробелов."""
    text = '' if value is None else str(value)
    return ' '.join(text.replace('\r', ' ').replace('\n', ' ').split())


def _quote(value: str) -> str:
    """Заключить значение в кавычки, если иначе ``.env`` прочитается неверно."""
    if _UNSAFE_VALUE_RE.search(value):
        return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'
    return value


def _detect_newline(existing: str, line_count: int) -> str:
    """Сохранить преобладающий перевод строки исходного файла."""
    crlf = existing.count('\r\n')
    if crlf and crlf * 2 >= max(line_count, 1):
        return '\r\n'
    return '\n'


def get_env_value(name: str, env_path: object = None, default: str = '') -> str:
    """Прочитать значение переменной прямо из файла ``.env``.

    Окружение процесса при этом не изменяется. Если переменной нет,
    возвращается ``default``.
    """
    path = Path(env_path) if env_path else ENV_PATH
    if not path.exists():
        return default
    for line in path.read_text(encoding='utf-8').splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        match = _LINE_RE.match(line)
        if match and match.group(1) == name:
            value = line.split('=', 1)[1].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
                value = value[1:-1]
            return value
    return default

def load_backend_settings(backend: str, env_path: object = None) -> dict[str, str]:
    """Прочитать сохранённые параметры бэкенда прямо из файла ``.env``.

    Возвращает словарь вида ``{'api_key': ..., 'base_url': ..., 'model': ...}``
    (для ``ollama`` без ``api_key``); отсутствующие переменные приходят
    пустыми строками. Окружение процесса не изменяется — значения всегда
    актуальны на момент вызова, даже если ``.env`` правили извне.
    Бросает ``ValueError`` для неизвестного бэкенда.
    """
    names = BACKEND_ENV_KEYS.get((backend or '').strip().lower())
    if names is None:
        raise ValueError(f'Неизвестный LLM-бэкенд: {backend!r}')
    return {
        kind: get_env_value(env_name, env_path=env_path)
        for kind, env_name in names.items()
    }


def load_active_backend(env_path: object = None) -> str:
    """Имя активного бэкенда из ``.env`` (``LLM_BACKEND``); '' если не задан."""
    return get_env_value(ACTIVE_BACKEND_ENV, env_path=env_path).strip().lower()


def save_env_values(values: Mapping[str, object], env_path: object = None) -> Path:
    """Записать набор ``KEY=VALUE`` в ``.env``; вернуть путь к файлу.

    Пустые значения (``None`` и ``''``) пропускаются — уже сохранённая
    переменная не затирается. Отсутствующие в файле ключи добавляются в
    конец отдельным блоком. Комментарии, порядок строк, регистр имён и
    переводы строк исходного файла сохраняются; запись атомарная
    (временный файл + ``os.replace``). После успешной записи значения
    попадают и в ``os.environ`` текущего процесса, поэтому вызывающий код
    сразу видит новый ключ через :func:`npazs.config.settings.get_settings`.
    """
    updates: dict[str, str] = {}
    for name, value in values.items():
        key = _normalize(name)
        text = _normalize(value)
        if key and text:
            updates[key] = text

    path = Path(env_path) if env_path else ENV_PATH
    if not updates:
        return path

    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding='utf-8') if path.exists() else ''
    lines = existing.splitlines()
    newline = _detect_newline(existing, len(lines))

    pending = dict(updates)
    for index, line in enumerate(lines):
        match = _LINE_RE.match(line)
        if not match:
            continue
        name = match.group(1)
        if name in pending:
            lines[index] = f'{name}={_quote(pending.pop(name))}'
    if pending:
        if lines and lines[-1].strip():
            lines.append('')
        lines.extend(f'{name}={_quote(value)}' for name, value in pending.items())

    tmp_path = path.with_name(path.name + '.tmp')
    try:
        tmp_path.write_text(newline.join(lines) + newline, encoding='utf-8')
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    for name, value in updates.items():
        os.environ[name] = value
    return path


def save_backend_settings(
    backend: str,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    make_active: bool = True,
    env_path: object = None,
) -> dict[str, str]:
    """Сохранить ключ/URL/модель выбранного бэкенда в ``.env``.

    Возвращает фактически записанные пары ``ПЕРЕМЕННАЯ=значение``.
    Пустые аргументы игнорируются (не затирают сохранённое значение).
    При ``make_active=True`` дополнительно записывается ``LLM_BACKEND``,
    то есть бэкенд становится активным при следующем запуске.

    Бросает ``ValueError`` для неизвестного бэкенда.
    """
    name = (backend or '').strip().lower()
    names = BACKEND_ENV_KEYS.get(name)
    if names is None:
        raise ValueError(f'Неизвестный LLM-бэкенд: {backend!r}')

    values: dict[str, str] = {}
    for kind, value in (('api_key', api_key), ('base_url', base_url), ('model', model)):
        env_name = names.get(kind)
        text = _normalize(value)
        if env_name and text:
            values[env_name] = text
    if make_active:
        values[ACTIVE_BACKEND_ENV] = name
    save_env_values(values, env_path=env_path)
    return values
