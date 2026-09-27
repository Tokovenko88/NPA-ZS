"""Тесты исправлений прогона 516-ЗС → 127-ЗС (23.09.2026).

Дефекты, которые здесь ловятся:

1. «поисковый» хвост (``---\\n[1] … | 来源: 未知来源``) после валидного JSON
   ломал разбор вердикта пост-анализа — ``repair_json`` превращал его в
   массив, пост-анализ падал в ``status отсутствует`` и терял коррекции;
2. склейка слов (``обращенияграждан``) и лишний пробел (``Федерации ;``)
   на границах детерминированного внесения правок;
3. «висячая» „»“ после исключения фразы с вложенной цитатой;
4. точка посреди предложения при инструкции «дополнить словами»
   (``… Уполномоченного. в порядке, предусмотренном … Закона``).
"""
import importlib.util
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "npazs_bootstrap", _ROOT / "src" / "bootstrap.py"
)
assert _spec is not None and _spec.loader is not None
_bootstrap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bootstrap)
_bootstrap.bootstrap()

from npazs.revision.ai_utils import _extract_first_json_value, _repair_json_answer
from npazs.revision.change_applier import (
    _append_before_terminal_punct,
    _ensure_addition_applied,
    _ensure_word_replacement_applied,
)
from npazs.revision.html_utils import (
    _join_two_fragments,
    apply_word_exclusion_fuzzy,
    apply_word_replacement_fuzzy,
    drop_orphan_close_quote,
    find_text_boundary_defects,
    html_to_plain_text,
    join_edit_span,
    normalize_space_boundaries,
    parse_addition_anchor,
    parse_ai_response_for_prompt4,
    parse_word_addition,
    parse_word_exclusion,
)

# ============================================================ 1. JSON + хвост

_SEARCH_TAIL = (
    "\n\n---\n"
    "[1] [Горячие документы. Магаданская область. 30 января 2016]"
    "(https://www.garant.ru/hotlaw/magadan/archive/2016/01/30/) | 来源: 未知来源\n"
    "[2] [Закон города Севастополя от 8 июля 2019 № 516-ЗС]"
    "(https://sevzakon.ru/view/laws/bank/2019/zakon_n_516_zs_ot_08_07_2019/"
    "tekst_zakonoproekta/) | 来源: 未知来源"
)


def _verdict():
    return {
        'status': 'incorrect',
        'summary': 'Выявлены ошибки применения изменений.',
        'issues': [
            {
                'index': 21,
                'path': 'Статья 6 > Часть 5 > Пункт 2)',
                'issue': 'Остался лишний пробел перед точкой с запятой.',
                'expected': '<p>копия паспорта гражданина Российской Федерации;</p>',
                'actual': '<p>копия паспорта гражданина Российской Федерации ;</p>',
                'fix': 'Убрать лишний пробел.',
                'corrections': [{
                    'item_id': '60050_article_6_part_5_point_2',
                    'field': 'element_html',
                    'value': '<p>копия паспорта гражданина Российской Федерации;</p>',
                }],
            },
        ],
    }


def test_extract_first_json_value_splits_object_and_tail():
    raw = json.dumps(_verdict(), ensure_ascii=False, indent=2) + _SEARCH_TAIL
    body, tail = _extract_first_json_value(raw)
    assert json.loads(body)['status'] == 'incorrect'
    assert 'garant.ru' in tail
    assert body + tail == raw


def test_extract_first_json_value_ignores_braces_inside_strings():
    src = '{"s": "a } b ] c \\" d", "status": "correct"} хвост'
    body, tail = _extract_first_json_value(src)
    assert json.loads(body) == {'s': 'a } b ] c " d', 'status': 'correct'}
    assert tail == ' хвост'


def test_extract_first_json_value_unbalanced_returns_none():
    assert _extract_first_json_value('{"status": "incorrect", "issues": [') == (None, '')
    assert _extract_first_json_value('обычный текст') == (None, '')


def test_repair_json_answer_drops_search_tail():
    """Кейс пост-анализа 516-ЗС: валидный JSON + хвост из ссылок.

    Раньше ``repair_json`` дочитывал хвост и превращал вердикт в массив —
    пост-анализ отвечал «status отсутствует» и не применял коррекции.
    """
    raw = json.dumps(_verdict(), ensure_ascii=False, indent=2) + _SEARCH_TAIL
    logs = []
    out = _repair_json_answer(raw, lambda msg, level=None: logs.append((level, msg)))
    assert out is not None
    verdict = json.loads(out)
    assert verdict['status'] == 'incorrect'
    assert len(verdict['issues']) == 1
    assert verdict['issues'][0]['corrections'][0]['item_id'] == \
        '60050_article_6_part_5_point_2'
    assert any('хвост' in msg for _level, msg in logs)


def test_repair_json_answer_fenced_json_with_tail():
    raw = '```json\n' + json.dumps(_verdict(), ensure_ascii=False) + '\n```' + _SEARCH_TAIL
    verdict = json.loads(_repair_json_answer(raw, None))
    assert verdict['status'] == 'incorrect'


def test_repair_json_answer_array_answer_stays_array():
    """Ответ stage-3 — валидный массив: его нельзя ломать."""
    src = json.dumps([{'revision_number': '1)->а)', 'type': 'add'}], ensure_ascii=False)
    assert json.loads(_repair_json_answer(src, None)) == [
        {'revision_number': '1)->а)', 'type': 'add'}]


def test_repair_json_answer_array_with_tail():
    src = '[{"revision_number": "1)->а)"}]' + _SEARCH_TAIL
    assert json.loads(_repair_json_answer(src, None)) == [
        {'revision_number': '1)->а)'}]


def test_repair_json_answer_json_prefix():
    src = 'json\n{"status": "correct", "issues": []}'
    assert json.loads(_repair_json_answer(src, None))['status'] == 'correct'


def test_repair_json_answer_truncated_json_still_repairs():
    src = '{"status": "incorrect", "issues": [{"index": 1, "path": "Статья 6"'
    out = _repair_json_answer(src, None)
    assert out is not None
    assert isinstance(json.loads(out), dict)


def test_repair_json_answer_plain_text_skipped():
    assert _repair_json_answer('просто текст без JSON', None) is None
    assert _repair_json_answer('', None) == ''


# ================================================= 2. Границы правок в HTML

def test_join_two_fragments_restores_space_after_punctuation_span():
    """Замена «, касающиеся» → «граждан, …»: запятая+пробел ушли в фразу."""
    assert _join_two_fragments('рассматривает обращения', 'граждан, объединений',
                               True) == 'рассматривает обращения граждан, объединений'


def test_join_two_fragments_drops_space_before_semicolon():
    assert _join_two_fragments('Российской Федерации ', ';') == \
        'Российской Федерации;'
    # пробел ПОСЛЕ «;» — это разделитель следующего текста, его не трогаем
    assert _join_two_fragments('Российской Федерации ', '; ') == \
        'Российской Федерации; '
    assert _join_two_fragments('Российской Федерации', '; части') == \
        'Российской Федерации; части'


def test_join_two_fragments_keeps_word_intact_without_broken_boundary():
    """Правка внутри слова не должна его разъединять."""
    assert _join_two_fragments('законо', 'тельный') == 'законотельный'
    assert _join_two_fragments('законо', 'тельный', True) == 'законо тельный'


def test_join_edit_span_full_chain():
    out = join_edit_span(
        '<p>рассматривает обращения', ', касающиеся', ' нарушения прав;',
        'граждан, объединений')
    assert out == '<p>рассматривает обращения граждан, объединений нарушения прав;'


def test_replacement_restores_boundary_space():
    """Контрольный кейс ст.10 ч.2 п.1: «обращенияграждан» → «обращения граждан»."""
    html = ('<p class="justifyfull">осуществляет прием граждан, рассматривает '
            'обращения, касающиеся нарушения прав и законных интересов детей;</p>')
    out = apply_word_replacement_fuzzy(
        html, ', касающиеся', 'граждан, объединений граждан, организаций, '
                              'содержащие предложения по вопросам, касающимся')
    assert out is not None
    assert 'обращения граждан, объединений' in out
    assert 'обращенияграждан' not in out


def test_ensure_word_replacement_no_glue_after_restore():
    """Diff-гвард пересобирает абзац — и тоже не должен склеивать слова."""
    desc = ('Изменение 1 :\n<p>слова «касается» заменить словами '
            '«граждан, объединений»;</p>')
    old = ('<p class="justifyfull">осуществляет прием граждан, рассматривает '
           'обращения, касается нарушения прав и жалобы на решения органов;</p>')
    ai = ('<p class="justifyfull">осуществляет прием граждан, рассматривает '
          'обращенияграждан, объединений нарушения прав и жалобы на решения '
          'органов;</p>')
    fixed = _ensure_word_replacement_applied(desc, old, ai)
    assert 'обращенияграждан' not in fixed


def test_exclusion_drops_space_before_semicolon():
    """Контрольный кейс ст.6 ч.5 п.2: «Федерации ;» → «Федерации;»."""
    html = ('<p class="justifyfull">копия паспорта гражданина Российской Федерации '
            'или копия основного документа, содержащего указание на гражданство '
            'кандидата;</p>')
    phrase = ('или копия основного документа, содержащего указание на гражданство '
              'кандидата')
    fixed, removed = apply_word_exclusion_fuzzy(html, phrase)
    assert removed
    assert fixed == ('<p class="justifyfull">копия паспорта гражданина '
                     'Российской Федерации;</p>')


def test_normalize_space_boundaries_only_touches_text_nodes():
    html = ('<p class="justifyfull">копия паспорта гражданина Российской Федерации '
            ';</p><a href="a ;b">ссылка</a>')
    out = normalize_space_boundaries(html)
    assert 'Федерации;' in out
    assert 'Федерации ;' not in out
    assert 'href="a ;b"' in out  # атрибуты не трогаем


def test_parse_ai_response_normalizes_space_before_semicolon():
    """Ответ ИИ на промпт 4 с «Федерации ;» нормализуется при разборе."""
    payload = json.dumps({
        'html': '<p class="justifyfull">копия паспорта гражданина Российской '
                'Федерации ;</p>',
        'highlights': None,
    }, ensure_ascii=False)
    html, _highlights = parse_ai_response_for_prompt4(payload, '')
    assert 'Федерации;' in html
    assert 'Федерации ;' not in html


# ================================================ 3. «Висячая» закрывающая »

def test_drop_orphan_close_quote_removes_quote_introduced_by_edit():
    source = ('<p>законодательной инициативы, указанными в статье 3 Закона '
              '«О правовых актах города Севастополя».</p>')
    broken = '<p>законодательной инициативы».</p>'
    assert drop_orphan_close_quote(broken, source) == \
        '<p>законодательной инициативы.</p>'


def test_drop_orphan_close_quote_keeps_balanced_quotes():
    source = '<p>цитата</p>'
    fixed = '<p>«цитата»</p>'
    assert drop_orphan_close_quote(fixed, source) == fixed


def test_drop_orphan_close_quote_keeps_preexisting_orphan():
    """Дисбаланс был уже в исходнике — правка его не «чинит» молча."""
    source = '<p>доб» остаток цитаты</p>'
    assert drop_orphan_close_quote(source, source) == source


def test_exclusion_with_shared_quote_leaves_no_orphan():
    desc = ('<p>слова «, указанными в статье 3 Закона города Севастополя от '
            '29 сентября 2015 года <a href="http://sevzakon.ru/view/laws/bank/'
            '09_2015/">№ 185-ЗС</a> «О правовых актах города Севастополя» '
            'исключить;</p>')
    phrase = parse_word_exclusion(desc)
    assert phrase and phrase.endswith('Севастополя»')
    html = ('<p class="justifyfull">Предложения о кандидатах на должность '
            'Уполномоченного вносятся в Законодательное Собрание города '
            'Севастополя субъектами права законодательной инициативы, указанными '
            'в статье 3 Закона города Севастополя от 29 сентября 2015 года '
            '<a href="view/laws/bank/09_2015/">№ 185-ЗС</a> «О правовых актах '
            'города Севастополя».</p>')
    fixed, _removed = apply_word_exclusion_fuzzy(html, phrase)
    plain = html_to_plain_text(fixed)
    assert plain.endswith('законодательной инициативы.')
    assert '»' not in plain
    assert 'указанными' not in plain


# ================================================ 4. Инструкция «дополнить»

_ADD_DESC = ('<p>часть 8 дополнить словами «в порядке, предусмотренном статьей 6 '
             'настоящего Закона»;</p>')
_ADD_PHRASE = 'в порядке, предусмотренном статьей 6 настоящего Закона'
_ADD_OLD = (
    '<p class="justifyfull">8. В случае досрочного прекращения полномочий '
    'Уполномоченного новый Уполномоченный должен быть назначен Законодательным '
    'Собранием города Севастополя в течение 60 дней со дня досрочного '
    'прекращения полномочий предыдущего Уполномоченного.</p>')
_ADD_AI_BAD = (
    '<p class="justifyfull">8. В случае досрочного прекращения полномочий '
    'Уполномоченный новый Уполномоченный должен быть назначен Законодательным '
    'Собранием города Севастополя в течение 60 дней со дня досрочного '
    'прекращения полномочий предыдущего Уполномоченного. в порядке, '
    'предусмотренном статьей 6 настоящего Закона</p>')
_ADD_AI_GOOD = (
    '<p class="justifyfull">8. В случае досрочного прекращения полномочий '
    'Уполномоченный новый Уполномоченный должен быть назначен Законодательным '
    'Собранием города Севастополя в течение 60 дней со дня досрочного '
    'прекращения полномочий предыдущего Уполномоченного в порядке, '
    'предусмотренном статьей 6 настоящего Закона.</p>')


def test_parse_word_addition():
    assert parse_word_addition(_ADD_DESC) == _ADD_PHRASE
    assert parse_word_addition(
        '<p>в пункте 1 после слов «на внесение его кандидатуры» дополнить '
        'словами «в Законодательное Собрание города Севастополя»;</p>') == \
        'в Законодательное Собрание города Севастополя'


def test_parse_word_addition_ignores_other_instructions():
    assert parse_word_addition('<p>пункт 9 дополнить предложением:</p>') is None
    assert parse_word_exclusion(_ADD_DESC) is None


def test_parse_addition_anchor():
    assert parse_addition_anchor(
        '<p>в пункте 1 после слов «на внесение его кандидатуры» дополнить '
        'словами «в Законодательное Собрание города Севастополя»;</p>') == \
        'на внесение его кандидатуры'
    assert parse_addition_anchor(_ADD_DESC) is None


def test_ensure_addition_moves_period_before_insertion():
    """Контрольный кейс ст.9 ч.8: точка не должна остаться посреди предложения."""
    fixed = _ensure_addition_applied(_ADD_DESC, _ADD_OLD, _ADD_AI_BAD, print)
    assert fixed.endswith('настоящего Закона.</p>')
    assert 'Уполномоченного. в порядке' not in fixed
    assert 'предыдущего Уполномоченного в порядке' in fixed


def test_ensure_addition_correct_answer_untouched():
    fixed = _ensure_addition_applied(_ADD_DESC, _ADD_OLD, _ADD_AI_GOOD, print)
    assert fixed == _ADD_AI_GOOD


def test_ensure_addition_handles_duplicated_period():
    """Двойная точка перед дополнением схлопывается, финальная остаётся одна."""
    doubled = _ADD_AI_BAD.replace('Уполномоченного. в порядке',
                                  'Уполномоченного.. в порядке')
    fixed = _ensure_addition_applied(_ADD_DESC, _ADD_OLD, doubled, print)
    assert fixed.count('..') == 0
    assert fixed.endswith('настоящего Закона.</p>')
    assert 'предыдущего Уполномоченного в порядке' in fixed


def test_ensure_addition_inserts_after_anchor_when_missing():
    desc = ('<p>в пункте 1 после слов «на внесение его кандидатуры» дополнить '
            'словами «в Законодательное Собрание города Севастополя»;</p>')
    old = '<p>Предложение о внесении его кандидатуры;</p>'
    fixed = _ensure_addition_applied(desc, old, old, print)
    assert 'его кандидатуры в Законодательное Собрание города Севастополя' in fixed


def test_ensure_addition_appends_before_terminal_punct_when_missing():
    """Инструкция без опоры («часть 8 дополнить словами …»)."""
    fixed = _ensure_addition_applied(_ADD_DESC, _ADD_OLD, _ADD_OLD, print)
    assert fixed.endswith('настоящего Закона.</p>')
    assert 'предыдущего Уполномоченного в порядке' in fixed


def test_append_before_terminal_punct_handles_semicolon():
    html = '<p>Первое утверждение.</p><p>Второе утверждение;</p>'
    out = _append_before_terminal_punct(html, 'дополнение')
    assert out.endswith('Второе утверждение дополнение;</p>')
    assert _append_before_terminal_punct('<p>без точки</p>', 'x') is None


def test_ensure_addition_ignored_for_non_addition_instruction():
    desc = '<p>слово «ошибочно» заменить словом «верно»;</p>'
    assert _ensure_addition_applied(desc, _ADD_OLD, _ADD_AI_BAD, print) == _ADD_AI_BAD


# ================================== 5. Страховочный детектор дефектов границ

def test_find_defects_detects_glued_words():
    old = ('<p>осуществляет прием граждан, рассматривает обращения, касающиеся '
           'нарушения прав детей;</p>')
    new = ('<p>осуществляет прием граждан, рассматривает обращенияграждан, '
           'объединений, содержащие предложения по вопросам, касающимся '
           'нарушения прав детей;</p>')
    defects = find_text_boundary_defects(old, new)
    assert any('склейка' in d and 'обращения' in d for d in defects), defects


def test_find_defects_detects_space_before_semicolon():
    old = '<p>копия паспорта гражданина РФ или паспорт;</p>'
    new = '<p>копия паспорта гражданина РФ ;</p>'
    assert any('пробел' in d for d in find_text_boundary_defects(old, new))


def test_find_defects_detects_orphan_close_quote():
    old = '<p>законодательной инициативы, указанными в статье 3;</p>'
    new = '<p>законодательной инициативы».</p>'
    assert any('»' in d for d in find_text_boundary_defects(old, new))


def test_find_defects_clean_edit_reports_nothing():
    old = '<p>копия паспорта гражданина РФ или паспорт;</p>'
    new = '<p>копия паспорта гражданина РФ;</p>'
    assert find_text_boundary_defects(old, new) == []
    assert find_text_boundary_defects(old, old) == []


def test_find_defects_ignores_preexisting_space_before_semicolon():
    """Дефект был в документе и до правки — новым не считается."""
    old = '<p>копия паспорта гражданина РФ ;</p>'
    new = '<p>копия паспорта гражданина РФ или паспорт ;</p>'
    assert find_text_boundary_defects(old, new) == []




