"""Тесты нормализации текста и извлечения примечаний/дат."""
import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "npazs_bootstrap", _ROOT / "src" / "bootstrap.py"
)
assert _spec is not None and _spec.loader is not None
_bootstrap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bootstrap)
_bootstrap.bootstrap()

from npazs.compare.converters import Block  # noqa: E402
from npazs.compare.normalizer import (  # noqa: E402
    extract_notes,
    normalize_block,
    parse_note,
)


def _blocks(*texts):
    return [Block(kind='paragraph', text=t, order=i) for i, t in enumerate(texts)]


# --------------------------------------------------------- normalize_block
def test_normalize_block_spaces():
    assert normalize_block('  А\u00a0\u00a0Б \t В  ') == 'А Б В'
    assert normalize_block(' строка \n  вторая ') == 'строка\nвторая'


# -------------------------------------------------------------- parse_note
def test_parse_note_numbers_and_valid_from():
    text = (
        'Примечание: В соответствии с Законом Севастополя от 10.06.2024 '
        '№ 41-ЗС/1038 настоящей статье придана часть 1.4, вступающая в силу '
        'с 01.01.2025.'
    )
    note = parse_note(text)
    assert '41-ЗС/1038' in note.npa_numbers
    assert note.valid_from == '01.01.2025'
    assert '10.06.2024' in note.dates


def test_parse_note_valid_from_word_date():
    text = 'Примечание: часть 2 вступает в силу с 1 июля 2025 года.'
    note = parse_note(text)
    assert note.valid_from == '1.07.2025'


def test_parse_note_fallback_latest_date():
    # нет фразы «вступает в силу» — берём самую позднюю дату хронологически
    text = 'Примечание: изменения внесены законом от 10.06.2024 № 41-ЗС, '
    text += 'опубликован 15.06.2024.'
    note = parse_note(text)
    assert note.valid_from == '15.06.2024'


def test_parse_note_no_dates():
    note = parse_note('Примечание: см. также разъяснения.')
    assert note.valid_from == ''
    assert note.dates == []


# ------------------------------------------------------------ extract_notes
def test_extract_notes_inline():
    body, notes = extract_notes(
        _blocks(
            'Статья 1. Общие положения',
            'Текст статьи.',
            'Примечание: часть 2 вступает в силу с 01.01.2025.',
        )
    )
    assert [b.text for b in body] == [
        'Статья 1. Общие положения',
        'Текст статьи.',
    ]
    assert len(notes) == 1
    assert notes[0].valid_from == '01.01.2025'


def test_extract_notes_trailing_section():
    body, notes = extract_notes(
        _blocks(
            'Статья 1. Общие положения',
            'Текст статьи.',
            'Примечания к документу:',
            'В соответствии с законом № 41-ЗС часть 2 вступает в силу с 01.01.2025.',
            'Статья 2. Финальные положения',
            'Вступает в силу через десять дней.',
        )
    )
    # структурный элемент после секции примечаний возвращает нас в тело
    assert any(b.text == 'Статья 2. Финальные положения' for b in body)
    assert len(notes) == 2
