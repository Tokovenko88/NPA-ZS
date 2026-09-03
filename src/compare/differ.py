"""Посимвольное сравнение элементов двух редакций НПА.

Для каждой пары структурных элементов выполняется сравнение через
``difflib.SequenceMatcher`` на уровне символов (юридический текст важен
посимвольно). Расхождения оформляются как :class:`DiffRecord`:

* ``change`` — замена фрагмента;
* ``add`` — фрагмент присутствует только в документе проекта;
* ``remove`` — фрагмент присутствует только в документе правовой системы.

Различия только в оформлении (регистр, пунктуация, пробелы, е/ё) не
включаются в основной список — они выносятся в отдельный список
«косметических» записей (:func:`is_cosmetic_diff`), чтобы отчёт показывал
изменения текста по существу, а не шум оформления.

Элементы, найденные только в одном документе, попадают в ``add``/``remove``
с полным текстом элемента.
"""

from __future__ import annotations

import difflib
import re
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Tuple

from .tree import Element

__all__ = [
    'DiffRecord',
    'clip_fragment',
    'compare_elements',
    'is_cosmetic_diff',
]

#: Максимальная длина фрагмента в отчёте.
_MAX_FRAG = 160


def clip_fragment(s: str, limit: int = _MAX_FRAG) -> str:
    """Обрезать фрагмент с многоточием, убирая переносы строк."""
    s = (s or '').replace('\n', ' ')
    s = ' '.join(s.split())
    if len(s) <= limit:
        return s
    return s[:limit] + '…'


#: «Значимая» часть фрагмента: буквы и цифры. Регистр, пунктуация,
#: пробелы и е/ё — оформление, которое у проекта и правовой системы
#: различается само по себе и содержание НПА не меняет.
_SIGNIFICANT_RE = re.compile(r'[^0-9a-zа-яё]+', re.IGNORECASE)


def is_cosmetic_diff(old: str, new: str) -> bool:
    """Различие только в оформлении (регистр, пунктуация, пробелы, е/ё)?

    Такие расхождения не включаются в основной список: они засоряют отчёт
    (запятые, кавычки, ЗАГЛАВНЫЕ заголовки) и не являются изменением
    текста по существу.
    """
    old_sig = _SIGNIFICANT_RE.sub('', (old or '').lower()).replace('ё', 'е')
    new_sig = _SIGNIFICANT_RE.sub('', (new or '').lower()).replace('ё', 'е')
    return old_sig == new_sig


def _with_context(source: str, start: int, end: int, span: int = 45) -> str:
    """Фрагмент ``source[start:end]`` с окружением ±``span`` символов.

    Короткие фрагменты замен («ов» → «ы») нечитабельны без контекста —
    в отчёт и промпт агента уходит фрагмент вместе с окружением;
    обрезанные края помечаются многоточием.
    """
    ctx_start = max(0, start - span)
    ctx_end = min(len(source), end + span)
    out = source[ctx_start:ctx_end]
    if ctx_start > 0:
        out = '…' + out
    if ctx_end < len(source):
        out = out + '…'
    return out


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


def _classify_whole(
    kind: str,
    element: Element,
    old: str,
    new: str,
    records: List[DiffRecord],
    cosmetics: List[DiffRecord],
    stats: Counter,
) -> None:
    """Целый элемент есть только в одном документе: add/remove-запись."""
    record = _make_record(kind, element, old, new)
    if is_cosmetic_diff(old, new):
        # «Элемент» без значимого текста (пустые блоки, только пунктуация).
        cosmetics.append(record)
        stats['cosmetic'] += 1
        return
    records.append(record)
    stats[kind] += 1


def _diff_match(records: List[DiffRecord], cosmetics: List[DiffRecord],
                stats: Counter, ours_el: Element, theirs_el: Element) -> None:
    a = ours_el.text or ''
    b = theirs_el.text or ''
    if a == b:
        return
    # autojunk=False: иначе difflib объявляет «мусором» частые символы
    # (запятые, пробелы) и дробит одно мелкое различие на несколько
    # крупных ложных фрагментов.
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            continue
        old = a[i1:i2]
        new = b[j1:j2]
        # Различие из одних пробелов/переносов строк (склейка блоков в элемент)
        # — не содержимое, пропускаем.
        if not (old or '').strip() and not (new or '').strip():
            continue
        kind = {'delete': 'add', 'insert': 'remove'}.get(tag, 'change')
        # delete: фрагмент есть только в a (проект)   -> add
        # insert: фрагмент есть только в b (правовая система) -> remove
        if is_cosmetic_diff(old, new):
            # Регистр/пунктуация/пробелы — оформление, в разбор не включаем.
            cosmetics.append(_make_record(kind, ours_el, old, new))
            stats['cosmetic'] += 1
            continue
        if kind == 'change':
            # Короткий фрагмент («ов» → «ы») нечитабелен: добавляем контекст.
            old = _with_context(a, i1, i2)
            new = _with_context(b, j1, j2)
        records.append(_make_record(kind, ours_el, old, new))
        stats[kind] += 1


def compare_elements(
    ours: List[Element], theirs: List[Element]
) -> Tuple[List[DiffRecord], Dict[str, int], List[DiffRecord]]:
    """Сравнить два списка элементов.

    Возвращает ``(записи, счётчики, косметические записи)``. В ``записи``
    попадают только содержательные различия; различия оформления
    (регистр, пунктуация, пробелы, е/ё) выносятся в ``косметические``
    и учитываются в ``stats['cosmetic']``.
    """
    records: List[DiffRecord] = []
    cosmetics: List[DiffRecord] = []
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
            _classify_whole(
                'add', oel, oel.text or oel.title, '', records, cosmetics, stats
            )
            continue
        tel = matches[0]
        used_theirs.add(id(tel))
        _diff_match(records, cosmetics, stats, oel, tel)

    for tel in theirs:
        if id(tel) in used_theirs:
            continue
        _classify_whole(
            'remove', tel, '', tel.text or tel.title, records, cosmetics, stats
        )

    # сортировка для стабильного отчёта
    records.sort(key=lambda r: (r.path, r.kind))
    return records, dict(stats), cosmetics