"""Конвертация текстовых документов в нормализованные структурные блоки.

Модуль не требует тяжёлых внешних библиотек сверх ``requirements.txt``:

* RTF разбирается собственным парсером управляющих слов и символов
  (поддерживаются ``\\uN``-юникод-эскейпы, ``\\'hh``-кодовые страницы,
  вложенные группы, игнорируемые назначения и таблицы);
* DOCX читается как ZIP и разбирается через lxml (уже есть в зависимостях);
* DOC (бинарный OLE) извлекается эвристически — поиском непрерывных
  печатных последовательностей байт;
* HTML/TXT/MD читаются через BeautifulSoup / plain text.

Результат — список :class:`Block` (абзацы и таблицы) + предупреждения о
возможных искажениях исходника.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import List, Optional

try:  # lxml и bs4 входят в requirements.txt
    from lxml import etree
except Exception:  # pragma: no cover
    etree = None  # type: ignore[assignment]

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover
    BeautifulSoup = None  # type: ignore[assignment]

__all__ = [
    'Block',
    'Document',
    'detect_format',
    'parse_doc_bytes',
    'parse_docx_bytes',
    'parse_html_text',
    'parse_plain_text',
    'parse_rtf_bytes',
    'read_document',
]

SUPPORTED_EXTENSIONS = {'.rtf', '.docx', '.doc', '.html', '.htm', '.txt', '.md', '.markdown'}


@dataclass
class Block:
    """Один смысловой блок документа: абзац или таблица."""

    #: Тип блока: ``paragraph`` | ``table`` | ``heading`` | ``page_break``.
    kind: str
    #: Текст блока (без служебных RTF/XML-конструкций).
    text: str
    #: Порядковый номер в исходном документе (0-базовый).
    order: int = 0


@dataclass
class Document:
    """Результат чтения одного файла."""

    source: str
    fmt: str
    blocks: List[Block] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return '\n'.join(b.text for b in self.blocks)


# ---------------------------------------------------------------------------
# Определение формата
# ---------------------------------------------------------------------------

def _by_magic(raw: bytes) -> Optional[str]:
    if raw.startswith(b'{\\rtf'):
        return 'rtf'
    if raw[:4] == b'PK\x03\x04':
        return 'docx'
    if raw.startswith(b'\xd0\xcf\x11\xe0'):
        return 'doc'
    if raw.lstrip().startswith(b'<!DOCTYPE html') or raw.lstrip().lower().startswith(b'<html'):
        return 'html'
    return None


def detect_format(path: str | Path, raw: Optional[bytes] = None) -> str:
    """Определить формат файла по расширению и/или сигнатуре."""
    p = Path(path)
    ext = p.suffix.lower()
    if raw is None:
        try:
            raw = p.read_bytes()
        except OSError:
            raw = b''
    magic = _by_magic(raw)
    if magic:
        return magic
    if ext in SUPPORTED_EXTENSIONS:
        return ext.lstrip('.')
    return 'txt'


# ---------------------------------------------------------------------------
# RTF-парсер
# ---------------------------------------------------------------------------

_RTF_SKIP_DESTINATIONS = {
    'fonttbl', 'colortbl', 'stylesheet', 'info', 'pict', 'header', 'headerl',
    'headerr', 'headerf', 'footer', 'footerl', 'footerr', 'footerf', 'footnote',
    'annotation', 'filetbl', 'listtable', 'listoverridetable', 'themedata',
    'datastore', 'nonshppict', 'shp', 'shpinst', 'background',
    'keywords', 'subject', 'author', 'operator', 'comment', 'company',
    'created', 'revtim', 'printim', 'buptim', 'vern', 'doccomm',
    'xmlnstbl', 'latentstyles', 'pgptbl', 'rsidtbl', 'generator',
    'fldinst', 'private', 'object', 'objdata', 'objhdr', 'mmath',
}

_RTF_TEXT_WORDS = {
    'emdash': '\u2014', 'endash': '\u2013', 'bullet': '\u2022',
    'lquote': '\u2018', 'rquote': '\u2019',
    'ldblquote': '\u00AB', 'rdblquote': '\u00BB',
    'enspace': ' ', 'emspace': ' ', 'qmspace': ' ',
    'zwj': '', 'zwnj': '', 'ltrmark': '', 'rtlmark': '',
}
_RTF_BREAK_WORDS = {'par', 'line', 'row', 'cell', 'page', 'sect', 'column'}


def _decode_cp_byte(b: int, codepage: str) -> str:
    try:
        return bytes([b]).decode(codepage)
    except Exception:
        return '?'


def _read_control(data: bytes, i: int):
    """Прочитать управляющее слово/символ. Возвращает (next_i, verb, param)."""
    n = len(data)
    if i >= n:
        return i, '', None
    if data[i] == ord("'"):
        hexpart = data[i + 1:i + 3]
        if len(hexpart) == 2:
            try:
                return i + 3, "'hh", int(hexpart, 16)
            except ValueError:
                pass
        return i + 1, "'hh", None
    ch = chr(data[i])
    if not ch.isascii() or not ch.isalpha():
        return i + 1, ch, None
    j = i
    while j < n and chr(data[j]).isalpha():
        j += 1
    k = j
    sign = 1
    if k < n and data[k] in (ord('-'), ord('+')):
        if data[k] == ord('-'):
            sign = -1
        k += 1
    dstart = k
    while k < n and ord('0') <= data[k] <= ord('9'):
        k += 1
    param = None
    if k > dstart:
        param = sign * int(data[dstart:k].decode('ascii'))
    if k < n and data[k] == 0x20:  # терминатор-пробел
        k += 1
    return k, ''.join(chr(q) for q in data[i:j]), param


def parse_rtf_bytes(data: bytes, codepage: str = 'cp1251') -> List[Block]:
    """Разобрать RTF-документ и вернуть список абзацев.

    Кодовая страница применяется к ``\\'hh`` и к «сырым» байтам текста
    (обычно cp1251 для русских RTF). Юникод-эскейпы ``\\uN`` всегда дают
    правильные символы.
    """
    blocks: List[Block] = []
    buf: List[str] = []
    i = 0
    n = len(data)
    group_stack: List[bool] = []   # bool = «группу игнорируем»
    skipping = False
    pending_ignorable = False      # перед «{» встречено \*
    unicode_count = 1              # после \ucN
    bin_remaining = 0

    def emit() -> None:
        text = ''.join(buf).strip()
        if text:
            blocks.append(Block(kind='paragraph', text=text, order=len(blocks)))
        buf.clear()

    while i < n:
        b = data[i]

        if bin_remaining > 0:
            bin_remaining -= 1
            i += 1
            continue

        if b == 0x7B:  # {
            group_stack.append(pending_ignorable or skipping)
            pending_ignorable = False
            skipping = any(group_stack)
            i += 1
            continue
        if b == 0x7D:  # }
            if group_stack:
                group_stack.pop()
            skipping = any(group_stack)
            i += 1
            continue
        if b == 0x5C:  # \
            if i + 1 >= n:
                break
            nxt = data[i + 1]
            if nxt == ord('*'):
                pending_ignorable = True
                i += 2
                continue
            if nxt == ord('~'):
                if not skipping:
                    buf.append('\u00A0')
                i += 2
                continue
            if nxt == ord('-'):
                if not skipping:
                    buf.append('-')
                i += 2
                continue
            if nxt == ord('_'):
                if not skipping:
                    buf.append('\u2011')
                i += 2
                continue

            j, verb, param = _read_control(data, i + 1)

            if verb == 'uc' and param is not None:
                unicode_count = max(0, param)
            elif verb == 'u' and param is not None:
                code = param if param >= 0 else param + 0x10000
                if not skipping:
                    buf.append(chr(code))
                i = j
                for _ in range(unicode_count):
                    if i < n and data[i] not in (0x7B, 0x7D):
                        i += 1
                continue
            elif verb == "'hh" and param is not None:
                if not skipping:
                    buf.append(_decode_cp_byte(param, codepage))
            elif verb == 'bin' and param is not None:
                bin_remaining = max(0, param)
            elif verb in _RTF_TEXT_WORDS:
                if not skipping:
                    buf.append(_RTF_TEXT_WORDS[verb])
            elif verb in _RTF_BREAK_WORDS:
                if not skipping:
                    if verb in ('par', 'line', 'row'):
                        emit()
                    elif verb == 'cell':
                        buf.append('\t')
            elif verb in _RTF_SKIP_DESTINATIONS and group_stack:
                group_stack[-1] = True
                skipping = True
            i = j
            continue

        if b >= 0x80:
            ch = _decode_cp_byte(b, codepage)
        elif b in (0x0D, 0x0A):
            i += 1
            continue
        elif b == 0x09:
            ch = '\t'
        else:
            ch = chr(b)
        if not skipping:
            buf.append(ch)
        i += 1

    emit()
    return blocks


# ---------------------------------------------------------------------------
# DOCX-парсер (ZIP + lxml)
# ---------------------------------------------------------------------------

_NS_W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'


def _w_qname(local: str) -> str:
    return f'{{{_NS_W}}}{local}'


def _localname(node) -> str:
    qn = node.tag
    if isinstance(qn, str) and qn.startswith('{'):
        return qn.rsplit('}', 1)[-1]
    return qn


def _paragraph_text(p_el) -> str:
    out: List[str] = []
    for node in p_el.iter():
        tag = _localname(node)
        if tag == 't':
            out.append(node.text or '')
        elif tag == 'tab':
            out.append('\t')
        elif tag == 'br' or tag == 'cr':
            out.append('\n')
        elif tag == 'noBreakHyphen':
            out.append('-')
    return ''.join(out)


def _cell_text(tc_el) -> str:
    parts: List[str] = []
    for child in tc_el:
        tag = _localname(child)
        if tag == 'p':
            parts.append(_paragraph_text(child).strip())
        elif tag == 'tbl':
            parts.append(_table_text(child))
    return '\n'.join(p for p in parts if p)


def _table_text(tbl_el) -> str:
    rows: List[str] = []
    for tr_el in tbl_el:
        if _localname(tr_el) != 'tr':
            continue
        cells = []
        for tc_el in tr_el:
            if _localname(tc_el) != 'tc':
                continue
            cells.append(_cell_text(tc_el))
        rows.append(' | '.join(cells))
    return '\n'.join(rows)


def parse_docx_bytes(data: bytes) -> List[Block]:
    """Разобрать DOCX (ZIP + ``word/document.xml``) в список блоков."""
    if etree is None:
        raise RuntimeError('lxml не установлен (pip install -r requirements.txt)')
    blocks: List[Block] = []
    with zipfile.ZipFile(BytesIO(data)) as zf:
        names = zf.namelist()
        name = next((nm for nm in names if nm.endswith('word/document.xml')), None)
        if name is None:
            raise ValueError('В DOCX не найден word/document.xml')
        xml = zf.read(name)
    root = etree.fromstring(xml)
    body = root.find(_w_qname('body'))
    if body is None:
        body = root
    order = 0
    for child in body:
        tag = _localname(child)
        if tag == 'p':
            text = _paragraph_text(child).strip()
            if text:
                blocks.append(Block(kind='paragraph', text=text, order=order))
            order += 1
        elif tag == 'tbl':
            text = _table_text(child).strip()
            if text:
                blocks.append(Block(kind='table', text=text, order=order))
            order += 1
    return blocks


# ---------------------------------------------------------------------------
# DOC-парсер (эвристический поиск текстового потока)
# ---------------------------------------------------------------------------

#: Печатные байты: ASCII printable + старшая половина (кириллица cp1251).
_RUN_RE = re.compile(rb'[\x20-\x7e\x80-\xff]{30,}')


def parse_doc_bytes(data: bytes) -> List[Block]:
    """Эвристически извлечь текст из бинарного .doc (OLE).

    Ищем непрерывные последовательности печатных байт. Разрывы (CR/LF/нули/
    управляющие байты) считаем границами абзацев. Качество обычно достаточное
    для сравнения, но не гарантируется.
    """
    blocks: List[Block] = []
    seen = set()
    for run in _RUN_RE.findall(data):
        try:
            text = run.decode('cp1251', errors='replace')
        except Exception:
            continue
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]+', '\n', text)
        text = re.sub(r'[ \t]+', ' ', text)
        text = text.strip()
        if len(text) < 24:
            continue
        key = text[:120]
        if key in seen:
            continue
        seen.add(key)
        blocks.append(Block(kind='paragraph', text=text, order=len(blocks)))
    return blocks


# ---------------------------------------------------------------------------
# HTML / plain text
# ---------------------------------------------------------------------------

def parse_html_text(text: str) -> List[Block]:
    """Разобрать HTML-текст в блоки (через BeautifulSoup, если доступен)."""
    if BeautifulSoup is None:
        blocks = []
        for chunk in re.split(r'<\s*(p|div|tr|br)\s*[^>]*>', text, flags=re.IGNORECASE):
            cleaned = re.sub(r'<[^>]+>', ' ', chunk)
            cleaned = re.sub(r'\s+', ' ', cleaned).strip()
            if cleaned:
                blocks.append(Block(kind='paragraph', text=cleaned, order=len(blocks)))
        return blocks
    soup = BeautifulSoup(text, 'html.parser')
    blocks: List[Block] = []
    for el in soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'tr']):
        txt = el.get_text('\n', strip=True)
        txt = re.sub(r'\n+', '\n', txt).strip()
        if txt:
            blocks.append(
                Block(
                    kind='heading' if el.name.startswith('h') else 'paragraph',
                    text=txt,
                    order=len(blocks),
                )
            )
    return blocks


def parse_plain_text(text: str) -> List[Block]:
    """Разобрать простой текст в абзацы (по \\n)."""
    blocks = []
    for line in text.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        line = line.strip()
        if line:
            blocks.append(Block(kind='paragraph', text=line, order=len(blocks)))
    return blocks


# ---------------------------------------------------------------------------
# Чтение файла
# ---------------------------------------------------------------------------

def read_document(path: str | Path) -> Document:
    """Прочитать документ любого поддержанного формата в :class:`Document`."""
    p = Path(path)
    raw = p.read_bytes()
    fmt = detect_format(p, raw)
    doc = Document(source=str(p), fmt=fmt)

    if fmt == 'rtf':
        doc.blocks = parse_rtf_bytes(raw)
    elif fmt == 'docx':
        doc.blocks = parse_docx_bytes(raw)
    elif fmt == 'doc':
        doc.blocks = parse_doc_bytes(raw)
        doc.warnings.append(
            'Файл .doc извлечён эвристически (без разбора OLE): возможны '
            'пропуски/искажения текста. Для точного сравнения конвертируйте '
            'в RTF или DOCX.'
        )
    elif fmt in ('html', 'htm'):
        doc.blocks = parse_html_text(raw.decode('utf-8', errors='replace'))
    else:
        doc.blocks = parse_plain_text(_auto_decode(raw))

    return doc


def _auto_decode(raw: bytes) -> str:
    for enc in ('utf-8-sig', 'cp1251', 'windows-1251', 'latin-1'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', errors='replace')