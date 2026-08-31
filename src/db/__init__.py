"""Слой работы с MySQL-базой НПА-ЗС.

Источник кода: проект ``JSON-To-DB``. Монолитный ``src/main.py`` разделён на
модули по ответственности, логика импорта сохранена без изменений.

Состав
------

:mod:`npazs.db.connection`
    ``DBConnection`` — подключение к MySQL, транзакции, повторы при deadlock/
    lock-wait timeout, быстрая массовая загрузка через ``LOAD DATA LOCAL INFILE``.
    Здесь же общие константы (``DB_CONFIG``, ``COLOR``, ``LOG_TAGS``,
    ``ITEM_TYPE_MAP``) и помощники дат/ФИО.

:mod:`npazs.db.importer`
    ``NpaImporter`` — перенос каноничного JSON НПА в реляционную схему, и
    ``ImporterApp`` — Tk-интерфейс импортёра.

:mod:`npazs.db.editor`
    GUI-редактор записей БД (``App``, ``DatabaseManager``, ``TableTab``,
    ``StructureTab``, ``NotesTab``, ``HistoryTab`` и диалоги правки).

:mod:`npazs.db.schema`
    Машиночитаемое описание схемы: список таблиц, порядок вставки/удаления,
    перечни ENUM. Используется валидацией и отчётами.

``sql/schema.sql``
    DDL-скрипт для создания схемы с нуля.

Реквизиты подключения
---------------------
Только из окружения (``DB_HOST``, ``DB_PORT``, ``DB_USER``, ``DB_PASSWORD``,
``DB_NAME``, ``DB_CHARSET``); см. :mod:`npazs.config.db` и ``.env.example``.
Значения по умолчанию с реальными хостами и паролями из исходных проектов
удалены намеренно.

Импорт подмодулей ленивый: ``importer`` и ``editor`` тянут ``tkinter``.
"""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    'connection',
    'importer',
    'editor',
    'schema',
    'DBConnection',
    'NpaImporter',
]

_LAZY_ATTRS = {
    'DBConnection': ('npazs.db.connection', 'DBConnection'),
    'NpaImporter': ('npazs.db.importer', 'NpaImporter'),
}


def __getattr__(name: str) -> Any:
    """Ленивая загрузка подмодулей и основных классов."""
    if name in _LAZY_ATTRS:
        module_name, attr = _LAZY_ATTRS[name]
        return getattr(importlib.import_module(module_name), attr)
    if name in __all__:
        return importlib.import_module(f'npazs.db.{name}')
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
