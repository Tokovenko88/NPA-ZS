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
    status: str = ''

    @property
    def number_label(self) -> str:
        return '; '.join(self.npa_numbers) if self.npa_numbers else '—'


def _match_note(note: Note, others: List[Note]) -> Optional[Note]:
    """Найти примечание-«двойник» по номерам НПА или тексту."""
    for other in others:
        for num in note.npa_numbers:
            if num in other.npa_numbers:
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


def build_notes_report(
    notes_ours: List[Note], notes_theirs: List[Note]
) -> Tuple[List[NoteCompRecord], str]:
    """Сравнить примечания двух документов.

    Возвращает (записи сравнения, markdown-таблица).
    """
    records: List[NoteCompRecord] = []
    theirs_used = [False] * len(notes_theirs)

    for note in notes_ours:
        match_idx = None
        for idx, other in enumerate(notes_theirs):
            if theirs_used[idx]:
                continue
            if _match_note(note, [other]):
                match_idx = idx
                break
        if match_idx is None:
            records.append(
                NoteCompRecord(
                    text=note.text,
                    npa_numbers=note.npa_numbers,
                    date_ours=note.valid_from,
                    status='Только в документе проекта',
                )
            )
        else:
            theirs_used[match_idx] = True
            other = notes_theirs[match_idx]
            date_eq = _norm_date(note.valid_from) == _norm_date(other.valid_from)
            if date_eq:
                status = 'Совпадает'
            else:
                status = 'Дата вступления различается'
            records.append(
                NoteCompRecord(
                    text=note.text,
                    npa_numbers=note.npa_numbers,
                    date_ours=note.valid_from,
                    date_theirs=other.valid_from,
                    status=status,
                )
            )

    for idx, other in enumerate(notes_theirs):
        if theirs_used[idx]:
            continue
        records.append(
            NoteCompRecord(
                text=other.text,
                npa_numbers=other.npa_numbers,
                date_theirs=other.valid_from,
                status='Только в документе правовой системы',
            )
        )

    lines = [
        '| № | Примечание (проект) | НПА | Дата (проект) | Дата (прав. система) | Статус |',
        '|---|---|---|---|---|---|',
    ]
    for i, rec in enumerate(records, start=1):
        text = (rec.text or '').replace('|', '\\|')
        if len(text) > 90:
            text = text[:87] + '…'
        lines.append(
            f'| {i} | {text} | {rec.number_label} | {rec.date_ours or "—"} | '
            f'{rec.date_theirs or "—"} | {rec.status} |'
        )
    return records, '\n'.join(lines)


def _quote_md(text: str, limit: int = 400) -> str:
    text = (text or '').replace('\n', ' ')
    text = ' '.join(text.split())
    if len(text) > limit:
        text = text[:limit] + '…'
    return text or '—'


def build_diffs_report(
    diffs: List[DiffRecord],
    mode: str = 'mechanical',
) -> str:
    """Сформировать раздел «Расхождения текста» по записям диффа."""
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

    lines.append(build_diffs_report(diffs, mode=mode))

    lines.append('## 3. Итоги и рекомендации')
    lines.append('')
    total = sum(diff_stats.values())
    lines.append(f'- Расхождений текста обнаружено: **{total}**')
    lines.append(f'  - изменений (замена): {diff_stats.get("change", 0)}')
    lines.append(f'  - добавлений (только в проекте): {diff_stats.get("add", 0)}')
    lines.append(f'  - удалений (только в правовой системе): {diff_stats.get("remove", 0)}')
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