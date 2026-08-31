"""Загрузка окружения и сводный объект настроек NPA-ZS.

Порядок поиска ``.env``:

1. ``$NPAZS_ENV_FILE`` — явное переопределение;
2. ``<корень проекта>/.env`` — обычный режим разработки;
3. каталог рядом с исполняемым файлом — режим PyInstaller (``sys.frozen``);
4. ``.env`` в текущем рабочем каталоге — как последний вариант.

Объект :class:`Settings` — ``namedtuple``, поэтому остаётся совместимым с
историческим ``_ModxSettings`` из ``npa_processor/config.py``: доступ по
именам полей и распаковка работают одинаково.
"""

from __future__ import annotations

import os
import sys
from collections import namedtuple
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dotenv является обязательной зависимостью
    def load_dotenv(*_args, **_kwargs):  # type: ignore[misc]
        return False


def _detect_project_root() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    # src/config/settings.py -> config -> src -> <корень>
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = _detect_project_root()


def _detect_env_path() -> Path:
    override = os.environ.get('NPAZS_ENV_FILE')
    if override:
        return Path(override)
    candidates = [
        PROJECT_ROOT / '.env',
        Path(sys.executable).resolve().parent / '.env' if getattr(sys, 'frozen', False) else None,
        Path.cwd() / '.env',
    ]
    for candidate in candidates:
        if candidate is not None and candidate.exists():
            return candidate
    return PROJECT_ROOT / '.env'


ENV_PATH = _detect_env_path()


def load_env(override: bool = False) -> bool:
    """Загрузить ``.env``. Возвращает True, если файл найден и прочитан."""
    if ENV_PATH.exists():
        load_dotenv(dotenv_path=str(ENV_PATH), override=override)
        return True
    load_dotenv(override=override)
    return False


load_env()


_SETTINGS_FIELDS = [
    # MODX / SSH
    'modx_ssh_host',
    'modx_ssh_port',
    'modx_ssh_username',
    'modx_ssh_password',
    'modx_base_path',
    # LLM
    'default_ollama_model',
    'ollama_base_url',
    'kilo_gateway_api_key',
    'kilo_gateway_base_url',
    'kilo_gateway_default_model',
    'llm_backend',
    # База НПА
    'db_host',
    'db_port',
    'db_user',
    'db_password',
    'db_name',
    'db_charset',
    # Прочее
    'log_level',
    'project_root',
]

Settings = namedtuple('Settings', _SETTINGS_FIELDS)

# Историческое имя типа (использовалось в npa_processor.config).
_ModxSettings = Settings


def _int_env(name: str, default: str) -> int:
    raw = os.environ.get(name, default)
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return int(default)


def get_settings() -> Settings:
    """Собрать актуальные настройки из переменных окружения."""
    return Settings(
        modx_ssh_host=os.environ.get('MODX_SSH_HOST'),
        modx_ssh_port=_int_env('MODX_SSH_PORT', '22'),
        modx_ssh_username=os.environ.get('MODX_SSH_USERNAME'),
        modx_ssh_password=os.environ.get('MODX_SSH_PASSWORD'),
        modx_base_path=os.environ.get('MODX_BASE_PATH'),
        default_ollama_model=os.environ.get('OLLAMA_DEFAULT_MODEL', 'gpt-oss:20b-cloud'),
        ollama_base_url=os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434'),
        kilo_gateway_api_key=os.environ.get('KILO_GATEWAY_API_KEY', ''),
        kilo_gateway_base_url=os.environ.get(
            'KILO_GATEWAY_BASE_URL', 'https://api.kilo.ai/api/gateway'
        ),
        kilo_gateway_default_model=os.environ.get(
            'KILO_GATEWAY_DEFAULT_MODEL', 'anthropic/claude-sonnet-4.5'
        ),
        llm_backend=os.environ.get('LLM_BACKEND', 'kilo_gateway'),
        db_host=os.environ.get('DB_HOST', 'localhost'),
        db_port=_int_env('DB_PORT', '3306'),
        db_user=os.environ.get('DB_USER', ''),
        db_password=os.environ.get('DB_PASSWORD', ''),
        db_name=os.environ.get('DB_NAME', ''),
        db_charset=os.environ.get('DB_CHARSET', 'utf8mb4'),
        log_level=os.environ.get('LOG_LEVEL', 'INFO'),
        project_root=str(PROJECT_ROOT),
    )


def reload_settings(override: bool = True) -> Settings:
    """Перечитать ``.env`` и вернуть свежие настройки."""
    load_env(override=override)
    return get_settings()


__all__ = [
    'ENV_PATH',
    'PROJECT_ROOT',
    'Settings',
    'get_settings',
    'load_env',
    'reload_settings',
]
