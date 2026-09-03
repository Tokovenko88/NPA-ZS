"""Формирование отчёта о сравнении документов в формате Markdown.

Отчёт строится по строгим шаблонам и состоит из разделов:

1. «Примечания и даты вступления в силу» — наличие примечаний, их привязка
   к изменяющим НПА и соответствие дат (без сравнения стиля оформления);
2. «Расхождения текста» — посимвольные различия по каждому структурному
   элементу с точным местом (элемент, абзац, часть/пункт), причинами
   и текстами изменений из базы;
3. «Итоги и рекомендации» — сводка расхождений и замечания конвертеров.
"""

from __future__ import annotations

import re
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


def _clean_note_text(text: str, limit: int = 90) -> str:
    """Однострочный текст примечания для отчёта.

    Переносы строк внутри примечания ломают и таблицы, и выравнивание,
    поэтому текст приводится к одной строке и усекается с многоточием.
    Остатки табличной разметки правовых систем («| | …») убираются.
    """
    text = (text or '').replace('\r', ' ').replace('\n', ' ')
    text = ' '.join(text.split())
    text = re.sub(r'^(?:\|\s*)+', '', text).strip()
    if len(text) > limit:
        text = text[:limit - 1].rstrip() + '…'
    return text or '—'


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

    Возвращает (записи сравнения, markdown-раздел). Пометки без дат и
    номеров НПА (пустые «В редакции —», «С изменениями:») в отчёт
    не выводятся — они уже исключены из сравнения текста. Повторяющиеся
    пометки группируются («вступили в силу с …» у каждого пункта) и
    выводятся одной записью с количеством вхождений.

    Записи выводятся списком, сгруппированным по статусу, — широкая
    таблица с длинными примечаниями нечитаема и ломается переносами
    строк внутри ячеек.
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
        f'_Всего записей: {len(records)}_',
        '',
    ]
    status_order = (
        'Даты различаются',
        'Только в документе проекта',
        'Только в документе правовой системы',
        'Совпадает',
    )
    for status in status_order:
        group = [r for r in records if r.status == status]
        if not group:
            continue
        lines.append(f'**{status} ({len(group)}):**')
        lines.append('')
        for i, rec in enumerate(group, start=1):
            text = _clean_note_text(rec.text)
            lines.append(f'{i}. «{text}»')
            lines.append(f'   - НПА: {rec.number_label}')
            dates_ours = '; '.join(rec.dates_ours) if rec.dates_ours else '—'
            dates_theirs = '; '.join(rec.dates_theirs) if rec.dates_theirs else '—'
            lines.append(f'   - Даты (проект): {dates_ours}')
            lines.append(f'   - Даты (прав. система): {dates_theirs}')
            if rec.count != 1:
                lines.append(f'   - Вхождений: {rec.count}')
        lines.append('')
    return records, '\n'.join(lines)


def _quote_md(text: str, limit: int = 400) -> str:
    text = (text or '').replace('\n', ' ')
    text = ' '.join(text.split())
    if len(text) > limit:
        text = text[:limit] + '…'
    return text or '—'


def _cosmetics_section(cosmetics: List[DiffRecord]) -> str:
    """Различия оформления с точным местом каждого вхождения.

    Такие различия затрагивают только оформление (регистр, пунктуация,
    пробелы, е/ё), однако в тексте НПА важен каждый знак — поэтому каждый
    случай выводится отдельным пунктом: элемент, название, номер абзаца
    (с нумерацией части/пункта) и контекст из обоих документов.
    """
    lines = [
        '',
        '### Различия оформления (регистр, пунктуация, пробелы, е/ё)',
        '',
        (
            'В тексте НПА важен каждый знак, поэтому каждое вхождение указано '
            'с точным местом: элемент, абзац, часть/пункт.'
        ),
        '',
    ]
    for idx, rec in enumerate(cosmetics, start=1):
        if rec.kind == 'add':
            change = f'есть только в документе проекта: «{rec.old}»'
        elif rec.kind == 'remove':
            change = f'есть только в документе правовой системы: «{rec.new}»'
        else:
            change = f'«{rec.old}» → «{rec.new}»'
        lines.append(f'{idx}. **{rec.location or rec.path}** — {change}')
        if (rec.context_old or '').strip() or (rec.context_new or '').strip():
            lines.append(f'   > ❌ Документ проекта: {_quote_md(rec.context_old, 160)}')
            lines.append(f'   > ✅ Документ правовой системы: {_quote_md(rec.context_new, 160)}')
        lines.append('')
    return '\n'.join(lines)


def build_diffs_report(
    diffs: List[DiffRecord],
    mode: str = 'mechanical',
    cosmetics: Optional[List[DiffRecord]] = None,
) -> str:
    """Сформировать раздел «Расхождения текста» по записям диффа.

    ``cosmetics`` — различия только в оформлении (см.
    :func:`npazs.compare.differ.is_cosmetic_diff`); при наличии выводятся
    отдельным перечнем с точным местом каждого вхождения.
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

        lines.append(f'### 2.{idx}. {diff.location or diff.path or "—"}')
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
            f'  - различий оформления (регистр/пунктуация/пробелы/е-ё; '
            f'каждое указано с точным местом): {diff_stats["cosmetic"]}'
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