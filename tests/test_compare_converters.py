"""Тесты конвертеров документов модуля сравнения (RTF, DOCX, HTML, TXT)."""
import importlib.util
import io
import sys
import zipfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "npazs_bootstrap", _ROOT / "src" / "bootstrap.py"
)
_bootstrap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bootstrap)
_bootstrap.bootstrap()

from npazs.compare.converters import (  # noqa: E402
    detect_format,
    parse_docx_bytes,
    parse_html_text,
    parse_plain_text,
    parse_rtf_bytes,
    read_document,
)


def _make_docx(paragraphs):
    """Собрать минимальный DOCX в памяти из списка абзацев."""
    def esc(t):
        return t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    pxml = ''.join(
        '<w:p><w:r><w:t xml:space="preserve">%s</w:t></w:r></w:p>' % esc(p)
        for p in paragraphs
    )
    doc_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document '
        'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body>%s</w:body></w:document>' % pxml
    )
    ct_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '</Types>'
    )
    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/></Relationships>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('[Content_Types].xml', ct_xml)
        zf.writestr('_rels/.rels', rels_xml)
        zf.writestr('word/document.xml', doc_xml)
    return buf.getvalue()


# --------------------------------------------------------------------- RTF
def _esc(s: str) -> str:
    """Закодировать кириллицу в RTF-escape \\'xx (cp1251)."""
    out = []
    for ch in s:
        if ord(ch) < 128:
            out.append(ch)
        else:
            out.append("\\'%02x" % ch.encode('cp1251')[0])
    return ''.join(out)


def test_parse_rtf_escapes_and_paragraphs():
    rtf = (
        '{\\rtf1\\ansi\\ansicpg1251\\deff0{\\fonttbl{\\f0 Times New Roman;}}'
        '\\f0\\fs24 '
        + _esc('ЗАКОН')
        + '\\par '
        + _esc('ГОРОДА СЕВАСТОПОЛЯ')
        + '\\par '
        + _esc('Статья 1. ')
        + '\\b '
        + _esc('Общие')
        + '\\b0  '
        + _esc('положения')
        + '\\par }'
    )
    blocks = parse_rtf_bytes(rtf.encode('ascii'))
    text = '\n'.join(b.text for b in blocks)
    assert 'ЗАКОН' in text
    assert 'ГОРОДА СЕВАСТОПОЛЯ' in text
    assert 'Статья 1. Общие положения' in text
    assert '\\par' not in text
    assert '\\b' not in text


def test_parse_rtf_hex_escape_cyrillic():
    # «Статья» в cp1251 через \'xx
    word = ''.join("\\'%02x" % b for b in 'Статья'.encode('cp1251'))
    rtf = '{\\rtf1\\ansi ' + word + _esc(' 1. Тест') + '\\par }'
    blocks = parse_rtf_bytes(rtf.encode('ascii'))
    assert blocks[0].text.startswith('Статья 1. Тест')


# -------------------------------------------------------------------- DOCX
def test_parse_docx_paragraphs():
    data = _make_docx(['ЗАКОН', 'Статья 1. Общие положения', 'Текст статьи.'])
    blocks = parse_docx_bytes(data)
    texts = [b.text for b in blocks]
    assert texts == ['ЗАКОН', 'Статья 1. Общие положения', 'Текст статьи.']


# -------------------------------------------------------------- HTML / TXT
def test_parse_html_and_plain():
    blocks = parse_html_text('<p>Статья 1. Общие положения</p><p>Текст.</p>')
    assert [b.text for b in blocks] == ['Статья 1. Общие положения', 'Текст.']

    blocks = parse_plain_text('Первая строка\n\nВторая строка')
    assert [b.text for b in blocks] == ['Первая строка', 'Вторая строка']


# ------------------------------------------------------------ read_document
def test_read_document_dispatch(tmp_path):
    docx = tmp_path / 'theirs.docx'
    docx.write_bytes(_make_docx(['Статья 1. Полномочия']))
    doc = read_document(str(docx))
    assert doc.fmt == 'docx'
    assert 'Статья 1. Полномочия' in doc.text
    assert doc.blocks

    txt = tmp_path / 'ours.txt'
    txt.write_text('Статья 2. Финальные положения\nСодержимое.', encoding='utf-8')
    doc = read_document(str(txt))
    assert doc.fmt == 'txt'
    assert 'Финальные' in doc.text


def test_detect_format_by_magic(tmp_path):
    assert detect_format('x.docx') == 'docx'
    assert detect_format('x.rtf') == 'rtf'
    assert detect_format('x.doc') == 'doc'
