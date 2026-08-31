"""Машиночитаемое описание схемы базы НПА-ЗС.

Полное человеко-читаемое описание — в ``docs/db_schema.md``; DDL — в
``src/db/sql/schema.sql``. Этот модуль нужен коду: валидации, отчётам и
GUI-редактору, которым требуется знать состав таблиц, порядок вставки и
допустимые значения ENUM, не разбирая SQL.

Ключевые инварианты схемы
-------------------------
1. ``npa_item.item_id`` — строковый неизменяемый идентификатор элемента
   (шаблон ``<npa_id>_<type>_<number>[_double_N]``). Он не меняется никогда,
   поэтому ссылки ``child_ref``, ``modified_by_id``, ``not_valid`` остаются
   корректными даже при перенумерации элемента.
2. Номер элемента версионируется отдельно (``npa_item_number_revision``);
   ``npa_item.item_number`` всегда равен последней действующей записи истории.
3. У элемента может быть только одна активная редакция
   (``valid_to IS NULL``) в каждой таблице ревизий.
4. Удаление НПА каскадное, кроме ``npa_note_unified.source_item_id``, где
   применяется ``ON DELETE SET NULL``: примечание переживает удаление источника.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

#: Путь к DDL-скрипту схемы.
SCHEMA_SQL_PATH = Path(__file__).resolve().parent / 'sql' / 'schema.sql'

# --- Справочники ------------------------------------------------------------
REFERENCE_TABLES: Tuple[str, ...] = (
    'person',
    'convocation',
    'person_post',
    'committees',
)

# --- Паспорт НПА ------------------------------------------------------------
CORE_TABLES: Tuple[str, ...] = (
    'npa_base',
    'npa_law',
    'npa_regulation',
    'npa_head_revision',
)

# --- Связи паспорта ---------------------------------------------------------
LINK_TABLES: Tuple[str, ...] = (
    'npa_author_link',
    'npa_signatory',
    'npa_committee_link',
    'npa_revision_info',
)

# --- Иерархия и контент -----------------------------------------------------
CONTENT_TABLES: Tuple[str, ...] = (
    'npa_item',
    'npa_item_revision',
    'npa_item_head_revision',
    'npa_item_prefix_revision',
    'npa_item_number_revision',
    'npa_paragraph',
)

# --- Примечания и служебное -------------------------------------------------
AUX_TABLES: Tuple[str, ...] = (
    'npa_note_unified',
    'npa_rendered_cache',
)

#: Все таблицы схемы.
ALL_TABLES: Tuple[str, ...] = (
    REFERENCE_TABLES + CORE_TABLES + LINK_TABLES + CONTENT_TABLES + AUX_TABLES
)

#: Порядок вставки при импорте: родители раньше детей (внешние ключи).
INSERT_ORDER: Tuple[str, ...] = (
    'person',
    'convocation',
    'person_post',
    'committees',
    'npa_base',
    'npa_law',
    'npa_regulation',
    'npa_head_revision',
    'npa_author_link',
    'npa_signatory',
    'npa_committee_link',
    'npa_revision_info',
    'npa_item',
    'npa_item_revision',
    'npa_item_head_revision',
    'npa_item_prefix_revision',
    'npa_item_number_revision',
    'npa_paragraph',
    'npa_note_unified',
    'npa_rendered_cache',
)

#: Порядок удаления при переимпорте НПА — обратный порядку вставки.
DELETE_ORDER: Tuple[str, ...] = tuple(reversed(INSERT_ORDER))

# --- ENUM-словари -----------------------------------------------------------
#: ``npa_base.npa_type``
NPA_TYPES: Tuple[str, ...] = ('law', 'regulation')

#: ``npa_item.item_type``
ITEM_TYPES: Tuple[str, ...] = (
    'preamble',
    'chapter',
    'section',
    'article',
    'part',
    'point',
    'subpoint',
    'appendix',
    'nested_appendix',
    'structured_table',
)

#: ``npa_item_revision.mod_type`` (и одноимённые поля других таблиц ревизий)
MOD_TYPES: Tuple[str, ...] = ('add', 'change', 'delete', 'new_redaction')

#: ``npa_item_number_revision.mod_type`` — отдельный набор значений
NUMBER_MOD_TYPES: Tuple[str, ...] = ('correction', 'renumber', 'editorial')

#: ``npa_paragraph.block_type``
BLOCK_TYPES: Tuple[str, ...] = (
    'paragraph',
    'table',
    'child_ref',
    'table_header',
    'table_fragment',
)

#: ``npa_note_unified.target_type``
NOTE_TARGET_TYPES: Tuple[str, ...] = ('npa', 'toc', 'item')

#: Типы, допустимые как дети ``structured_table``.
STRUCTURED_TABLE_CHILD_TYPES: Tuple[str, ...] = ('section', 'point', 'subpoint')

# --- Таблицы ревизий --------------------------------------------------------
#: Таблицы с полями ``valid_from``/``valid_to``/``not_valid``/``modified_by_id``.
REVISION_TABLES: Tuple[str, ...] = (
    'npa_head_revision',
    'npa_item_revision',
    'npa_item_head_revision',
    'npa_item_prefix_revision',
    'npa_item_number_revision',
)

#: Поля периода действия.
VALIDITY_COLUMNS: Tuple[str, str] = ('valid_from', 'valid_to')

#: Единый формат дат в JSON-данных проекта (в БД — нативный DATE).
JSON_DATE_FORMAT = '%d.%m.%Y'

#: Человекочитаемые названия таблиц (для GUI и отчётов).
TABLE_TITLES: Dict[str, str] = {
    'person': 'Физические лица',
    'convocation': 'Созывы',
    'person_post': 'Должности',
    'committees': 'Комитеты',
    'npa_base': 'НПА: паспорт',
    'npa_law': 'НПА: законы',
    'npa_regulation': 'НПА: постановления',
    'npa_head_revision': 'НПА: редакции заголовка',
    'npa_author_link': 'НПА: авторы',
    'npa_signatory': 'НПА: подписанты',
    'npa_committee_link': 'НПА: комитеты',
    'npa_revision_info': 'НПА: изменяющие документы',
    'npa_item': 'Элементы (иерархия)',
    'npa_item_revision': 'Элементы: редакции контента',
    'npa_item_head_revision': 'Элементы: редакции заголовков',
    'npa_item_prefix_revision': 'Элементы: редакции префиксов',
    'npa_item_number_revision': 'Элементы: история номеров',
    'npa_paragraph': 'Блоки контента (абзацы)',
    'npa_note_unified': 'Примечания',
    'npa_rendered_cache': 'Кэш отрендеренного HTML',
}


def read_schema_sql() -> str:
    """Прочитать DDL-скрипт схемы."""
    return SCHEMA_SQL_PATH.read_text(encoding='utf-8')


def is_known_table(name: str) -> bool:
    """True, если таблица описана в схеме проекта."""
    return name in ALL_TABLES


def table_title(name: str) -> str:
    """Человекочитаемое название таблицы (или само имя, если неизвестно)."""
    return TABLE_TITLES.get(name, name)


__all__ = [
    'SCHEMA_SQL_PATH',
    'REFERENCE_TABLES',
    'CORE_TABLES',
    'LINK_TABLES',
    'CONTENT_TABLES',
    'AUX_TABLES',
    'ALL_TABLES',
    'INSERT_ORDER',
    'DELETE_ORDER',
    'NPA_TYPES',
    'ITEM_TYPES',
    'MOD_TYPES',
    'NUMBER_MOD_TYPES',
    'BLOCK_TYPES',
    'NOTE_TARGET_TYPES',
    'STRUCTURED_TABLE_CHILD_TYPES',
    'REVISION_TABLES',
    'VALIDITY_COLUMNS',
    'JSON_DATE_FORMAT',
    'TABLE_TITLES',
    'read_schema_sql',
    'is_known_table',
    'table_title',
]
