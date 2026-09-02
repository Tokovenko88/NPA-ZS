"""Тесты доступа к базе JSON НПА (поиск изменяющего НПА, тексты изменений)."""
import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "npazs_bootstrap", _ROOT / "src" / "bootstrap.py"
)
_bootstrap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bootstrap)
_bootstrap.bootstrap()

from npazs.compare import npa_resolver  # noqa: E402
from npazs.compare.npa_resolver import (  # noqa: E402
    clean_number,
    extract_change_text,
    find_npa_document,
    find_npa_files,
    parse_path_description,
)


def test_clean_number():
    assert clean_number('№ 41-ЗС/1038') == '411038'
    assert clean_number('41-ЗС') == '41'
    assert clean_number('') == ''


def test_parse_path_description():
    key = parse_path_description('статья 2 -> часть 1.4')
    assert key == (('article', '2'), ('part', '1.4'))


def test_find_npa_files_by_prefix():
    # 41-ЗС/1038 лежит в data/base/law/103/41.json (npa_number содержит
    # регистрационный номер) — поиск по краткому «41» должен его находить.
    results = find_npa_files('41')
    assert results, 'изменяющий НПА 41 не найден в data/base'
    numbers = [doc.get('npa_number', '') for _, doc in results]
    assert any(clean_number(n).startswith('41') for n in numbers)


def test_find_npa_document_skips_generated():
    doc = find_npa_document('41')
    if doc is not None:  # база присутствует
        number = doc.get('npa_number', '')
        assert clean_number(number).startswith('41')


def test_extract_change_text_full_fallback():
    # несуществующий номер -> full-фолбэк с ошибкой
    result = extract_change_text('999999-ЗС')
    assert result['full'] is True
    assert 'error' in result


def test_extract_change_text_by_path_key():
    doc = find_npa_document('41')
    if doc is None:
        print('база недоступна — тест пропущен')
        return
    # ищем в изменяющем НПА структурный элемент «статья 1» (или первую статью)
    result = extract_change_text('41', path_key=(('article', '1'),))
    assert result['npa_number']
    # элемент может не существовать — тогда full-фолбэк с полным текстом
    if result['full']:
        assert result['text']
    else:
        assert result['item_id']
        assert result['text']


def test_extract_change_text_accepts_full_number():
    # поиск по полному номеру «41-ЗС/1038» и по краткому «41» дают один НПА
    full = extract_change_text('41-ЗС/1038', path_key=(('article', '1'),))
    short = extract_change_text('41', path_key=(('article', '1'),))
    assert full['npa_number'] == short['npa_number']
