"""Тесты модуля пост-анализа внесения изменений (src/revision/post_analysis.py)."""
import copy
import importlib.util
import json
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "npazs_bootstrap", _ROOT / "src" / "bootstrap.py"
)
assert _spec is not None and _spec.loader is not None
_bootstrap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bootstrap)
_bootstrap.bootstrap()

from npazs.revision import post_analysis as pa

ORIGINAL_HTML = '<p>Положение первое. <b>Органы</b> государственной власти города Севастополя, органы местного самоуправления принимают меры.</p>'
BAD_HTML = '<p>Положение первое. <b>Территориальные органы федеральных органов</b></p>'  # потерян «хвост»
GOOD_HTML = ('<p>Положение первое. <b>Территориальные органы федеральных органов'
             ' государственной власти города Севастополя, органы местного '
             'самоуправления</b> принимают меры.</p>')


def _make_result():
    """Целевой НПА с одной статьёй, в которую внесено (неправильное) изменение."""
    return {
        'npa_id': '127',
        'npa_number': 'ЗС-127',
        'doc_type': 'law',
        'date_signed': '17.04.2015',
        'head_revision': [{'npa_head': 'О базовых НПА', 'valid_to': ''}],
        'npa_notes': [],
        'revision_info': [],
        'npa_items_revision': [
            {
                'item_id': '127_law_1_art_5',
                'item_type': 'article',
                'item_number': '5',
                'item_children': [],
                'head_revisions': [{'head_text': 'Статья 5', 'valid_to': ''}],
                'number_revisions': [],
                'item_notes': [],
                'revisions': [
                    {
                        'valid_from': '01.05.2015',
                        'valid_to': '08.07.2019',
                        'modified_by_id': '127',
                        'body': [{'type': 'paragraph', 'html_text': ORIGINAL_HTML, 'order': 1}],
                    },
                    {
                        'valid_from': '08.07.2019',
                        'valid_to': '',
                        'modified_by_id': '516_law_1_art_3',
                        'body': [{'type': 'paragraph', 'html_text': BAD_HTML, 'order': 1}],
                        'highlights': {
                            'previous_edition': {
                                'deletion': [
                                    {'text': 'Органы государственной власти города '
                                             'Севастополя, органы местного самоуправления '
                                             'принимают меры', 'positions': '1-2'},
                                ],
                                'addition': [],
                                'difference': [],
                            },
                            'current_edition': {
                                'deletion': [],
                                'addition': [
                                    {'text': 'Территориальные органы федеральных органов',
                                     'positions': '1-2'},
                                ],
                                'difference': [],
                            },
                        },
                    },
                ],
            },
        ],
    }


def _make_change_law():
    return {
        'npa_id': '516',
        'npa_number': 'ЗС-516',
        'doc_type': 'law',
        'date_signed': '08.07.2019',
        'npa_items_revision': [
            {
                'item_id': '516_law_1_art_3',
                'item_type': 'article',
                'item_number': '3',
                'text': 'В части 1 статьи 5 закона ЗС-127 слово «Органы» заменить словами '
                        '«Территориальные органы федеральных органов государственной власти '
                        'города Севастополя, органы местного самоуправления».',
            },
            # Вложенная норма «пункт 6) подпункт б)» — текст инструкции
            # совпадает с description трекера для foreign_revision (fallback
            # резолвинга нормы по тексту).
            {
                'item_id': '516_law_1_art_1',
                'item_type': 'article',
                'item_number': '1',
                'item_children': [
                    {
                        'item_id': '516_law_1_art_1_point_6',
                        'item_type': 'point',
                        'item_number': '6)',
                        'item_children': [
                            {
                                'item_id': '516_law_1_art_1_point_6_subpoint_b',
                                'item_type': 'subpoint',
                                'item_number': 'б)',
                                'revisions': [
                                    {
                                        'valid_from': '20.07.2019',
                                        'body': [
                                            {
                                                'type': 'paragraph',
                                                'html_text': '<p>в части 3 слова «, указанными '
                                                             'в статье 3» исключить;</p>',
                                                'order': 1,
                                            },
                                        ],
                                    },
                                ],
                            },
                        ],
                    },
                ],
            },
        ],
    }


def _write_result_file(tmp_path, result):
    change = _make_change_law()
    path = tmp_path / '127_2015_04_17_izm_516_2019_07_08.json'
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return tmp_path / '127.json', change


def test_ids_match_prefix_safety():
    assert pa._ids_match('516_law_1_art_3', '516')
    assert pa._ids_match('516', '516')
    assert pa._ids_match('127, 516', '516')
    assert not pa._ids_match('5162_law_1', '516')
    assert not pa._ids_match('', '516')
    assert not pa._ids_match(None, '516')


def test_collect_changes_finds_all_kinds():
    result = _make_result()
    result['npa_notes'] = [
        {'text': 'Поправка 516-ЗС применяется…', 'valid_from': '08.07.2019',
         'source_item_id': '516'},
    ]
    changes = pa.collect_changes(result, _make_change_law())
    kinds = {c['kind'] for c in changes}
    assert kinds == {'change', 'note'}
    entry = next(c for c in changes if c['kind'] == 'change')
    assert entry['item_id'] == '127_law_1_art_5'
    assert 'Органы' in entry['before']
    assert 'Территориальные органы' in entry['after']
    assert entry['highlights']


def test_collect_changes_parent_excludes_children_inline():
    """Родитель с дочерними элементами, изменяемыми тем же НПА:
    ``after`` не должен содержать текст детей inline — у детей свои
    записи в changes. Иначе пост-анализ интерпретирует добавление
    структуры как полную замену текста родителя.
    (кейс 444-ЗС -> 269-ЗС: «1. » добавлено в неструктурированный
    абзац, он становится структурным элементом с детьми)"""
    result = {
        'npa_id': '269',
        'npa_number': '269-ЗС',
        'doc_type': 'law',
        'head_revision': [{'npa_head': 'Наименование', 'valid_to': ''}],
        'npa_notes': [],
        'revision_info': [],
        'npa_items_revision': [
            {
                'item_id': '269_article_3',
                'item_type': 'article',
                'item_number': '3',
                'item_children': [
                    {
                        'item_id': '269_article_3_part_1',
                        'item_type': 'part',
                        'item_number': '1',
                        'revisions': [
                            {
                                'valid_from': '15.12.2017',
                                'modified_by_id': '444_article_3_part_1',
                                'body': [
                                    {'type': 'paragraph',
                                     'html_text': '<p>1. К отдельным '
                                                  'категориям граждан</p>',
                                     'order': 1},
                                    {'type': 'child_ref',
                                     'item_id': '269_article_3_part_1_point_1',
                                     'order': 2},
                                ],
                            },
                        ],
                        'item_children': [
                            {
                                'item_id': '269_article_3_part_1_point_1',
                                'item_type': 'point',
                                'item_number': '1)',
                                'revisions': [
                                    {
                                        'valid_from': '15.12.2017',
                                        'modified_by_id': '444_article_3_part_1',
                                        'body': [
                                            {'type': 'paragraph',
                                             'html_text': '<p>имеющих право</p>',
                                             'order': 1},
                                        ],
                                    },
                                ],
                            },
                        ],
                    },
                ],
                'revisions': [
                    {
                        'valid_from': '05.01.2016',
                        'modified_by_id': '269',
                        'body': [
                            {'type': 'paragraph',
                             'html_text': '<p>К отдельным категориям '
                                          'граждан</p>',
                             'order': 1},
                        ],
                    },
                    {
                        'valid_from': '15.12.2017',
                        'modified_by_id': '444_article_3',
                        'body': [
                            {'type': 'child_ref',
                             'item_id': '269_article_3_part_1',
                             'order': 1},
                        ],
                    },
                ],
            },
        ],
    }
    change = {'npa_id': '444', 'npa_number': '444-ЗС'}
    changes = pa.collect_changes(result, change)
    article_entry = next(
        c for c in changes if c['item_id'] == '269_article_3')
    assert article_entry['kind'] == 'change', (
        f"ожидался kind='change', получен {article_entry['kind']}")
    assert 'К отдельным категориям' in article_entry['before'], (
        f"before неверен: {article_entry['before']!r}")
    # after пуст (Rev 2 имеет только child_ref — собственного текста нет)
    # Это структурная перестройка, а не замена текста.
    assert article_entry['after'] == '', (
        f"after должен быть пуст (parent body — только child_ref), "
        f"получен: {article_entry['after']!r}")

    part_entry = next(
        c for c in changes if c['item_id'] == '269_article_3_part_1')
    assert part_entry['kind'] == 'add', (
        f"ожидался kind='add', получен {part_entry['kind']}")
    assert '1. К отдельным категориям' in part_entry['after'], (
        f"after части 1 должен содержать '1. К отдельным категориям': "
        f"{part_entry['after']!r}")
    assert 'имеющих право' not in part_entry['after'], (
        f"after части 1 НЕ должен содержать текст дочернего пункта: "
        f"{part_entry['after']!r}")

    point_entry = next(
        c for c in changes if c['item_id']
        == '269_article_3_part_1_point_1')
    assert point_entry['kind'] == 'add', (
        f"ожидался kind='add', получен {point_entry['kind']}")


def test_build_prompt_contains_parts(tmp_path):
    _, change = _write_result_file(tmp_path, _make_result())
    result_data = json.loads((tmp_path / '127_2015_04_17_izm_516_2019_07_08.json')
                             .read_text(encoding='utf-8'))
    changes = pa.collect_changes(result_data, change)
    prompt = pa.build_prompt(result_data, change, changes)
    assert '<json_schema>' in prompt
    assert '<instructions>' in prompt
    assert '<changes>' in prompt
    assert 'Территориальные органы' in prompt
    assert 'ЗС-516' in prompt


def test_run_post_analysis_correct_verdict(tmp_path, monkeypatch):
    orig_file, change = _write_result_file(tmp_path, _make_result())
    result_data = json.loads(
        (tmp_path / '127_2015_04_17_izm_516_2019_07_08.json').read_text(encoding='utf-8'))

    verdict = {'status': 'correct', 'summary': 'Все изменения соответствуют инструкциям.'}
    captured = {}

    def fake_ask(prompt, model, log_callback, **kwargs):
        captured['prompt'] = prompt
        return json.dumps(verdict, ensure_ascii=False)

    monkeypatch.setattr(pa, 'ask_ollama', fake_ask)
    res = pa.run_post_analysis(str(orig_file), result_data, change,
                               model='stub', backend='kilo_gateway')
    assert res['status'] == 'correct'
    assert res['checked'] >= 1
    assert res['corrected_path'] is None
    report = Path(res['report_path'])
    assert report.exists()
    text = report.read_text(encoding='utf-8')
    assert 'КОРРЕКТНО' in text
    assert 'ЗС-127' in text and 'ЗС-516' in text
    assert not (tmp_path / '127_2015_04_17_izm_516_2019_07_08_corrected.json').exists()


def _make_numbering_result():
    """Целевой НПА, где абзац корректно оформлен частью 1 (номер в item_number).

    Структура повторяет кейс 444-ЗС → 269-ЗС: в статье 3 появилась часть 1,
    её абзац имеет структурный номер только в ``item_number``, а сам текст в
    ``html_text`` начинается без «1. ».
    """
    return {
        'npa_id': '269', 'npa_number': '269-ЗС', 'doc_type': 'law',
        'date_signed': '27.07.2016',
        'head_revision': [{'npa_head': 'О предоставлении участков', 'valid_to': ''}],
        'npa_notes': [], 'revision_info': [],
        'npa_items_revision': [
            {
                'item_id': '269_article_3', 'item_type': 'article',
                'item_number': '3',
                'head_revisions': [{'head_text': 'Статья 3', 'valid_to': ''}],
                'number_revisions': [], 'item_notes': [],
                'item_children': [
                    {
                        'item_id': '269_article_3_part_1', 'item_type': 'part',
                        'item_number': '1',
                        'head_revisions': [], 'number_revisions': [], 'item_notes': [],
                        'item_children': [
                            {
                                'item_id': '269_article_3_part_1_point_1',
                                'item_type': 'point', 'item_number': '1)',
                                'head_revisions': [], 'number_revisions': [],
                                'item_notes': [], 'item_children': [],
                                'revisions': [
                                    {'valid_from': '23.10.2018', 'valid_to': '',
                                     'modified_by_id': '444_article_3',
                                     'body': [{'type': 'paragraph',
                                               'html_text': '<p>имеющих право</p>',
                                               'order': 1}]},
                                ],
                            },
                        ],
                        'revisions': [
                            {'valid_from': '23.10.2018', 'valid_to': '',
                             'modified_by_id': '444_article_3',
                             'body': [{'type': 'paragraph',
                                       'html_text': '<p>К отдельным категориям '
                                                    'граждан, относятся:</p>',
                                       'order': 1}]},
                        ],
                    },
                ],
                'revisions': [
                    {'valid_from': '27.07.2016', 'valid_to': '23.10.2018',
                     'modified_by_id': '269',
                     'body': [{'type': 'paragraph',
                               'html_text': '<p>К отдельным категориям граждан, '
                                            'относятся:</p>',
                               'order': 1}]},
                    {'valid_from': '23.10.2018', 'valid_to': '',
                     'modified_by_id': '444_article_3',
                     'body': [{'type': 'child_ref',
                               'item_id': '269_article_3_part_1', 'order': 1}]},
                ],
            },
        ],
    }


def test_run_post_analysis_filters_numbering_hallucination(tmp_path, monkeypatch):
    """Кейс 444-ЗС → 269-ЗС: претензия «в тексте нет 1. » отсеивается.

    Абзац корректно оформлен частью 1 (номер в item_number), а ИИ сообщает об
    отсутствии номера в тексте — вердикт обязан стать correct, а файл
    ``_corrected.json`` не создаваться.
    """
    result = _make_numbering_result()
    change = {'npa_id': '444', 'npa_number': '444-ЗС'}
    path = tmp_path / '269_2016_07_27_izm_444_2018_10_12.json'
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    result_data = json.loads(path.read_text(encoding='utf-8'))

    verdict = {
        'status': 'incorrect',
        'summary': 'В части 1 статьи 3 не добавлен номер «1. ».',
        'issues': [{
            'index': 1,
            'path': 'Статья 3 > Часть 1',
            'issue': 'Абзац не получил структурный номер 1.',
            'expected': '<p>1. К отдельным категориям граждан, относятся:</p>',
            'actual': '<p>К отдельным категориям граждан, относятся:</p>',
            'fix': 'Добавить «1. » в начало абзаца.',
            'corrections': [{
                'item_id': '269_article_3_part_1',
                'field': 'element_html',
                'value': '<p>1. К отдельным категориям граждан, относятся:</p>',
            }],
        }],
    }
    monkeypatch.setattr(pa, 'ask_ollama',
                        lambda *a, **kw: json.dumps(verdict, ensure_ascii=False))
    res = pa.run_post_analysis(str(path), result_data, change,
                               model='stub', backend='kilo_gateway')
    assert res['status'] == 'correct', res
    assert res['issues'] == 0
    assert res['corrected_path'] is None
    assert not (tmp_path / '269_2016_07_27_izm_444_2018_10_12_corrected.json').exists()
    report = Path(res['report_path']).read_text(encoding='utf-8')
    assert 'КОРРЕКТНО' in report
    assert 'конвенции нумерации' in report


def test_run_post_analysis_incorrect_creates_corrected(tmp_path, monkeypatch):
    orig_file, change = _write_result_file(tmp_path, _make_result())
    result_data = json.loads(
        (tmp_path / '127_2015_04_17_izm_516_2019_07_08.json').read_text(encoding='utf-8'))

    verdict = {
        'status': 'incorrect',
        'summary': 'Потерян «хвост» предложения при замене.',
        'issues': [{
            'index': 0,
            'path': 'Статья 5',
            'issue': 'часть текста удалена без указания в инструкции',
            'expected': GOOD_HTML,
            'actual': BAD_HTML,
            'fix': 'восстановить окончание предложения',
            'corrections': [{
                'item_id': '127_law_1_art_5',
                'field': 'element_html',
                'value': GOOD_HTML,
            }],
        }],
    }
    monkeypatch.setattr(
        pa, 'ask_ollama',
        lambda *a, **k: json.dumps(verdict, ensure_ascii=False))

    res = pa.run_post_analysis(str(orig_file), result_data, change,
                               model='stub', backend='kilo_gateway')
    assert res['status'] == 'incorrect'
    corrected = res['corrected_path']
    assert corrected and Path(corrected).exists()

    fixed = json.loads(Path(corrected).read_text(encoding='utf-8'))
    art = fixed['npa_items_revision'][0]
    body_html = ' '.join(
        b['html_text'] for b in art['revisions'][-1]['body'] if b.get('type') == 'paragraph')
    body_plain = pa._strip_html(body_html)
    assert 'органы местного самоуправления принимают меры' in body_plain
    assert 'Территориальные органы федеральных органов' in body_plain
    # Подсветка current_edition осталась (текст присутствует), previous — тоже
    hl = art['revisions'][-1]['highlights']
    assert hl['current_edition']['addition']

    report = Path(res['report_path']).read_text(encoding='utf-8')
    assert 'ОШИБКИ' in report
    assert '_corrected' in report
    assert 'восстановить окончание' in report
    # Исходный файл результата не изменён (в теле по-прежнему нет «хвоста»)
    original_now = json.loads(
        (tmp_path / '127_2015_04_17_izm_516_2019_07_08.json').read_text(encoding='utf-8'))
    orig_body = ' '.join(
        b.get('html_text', '') for b in original_now['npa_items_revision'][0]['revisions'][-1]['body'])
    assert 'органы местного самоуправления принимают меры' not in pa._strip_html(orig_body)
    assert 'Территориальные органы федеральных органов' in pa._strip_html(orig_body)


def test_run_post_analysis_sanitize_stale_highlights(tmp_path, monkeypatch):
    orig_file, change = _write_result_file(tmp_path, _make_result())
    result_data = json.loads(
        (tmp_path / '127_2015_04_17_izm_516_2019_07_08.json').read_text(encoding='utf-8'))
    verdict = {
        'status': 'incorrect', 'summary': 's',
        'issues': [{'index': 0, 'path': 'Статья 5', 'issue': 'i',
                    'corrections': [{'item_id': '127_law_1_art_5',
                                     'field': 'element_html', 'value': GOOD_HTML}]}],
    }
    monkeypatch.setattr(
        pa, 'ask_ollama', lambda *a, **k: json.dumps(verdict, ensure_ascii=False))
    res = pa.run_post_analysis(str(orig_file), result_data, change,
                               model='stub', backend='kilo_gateway')
    fixed = json.loads(Path(res['corrected_path']).read_text(encoding='utf-8'))
    hl = fixed['npa_items_revision'][0]['revisions'][-1].get('highlights')
    # previous_edition deletion-текст больше не встречается целиком… но это
    # previous (старая редакция) — она сохраняется; проверяем, что sanitize
    # не уронил валидные записи
    assert hl is not None


def test_run_post_analysis_skips_when_no_changes(tmp_path, monkeypatch):
    result = _make_result()
    result['npa_items_revision'][0]['revisions'][-1]['modified_by_id'] = '999'
    orig_file, change = _write_result_file(tmp_path, result)
    monkeypatch.setattr(
        pa, 'ask_ollama', lambda *a, **k: pytest.fail('AI не должен вызываться'))
    res = pa.run_post_analysis(str(orig_file), result, change,
                               model='stub', backend='kilo_gateway')
    assert res['status'] == 'skipped'
    assert res['report_path'] and Path(res['report_path']).exists()


def test_apply_deletion_instruction_shared_quote():
    """Правка «слова «...№ 185-ЗС «О правовых актах...»» исключить» — внешняя и
    внутренняя цитаты разделяют одну „»". Фраза должна быть удалена вместе с
    внутренними кавычками, а пустая ссылка (остаток <a href="..."></a>) — вычищена.
    """
    desc = ('<p>в части 3 слова «, указанными в статье 3 Закона города Севастополя'
            ' от 29 сентября 2015 года <a href="http://sevzakon.ru/">№ 185-ЗС</a>'
            ' «О правовых актах города Севастополя» исключить;</p>')
    current = ('<p class="justifyfull">Предложения о кандидатах на должность'
               ' Уполномоченного вносятся в Законодательное Собрание города'
               ' Севастополя субъектами права законодательной инициативы,'
               ' указанными в статье 3 Закона города Севастополя от 29 сентября'
               ' 2015 года <a href="view/laws/bank/09_2015/o_pravovyh_aktah_goroda_sevastopolya/">'
               '№ 185-ЗС</a> «О правовых актах города Севастополя».</p>')
    corrected = pa._apply_deletion_instruction(current, desc)
    assert corrected is not None, 'Удаление должно было примениться'
    # Фраза удалена
    assert 'указанными в статье 3 Закона города Севастополя' not in pa._strip_html(corrected)
    assert '№ 185-ЗС' not in pa._strip_html(corrected)
    # Текст-обёртка сохранён
    assert 'Предложения о кандидатах на должность Уполномоченного вносятся' in pa._strip_html(corrected)
    assert 'субъектами права законодательной инициативы' in pa._strip_html(corrected)
    # Пустая ссылка вычищена
    assert '<a href=' not in corrected
    # Нет двойных пробелов
    assert '  ' not in corrected


def test_apply_deletion_instruction_balanced_quote():
    """Простая сбалансированная правка: «слова «X» исключить»."""
    desc = '<p>в части 2 слова «в возрасте до 35 лет» исключить;</p>'
    current = '<p>Лицо, достигшее возраста «в возрасте до 35 лет», назначается.</p>'
    corrected = pa._apply_deletion_instruction(current, desc)
    assert corrected is not None
    text = pa._strip_html(corrected)
    assert 'до 35 лет' not in text
    assert 'Лицо, достигшее возраста' in text


def test_foreign_revision_creates_new_revision(tmp_path, monkeypatch):
    """Баг 516-ЗС: foreign_revision должна автоматически создавать новую ревизию
    от изменяющего НПА через element_html_new_rev.
    """
    from npazs.revision.change_tracker import ChangeTracker

    result = _make_result()
    # Симулируем foreign_revision: ревизия от чужого НПА (9982)
    result['npa_items_revision'][0]['revisions'][-1]['modified_by_id'] = '9982_law_1_art_2'
    result['npa_items_revision'][0]['revisions'][-1]['revision_id'] = 'foreign-rev-001'
    # Новая ревизия должна содержать реальную правку (удаление фразы),
    # а не копию текущего текста.
    result['npa_items_revision'][0]['revisions'][-1]['body'][0][
        'html_text'] = '<p>Предложения о кандидатах вносятся, указанными в статье 3.</p>'

    orig_file, change = _write_result_file(tmp_path, result)

    # Реальный ChangeTracker: норма закрыта чужой ревизией 9982
    tracker = ChangeTracker()
    cid = tracker.register_change({
        'revision_number': '6)->б)',
        'structural_element': 'Статья 6 часть 3',
        'type': 'change',
        'description': '<p>в части 3 слова «, указанными в статье 3» исключить;</p>',
    })
    tracker.mark_applying(cid, '127_law_1_art_5')
    tracker.mark_applied(cid, 'foreign-rev-001', '127_law_1_art_5')
    tracker.mark_verified(cid)

    verdict = {'status': 'correct', 'summary': 'LLM не видит coverage gaps'}
    monkeypatch.setattr(
        pa, 'ask_ollama',
        lambda *a, **k: json.dumps(verdict, ensure_ascii=False))

    res = pa.run_post_analysis(str(orig_file), result, change,
                               model='stub', backend='kilo_gateway',
                               tracker_snapshot=tracker)

    # Статус должен быть incorrect из-за foreign_revision
    assert res['status'] == 'incorrect'
    assert res['corrected_path'] and Path(res['corrected_path']).exists()

    fixed = json.loads(Path(res['corrected_path']).read_text(encoding='utf-8'))
    art = fixed['npa_items_revision'][0]

    # Должна появиться новая ревизия от изменяющего НПА (516)
    assert len(art['revisions']) == 3, f"Ожидалось 3 ревизии, получено {len(art['revisions'])}"
    new_rev = art['revisions'][-1]
    # modified_by_id — резолвнутая норма изменяющего НПА («6)->б)» найдена
    # fallback-поиском по тексту инструкции), а не голый npa_id.
    assert new_rev['modified_by_id'] == '516_law_1_art_1_point_6_subpoint_b', (
        f"Ожидался modified_by_id='516_law_1_art_1_point_6_subpoint_b', "
        f"получено '{new_rev['modified_by_id']}'")
    assert new_rev.get('mod_type') == 'change', (
        f"Ожидался mod_type='change', получено '{new_rev.get('mod_type')}'")
    assert new_rev['valid_to'] == '', "Новая ревизия должна быть активной"
    # Закрытая чужая ревизия: valid_to = за день до valid_from новой (конвенция базы)
    foreign_rev = art['revisions'][1]
    assert foreign_rev['valid_to'] == '07.07.2019', (
        f"Ожидался valid_to='07.07.2019' (день до 08.07.2019), "
        f"получено '{foreign_rev.get('valid_to')}'")

    # Основное: реальная правка применена — фраза «указанными в статье 3» удалена
    new_body_text = ' '.join(
        pa._strip_html(b.get('html_text', ''))
        for b in new_rev.get('body', []) if b.get('type') == 'paragraph')
    assert 'указанными в статье 3' not in new_body_text, (
        f"Фраза должна быть удалена, но осталась: {new_body_text}")
    assert 'Предложения о кандидатах вносятся' in new_body_text

    # Предыдущая ревизия должна быть закрыта
    prev_rev = art['revisions'][-2]
    assert prev_rev['valid_to'] != '', "Предыдущая ревизия должна быть закрыта"


def test_delete_repel_not_marked_gets_not_valid(tmp_path, monkeypatch):
    """Баг 516-ЗС: delete-пробел покрытия («признать утратившим силу») должен
    исправляться детерминированной коррекцией element_not_valid, а НЕ созданием
    ложной текстовой ревизии (element_html_new_rev).
    """
    from npazs.revision.change_tracker import ChangeTracker

    result = _make_result()
    # Активная ревизия, repel НЕ применён (нет not_valid/valid_to)
    result['npa_items_revision'][0]['revisions'][-1]['modified_by_id'] = '127'
    result['npa_items_revision'][0]['revisions'][-1].pop('highlights', None)

    orig_file, change = _write_result_file(tmp_path, result)

    tracker = ChangeTracker()
    cid = tracker.register_change({
        'revision_number': '10)->б)',
        'structural_element': 'Статья 5',
        'type': 'delete',
        'description': '<p>часть 1 статьи 5 признать утратившей силу;</p>',
    })
    tracker.mark_applying(cid, '127_law_1_art_5')
    tracker.mark_applied(cid, 'foreign-rev-002', '127_law_1_art_5')
    tracker.mark_verified(cid)

    verdict = {'status': 'correct', 'summary': 'LLM не видит coverage gaps'}
    monkeypatch.setattr(
        pa, 'ask_ollama',
        lambda *a, **k: json.dumps(verdict, ensure_ascii=False))

    res = pa.run_post_analysis(str(orig_file), result, change,
                               model='stub', backend='kilo_gateway',
                               tracker_snapshot=tracker)

    assert res['status'] == 'incorrect'
    assert res['corrected_path'] and Path(res['corrected_path']).exists()

    fixed = json.loads(Path(res['corrected_path']).read_text(encoding='utf-8'))
    art = fixed['npa_items_revision'][0]
    # Ложной текстовой ревизии НЕ создано
    assert len(art['revisions']) == 2, (
        f"Ревизия не должна создаваться для repel, получено {len(art['revisions'])}")
    rev = art['revisions'][-1]
    # Активная ревизия помечена утратившей силу (конвенция change_applier)
    assert rev['valid_to'] == '07.07.2019', (
        f"Ожидался valid_to='07.07.2019' (день до 08.07.2019), получено '{rev['valid_to']}'")
    assert rev.get('not_valid'), "not_valid должен быть проставлен"
    assert str(rev['not_valid']).startswith('516'), (
        f"not_valid должен ссылаться на изменяющий НПА, получено '{rev['not_valid']}'")
    assert rev.get('revision_id'), "revision_id должен быть проставлен"


def test_delete_repel_correctly_marked_no_gap(tmp_path, monkeypatch):
    """Баг 516-ЗС: корректно применённый repel (not_valid проставлен изменяющим
    НПА) НЕ должен порождать coverage gap и переводить вердикт в incorrect.
    """
    from npazs.revision.change_tracker import ChangeTracker

    result = _make_result()
    rev = result['npa_items_revision'][0]['revisions'][-1]
    rev['valid_to'] = '18.07.2019'
    rev['not_valid'] = '516_law_1_art_1_point_10_subpoint_b'
    rev['revision_id'] = 'repel-rev-001'
    rev.pop('highlights', None)

    orig_file, change = _write_result_file(tmp_path, result)

    tracker = ChangeTracker()
    cid = tracker.register_change({
        'revision_number': '10)->б)',
        'structural_element': 'Статья 5',
        'type': 'delete',
        'description': '<p>часть 1 статьи 5 признать утратившей силу;</p>',
    })
    tracker.mark_applying(cid, '127_law_1_art_5')
    tracker.mark_applied(cid, 'repel-rev-001', '127_law_1_art_5')
    tracker.mark_verified(cid)

    verdict = {'status': 'correct', 'summary': 'всё применено корректно'}
    monkeypatch.setattr(
        pa, 'ask_ollama',
        lambda *a, **k: json.dumps(verdict, ensure_ascii=False))

    res = pa.run_post_analysis(str(orig_file), result, change,
                               model='stub', backend='kilo_gateway',
                               tracker_snapshot=tracker)

    assert res['status'] == 'correct', (
        f"Корректный repel не должен давать incorrect, получено: {res}")
    assert res['corrected_path'] is None


def test_foreign_revision_new_rev_has_highlights_and_preserves_history(tmp_path, monkeypatch):
    """Баг 516-ЗС (ст. 6 часть 3): ревизия, созданная пост-анализом для
    foreign_revision, должна получать подсветку удалённой фразы, а историческая
    чужая ревизия не должна быть затёрта плейсхолдером ИИ‑агента."""
    from npazs.revision.change_tracker import ChangeTracker

    result = _make_result()
    art = result['npa_items_revision'][0]
    active = art['revisions'][1]
    active['valid_from'] = '08.07.2019'
    active['valid_to'] = ''
    active['modified_by_id'] = '9982_law_1_art_2'
    active['revision_id'] = 'foreign-rev-003'
    active['body'][0]['html_text'] = (
        '<p class="justifyfull">Предложения о кандидатах на должность '
        'Уполномоченного вносятся в Законодательное Собрание города Севастополя '
        'субъектами права законодательной инициативы, указанных в статье 3 '
        'Закона города Севастополя от 29 сентября 2015 года '
        '<a href="view/laws/bank/09_2015/x/">№ 185-ЗС</a> '
        '«О правовых актах города Севастополя».</p>'
    )
    hist_body_before = copy.deepcopy(art['revisions'][1]['body'])

    orig_file, change = _write_result_file(tmp_path, result)

    tracker = ChangeTracker()
    cid = tracker.register_change({
        'revision_number': '6)->б)',
        'structural_element': 'Статья 5',
        'type': 'change',
        'description': '<p>в части 3 слова «, указанных в статье 3» исключить;</p>',
    })
    tracker.mark_applying(cid, '127_law_1_art_5')
    tracker.mark_applied(cid, 'foreign-rev-003', '127_law_1_art_5')
    tracker.mark_verified(cid)

    # LLM не видит проблемы, но «исправляет» активную ревизию плейсхолдером
    verdict = {
        'status': 'correct',
        'summary': 'LLM не видит coverage gaps',
        'issues': [{
            'index': 0,
            'path': 'Статья 5',
            'issue': 'правка не применена',
            'expected': 'Текст без указанных слов',
            'actual': 'Текст без изменений',
            'fix': 'Исключить слова',
            'corrections': [{
                'item_id': '127_law_1_art_5',
                'field': 'element_html',
                'value': '<p class="justifyfull">[текст части 3 без указанных слов]</p>',
            }],
        }],
    }
    monkeypatch.setattr(pa, 'ask_ollama',
                        lambda *a, **k: json.dumps(verdict, ensure_ascii=False))

    res = pa.run_post_analysis(str(orig_file), result, change,
                               model='stub', backend='kilo_gateway',
                               tracker_snapshot=tracker)
    assert res['status'] == 'incorrect'
    assert res['corrected_path'] and Path(res['corrected_path']).exists()

    fixed = json.loads(Path(res['corrected_path']).read_text(encoding='utf-8'))
    revs = fixed['npa_items_revision'][0]['revisions']
    assert len(revs) == 3, f"Ожидалось 3 ревизии, получено {len(revs)}"
    new_rev = revs[-1]
    assert new_rev['valid_to'] == ''
    assert new_rev['valid_from'] == '08.07.2019'
    assert str(new_rev.get('modified_by_id', '')).startswith('516')

    new_body_text = ' '.join(
        pa._strip_html(b.get('html_text', ''))
        for b in new_rev.get('body', []) if b.get('type') == 'paragraph')
    assert 'указанных в статье 3' not in new_body_text, \
        f"Фраза должна быть удалена, но осталась: {new_body_text}"
    assert 'Предложения о кандидатах' in new_body_text

    # Подсветка правки: удалённая фраза отмечена в previous_edition.deletion
    hl = new_rev.get('highlights')
    assert hl, 'Подсветка правки не создана — это баг 516-ЗС (подсветка пропала)!'
    del_entries = (hl.get('previous_edition', {}) or {}).get('deletion') or []
    assert del_entries, 'deletion в подсветке пуст — это баг 516-ЗС (подсветка пропала)'
    deleted_text = ' '.join(
        e[0] if isinstance(e, list) else e.get('text', '') for e in del_entries)
    assert 'указанных в статье 3' in deleted_text, \
        f"Фраза в подсветке не найдена: {deleted_text}"
    for e in del_entries:
        pos = e[1] if isinstance(e, list) else e.get('positions', '')
        assert re.match(r'^\d+-\d+$', pos), f'Формат позиции не "M-N": {pos}'

    # Историческая ревизия НЕ затерта плейсхолдером и сохранила фразу
    hist_text = ' '.join(
        pa._strip_html(b.get('html_text', ''))
        for b in revs[1].get('body', []) if b.get('type') == 'paragraph')
    assert '[текст' not in hist_text, 'Плейсхолдер попал в историю ревизий!'
    assert 'указанных в статье 3' in hist_text, 'История потеряла фразу!'
    assert revs[1]['body'] == hist_body_before, 'Историческая ревизия изменена!'

    # Ни в одной ревизии не должно быть плейсхолдера
    for r in revs:
        t = ' '.join(
            pa._strip_html(b.get('html_text', ''))
            for b in r.get('body', []) if b.get('type') == 'paragraph')
        assert '[текст' not in t, 'Плейсхолдер в тексте ревизии!'



def test_element_not_valid_rejected_for_child_still_referenced():
    """Защита от вредной автоправки: нельзя помечать not_valid норму, которая
    по-прежнему входит в действующую редакцию родителя (child_ref в открытой
    ревизии). Кейс 380-ЗС -> 269-ЗС: LLM-агент предлагал отменить часть 7
    статьи 7, перенесённую новой редакцией без изменений."""
    result = {
        'npa_items_revision': [
            {
                'item_id': '16012_article_7',
                'item_type': 'article',
                'item_number': '7',
                'revisions': [
                    {
                        'valid_from': '15.12.2017',
                        'valid_to': None,
                        'mod_type': 'new_redaction',
                        'modified_by_id': '33699_article_1_point_9',
                        'body': [
                            {'type': 'child_ref',
                             'item_id': '16012_article_7_part_7', 'order': 1},
                        ],
                    },
                ],
                'item_children': [
                    {
                        'item_id': '16012_article_7_part_7',
                        'item_type': 'part',
                        'item_number': '7',
                        'revisions': [
                            {'body': [
                                {'type': 'paragraph',
                                 'html_text': '<p>Решение о предоставлении…</p>',
                                 'order': 1},
                            ]},
                        ],
                    },
                ],
            },
        ],
    }
    verdict = {
        'issues': [
            {
                'path': 'Статья 7 > Часть 7',
                'corrections': [
                    {
                        'item_id': '16012_article_7_part_7',
                        'field': 'element_not_valid',
                        'value': '15.12.2017',
                    },
                ],
            },
        ],
    }
    applied = pa.apply_corrections(result, verdict, '33699', '15.12.2017')
    assert applied and applied[0]['ok'] is False, applied
    rev = result['npa_items_revision'][0]['item_children'][0]['revisions'][0]
    assert not rev.get('not_valid'), 'ревизия не должна быть помечена not_valid'
    assert rev.get('valid_to') in (None, ''), 'активная ревизия не должна закрываться'


def test_element_not_valid_allowed_for_unreferenced_element():
    """Обычный repel (родитель не ссылается на элемент) продолжает работать."""
    result = {
        'npa_items_revision': [
            {
                'item_id': '16012_article_8',
                'item_type': 'article',
                'item_number': '8',
                'revisions': [
                    {'valid_from': '15.12.2017', 'valid_to': None,
                     'modified_by_id': '33699_article_1_point_9', 'body': []},
                ],
                'item_children': [
                    {
                        'item_id': '16012_article_8_part_1',
                        'item_type': 'part',
                        'item_number': '1',
                        'revisions': [
                            {'body': [
                                {'type': 'paragraph',
                                 'html_text': '<p>Отменяемая норма</p>',
                                 'order': 1},
                            ]},
                        ],
                    },
                ],
            },
        ],
    }
    verdict = {
        'issues': [
            {
                'corrections': [
                    {
                        'item_id': '16012_article_8_part_1',
                        'field': 'element_not_valid',
                        'value': '15.12.2017',
                        'modified_by_id': '33699_article_1_point_9',
                    },
                ],
            },
        ],
    }
    applied = pa.apply_corrections(result, verdict, '33699', '15.12.2017')
    assert applied and applied[0]['ok'] is True, applied
    rev = result['npa_items_revision'][0]['item_children'][0]['revisions'][0]
    assert rev.get('not_valid') == '33699_article_1_point_9'
    assert rev.get('valid_to') == '14.12.2017'


def test_not_valid_with_item_id_does_not_revoke_whole_npa():
    """Кейс 380-ЗС -> 269-ЗС: LLM вернул коррекцию field='not_valid' С item_id
    конкретного элемента. Ветка not_valid игнорировала item_id и помечала
    утратившим силу ВЕСЬ закон (corrected JSON: not_valid='15.12.2017',
    not_valid_npa='33699' на корне) — после импорта закон 269-ЗС исчез с
    сайта целиком. Коррекция с item_id должна применяться на уровне
    элемента (element_not_valid), а не корня."""
    result = {
        'npa_items_revision': [
            {
                'item_id': '16012_article_8',
                'item_type': 'article',
                'item_number': '8',
                'revisions': [
                    {'valid_from': '15.12.2017', 'valid_to': None,
                     'modified_by_id': '33699_article_1_point_9', 'body': []},
                ],
                'item_children': [
                    {
                        'item_id': '16012_article_8_part_1',
                        'item_type': 'part',
                        'item_number': '1',
                        'revisions': [
                            {'body': [
                                {'type': 'paragraph',
                                 'html_text': '<p>Отменяемая норма</p>',
                                 'order': 1},
                            ]},
                        ],
                    },
                ],
            },
        ],
    }
    verdict = {
        'issues': [
            {
                'path': 'Статья 8 > Часть 1',
                'corrections': [
                    {
                        'item_id': '16012_article_8_part_1',
                        'field': 'not_valid',
                        'value': '15.12.2017',
                        'modified_by_id': '33699_article_1_point_9',
                    },
                ],
            },
        ],
    }
    applied = pa.apply_corrections(result, verdict, '33699', '15.12.2017')
    assert applied and applied[0]['ok'] is True, applied
    # Целый закон НЕ должен быть отменён
    assert not result.get('not_valid'), (
        'коррекция not_valid с item_id не должна отменять весь НПА')
    # А элемент — должен быть помечен утратившим силу
    rev = result['npa_items_revision'][0]['item_children'][0]['revisions'][0]
    assert rev.get('not_valid') == '33699_article_1_point_9'
    assert rev.get('valid_to') == '14.12.2017'


def test_not_valid_with_item_id_referenced_by_parent_rejected():
    """Коррекция not_valid с item_id элемента, который всё ещё входит в
    действующую редакцию родителя (child_ref), отклоняется целиком —
    и, главное, не отменяет весь НПА (кейс: часть 7 статьи 7 перенесена
    новой редакцией 380-ЗС без изменений)."""
    result = {
        'npa_items_revision': [
            {
                'item_id': '16012_article_7',
                'item_type': 'article',
                'item_number': '7',
                'revisions': [
                    {
                        'valid_from': '15.12.2017',
                        'valid_to': None,
                        'mod_type': 'new_redaction',
                        'modified_by_id': '33699_article_1_point_9',
                        'body': [
                            {'type': 'child_ref',
                             'item_id': '16012_article_7_part_7', 'order': 1},
                        ],
                    },
                ],
                'item_children': [
                    {
                        'item_id': '16012_article_7_part_7',
                        'item_type': 'part',
                        'item_number': '7',
                        'revisions': [
                            {'body': [
                                {'type': 'paragraph',
                                 'html_text': '<p>Решение о предоставлении…</p>',
                                 'order': 1},
                            ]},
                        ],
                    },
                ],
            },
        ],
    }
    verdict = {
        'issues': [
            {
                'corrections': [
                    {
                        'item_id': '16012_article_7_part_7',
                        'field': 'not_valid',
                        'value': '15.12.2017',
                    },
                ],
            },
        ],
    }
    applied = pa.apply_corrections(result, verdict, '33699', '15.12.2017')
    assert applied and applied[0]['ok'] is False, applied
    # Ни элемент, ни весь закон не должны быть отменены
    rev = result['npa_items_revision'][0]['item_children'][0]['revisions'][0]
    assert not rev.get('not_valid')
    assert rev.get('valid_to') in (None, '')
    assert not result.get('not_valid'), (
        'отклонённая коррекция не должна отменять весь НПА')


def test_not_valid_without_item_id_still_revokes_whole_npa():
    """Штатный случай: not_valid без item_id (или __npa__) — отмена целого
    НПА — продолжает работать."""
    result = {'npa_items_revision': []}
    verdict = {
        'issues': [
            {
                'corrections': [
                    {'item_id': '__npa__', 'field': 'not_valid',
                     'value': '01.01.2021'},
                ],
            },
        ],
    }
    applied = pa.apply_corrections(result, verdict, '33699', '01.01.2021')
    assert applied and applied[0]['ok'] is True, applied
    assert result['not_valid'] == '01.01.2021'
    assert result['not_valid_npa'] == '33699'


def _make_repealed_result():
    """Элемент, корректно закрытый текущим изменяющим НПА (кейс 925-ЗС → 127-ЗС).

    Конвенция отмены («признать утратившим силу» новой ревизии не создаёт):
    исходный текст сохранён в закрытой ревизии, пометка not_valid выставлена,
    открытой ревизии (valid_to == '') нет.
    """
    return {
        'npa_items_revision': [
            {
                'item_id': '60050_article_8_part_4',
                'item_type': 'part',
                'item_number': '4',
                'revisions': [
                    {
                        'body': [
                            {'type': 'paragraph',
                             'html_text': '<p>Отменяемая норма</p>',
                             'order': 1},
                        ],
                        'valid_from': '29.04.2015',
                        'valid_to': '20.07.2026',
                        'not_valid': '143532_article_2_point_2_subpoint_б',
                        'revision_id': '69cc04fe-8538-437d-9f12-9443c3bd4d34',
                    },
                ],
            },
        ],
    }


def test_repealed_by_current_change_detected():
    result = _make_repealed_result()
    element = result['npa_items_revision'][0]
    assert pa._repealed_by_current_change(element, '143532') is True


def test_repealed_by_current_change_not_triggered_for_open_revision():
    """Открытая ревизия (действующая норма) — не «отменённая»."""
    result = _make_repealed_result()
    element = result['npa_items_revision'][0]
    element['revisions'][0]['valid_to'] = ''
    element['revisions'][0].pop('not_valid', None)
    assert pa._repealed_by_current_change(element, '143532') is False


def test_repealed_by_current_change_not_triggered_for_other_npa():
    """Пометка not_valid от ДРУГОГО закона — не основание отклонять правки
    текущего прогона."""
    result = _make_repealed_result()
    element = result['npa_items_revision'][0]
    element['revisions'][0]['not_valid'] = '59121_article_1_point_6_subpoint_ж'
    assert pa._repealed_by_current_change(element, '143532') is False


def test_element_html_correction_on_repealed_element_rejected():
    """Кейс 925-ЗС → 127-ЗС: ИИ принял строку-заглушку after за утрату текста
    и потребовал «восстановить» текст отменённой нормы. Коррекция element_html
    на таком элементе должна отклоняться — иначе создаётся открытая ревизия
    с not_valid=False, «воскрешающая» отменённую норму."""
    result = _make_repealed_result()
    verdict = {
        'issues': [
            {
                'index': 2,
                'path': 'Статья 8 > Часть 4',
                'corrections': [
                    {
                        'item_id': '60050_article_8_part_4',
                        'field': 'element_html',
                        'value': '<p>Отменяемая норма</p>',
                    },
                ],
            },
        ],
    }
    applied = pa.apply_corrections(result, verdict, '143532', '21.07.2026')
    assert applied and applied[0]['ok'] is False, applied
    element = result['npa_items_revision'][0]
    assert len(element['revisions']) == 1, (
        'новая ревизия для отменённой нормы создаваться не должна')
    rev = element['revisions'][0]
    assert rev.get('valid_to') == '20.07.2026'
    assert rev.get('not_valid') == '143532_article_2_point_2_subpoint_б'
    assert pa._repealed_by_current_change(element, '143532') is True


def test_element_html_new_rev_on_repealed_element_rejected():
    """Прямой вызов с field='element_html_new_rev' на отменённом элементе
    также отклоняется (дублирующая защита)."""
    result = _make_repealed_result()
    verdict = {
        'issues': [
            {
                'corrections': [
                    {
                        'item_id': '60050_article_8_part_4',
                        'field': 'element_html_new_rev',
                        'value': '<p>Отменяемая норма</p>',
                    },
                ],
            },
        ],
    }
    applied = pa.apply_corrections(result, verdict, '143532', '21.07.2026')
    assert applied and applied[0]['ok'] is False, applied
    element = result['npa_items_revision'][0]
    assert len(element['revisions']) == 1
    assert element['revisions'][0].get('not_valid') == \
        '143532_article_2_point_2_subpoint_б'


def test_repel_law_change_entry_keeps_before_text():
    """Запись kind=repel_law: before — исходный текст закрытой ревизии,
    after — статусная строка с явным указанием, что это штатное конечное
    состояние (а не утрата текста)."""
    changes = pa.collect_changes(
        _make_repealed_result(), {'npa_id': '143532', 'npa_number': '925-ЗС'})
    assert len(changes) == 1
    entry = changes[0]
    assert entry['kind'] == 'repel_law'
    assert 'Отменяемая норма' in entry['before']
    assert 'помечен утратившим силу' in entry['after']
    assert 'before' in entry['after'] or 'закрытой ревизии' in entry['after']


# --------------- скоуп инструкций (кейс 516-ЗС: статья 2 правит Закон 51-ЗС)
def _two_law_change():
    """Изменяющий закон из двух статей: статья 1 правит 127-ЗС, статья 2 — 51-ЗС."""
    return {
        'npa_id': '59121',
        'npa_number': '516-ЗС',
        'npa_items_revision': [
            {
                'item_id': '59121_article_1', 'item_type': 'article',
                'item_number': '1',
                'revisions': [{'body': [{
                    'type': 'paragraph',
                    'html_text': '<p>Внести в Закон города Севастополя от 17 апреля '
                                 '2015 года № 127-ЗС следующие изменения:</p>',
                    'order': 1,
                }]}],
            },
            {
                'item_id': '59121_article_2', 'item_type': 'article',
                'item_number': '2',
                'revisions': [{'body': [{
                    'type': 'paragraph',
                    'html_text': '<p>Внести в Закон города Севастополя от 25 июля '
                                 '2014 года № 51-ЗС следующие изменения:</p>',
                    'order': 1,
                }]}],
            },
        ],
    }


def test_extract_instructions_text_scopes_to_target_law():
    """Разделы изменяющего закона, не относящиеся к целевому НПА, отбрасываются
    (иначе постанализ требует применить чужие правки — ложное срабатывание
    «отсутствуют изменения в статью 16 Закона 51-ЗС», прогон 23.09.2026)."""
    change = _two_law_change()
    text = pa.extract_instructions_text(change, '127-ЗС')
    assert '127-ЗС' in text
    assert '51-ЗС' not in text
    # Без номера целевого закона или при нестандартном формате («ЗС-127»)
    # фильтр не применяется — страховка от ложной фильтрации.
    assert '51-ЗС' in pa.extract_instructions_text(change, '')
    assert '51-ЗС' in pa.extract_instructions_text(change, 'ЗС-127')


def test_build_prompt_scopes_instructions_and_adds_scope_block():
    result = {'npa_number': '127-ЗС'}
    prompt = pa.build_prompt(result, _two_law_change(), [])
    instructions = prompt.split('<instructions>', 1)[1].split('</instructions>', 1)[0]
    assert '127-ЗС' in instructions
    assert '51-ЗС' not in instructions
    assert '<scope>' in prompt
    assert 'НЕ является ошибкой' in prompt
    # Правило против фиктивных претензий (expected ≡ actual)
    assert 'НЕ репортите issue, если expected и actual' in prompt


def test_is_vacuous_issue():
    # Совпадение без учёта регистра/пунктуации — фиктивная претензия
    assert pa._is_vacuous_issue(
        {'expected': '<p>Текст нормы.</p>', 'actual': '<p>текст  нормы .</p>'})
    # Содержательное расхождение — не фиктивная
    assert not pa._is_vacuous_issue(
        {'expected': '<p>Текст нормы.</p>', 'actual': '<p>Другой текст.</p>'})
    # Без текстов expected/actual (пробелы покрытия и т.п.) — не фильтруется
    assert not pa._is_vacuous_issue({'issue': 'нет текстов'})


def test_run_post_analysis_filters_vacuous_issue(tmp_path, monkeypatch):
    """Претензия с expected ≡ actual (кейс 516-ЗС, обе претензии повторного
    пост-анализа 23.09.2026 01:04) отсеивается — статус correct, corrected не
    создаётся."""
    orig_file, change = _write_result_file(tmp_path, _make_result())
    result_data = json.loads(
        (tmp_path / '127_2015_04_17_izm_516_2019_07_08.json').read_text(encoding='utf-8'))
    verdict = {
        'status': 'incorrect',
        'summary': 'Некорректно применено исключение слов в статье 6.',
        'issues': [{
            'index': 17,
            'path': 'Статья 6 > Часть 3',
            'issue': 'фиктивная претензия при идентичных expected/actual',
            'expected': GOOD_HTML,
            'actual': GOOD_HTML.replace('Положение', 'положение', 1),
            'fix': 'no-op',
            'corrections': [{
                'item_id': '127_law_1_art_5',
                'field': 'element_html',
                'value': GOOD_HTML,
            }],
        }],
    }
    monkeypatch.setattr(
        pa, 'ask_ollama', lambda *a, **k: json.dumps(verdict, ensure_ascii=False))
    res = pa.run_post_analysis(str(orig_file), result_data, change,
                               model='stub', backend='kilo_gateway')
    assert res['status'] == 'correct', res
    assert res['issues'] == 0
    assert res['corrected_path'] is None
    report = Path(res['report_path']).read_text(encoding='utf-8')
    assert 'КОРРЕКТНО' in report
    assert 'expected/actual' in report


# ------------- list-записи подсветки (формат change_applier, кейс «Севастоля»)
def test_sanitize_highlights_handles_list_entries():
    """Записи [текст, "M-N»] сверяются с текстом, а не проходят мимо фильтра."""
    highlights = {
        'previous_edition': {'deletion': [], 'addition': [],
                             'difference': [['в городе Севастополе', '1-1']]},
        'current_edition': {'deletion': [], 'addition': [],
                            'difference': [['города Севастоля', '1-1']]},
    }
    old = '<p>8) получать гонорары … должность в городе Севастополе;</p>'
    new = '<p>8) получать гонорары … должность города Севастополя;</p>'
    cleaned = pa._sanitize_highlights(highlights, old, new)
    assert cleaned['previous_edition']['difference'] == [['в городе Севастополе', '1-1']]
    assert cleaned['current_edition']['difference'] == []


def test_element_html_correction_regenerates_stale_list_highlights():
    """Коррекция element_html при полностью устаревшей list-подсветке пересобирает
    её по diff «предыдущая ревизия → исправленный текст» вместо сохранения ложных
    меток (кейс 516-ЗС: подсветка «города Севастоля» после исправления опечатки)."""
    result = _make_result()
    rev = result['npa_items_revision'][0]['revisions'][-1]
    rev['highlights'] = {
        'previous_edition': {'deletion': [], 'addition': [],
                             'difference': [['НЕТ В СТАРОМ ТЕКСТЕ', '1-1']]},
        'current_edition': {'deletion': [], 'addition': [],
                            'difference': [['ГОРОДА СЕВАСТОЛЯ', '1-1']]},
    }
    corr = {'item_id': '127_law_1_art_5', 'field': 'element_html', 'value': GOOD_HTML}
    ok, err = pa._apply_correction(result, corr, '516', '19.07.2019')
    assert ok, err
    dumped = json.dumps(rev.get('highlights'), ensure_ascii=False)
    assert 'СЕВАСТОЛЯ' not in dumped
    assert 'НЕТ В СТАРОМ ТЕКСТЕ' not in dumped
    # Подсветка пересобрана по diff ORIGINAL_HTML → GOOD_HTML
    assert rev['highlights']['current_edition']['addition']


# ---------- хвост «поисковых» ссылок после JSON (кейс 516-ЗС → 127-ЗС, 23.09.2026)

_SEARCH_TAIL = (
    "\n\n---\n"
    "[1] [Горячие документы. Магаданская область. 30 января 2016]"
    "(https://www.garant.ru/hotlaw/magadan/archive/2016/01/30/) | 来源: 未知来源\n"
    "[2] [Закон города Севастополя от 8 июля 2019 № 516-ЗС]"
    "(https://sevzakon.ru/view/laws/bank/2019/zakon_n_516_zs_ot_08_07_2019/"
    "tekst_zakonoproekta/) | 来源: 未知来源"
)


def _issue():
    return {
        'index': 0,
        'path': 'Статья 5',
        'issue': 'часть текста удалена без указания в инструкции',
        'expected': GOOD_HTML,
        'actual': BAD_HTML,
        'fix': 'восстановить окончание предложения',
        'corrections': [{
            'item_id': '127_law_1_art_5',
            'field': 'element_html',
            'value': GOOD_HTML,
        }],
    }


def test_run_post_analysis_trailing_search_tail_applies_corrections(tmp_path,
                                                                   monkeypatch):
    """Валидный JSON + хвост из цитат ссылок не должен терять коррекции.

    Прогон 516-ЗС → 127-ЗС от 23.09.2026: бэкенд дописал после вердикта
    «---\\n[1] … | 来源: 未知来源», ``repair_json`` дочитал хвост и превратил
    объект в массив — пост-анализ падал в ``status=error, issues=0,
    corrected_path=null``, хотя все 5 претензий с коррекциями были в ответе.
    """
    orig_file, change = _write_result_file(tmp_path, _make_result())
    result_data = json.loads(
        (tmp_path / '127_2015_04_17_izm_516_2019_07_08.json').read_text(encoding='utf-8'))
    verdict = {'status': 'incorrect', 'summary': 'Найдены ошибки внесения.',
               'issues': [_issue()]}
    answer = json.dumps(verdict, ensure_ascii=False, indent=2) + _SEARCH_TAIL

    monkeypatch.setattr(pa, 'ask_ollama', lambda *a, **k: answer)
    res = pa.run_post_analysis(str(orig_file), result_data, change,
                               model='stub', backend='kilo_gateway')
    assert res['status'] == 'incorrect', res
    assert res['issues'] == 1, res
    corrected = res['corrected_path']
    assert corrected and Path(corrected).exists()
    report = Path(res['report_path']).read_text(encoding='utf-8')
    assert 'ОШИБКИ' in report
    assert 'восстановить окончание' in report
    assert '[2] [Закон города Севастополя' in report


def test_run_post_analysis_passes_raw_json_to_single_parser(tmp_path,
                                                           monkeypatch):
    """HTTP-слой не ремонтирует JSON заранее: хвост доступен пост-анализу."""
    orig_file, change = _write_result_file(tmp_path, _make_result())
    result_data = json.loads(
        (tmp_path / '127_2015_04_17_izm_516_2019_07_08.json').read_text(encoding='utf-8'))
    answer = json.dumps(
        {'status': 'incorrect', 'issues': [_issue()]}, ensure_ascii=False) + _SEARCH_TAIL
    seen = {}

    def _ask(*args, **kwargs):
        seen.update(kwargs)
        return answer

    monkeypatch.setattr(pa, 'ask_ollama', _ask)
    res = pa.run_post_analysis(
        str(orig_file), result_data, change,
        model='stub', backend='kilo_gateway')
    assert seen['repair_json'] is False
    assert res['status'] == 'incorrect'
    assert res['corrected_path'] and Path(res['corrected_path']).exists()


def test_run_post_analysis_derives_status_from_issues(tmp_path, monkeypatch):
    """Ответ без поля status, но со списком претензий — статус выводится по факту."""
    orig_file, change = _write_result_file(tmp_path, _make_result())
    result_data = json.loads(
        (tmp_path / '127_2015_04_17_izm_516_2019_07_08.json').read_text(encoding='utf-8'))
    verdict = {'summary': 'Найдены ошибки внесения.', 'issues': [_issue()]}

    monkeypatch.setattr(pa, 'ask_ollama',
                        lambda *a, **k: json.dumps(verdict, ensure_ascii=False))
    res = pa.run_post_analysis(str(orig_file), result_data, change,
                               model='stub', backend='kilo_gateway')
    assert res['status'] == 'incorrect', res
    assert res['issues'] == 1, res
    assert res['corrected_path'] and Path(res['corrected_path']).exists()
