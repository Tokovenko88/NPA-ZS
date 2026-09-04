"""Тесты агент-классификатора и механизма возобновления (чекпойнта)."""
import importlib.util
import json
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

from npazs.compare.agent_compare import (  # noqa: E402
    DEFAULT_PROMPT,
    _apply_guards,
    _direction_neutral_explanation,
    _is_same_npa,
    _parse_classification,
    build_classify_prompt,
    mechanical_resolve,
)
from npazs.compare.differ import DiffRecord  # noqa: E402
from npazs.compare.runner import (  # noqa: E402
    CompareOptions,
    _diffs_from_json,
    _diffs_to_json,
    _fingerprint,
    _load_checkpoint,
    _load_prompt_template,
    _save_checkpoint,
)


def _diff():
    return DiffRecord(
        path='статья 2',
        path_key=(('article', '2'),),
        kind='change',
        old='решения',
        new='акты',
        count=7,
    )


# ---------------------------------------------------------- _parse_classification
def test_parse_plain_array():
    parsed = _parse_classification(
        '[{"id": 0, "reason": "amendment", "source_npa": "41-ЗС", '
        '"explanation": "правка"}]'
    )
    assert parsed == [
        {"id": 0, "reason": "amendment", "source_npa": "41-ЗС", "explanation": "правка"}
    ]


def test_parse_markdown_fenced():
    text = '```json\n[{"id": 0, "reason": "unclear"}]\n```'
    assert _parse_classification(text) == [{"id": 0, "reason": "unclear"}]


def test_parse_dict_wrapper():
    data = {"items": [{"id": 1, "reason": "formatting"}]}
    parsed = _parse_classification(json.dumps(data, ensure_ascii=False))
    assert parsed == [{"id": 1, "reason": "formatting"}]


def test_parse_repair_broken_json():
    # одинарные кавычки — чинится json_repair
    parsed = _parse_classification("[{'id': 0, 'reason': 'amendment'}]")
    assert parsed and parsed[0]['reason'] == 'amendment'


def test_parse_garbage_and_empty():
    assert _parse_classification('') == []
    assert _parse_classification('модель не ответила') == []
    # словарь без известных ключей-обёрток
    assert _parse_classification('{"a": 1}') == []


# ------------------------------------------------------------------ промпт
def test_build_classify_prompt_substitution():
    template = _load_prompt_template() or DEFAULT_PROMPT
    prompt = build_classify_prompt(template, [_diff()], '[{"note": true}]', '103-ЗС')
    assert '{diff_json}' not in prompt
    assert '{notes_json}' not in prompt
    assert '{target_number}' not in prompt
    assert '103-ЗС' in prompt
    assert 'решения' in prompt and 'акты' in prompt
    # в промпте из файла пример ответа — одинарными скобками
    assert '[{"id": 0' in template


def test_default_prompt_directly_usable():
    prompt = build_classify_prompt(DEFAULT_PROMPT, [_diff()], '[]', '')
    assert '"id": 0' in prompt or '"id":0' in prompt


# -------------------------------------------------------- чекпойнт / resume
def test_diffs_json_round_trip():
    diffs = [
        _diff(),
        DiffRecord(
            path='статья 3', path_key=(('article', '3'), ('part', '1')),
            kind='add', new='Новый элемент',
        ),
    ]
    payload = json.loads(json.dumps(_diffs_to_json(diffs)))
    restored = _diffs_from_json(payload)
    got = [(d.path, d.kind, d.path_key, d.old, d.new) for d in restored]
    expected = [(d.path, d.kind, d.path_key, d.old, d.new) for d in diffs]
    assert got == expected


def test_checkpoint_round_trip(tmp_path):
    path = str(tmp_path / 'report.md.checkpoint.json')
    diffs = [_diff()]
    _save_checkpoint(path, 'fp001', diffs, processed=1, started_at='2026-01-01T00:00:00')
    data = _load_checkpoint(path)
    assert data['fingerprint'] == 'fp001'
    assert data['processed'] == 1
    restored = _diffs_from_json(data['diffs'])
    assert restored[0].path == 'статья 2'
    assert restored[0].path_key == (('article', '2'),)


def test_load_checkpoint_missing(tmp_path):
    assert _load_checkpoint(str(tmp_path / 'nope.json')) is None


def test_fingerprint_changes_with_inputs(tmp_path):
    a = tmp_path / 'a.rtf'
    b = tmp_path / 'b.docx'
    a.write_text('x', encoding='utf-8')
    b.write_text('y', encoding='utf-8')
    o1 = CompareOptions(ours_path=str(a), theirs_path=str(b), mode='agent')
    o2 = CompareOptions(ours_path=str(a), theirs_path=str(b), mode='agent', model='qwen')
    assert _fingerprint(o1, '103-ЗС') == _fingerprint(o1, '103-ЗС')
    assert _fingerprint(o1, '103-ЗС') != _fingerprint(o2, '103-ЗС')


# --------------------------------------------------------- mechanical_resolve
def test_mechanical_resolve_amendment_from_notes():
    diff = _diff()
    notes = {
        diff.path: [{
            'text': 'В соответствии с законом…',
            'npa_numbers': ['41-ЗС/1038'],
            'dates': ['01.01.2025'],
            'valid_from': '01.01.2025',
        }],
    }
    mechanical_resolve(diff, notes, '103-ЗС', lambda tn, key: '')
    assert diff.reason == 'amendment'
    assert diff.source_npa == '41-ЗС/1038'
    assert diff.change_text  # текст изменения подтянут из базы


def test_mechanical_resolve_unclear_with_original():
    diff = _diff()
    mechanical_resolve(diff, {}, '103-ЗС', lambda tn, key: 'оригинальный текст')
    assert diff.reason == 'unclear'
    assert diff.original_text == 'оригинальный текст'


def test_mechanical_resolve_unclear_no_target():
    diff = _diff()
    mechanical_resolve(diff, {}, '', lambda tn, key: 'x')
    assert diff.reason == 'unclear'
    assert diff.original_text == ''


# --------------------------------------------------- гварды классификации
def _diff_kind(kind, old='', new=''):
    return DiffRecord(
        path='статья 2', path_key=(('article', '2'),),
        kind=kind, old=old, new=new, count=7,
    )


def test_guards_formatting_overridden_to_unclear():
    # reason=formatting невозможен для содержательного различия основного
    # списка: модель ошибается, и «Только оформление» не должно попасть в отчёт.
    diff = _diff_kind('change', old='интересов', new='интересы')
    diff.reason = 'formatting'
    diff.explanation = 'Отличие только в оформлении (пробелы), содержание не изменилось.'
    _apply_guards(diff, '127-ЗС')
    assert diff.reason == 'unclear'
    # ложная формулировка модели «содержание не изменилось» отброшена
    assert 'содержание не изменилось' not in diff.explanation


def test_guards_add_direction_contradiction_replaced():
    # add = текст есть ТОЛЬКО в проекте; объяснение «в проекте отсутствует»
    # инвертировано и должно быть заменено нейтральным, согласованным с видом.
    diff = _diff_kind('add', old='фрагмент только в проекте')
    diff.reason = 'implementation_gap'
    diff.explanation = 'В проекте отсутствует третья часть статьи 6.'
    _apply_guards(diff, '127-ЗС')
    assert 'отсутствует' in diff.explanation  # но теперь про правовую систему
    assert 'правовой системы' in diff.explanation
    assert 'в проекте' not in diff.explanation.lower()


def test_guards_remove_direction_contradiction_replaced():
    diff = _diff_kind('remove', new='фрагмент только в правовой системе')
    diff.reason = 'amendment'
    diff.explanation = 'В правовой системе эта норма отсутствует.'
    _apply_guards(diff, '127-ЗС')
    assert 'правовой системы' in diff.explanation


def test_guards_direction_kept_when_consistent():
    diff = _diff_kind('add', old='фрагмент')
    diff.reason = 'amendment'
    diff.explanation = 'Фрагмент добавлен в проект нормой 516-ЗС.'
    _apply_guards(diff, '127-ЗС')
    assert diff.reason == 'amendment'
    assert 'добавлен' in diff.explanation


def test_guards_source_npa_equal_target_dropped():
    # source_npa = целевой НПА — это не изменяющий акт, а сам закон.
    diff = _diff_kind('change', old='а', new='б')
    diff.reason = 'amendment'
    diff.source_npa = '127-ЗС'
    _apply_guards(diff, '127-ЗС')
    assert diff.source_npa == ''


def test_guards_source_npa_other_kept():
    diff = _diff_kind('change', old='а', new='б')
    diff.reason = 'amendment'
    diff.source_npa = '516-ЗС'
    _apply_guards(diff, '127-ЗС')
    assert diff.source_npa == '516-ЗС'


def test_is_same_npa():
    assert _is_same_npa('127-ЗС', '№ 127-ЗС')
    assert _is_same_npa('127-ЗС', '127')
    assert not _is_same_npa('127-ЗС', '516-ЗС')


def test_direction_neutral_explanation():
    assert 'проекта' in _direction_neutral_explanation(_diff_kind('add'))
    assert 'правовой системы' in _direction_neutral_explanation(_diff_kind('remove'))
    assert _direction_neutral_explanation(_diff_kind('change')) == ''


def test_prompt_documents_direction_semantics():
    # Промпт обязан объяснить модели смысл kind/old/new, иначе модель
    # инвертирует направление («в проекте отсутствует» при add).
    template = _load_prompt_template() or DEFAULT_PROMPT
    for needle in ('old', 'new', 'ДОКУМЕНТА ПРОЕКТА', 'ДОКУМЕНТА ПРАВОВОЙ СИСТЕМЫ', 'add', 'remove'):
        assert needle in template
    assert 'должно противоречить направлению' in template.lower()
