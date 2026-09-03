"""Тесты сборки Markdown-отчёта (без ИИ)."""
import importlib.util
import sys
from datetime import datetime
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
from npazs.compare.differ import DiffRecord, compare_elements  # noqa: E402
from npazs.compare.normalizer import extract_notes, parse_note  # noqa: E402
from npazs.compare.report_builder import (  # noqa: E402
    build_diffs_report,
    build_notes_report,
    build_report,
)
from npazs.compare.tree import build_elements  # noqa: E402


def _blocks(*texts):
    return [Block(kind='paragraph', text=t, order=i) for i, t in enumerate(texts)]


def _diff(**kwargs):
    defaults = dict(
        kind='change',
        path='статья 1',
        path_key=(('article', '1'),),
        old='Срок равен 10 дням.',
        new='Срок равен 15 дням.',
        count=18,
        reason='',
        source_npa='',
        source_item_id='',
        change_text='',
        original_text='',
        explanation='',
    )
    defaults.update(kwargs)
    return DiffRecord(**defaults)


def test_build_report_structure_and_sections():
    ours_blocks = _blocks(
        'Статья 1. Положения',
        'Срок равен 10 дням.',
        'Примечание: часть 2 вступает в силу с 01.01.2025.',
    )
    theirs_blocks = _blocks('Статья 1. Положения', 'Срок равен 15 дням.')

    ours_body, ours_notes = extract_notes(ours_blocks)
    theirs_body, theirs_notes = extract_notes(theirs_blocks)
    notes_records, notes_table = build_notes_report(ours_notes, theirs_notes)

    ours_elements = build_elements(ours_body)
    theirs_elements = build_elements(theirs_body)
    diffs, stats, cosmetics = compare_elements(ours_elements, theirs_elements)
    diff = diffs[0]
    diff.reason = 'implementation_gap'
    diff.source_npa = '41-ЗС/1038'
    diff.change_text = 'изложить в новой редакции'
    diff.explanation = 'Правка внесена одним НПА по-разному.'
    diff.old = 'Срок равен 10 дням.'
    diff.new = 'Срок равен 15 дням.'

    report = build_report(
        ours_path='ours.rtf',
        theirs_path='theirs.docx',
        ours_fmt='rtf',
        theirs_fmt='docx',
        mode='agent',
        target_number='22-ЗС',
        notes_records=notes_records,
        notes_table=notes_table,
        diffs=[diff],
        diff_stats=stats,
        warnings=['Тестовое предупреждение конвертера'],
        started_at=datetime(2026, 9, 2, 12, 0, 0),
    )

    assert '# Отчёт о сравнении' in report
    assert 'Примечания и даты вступления в силу' in report
    assert 'Расхождения текста' in report
    assert 'Итоги и рекомендации' in report
    # путь к элементу указан полностью
    assert 'статья 1' in report
    # фрагменты было/стало
    assert 'Срок равен 10 дням.' in report
    assert 'Срок равен 15 дням.' in report
    # причина, источник и текст изменения из базы
    assert '41-ЗС/1038' in report
    assert 'изложить в новой редакции' in report
    assert 'Замечания конвертеров' in report


def test_build_report_mechanical_mode_label():
    report = build_report(
        ours_path='a.rtf', theirs_path='b.docx', ours_fmt='rtf', theirs_fmt='docx',
        mode='mechanical', target_number='', notes_records=[], notes_table='',
        diffs=[], diff_stats={'change': 0, 'add': 0, 'remove': 0}, warnings=[],
        started_at=datetime(2026, 9, 2),
    )
    assert 'Механическ' in report or 'механическ' in report
    assert 'не обнаружено' in report


def test_build_notes_report_matches_dates():
    ours = parse_note('Примечание: вступает в силу с 01.01.2025.')
    theirs = parse_note('Примечание: вступает в силу с 01.01.2026.')
    records, table = build_notes_report([ours], [theirs])
    assert table
    assert any(r.status != 'match' for r in records)


def test_notes_report_is_readable_list():
    # Раздел примечаний — читаемый список по статусам, а не широкая
    # таблица; перенос строки внутри примечания не ломает формат.
    ours = parse_note('в редакции от 19.07.2019')
    theirs = parse_note(
        '| | Список изменяющих документов\n'
        '(в ред. Закона города Севастополя от 08.07.2019 N 516-ЗС)'
    )
    records, section = build_notes_report([ours], [theirs])
    assert len(records) == 2
    assert '| № |' not in section
    assert '**Только в документе проекта (1):**' in section
    assert '**Только в документе правовой системы (1):**' in section
    # перенос строки заменён пробелом — примечание на одной строке
    assert (
        'Список изменяющих документов (в ред. Закона города Севастополя'
        in section
    )
    assert 'Даты (проект): 19.07.2019' in section


def test_diff_heading_shows_lowest_level():
    # Заголовок различия содержит самый нижний уровень: элемент, название,
    # номер абзаца и нумерацию блока.
    diff = _diff(para_no=3, item_label='часть 2', element_title='Положения')
    report = build_diffs_report([diff], mode='mechanical')
    assert '### 2.1. статья 1 «Положения», абзац 3 (часть 2)' in report


def test_cosmetics_section_lists_each_occurrence_with_location():
    # Различия оформления — важная часть отчёта: каждый случай отдельным
    # пунктом с точным местом и контекстом из обоих документов.
    cosmetics = [
        DiffRecord(
            path='статья 4', path_key=(('article', '4'),), kind='add',
            old=',', count=1, para_no=2, item_label='часть 2',
            element_title='Принципы деятельности',
            context_old='…гуманности, ответственности…',
            context_new='…гуманности ответственности…',
        ),
        DiffRecord(
            path='статья 14', path_key=(('article', '14'),), kind='remove',
            new='-', count=1, para_no=1,
            context_old='… подпунктах «а» - «д» …',
            context_new='… подпунктах «а» — «д» …',
        ),
    ]
    section = build_diffs_report([_diff()], mode='agent', cosmetics=cosmetics)
    assert '### Различия оформления (регистр, пунктуация, пробелы, е/ё)' in section
    assert 'Мелкие' not in section
    assert '**статья 4 «Принципы деятельности», абзац 2 (часть 2)**' in section
    assert 'есть только в документе проекта: «,»' in section
    assert 'есть только в документе правовой системы: «-»' in section
    assert section.count('❌ Документ проекта') == 2
    assert section.count('✅ Документ правовой системы') == 2
