"""Параметры подключения к MySQL-базе НПА-ЗС.

Единственный источник истины для реквизитов БД — переменные окружения
(``.env``). Значений по умолчанию с реальными хостами/паролями в коде нет
намеренно: при переносе кода из исходных проектов production-реквизиты были
удалены (см. ``docs/db_schema.md``, раздел «Безопасность»).

Используется двумя потребителями:

* :mod:`npazs.db.connection` / :mod:`npazs.db.importer` — импорт JSON в БД;
* :mod:`npazs.db.editor` — GUI-редактор записей.
"""

from __future__ import annotations

from typing import Any, Dict

from npazs.config.settings import get_settings

#: Имена переменных окружения, описывающих подключение к базе НПА.
DB_ENV_KEYS = (
    'DB_HOST',
    'DB_PORT',
    'DB_USER',
    'DB_PASSWORD',
    'DB_NAME',
    'DB_CHARSET',
)

#: Обязательные переменные — без них подключение бессмысленно.
DB_REQUIRED_KEYS = ('DB_HOST', 'DB_USER', 'DB_PASSWORD', 'DB_NAME')


def get_db_config() -> Dict[str, Any]:
    """Вернуть параметры подключения к базе НПА в виде dict для ``pymysql``."""
    s = get_settings()
    return {
        'host': s.db_host,
        'port': s.db_port,
        'user': s.db_user,
        'password': s.db_password,
        'database': s.db_name,
        'charset': s.db_charset,
    }


# Историческое/альтернативное имя.
get_db_config_dict = get_db_config


def missing_db_settings() -> list[str]:
    """Список незаполненных обязательных переменных окружения."""
    config = get_db_config()
    mapping = {
        'DB_HOST': config['host'],
        'DB_USER': config['user'],
        'DB_PASSWORD': config['password'],
        'DB_NAME': config['database'],
    }
    return [name for name in DB_REQUIRED_KEYS if not mapping.get(name)]


def get_db_config_checked() -> Dict[str, Any]:
    """Как :func:`get_db_config`, но падает с понятной ошибкой при нехватке данных."""
    missing = missing_db_settings()
    if missing:
        raise RuntimeError(
            'Не заданы обязательные переменные окружения для подключения к БД: '
            + ', '.join(missing)
            + '. Скопируйте .env.example в .env и заполните значения.'
        )
    return get_db_config()


__all__ = [
    'DB_ENV_KEYS',
    'DB_REQUIRED_KEYS',
    'get_db_config',
    'get_db_config_dict',
    'get_db_config_checked',
    'missing_db_settings',
]
