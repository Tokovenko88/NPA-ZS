"""Тесты модуля пост-анализа внесения изменений (src/revision/post_analysis.py)."""
import importlib.util
import json
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
