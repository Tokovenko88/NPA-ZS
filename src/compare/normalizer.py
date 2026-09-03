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
    'clean_body_blocks',
    'extract_notes',
    'is_service_mark_block',
    'normalize_block',
    'normalize_text',
    'normalize_typography',
    'parse_note',
    'split_document_frame',
    'strip_service_markup',
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

# ---------------------------------------------------------------------------
# Служебные/редакционные пометки
# ---------------------------------------------------------------------------
#: Пометки, которые НЕ являются содержанием НПА:
#:  * ревизионный пайплайн проекта — «Последние изменения вступили в силу…»,
#:    «В редакции —», «С изменениями:», «Введен —»;
#:  * правовые системы (КонсультантПлюс и др.) — «(в ред. …)»,
#:    «(часть 1 в ред. …)», «(п. 3 в ред. …)», «Список изменяющих документов»,
#:    «Документ предоставлен …», «www.consultant.ru», «Дата сохранения …».
#: Такие блоки целиком уходят в примечания и не участвуют в сравнении текста.
#: Допускается префикс из ячеек таблицы («| | …»).
_SERVICE_MARK_BLOCK_RE = re.compile(
    r'^\s*(?:\|\s*)*(?:'
    r'последние изменения вступили в силу[^\n]*'
    r'|в редакции[^\n]*'
    r'|с изменениями[:\s][^\n]*'
    r'|введен(?:\s*[-—:])?[^\n]*'
    r'|заголовок изменен[^\n]*'
    r'|\([^)]*\bв\s+ред\.[^)]*\)'
    r'|\([^)]*\bв\s+редакции\b[^)]*\)'
    r'|\([^)]*\bвведен\w*\b[^)]*\)'
    r'|\([^)]*\bутрати[лл][аои]?\s+сил\w*\b[^)]*\)'
    r'|\(ред\.\s+от\s+\d[^)]*\)'
    r'|[\d()\s.,\-–—]*утрати[лл][аои]?\s+сил\w*[^\n]*'
    r'|список изменяющих документов[^\n]*'
    r'|документ предоставлен\s+[^\n]*'
    r'|www\.[^\s]+'
    r'|дата сохранения[:\s][^\n]*'
    r')\s*$',
    re.IGNORECASE,
)

#: Скобочные примечания правовых систем, встречающиеся в середине абзаца:
#: «(в ред. …)», «(часть 1 в ред. …)», «(утратил силу …)» и т.п.
_INLINE_SERVICE_MARKS_RE = re.compile(
    r'\([^)]*(?:'
    r'\bв\s+ред\.[^)]*'
    r'|\bв\s+редакции\b'
    r'|\bвведен\w*\b'
    r'|\bутрати[лл][аои]?\s+сил\w*\b'
    r'|\bред\.\s+от\s+\d'
    r')[^)]*\)',
    re.IGNORECASE,
)

#: Пометки без скобок в середине абзаца:
#: «Последние изменения вступили в силу с ДД.ММ.ГГГГ»,
#: «утратили силу. - Закон города Севастополя от ДД.ММ.ГГГГ N …»,
#: «Утратил силу с ДД.ММ.ГГГГ -».
_INLINE_MARK_RE = re.compile(
    r'(?:'
    r'последние изменения вступили в силу[^.,;\n]{0,50}[.;]?'
    r'|заголовок изменен[^.,;\n]{0,60}'
    r'|(?:[\d()\s.,\-–—]+)?\bутрати[лл][аои]?\s+сил\w*\s*[.;]?\s*[-–—]\s*'
    r'(?:закон|постановление|указ|решение)\w*[^\n;]{0,120}'
    r'|\bутрати[лл][аои]?\s+сил\w*\s+с\s+\d{1,2}\.\d{1,2}\.\d{4}\b\s*[-–—]?\s*'
    r')',
    re.IGNORECASE,
)


def is_service_mark_block(text: str) -> bool:
    """Является ли блок целиком служебной пометкой (не содержанием НПА)."""
    if not text:
        return False
    # Многострочные ячейки таблиц: переносы не мешают распознаванию.
    return bool(_SERVICE_MARK_BLOCK_RE.match(text.replace('\n', ' ')))


def strip_service_markup(text: str) -> str:
    """Удалить из текста служебные пометки и примечания правовых систем.

    Оставляет содержательный текст; используется перед сравнением, чтобы
    редакционные пометки («(в ред. …)», «Последние изменения вступили
    в силу…», «В редакции —» и т.п.) не порождали ложных расхождений.
    Многострочные абзацы/ячейки таблиц сжимаются в одну строку, чтобы
    разорванная переносами пометка удалялась целиком.
    """
    if not text:
        return ''
    text = re.sub(r'\s*\n\s*', ' ', text)
    text = _SERVICE_MARK_BLOCK_RE.sub('', text)
    text = _INLINE_SERVICE_MARKS_RE.sub('', text)
    text = _INLINE_MARK_RE.sub('', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip(' ,.;:')


#: Типографические эквиваленты: оформление, которое не меняет содержание.
#: Проект использует «ёлочки», № и тире; КонсультантПлюс — прямые кавычки,
#: «N» и дефисы. Перед сравнением символы приводятся к общему виду, чтобы
#: такие различия не порождали ложных расхождений.
_TYPOGRAPHIC_MAP = {
    '№': 'N',
    '«': '"',
    '»': '"',
    '–': '-',
    '—': '-',
    '\xad': '',
}


def normalize_typography(text: str) -> str:
    """Привести типографические эквиваленты к общему виду."""
    if not text:
        return ''
    for ch, repl in _TYPOGRAPHIC_MAP.items():
        if ch in text:
            text = text.replace(ch, repl)
    return text


def clean_body_blocks(blocks: List[Block]) -> List[Block]:
    """Привести блоки тела к сопоставимому виду.

    Нормализует пробелы (:func:`normalize_block`), снимает служебные пометки
    (:func:`strip_service_markup`) и выравнивает типографические эквиваленты
    (:func:`normalize_typography`). Пустые после очистки блоки отбрасываются,
    порядковые номера перенумеровываются.
    """
    cleaned: List[Block] = []
    for blk in blocks:
        text = normalize_typography(strip_service_markup(normalize_block(blk.text)))
        if not text:
            continue
        cleaned.append(Block(kind=blk.kind, text=text, order=len(cleaned)))
    return cleaned


# ---------------------------------------------------------------------------
# Шапка и подписной блок документа (оформление, а не содержание НПА)
# ---------------------------------------------------------------------------
#: Библиографическая строка правовых систем («Закон города Севастополя
#: от 17.04.2015 N 127-ЗС …»), гриф «ПРОЕКТ».
_LEADING_FRAME_RE = re.compile(
    r'^\s*(?:закон[аы]?\s+(?:города\s+)?севастопол|проект\s*[-–—]?\s*$)',
    re.IGNORECASE,
)
#: Первый содержательный блок преамбулы («Настоящий Закон определяет …»).
_PREAMBLE_BODY_RE = re.compile(r'^настоящ\w*\s+(?:закон|положен)', re.IGNORECASE)
#: Структурный заголовок — шапка закончилась.
_FRAME_STRUCT_RE = re.compile(
    r'^(статья|глава|раздел|часть|приложение)\s', re.IGNORECASE
)
#: Якоря подписного блока: должность, город, номер закона, инициалы,
#: линия подчёркивания.
_SIGNATURE_ANCHOR_RE = re.compile(
    r'^\s*(?:'
    r'(?:глава|губернатор|мэр|председатель|вице|первый\s+заместитель)'
    r'|(?:города?|г\.)?\s*севастопол[еяь]?\s*$'
    r'|[nN№]\s*\d{1,4}\s*[-–—]\s*[а-яёa-z]{1,6}\s*$'
    r'|[а-яё]\.\s*[а-яё]\.'
    r'|_{3,}'
    r')',
    re.IGNORECASE,
)
#: Строка-дата в подписи («17 апреля 2015 года»).
_FRAME_DATE_LINE_RE = re.compile(
    r'^\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|'
    r'сентября|октября|ноября|декабря)\s+\d{4}\s*(?:года)?\s*$',
    re.IGNORECASE,
)


#: Инициалы (И.О. / И. О.) — где угодно в короткой строке подписи.
_SIGNATURE_INITIALS_RE = re.compile(r'[а-яё]\.\s*[а-яё]\.', re.IGNORECASE)


def split_document_frame(blocks: List[Block]) -> Tuple[List[Block], List[Block]]:
    """Отделить шапку (титул, гриф, библиографическую строку) и подписной
    блок от содержательного текста.

    Шапка — все блоки до первого содержательного (преамбула «Настоящий
    Закон …» или структурный заголовок «Статья 1 …»); подпись — блоки
    с конца документа, похожие на подписные реквизиты (должность, фамилия,
    город, дата, номер закона). Возвращает ``(тело, рамка)``.

    Рамка не участвует в сравнении текста: титул и подпись оформляются
    в проекте и в документе правовой системы по-разному по определению
    и порождают только ложные расхождения. Даты рамки (принятие,
    подписание) сравниваются отдельно — через примечания.

    Если содержательных блоков не остаётся, документ не режется
    (возвращается целиком в теле).
    """
    if not blocks:
        return [], []

    # Шапка: от начала до первого содержательного блока.
    head = 0
    for i, blk in enumerate(blocks):
        low = blk.text.lower()
        if _PREAMBLE_BODY_RE.match(low) or _FRAME_STRUCT_RE.match(low):
            head = i
            break

    # Подпись: с конца, пока блоки похожи на реквизиты подписи.
    tail = len(blocks)
    while tail > head:
        text = blocks[tail - 1].text
        low = text.lower()
        letters = [ch for ch in text if ch.isalpha()]
        is_caps = len(text) >= 2 and bool(letters) and all(
            not ch.islower() for ch in letters
        )
        if (
            is_caps
            or _LEADING_FRAME_RE.match(text)
            or _SIGNATURE_ANCHOR_RE.match(low)
            or _FRAME_DATE_LINE_RE.match(low)
            or (len(text) <= 100 and _SIGNATURE_INITIALS_RE.search(low))
        ):
            tail -= 1
        else:
            break

    body = list(blocks[head:tail])
    if not body:
        # Документ целиком «рамочный» (титульный лист без содержания) —
        # ничего не отрезаем, чтобы не потерять элементы сравнения.
        return list(blocks), []
    frame = list(blocks[:head]) + list(blocks[tail:])
    return body, frame


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
    «примечан…», блок внутри секции «Примечания к документу:», либо блок,
    целиком состоящий из служебной пометки (:func:`is_service_mark_block`) —
    «в ред. …», «С изменениями:», «Последние изменения вступили в силу…»,
    «В редакции —» и т.п. Такие блоки уходят в примечания и не участвуют
    в сравнении текста.
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
        is_service_mark = is_service_mark_block(text)
        is_section_header = 'примечания к документу' in low or re.match(r'^примечан', low)
        is_structural = re.match(
            r'^(статья|глава|раздел|часть|пункт|подпункт|приложение)\s+', low
        )
        if is_section_header:
            in_notes_section = True
        if in_notes_section and not is_note_marker and not is_service_mark and is_structural:
            in_notes_section = False
        if is_note_marker or is_service_mark or in_notes_section:
            notes.append(parse_note(text, order=blk.order))
        else:
            body.append(blk)
    return body, notes