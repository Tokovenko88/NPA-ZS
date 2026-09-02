"""Доступ к базе НПА (JSON) для подтягивания текстов изменяющих документов.

База хранится в ``data/base/law`` / ``data/base/resolition`` и в рабочей базе
``<родитель проекта>/Base`` (см :mod:`npazs.constants`). Каждый изменяющий
НПА лежит под номером (файл ``<номер>.json`` или ``<номер>_ответ.json``),
структура документа — иерирrхие ``npa_items_revision`` / ``item_children``.
Примечания со ссылками на элемент изменяющего НПА содержат ``source_item_id``
(нотация «ссылка через # на элемент»), что позволяет достать конкретный
структурный элемент и его текст без полного разбора документа.
"""

from __future__ import annotations

import json
import re
from functools import cache, lru_cache
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover
    BeautifulSoup = None  # type: ignore[assignment]

from npazs.constants import (
    BASE_LAW_DIR,
    BASE_RESOLUTION_DIR,
    PRODUCTION_BASE_LAW_DIR,
    PRODUCTION_BASE_RESOLUTION_DIR,
)

from .tree import _RU_TOKEN

__all__ = [
    'base_search_dirs',
    'clean_number',
    'extract_change_text',
    'find_item_in_tree',
    'find_npa_document',
    'find_npa_files',
    'get_element_text',
    'get_full_document_text',
    'get_original_element_text',
    'load_npa_document',
]


def clean_number(number: str) -> str:
    """Очистить номер НПА до цифр (для сопоставления)."""
    if not number:
        return ''
    return re.sub(r'\D', '', str(number))


@cache
def base_search_dirs() -> Tuple[str, ...]:
    """Каталоги базы JSON НПА (в порядке приоритета)."""
    dirs: List[str] = []
    for d in (BASE_LAW_DIR, BASE_RESOLUTION_DIR,
              PRODUCTION_BASE_LAW_DIR, PRODUCTION_BASE_RESOLUTION_DIR):
        try:
            if d and Path(d).is_dir():
                dirs.append(str(d))
        except OSError:
            continue
    return tuple(dirs)


@lru_cache(maxsize=256)
def load_npa_document(path: str) -> Optional[dict]:
    """Загрузить JSON НПА (с кэшем)."""
    p = Path(path)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _iter_base_files() -> Iterable[Path]:
    seen = set()
    for base in base_search_dirs():
        for path in Path(base).glob('**/*.json'):
            if path in seen:
                continue
            seen.add(path)
            yield path


def find_npa_files(
    number: str, *, skip_generated: bool = True
) -> List[Tuple[str, dict]]:
    """Найти все JSON-документы с номером ``number``.

    ``skip_generated`` исключает служебные артефакты ревизионного пайплайна
    (``*_izm_*``, ``FAILED_*``, ``*_work.json``, ``*_ответ.json``).
    """
    target = clean_number(number)
    if not target:
        return []
    results: List[Tuple[str, dict]] = []
    exact: List[Tuple[str, dict]] = []
    for path in _iter_base_files():
        name = path.name.lower()
        if skip_generated and any(
            marker in name for marker in ('_izm_', 'failed_', '_work.', '_ответ', '_otvet')
        ):
            continue
        doc = load_npa_document(str(path))
        if doc is None:
            continue
        doc_clean = clean_number(doc.get('npa_number', ''))
        if not doc_clean:
            continue
        if doc_clean == target:
            exact.append((str(path), doc))
        elif doc_clean.startswith(target) or target.startswith(doc_clean):
            # «41-ЗС» ↔ «41-ЗС/1038»: номер Севастополя может храниться
            # в базе как в краткой, так и в полной (с регистрационным
            # номером) форме — считаем совпадением префикс цифр.
            results.append((str(path), doc))
    # Точные совпадения — первыми (find_npa_document берёт первый).
    return exact + results


def find_npa_document(number: str) -> Optional[dict]:
    """Найти первый документ с номером (без служебных артефактов)."""
    results = find_npa_files(number)
    if not results:
        return None
    # приоритет файлу, имя которого начинается с чистого номера
    clean = clean_number(number)
    for path, doc in results:
        if Path(path).stem.split('_')[0] == clean:
            return doc
    return results[0][1]


# ---------------------------------------------------------------------------
# Поиск элемента в дереве НПА
# ---------------------------------------------------------------------------

def _norm_json_number(number: str) -> str:
    number = (number or '').strip().lower()
    return re.sub(r'\s+', '', number)


def find_item_in_tree(doc: dict, path_key: tuple) -> Optional[dict]:
    """Найти структурный элемент по каноническому ключу пути.

    ``path_key`` — tuple из (тип_ru, номер) в той же форме, что выдаёт
    :func:`npazs.compare.tree.path_key`.
    """
    current_items = doc.get('npa_items_revision', []) or []
    found: Optional[dict] = None
    for token_en, number in path_key:
        if not current_items:
            return None
        found = None
        for item in current_items:
            item_type = str(item.get('item_type', '')).lower()
            item_number = _norm_json_number(item.get('item_number', ''))
            if item_type == token_en and item_number == _norm_json_number(number):
                found = item
                break
        if found is None:
            return None
        current_items = found.get('item_children', []) or []
    return found


def _walk_items(items: List[dict]) -> Iterable[dict]:
    for item in items:
        yield item
        yield from _walk_items(item.get('item_children', []) or [])


def _html_to_text(html: str) -> str:
    if not html:
        return ''
    if BeautifulSoup is not None:
        return BeautifulSoup(html, 'html.parser').get_text(' ', strip=True)
    return re.sub(r'<[^>]+>', ' ', html)


def get_element_text(item: dict) -> str:
    """Текст структурного элемента: заголовок + абзацы последней редакции."""
    parts: List[str] = []

    head_revs = item.get('head_revisions') or []
    if head_revs:
        head = head_revs[-1].get('head_text', '')
        if head:
            parts.append(_html_to_text(head))

    revisions = item.get('revisions') or []
    if revisions:
        body = revisions[-1].get('body') or []
        for block in body:
            btype = block.get('type', '')
            if btype == 'child_ref':
                continue
            html = block.get('html_text', '')
            if html:
                text = _html_to_text(html)
                if text.strip():
                    parts.append(text.strip())
    return '\n'.join(parts)


def _ru_type(item_type: str) -> str:
    inverse = {v: k for k, v in _RU_TOKEN.items()}
    return inverse.get(item_type.lower(), item_type)


def _attach_parents(doc: dict, item: dict) -> dict:
    """Прикрепить ссылки ``_parent`` для построения пути элемента."""
    def walk(items: List[dict], parent: Optional[dict] = None) -> None:
        for child in items:
            child['_parent'] = parent
            walk(child.get('item_children', []) or [], child)
    walk(doc.get('npa_items_revision', []) or [])
    return item


def item_human_path(item: dict) -> str:
    """Человекочитаемый путь элемента (например, «статья 2 -> часть 1.4»)."""
    segments = []
    cur: Optional[dict] = item
    while cur is not None:
        label = f'{_ru_type(cur.get("item_type", ""))} {cur.get("item_number", "")}'.strip()
        segments.append(label)
        cur = cur.get('_parent')
    return ' -> '.join(reversed(segments))


def parse_path_description(description: str) -> Optional[tuple]:
    """Разобрать строку «статья 2 -> часть 1.4» в кортеж (тип, номер)."""
    if not description:
        return None
    result = []
    parts = re.split(r'->|,', description)
    for part in parts:
        part = part.strip()
        m = re.match(
            r'^(статья|глава|раздел|часть|приложение|подпункт|пункт)\s*\(?([\dIVXLC][\w.\-()]*)?',
            part,
            re.IGNORECASE,
        )
        if not m:
            return None
        token_ru = m.group(1).lower()
        number = (m.group(2) or '').strip().strip('.').strip()
        token_en = _RU_TOKEN.get(token_ru, token_ru)
        result.append((token_en, number))
    return tuple(result) if result else None


# ---------------------------------------------------------------------------
# Главные функции для агента
# ---------------------------------------------------------------------------

def extract_change_text(
    change_number: str,
    path_key: Optional[tuple] = None,
    item_id: Optional[str] = None,
) -> dict:
    """Достать текст конкретного изменения из базы JSON.

    Возвращает словарь::

        {
            'npa_number': ..., 'npa_id': ..., 'item_id': ...,
            'item_type': ..., 'item_number': ..., 'path': ..., 'text': ...,
            'full': False,
        }

    Если элемент не найден (или путь/item_id не задан) — возвращает
    ``full=True`` с полным текстом изменяющего НПА в ``text``.
    """
    doc = find_npa_document(change_number)
    if doc is None:
        return {
            'npa_number': change_number,
            'item_id': '', 'item_type': '', 'item_number': '',
            'path': '', 'text': '', 'full': True,
            'error': 'НПА не найден в базе',
        }

    item: Optional[dict] = None
    if item_id:
        item = next(
            (
                it for it in _walk_items(doc.get('npa_items_revision', []) or [])
                if it.get('item_id') == item_id
            ),
            None,
        )
    elif path_key:
        item = find_item_in_tree(doc, path_key)

    if item is None:
        return {
            'npa_number': doc.get('npa_number', change_number),
            'npa_id': doc.get('npa_id', ''),
            'item_id': '',
            'item_type': '', 'item_number': '',
            'path': '',
            'text': get_full_document_text(doc),
            'full': True,
        }

    return {
        'npa_number': doc.get('npa_number', change_number),
        'npa_id': doc.get('npa_id', ''),
        'item_id': item.get('item_id', ''),
        'item_type': item.get('item_type', ''),
        'item_number': item.get('item_number', ''),
        'path': item_human_path(_attach_parents(doc, item)),
        'text': get_element_text(item),
        'full': False,
    }


def get_full_document_text(doc: dict) -> str:
    """Полный текст НПА (все элементы подряд, для ручного поиска)."""
    parts = []
    for item in _walk_items(doc.get('npa_items_revision', []) or []):
        text = get_element_text(item)
        if text.strip():
            parts.append(text.strip())
    return '\n'.join(parts)


def get_original_element_text(target_number: str, path_key: tuple) -> str:
    """Текст того же элемента в исходной (базовой) редакции НПА.

    Используется, когда агент считает, что различие не связано с внесением
    изменений: сравниваем оба документа с оригиналом из базы.
    """
    doc = find_npa_document(target_number)
    if doc is None:
        return ''
    item = find_item_in_tree(doc, path_key)
    if item is None:
        return ''
    return get_element_text(item)