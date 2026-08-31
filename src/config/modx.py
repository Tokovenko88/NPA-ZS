"""Параметры MODX: SSH-доступ и база данных сайта.

MODX Revolution — CMS, из которой :mod:`npazs.core.modx_processor` забирает
HTML-ресурсы НПА для последующего парсинга в JSON. Нужны два набора реквизитов:

* SSH (``MODX_SSH_*``) — доступ к файлам сайта и путь ``MODX_BASE_PATH``;
* БД MODX (``MODX_DB_*``) — чтение таблиц ресурсов и шаблонных переменных (TV).

Важно: база MODX (``MODX_DB_*``) и база НПА (``DB_*``, см.
:mod:`npazs.config.db`) — это разные базы. Не смешивайте их реквизиты.
"""

from __future__ import annotations

import os
from typing import Any, Dict

from npazs.config.settings import get_settings


def _int_env(name: str, default: str) -> int:
    raw = os.environ.get(name, default)
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return int(default)


def get_modx_db_config() -> Dict[str, Any]:
    """Параметры подключения к базе данных MODX.

    Имя и сигнатура сохранены из ``npa_processor.config.get_modx_db_config``,
    поэтому :mod:`npazs.core.html_parser` и :mod:`npazs.core.modx_processor`
    работают без изменений.
    """
    return {
        'host': os.environ.get('MODX_DB_HOST'),
        'port': _int_env('MODX_DB_PORT', '3306'),
        'user': os.environ.get('MODX_DB_USER'),
        'password': os.environ.get('MODX_DB_PASSWORD'),
        'database': os.environ.get('MODX_DB_NAME'),
        'charset': os.environ.get('MODX_DB_CHARSET', 'utf8'),
    }


def get_modx_ssh_config() -> Dict[str, Any]:
    """Параметры SSH-доступа к серверу MODX."""
    s = get_settings()
    return {
        'host': s.modx_ssh_host,
        'port': s.modx_ssh_port,
        'username': s.modx_ssh_username,
        'password': s.modx_ssh_password,
        'base_path': s.modx_base_path,
    }


def modx_is_configured() -> bool:
    """True, если заданы минимальные реквизиты для работы с MODX."""
    ssh = get_modx_ssh_config()
    db = get_modx_db_config()
    return bool(ssh['host'] and ssh['username']) or bool(db['host'] and db['database'])


__all__ = [
    'get_modx_db_config',
    'get_modx_ssh_config',
    'modx_is_configured',
]
