"""Формирование отчёта о сравнении документов в формате Markdown.

Отчёт строится по строгим шаблонам и состоит из разделов:

1. «Примечания и даты вступления в силу» — наличие примечаний, их привязка
   к изменяющим НПА и соответствие дат (без сравнения стиля оформления);
2. «Расхождения текста» — посимвольные различия по каждому структурному
   элементу с полным путём, причинами и текстами изменений из базы;
3. «Итоги и рекомендации» — сводка расхождений и замечания конвертеров.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .agent_compare import REASON_LABELS
from .differ import DiffRecord
from .normalizer import Note

__all__ = [
    'NoteCompRecord',
    'build_diffs_report',
    'build_notes_report',
    'build_report',
]


@dataclass
class NoteCompRecord:
    """Результат сравнения одного примечания."""

    text: str = ''
    npa_numbers: List[str] = field(default_factory=list)
    date_ours: str = ''
    date_theirs: str = ''
    dates_ours: List[str] = field(default_factory=list)
    dates_theirs: List[str] = field(default_factory=list)
    count: int = 1
    status: str = ''

    @property
    def number_label(self) -> str:
        return '; '.join(self.npa_numbers) if self.npa_numbers else '—'


def _match_note(note: Note, others: List[Note]) -> Optional[Note]:
    """Найти примечание-«двойник» по номерам НПА, датам или тексту."""
    for other in others:
        for num in note.npa_numbers:
            if num in other.npa_numbers:
                return other
    for other in others:
        if set(note.dates) & set(other.dates):
            return other
    for other in others:
        if (note.text or '') == (other.text or '') and note.text:
            return other
    return None


def _norm_date(date: str) -> str:
    parts = str(date or '').split('.')
    if len(parts) == 3:
        return f'{parts[2]}-{parts[1]}-{parts[0]}'
    return str(date or '')


def _group_notes(notes: List[Note]) -> List[Tuple[List[Note], int]]:
    """Сгруппировать примечания по (НПА, даты, дата вступления).

    Возвращает список (представители группы, количество) — одинаковые пометки
    («Последние изменения вступили в силу с …» выводится для каждого пункта)
    схлопываются в одну строку с количеством вхождений.
    """
    groups: dict = {}
    for n in notes:
        key = (
            tuple(sorted(set(n.npa_numbers))),
            tuple(sorted(set(n.dates), key=_norm_date)),
            n.valid_from,
        )
        groups.setdefault(key, []).append(n)
    out = []
    for group in groups.values():
        out.append((group, len(group)))
    return out


def build_notes_report(
    notes_ours: List[Note], notes_theirs: List[Note]
) -> Tuple[List[NoteCompRecord], str]:
    """Сравнить примечания двух документов.

    Возвращает (записи сравнения, markdown-таблица). Пометки без дат и
    номеров НПА (пустые «В редакции —», «С изменениями:») в таблицу
    не выводятся — они уже исключены из сравнения текста. Повторяющиеся
    пометки группируются («вступили в силу с …» у каждого пункта) и
    выводятся одной строкой с количеством вхождений.
    """
    notes_ours = [n for n in notes_ours if n.npa_numbers or n.dates]
    notes_theirs = [n for n in notes_theirs if n.npa_numbers or n.dates]
    ours_groups = _group_notes(notes_ours)
    theirs_groups = _group_notes(notes_theirs)

    records: List[NoteCompRecord] = []
    theirs_used = [False] * len(theirs_groups)

    def _dates(note: Note) -> List[str]:
        return list(note.dates) or ([note.valid_from] if note.valid_from else [])

    for ogroup, ocount in ours_groups:
        note = ogroup[0]
        match_idx = None
        for idx, (tgroup, _tcount) in enumerate(theirs_groups):
            if theirs_used[idx]:
                continue
            if _match_note(note, [tgroup[0]]):
                match_idx = idx
                break
        if match_idx is None:
            records.append(
                NoteCompRecord(
                    text=note.text,
                    npa_numbers=note.npa_numbers,
                    date_ours=note.valid_from,
                    dates_ours=_dates(note),
                    count=ocount,
                    status='Только в документе проекта',
                )
            )
        else:
            theirs_used[match_idx] = True
            other = theirs_groups[match_idx][0][0]
            date_eq = _norm_date(note.valid_from) == _norm_date(other.valid_from)
            if date_eq:
                status = 'Совпадает'
            else:
                status = 'Даты различаются'
            records.append(
                NoteCompRecord(
                    text=note.text,
                    npa_numbers=note.npa_numbers,
                    date_ours=note.valid_from,
                    date_theirs=other.valid_from,
                    dates_ours=_dates(note),
                    dates_theirs=_dates(other),
                    count=max(ocount, theirs_groups[match_idx][1]),
                    status=status,
                )
            )

    for idx, (tgroup, tcount) in enumerate(theirs_groups):
        if theirs_used[idx]:
            continue
        other = tgroup[0]
        records.append(
            NoteCompRecord(
                text=other.text,
                npa_numbers=other.npa_numbers,
                date_theirs=other.valid_from,
                dates_theirs=_dates(other),
                count=tcount,
                status='Только в документе правовой системы',
            )
        )

    lines = [
        '| № | Примечание | НПА | Даты (проект) | Даты (прав. система) | Кол-во | Статус |',
        '|---|---|---|---|---|---|---|',
    ]
    for i, rec in enumerate(records, start=1):
        text = (rec.text or '').replace('|', '\\|')
        if len(text) > 90:
            text = text[:87] + '…'
        ours_dates = '; '.join(rec.dates_ours) if rec.dates_ours else '—'
        theirs_dates = '; '.join(rec.dates_theirs) if rec.dates_theirs else '—'
        lines.append(
            f'| {i} | {text} | {rec.number_label} | {ours_dates} | '
            f'{theirs_dates} | {rec.count} | {rec.status} |'
        )
    return records, '\n'.join(lines)


def _quote_md(text: str, limit: int = 400) -> str:
    text = (text or '').replace('\n', ' ')
    text = ' '.join(text.split())
    if len(text) > limit:
        text = text[:limit] + '…'
    return text or '—'


def _cosmetics_section(cosmetics: List[DiffRecord]) -> str:
    """Компактная сводка различий оформления (регистр/пунктуация/пробелы).

    Такие различия не требуют разбора и классификации — выводятся одной
    таблицей «элемент → количество → пример», чтобы не засорять основной
    список расхождений.
    """
    lines = [
        '',
        '### Мелкие различия оформления (в разбор не включены)',
        '',
        'Различия только в оформлении: регистр, пунктуация, пробелы, е/ё. '
        'Содержание текста не меняют, классификация не требуется.',
        '',
        '| Элемент | Кол-во | Пример |',
        '|---|---|---|',
    ]
    by_path: Dict[str, List[DiffRecord]] = {}
    order: List[str] = []
    for rec in cosmetics:
        if rec.path not in by_path:
            by_path[rec.path] = []
            order.append(rec.path)
        by_path[rec.path].append(rec)
    for path in order:
        recs = by_path[path]
        sample = next(
            (
                r for r in recs
                if (r.old or '').strip() or (r.new or '').strip()
            ),
            recs[0],
        )
        old = _quote_md(sample.old, 70)
        new = _quote_md(sample.new, 70)
        lines.append(f'| {path} | {len(recs)} | {old} → {new} |')
    return '\n'.join(lines)


def build_diffs_report(
    diffs: List[DiffRecord],
    mode: str = 'mechanical',
    cosmetics: Optional[List[DiffRecord]] = None,
) -> str:
    """Сформировать раздел «Расхождения текста» по записям диффа.

    ``cosmetics`` — различия только в оформлении (см.
    :func:`npazs.compare.differ.is_cosmetic_diff`); при наличии выводятся
    компактной таблицей в конце раздела.
    """
    lines = ['## 2. Расхождения текста', '']
    if not diffs:
        lines.append('_Расхождений не обнаружено._')
        lines.append('')
        return '\n'.join(lines)

    for idx, diff in enumerate(diffs, start=1):
        kind_label = {
            'change': 'Замена фрагмента',
            'add': 'Есть только в документе проекта',
            'remove': 'Есть только в документе правовой системы',
        }.get(diff.kind, diff.kind)

        lines.append(f'### 2.{idx}. {diff.path}')
        lines.append('')
        lines.append(f'**Тип различия:** {kind_label}')
        if diff.reason:
            lines.append(f'**Причина:** {REASON_LABELS.get(diff.reason, diff.reason)}')
        if diff.explanation:
            lines.append(f'**Объяснение агента:** {_quote_md(diff.explanation, 600)}')
        if diff.old:
            lines.append('')
            lines.append('> ❌ **Документ проекта:**')
            lines.append('>')
            lines.append(f'> {_quote_md(diff.old)}')
        if diff.new:
            lines.append('')
            lines.append('> ✅ **Документ правовой системы:**')
            lines.append('>')
            lines.append(f'> {_quote_md(diff.new)}')
        if diff.source_npa:
            lines.append('')
            lines.append(f'**Изменяющий НПА:** № {diff.source_npa}')
            if diff.source_item_id:
                lines.append(f'**Элемент изменяющего НПА:** `{diff.source_item_id}`')
        if diff.change_text:
            lines.append('')
            lines.append('**Текст изменения из базы:**')
            lines.append('')
            lines.append(f'```{_quote_md(diff.change_text, 1000)}```')
        if diff.original_text:
            lines.append('')
            lines.append('**Текст элемента в исходной (базовой) редакции НПА:**')
            lines.append('')
            lines.append(f'```{_quote_md(diff.original_text, 1000)}```')
        lines.append('')
        lines.append('---')
        lines.append('')

    if cosmetics:
        lines.append(_cosmetics_section(cosmetics))

    return '\n'.join(lines)


def build_report(
    *,
    ours_path: str,
    theirs_path: str,
    ours_fmt: str,
    theirs_fmt: str,
    mode: str,
    target_number: str = '',
    notes_records: List[NoteCompRecord],
    notes_table: str,
    diffs: List[DiffRecord],
    diff_stats: Dict[str, int],
    cosmetics: Optional[List[DiffRecord]] = None,
    warnings: List[str],
    started_at: Optional[datetime] = None,
) -> str:
    """Собрать полный Markdown-отчёт о сравнении."""
    started_at = started_at or datetime.now()
    lines = [
        '# Отчёт о сравнении редакций НПА',
        '',
        f'_Сформировано: {started_at.strftime("%d.%m.%Y %H:%M:%S")}_',
        '',
        '## Исходные данные',
        '',
        f'- Документ проекта: `{ours_path}` (формат: {ours_fmt})',
        f'- Документ правовой системы: `{theirs_path}` (формат: {theirs_fmt})',
        f'- Целевой НПА: `{target_number or "не определён"}`',
        f'- Режим сравнения: `{"агентный" if mode == "agent" else "механический"}`',
        '',
    ]
    if warnings:
        lines.append('**Замечания конвертеров:**')
        lines.append('')
        for w in warnings:
            lines.append(f'- {w}')
        lines.append('')

    lines.append('## 1. Примечания и даты вступления в силу')
    lines.append('')
    lines.append(
        '_Сравниваются только наличие примечания, его привязка к изменяющему '
        'НПА и дата вступления в силу; расположение и оформление не '
        'учитываются._'
    )
    lines.append('')
    lines.append(notes_table)
    lines.append('')

    lines.append(build_diffs_report(diffs, mode=mode, cosmetics=cosmetics))

    lines.append('## 3. Итоги и рекомендации')
    lines.append('')
    total = sum(v for k, v in diff_stats.items() if k != 'cosmetic')
    lines.append(f'- Расхождений текста обнаружено: **{total}**')
    lines.append(f'  - изменений (замена): {diff_stats.get("change", 0)}')
    lines.append(f'  - добавлений (только в проекте): {diff_stats.get("add", 0)}')
    lines.append(f'  - удалений (только в правовой системе): {diff_stats.get("remove", 0)}')
    if diff_stats.get('cosmetic'):
        lines.append(
            f'  - различий оформления (регистр/пунктуация, справочно): '
            f'{diff_stats["cosmetic"]}'
        )
    lines.append('')
    by_reason: Dict[str, int] = {}
    for d in diffs:
        why = d.reason or 'unclear'
        by_reason[why] = by_reason.get(why, 0) + 1
    lines.append('**Классификация расхождений (по причине):**')
    lines.append('')
    lines.append('| Причина | Количество |')
    lines.append('|---|---|')
    for reas in (
        'amendment', 'implementation_gap', 'original_edition',
        'technical_correction', 'formatting', 'unclear',
    ):
        if by_reason.get(reas):
            lines.append(f'| {REASON_LABELS.get(reas, reas)} | {by_reason[reas]} |')
    lines.append('')
    lines.append(
        '_Отчёт построен автоматически. Агентная классификация применяется '
        'в режиме ``agent`` и требует доступной LLM._'
    )
    lines.append('')
    return '\n'.join(lines)