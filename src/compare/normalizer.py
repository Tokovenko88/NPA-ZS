"""Нормализация текста и выделение примечаний/дат.

Задача модуля — привести тексты, извлечённые из разных форматов (RTF, DOCX,
DOC, HTML), к сопоставимому виду и отделить «примечания» от тела документа.

Нормализация НЕ трогает знаки препинания и буквы (юридический текст важен
посимвольно): выравниваются только пробельные символы (неразрывные пробелы,
множественные пробелы/табы, служебные переносы строк), чтобы конвертация из
одного формата в другой не порождала ложных расхождений.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Tuple

from .converters import Block

__all__ = [
    'Note',
    'extract_notes',
    'normalize_block',
    'normalize_text',
    'parse_note',
]

_MONTHS_RU = {
    'января': '01', 'февраля': '02', 'марта': '03', 'апреля': '04',
    'мая': '05', 'июня': '06', 'июля': '07', 'августа': '08',
    'сентября': '09', 'октября': '10', 'ноября': '11', 'декабря': '12',
}

_REF_RE = re.compile(r'№\s*([\d][\w\-–./]*)')
_REF_RE_2 = re.compile(r'\b(\d{1,4}[-–]\w{1,6})\b')
_DATE_DOT_RE = re.compile(r'\b(\d{1,2})\.(\d{1,2})\.(\d{2,4})\b')
_DATE_WORD_RE = re.compile(r'\b(\d{1,2})\s+([а-яё]+)\s+(\d{4})\b', re.IGNORECASE)
#: Дата вступления в силу: «вступает в силу с 01.01.2025» и т.п.
_VALID_FROM_DOT_RE = re.compile(
    r'вступа\w*\s+в\s+силу[^.]{0,60}?(\d{1,2}\.\d{1,2}\.\d{2,4})', re.IGNORECASE
)
_VALID_FROM_WORD_RE = re.compile(
    r'вступа\w*\s+в\s+силу[^.]{0,60}?(\d{1,2})\s+([а-яё]+)\s+(\d{4})', re.IGNORECASE
)


def _date_key(date: str) -> tuple:
    """Ключ для хронологического сравнения дат «ДД.ММ.ГГГГ»."""
    parts = str(date).split('.')
    if len(parts) == 3:
        try:
            return (int(parts[2]), int(parts[1]), int(parts[0]))
        except ValueError:
            return (0, 0, 0)
    return (0, 0, 0)


@dataclass
class Note:
    """Примечание к НПА: текст + связанные НПА + даты."""

    text: str
    npa_numbers: List[str] = field(default_factory=list)
    dates: List[str] = field(default_factory=list)
    valid_from: str = ''
    order: int = 0

    @property
    def key(self) -> str:
        """Ключ для сравнения: отсортированный список номеров НПА."""
        return '|'.join(sorted(self.npa_numbers))


def normalize_text(s: str) -> str:
    """Unicode NFC-нормализация (без косметики пробелов)."""
    if not s:
        return ''
    return unicodedata.normalize('NFC', s)


def normalize_block(s: str) -> str:
    """Привести блок к сопоставимому виду."""
    if not s:
        return ''
    s = s.replace('\u00a0', ' ')
    s = s.replace('\u200B', '')  # zero-width space
    s = s.replace('\r\n', '\n').replace('\r', '\n')
    s = re.sub(r'[ \t]+', ' ', s)
    s = re.sub(r' *\n *', '\n', s)
    return s.strip()


def parse_note(text: str, order: int = 0) -> Note:
    """Извлечь из текста примечания номера НПА и даты."""
    note = Note(text=normalize_block(text), order=order)
    refs = _REF_RE.findall(note.text)
    refs += _REF_RE_2.findall(note.text[:400])
    npa_numbers: List[str] = []
    for ref in refs:
        ref = ref.strip()
        if not ref or not any(ch.isdigit() for ch in ref):
            continue
        if ref not in npa_numbers:
            npa_numbers.append(ref)
    note.npa_numbers = npa_numbers

    dates: List[str] = []
    for dd, mm, yyyy in _DATE_DOT_RE.findall(note.text):
        year = yyyy if len(yyyy) == 4 else '20' + yyyy
        dates.append(f'{dd}.{mm}.{year}')
    for dd, month, year in _DATE_WORD_RE.findall(note.text):
        mm = _MONTHS_RU.get(month.lower())
        if mm:
            dates.append(f'{dd}.{mm}.{year}')
    uniq = sorted(set(dates), key=_date_key)
    note.dates = uniq

    valid_from = ''
    m = _VALID_FROM_DOT_RE.search(note.text)
    if m:
        dd, mm, yyyy = m.group(1).split('.')
        valid_from = f'{dd}.{mm}.{yyyy if len(yyyy) == 4 else "20" + yyyy}'
    else:
        m = _VALID_FROM_WORD_RE.search(note.text)
        if m:
            mm = _MONTHS_RU.get(m.group(2).lower())
            if mm:
                valid_from = f'{m.group(1)}.{mm}.{m.group(3)}'
    if not valid_from and uniq:
        valid_from = max(uniq, key=_date_key)
    note.valid_from = valid_from
    return note


def extract_notes(blocks: List[Block]) -> Tuple[List[Block], List[Note]]:
    """Отделить примечания от тела документа.

    Возвращает ``(тело, примечания)``. Примечание — блок, содержащий слово
    «примечан…», либо блок внутри секции «Примечания к документу:».
    """
    notes: List[Note] = []
    body: List[Block] = []
    in_notes_section = False

    for blk in blocks:
        text = normalize_block(blk.text)
        if not text:
            continue
        low = text.lower()
        is_note_marker = 'примечан' in low
        is_section_header = 'примечания к документу' in low or re.match(r'^примечан', low)
        is_structural = re.match(
            r'^(статья|глава|раздел|часть|пункт|подпункт|приложение)\s+', low
        )
        if is_section_header:
            in_notes_section = True
        if in_notes_section and not is_note_marker and is_structural:
            in_notes_section = False
        if is_note_marker or in_notes_section:
            notes.append(parse_note(text, order=blk.order))
        else:
            body.append(blk)
    return body, notes