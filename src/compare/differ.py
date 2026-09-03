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

Каждая запись несёт точное место различия (``location``): элемент,
его название и номер абзаца внутри элемента вплоть до нумерации блока
(«часть 2», «пункт 1», «подпункт «а»»), — одной статьи недостаточно.

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

#: Нумерация внутри элемента: «1. …» / «5.1. …» — часть, «1) …» / «3.1) …» —
#: пункт, «а) …» — подпункт. Используется для точного места различия.
_PART_RE = re.compile(r'^(\d{1,3}(?:\.\d+)*)\.\s+')
_POINT_RE = re.compile(r'^(\d{1,3}(?:\.\d+)*)\)\s*')
_SUBPOINT_RE = re.compile(r'^([а-яё])\)\s*', re.IGNORECASE)
#: Служебный номер в заголовке элемента («10. Полномочия…» → «Полномочия…»).
_TITLE_NUM_RE = re.compile(r'^\d{1,3}(?:\.\d+)*[.\s]+')


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

    # Точное место различия внутри элемента (для отчёта).
    para_no: int = 0         # номер абзаца (блока) внутри элемента, с 1
    item_label: str = ''     # «часть 2», «пункт 1», «подпункт «а»» — если нумерован
    element_title: str = ''  # название элемента (статьи) без служебного номера
    # Контекст фрагмента в обоих документах (заполняется для различий
    # оформления, чтобы в отчёте было видно, где именно символ отличается).
    context_old: str = ''
    context_new: str = ''

    # Поля, заполняемые агент-классификатором и резолвером базы.
    reason: str = ''
    explanation: str = ''
    source_npa: str = ''
    source_item_id: str = ''
    change_text: str = ''
    original_text: str = ''

    @property
    def location(self) -> str:
        """Человекочитаемое место различия с точностью до абзаца.

        Например: «статья 10 «Полномочия Уполномоченного», абзац 3
        (часть 2)». Для записей, восстановленных из старых чекпойнтов,
        абзац может быть неизвестен — возвращается только путь элемента.
        """
        head = self.path or '—'
        if self.element_title:
            head = f'{head} «{self.element_title}»'
        if not self.para_no:
            return head
        label = f'{head}, абзац {self.para_no}'
        if self.item_label:
            label = f'{label} ({self.item_label})'
        return label


def _clean_title(title: str) -> str:
    """Название элемента без служебного номера («10. Полномочия…»)."""
    title = ' '.join((title or '').split())
    if not title:
        return ''
    cleaned = _TITLE_NUM_RE.sub('', title)
    return cleaned or title


def _block_index(el: Element, pos: int) -> int:
    """Индекс блока (0-based), содержащего позицию ``pos`` текста элемента.

    Блоки в ``el.text`` разделены переводом строки, поэтому смещение блока
    равно сумме длин предыдущих блоков плюс по одному символу на разделитель.
    """
    if not el.blocks:
        return 0
    start = 0
    last = len(el.blocks) - 1
    for idx, blk in enumerate(el.blocks):
        end = start + len(blk.text)
        if pos < end or idx == last:
            return idx
        start = end + 1
    return 0


def _locate(el: Element, pos: int) -> Tuple[int, str]:
    """Определить абзац и нумерацию блока для позиции ``pos`` в ``el.text``.

    Возвращает ``(номер абзаца с 1, метка нумерации)``; метка пуста для
    ненумерованного абзаца.
    """
    if not el.blocks:
        return 0, ''
    text_len = len(el.text)
    if text_len and pos >= text_len:
        pos = text_len - 1
    idx = _block_index(el, pos)
    blk_text = (el.blocks[idx].text or '').lstrip()
    m = _PART_RE.match(blk_text)
    if m:
        return idx + 1, f'часть {m.group(1)}'
    m = _POINT_RE.match(blk_text)
    if m:
        return idx + 1, f'пункт {m.group(1)}'
    m = _SUBPOINT_RE.match(blk_text)
    if m:
        return idx + 1, f'подпункт «{m.group(1).lower()}»'
    return idx + 1, ''


def _make_record(
    kind: str,
    element: Element,
    old: str,
    new: str,
    para_no: int = 0,
    item_label: str = '',
) -> DiffRecord:
    return DiffRecord(
        path=element.path_text,
        path_key=element.key,
        kind=kind,
        old=clip_fragment(old),
        new=clip_fragment(new),
        count=max(len(old), len(new)),
        para_no=para_no,
        item_label=item_label,
        element_title=_clean_title(element.title),
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
        # Место различия привязываем к документу, где начинается новый
        # текст: для add — проект, для change/remove — правовая система.
        # Якорь по началу фрагмента корректен и для вставок в конце абзаца
        # (например, добавленная точка остаётся в предыдущем абзаце).
        if kind == 'add':
            loc_el, loc_pos = ours_el, i1
        else:
            loc_el, loc_pos = theirs_el, j1
        para_no, item_label = _locate(loc_el, loc_pos)
        if is_cosmetic_diff(old, new):
            # Регистр/пунктуация/пробелы — оформление, в основной список не
            # включаем; в отчёте каждый случай показывается с точным местом
            # и контекстом из обоих документов.
            record = _make_record(kind, ours_el, old, new, para_no, item_label)
            record.context_old = _with_context(a, i1, i2)
            record.context_new = _with_context(b, j1, j2)
            cosmetics.append(record)
            stats['cosmetic'] += 1
            continue
        if kind == 'change':
            # Короткий фрагмент («ов» → «ы») нечитабелен: добавляем контекст.
            old = _with_context(a, i1, i2)
            new = _with_context(b, j1, j2)
        records.append(_make_record(kind, ours_el, old, new, para_no, item_label))
        stats[kind] += 1


def _record_order(rec: DiffRecord) -> tuple:
    """Ключ сортировки в порядке документа: преамбула, статьи по номеру,
    затем абзац и тип различия (стабильный, читаемый отчёт)."""
    pk = rec.path_key or ()
    token, number = pk[0] if pk else ('', '')
    rank = 0 if token == 'preamble' else 1
    try:
        num = int(number)
    except (TypeError, ValueError):
        num = 10 ** 9
    return (rank, num, rec.para_no or 10 ** 9, rec.kind, rec.path)


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

    # сортировка для стабильного отчёта: порядок документа
    records.sort(key=_record_order)
    cosmetics.sort(key=_record_order)
    return records, dict(stats), cosmetics