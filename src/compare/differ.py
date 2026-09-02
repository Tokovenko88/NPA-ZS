"""Посимвольное сравнение элементов двух редакций НПА.

Для каждой пары структурных элементов выполняется сравнение через
``difflib.SequenceMatcher`` на уровне символов (юридический текст важен
посимвольно). Расхождения оформляются как :class:`DiffRecord`:

* ``change`` — замена фрагмента;
* ``add`` — фрагмент присутствует только в документе проекта;
* ``remove`` — фрагмент присутствует только в документе правовой системы.

Элементы, найденные только в одном документе, попадают в ``add``/``remove``
с полным текстом элемента.
"""

from __future__ import annotations

import difflib
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Tuple

from .tree import Element

__all__ = ['DiffRecord', 'clip_fragment', 'compare_elements']

#: Максимальная длина фрагмента в отчёте.
_MAX_FRAG = 160


def clip_fragment(s: str, limit: int = _MAX_FRAG) -> str:
    """Обрезать фрагмент с многоточием, убирая переносы строк."""
    s = (s or '').replace('\n', ' ')
    s = ' '.join(s.split())
    if len(s) <= limit:
        return s
    return s[:limit] + '…'


@dataclass
class DiffRecord:
    """Одно различие между документами."""

    path: str
    path_key: tuple
    kind: str          # change | add | remove
    old: str = ''
    new: str = ''
    count: int = 0

    # Поля, заполняемые агент-классификатором и резолвером базы.
    reason: str = ''
    explanation: str = ''
    source_npa: str = ''
    source_item_id: str = ''
    change_text: str = ''
    original_text: str = ''


def _make_record(kind: str, element: Element, old: str, new: str) -> DiffRecord:
    return DiffRecord(
        path=element.path_text,
        path_key=element.key,
        kind=kind,
        old=clip_fragment(old),
        new=clip_fragment(new),
        count=max(len(old), len(new)),
    )


def _diff_match(records: List[DiffRecord], stats: Counter,
                ours_el: Element, theirs_el: Element) -> None:
    a = ours_el.text or ''
    b = theirs_el.text or ''
    if a == b:
        return
    sm = difflib.SequenceMatcher(None, a, b)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            continue
        old = a[i1:i2]
        new = b[j1:j2]
        kind = {'delete': 'add', 'insert': 'remove'}.get(tag, 'change')
        # delete: фрагмент есть только в a (проект)   -> add
        # insert: фрагмент есть только в b (правовая система) -> remove
        record = _make_record(kind, ours_el, old, new)
        records.append(record)
        stats[kind] += 1


def compare_elements(
    ours: List[Element], theirs: List[Element]
) -> Tuple[List[DiffRecord], Dict[str, int]]:
    """Сравнить два списка элементов. Возвращает (записи, счётчики)."""
    records: List[DiffRecord] = []
    stats: Counter = Counter()

    ours_map: Dict[tuple, List[Element]] = {}
    theirs_map: Dict[tuple, List[Element]] = {}
    for el in ours:
        ours_map.setdefault(el.key, []).append(el)
    for el in theirs:
        theirs_map.setdefault(el.key, []).append(el)

    used_theirs = set()

    for oel in ours:
        matches = theirs_map.get(oel.key, [])
        if not matches:
            records.append(_make_record('add', oel, oel.text or oel.title, ''))
            stats['add'] += 1
            continue
        tel = matches[0]
        used_theirs.add(id(tel))
        _diff_match(records, stats, oel, tel)

    for tel in theirs:
        if id(tel) in used_theirs:
            continue
        records.append(_make_record('remove', tel, '', tel.text or tel.title))
        stats['remove'] += 1

    # сортировка для стабильного отчёта
    records.sort(key=lambda r: (r.path, r.kind))
    return records, dict(stats)