"""Тесты исправлений по кейсу 444-ЗС → 269-ЗС:

- ``check_orphan_children`` не считает «сиротой» ребёнка, чья последняя ревизия
  была закрыта другим законом раньше даты изменяющего НПА;
- пустая часть (без ревизий) остаётся сиротой — реальная проблема пайплайна;
- ``format_coverage_gaps`` печатает ``target_item_id`` (устранение путаницы
  одноимённых пунктов у LLM);
- детерминированный fallback замены слов «слова «X» заменить словами «Y»»
  (html_utils) срабатывает при опечатках OCR;
- «префиксная» автоправка постанализа («дописать N. в текст») отклоняется,
  если у элемента уже есть дочерняя часть/пункт с этим номером.
"""
import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "npazs_bootstrap", _ROOT / "src" / "bootstrap.py"
)
assert _spec is not None and _spec.loader is not None
_bootstrap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bootstrap)
_bootstrap.bootstrap()

from npazs.revision.coverage_check import (
    check_orphan_children,
    check_tracker_coverage,
    format_coverage_gaps,
)
from npazs.revision.html_utils import (
    apply_word_replacement_fuzzy,
    find_phrase_raw_range_fuzzy,
    parse_word_replacement,
    refine_word_replacement,
)
from npazs.revision.post_analysis import _apply_correction

_AMENDER = "46989"
_CHANGE_DATE = "23.10.2018"


def _parent_with_closed_child(child_valid_to="14.12.2017", child_revisions=None):
    """Родитель (статья) с активной ревизией от изменяющего НПА и ребёнок-пункт."""
    child = {
        "item_id": "16012_article_3_point_3",
        "item_type": "point",
        "item_number": "3)",
        "revisions": child_revisions if child_revisions is not None else [
            {
                "body": [{"type": "paragraph", "html_text": "<p>текст нормы</p>", "order": 1}],
                "valid_from": "08.08.2016",
                "valid_to": child_valid_to,
                "not_valid": "33699_article_1_point_4",
            },
        ],
    }
    parent = {
        "item_id": "16012_article_3",
        "item_type": "article",
        "item_number": "3",
        "item_children": [child],
        "revisions": [
            {
                "body": [
                    {"type": "paragraph", "html_text": "<p>абзац статьи</p>", "order": 1},
                    {"type": "child_ref", "item_id": child["item_id"], "order": 2},
                ],
                "valid_from": "15.12.2017",
                "mod_type": "new_redaction",
                "modified_by_id": "33699_article_1_point_4",
            },
            {
                "body": [
                    {"type": "paragraph", "html_text": "<p>абзац статьи</p>", "order": 1},
                    {"type": "child_ref", "item_id": child["item_id"], "order": 2},
                ],
                "valid_from": _CHANGE_DATE,
                "mod_type": "change",
                "modified_by_id": "46989_article_1_point_1_subpoint_а",
            },
        ],
    }
    return {"npa_items_revision": [parent]}


# ------------------------------------------------------- check_orphan_children
def test_child_closed_before_change_date_not_orphan():
    """Ребёнок, закрытый другим законом до даты изменяющего НПА — не сирота."""
    result = _parent_with_closed_child()
    gaps = check_orphan_children(result, _AMENDER, change_date=_CHANGE_DATE)
    assert gaps == []


def test_child_closed_after_change_date_is_orphan():
    """Ребёнок, закрытый ПОСЛЕ даты изменяющего НПА (в этом же прогоне) — сирота."""
    result = _parent_with_closed_child(child_valid_to="01.01.2019")
    gaps = check_orphan_children(result, _AMENDER, change_date=_CHANGE_DATE)
    assert len(gaps) == 1
    assert gaps[0]["reason"] == "orphan_child_not_closed"
    assert gaps[0]["target_item_id"] == "16012_article_3_point_3"


def test_child_without_change_date_keeps_old_behavior():
    """Без change_date прежнее поведение: закрытый ребёнок помечается сиротой."""
    result = _parent_with_closed_child()
    gaps = check_orphan_children(result, _AMENDER)
    assert len(gaps) == 1
    assert gaps[0]["reason"] == "orphan_child_not_closed"


def test_empty_part_still_orphan():
    """Пустая часть (0 ревизий) остаётся сиротой даже с change_date — реальная
    проблема пайплайна (кейс 444-ЗС: часть 1 без ревизии)."""
    result = _parent_with_closed_child()
    empty_part = {
        "item_id": "16012_article_3_part_1",
        "item_type": "part",
        "item_number": "1",
        "revisions": [],
    }
    result["npa_items_revision"][0]["item_children"].append(empty_part)
    gaps = check_orphan_children(result, _AMENDER, change_date=_CHANGE_DATE)
    assert [g["target_item_id"] for g in gaps] == ["16012_article_3_part_1"]


def test_check_tracker_coverage_passes_change_date():
    """check_tracker_coverage прокидывает change_date в проверку сирот."""
    result = _parent_with_closed_child()
    gaps = check_tracker_coverage(result, [], _AMENDER, change_date=_CHANGE_DATE)
    assert gaps == []


# -------------------------------------------------------- format_coverage_gaps
def test_format_gaps_contains_target_item_id():
    gaps = [{
        "change_id": None,
        "revision_number": "4)",
        "structural_element": "point 4)",
        "type": "new_redaction",
        "status": "applied",
        "reason": "orphan_child_not_closed",
        "revision_id": None,
        "target_item_id": "16012_article_3_point_4",
        "description": "",
    }]
    text = format_coverage_gaps(gaps)
    assert "target_item_id: 16012_article_3_point_4" in text


# --------------------------------------------------- замена слов (html_utils)
def test_parse_word_replacement_with_ocr_typos():
    description = (
        "<p class=\"justifyfull\">в абцае первом слова «К отельным категориям "
        "граждан» заменить словами «1. К отельным категориям граждан»;</p>"
    )
    pair = parse_word_replacement(description)
    assert pair == (
        "К отельным категориям граждан",
        "1. К отельным категориям граждан",
    )


def test_parse_word_replacement_no_match():
    assert parse_word_replacement("<p>дополнить пунктом 3 следующего содержания:</p>") is None


_PARA = (
    '<p class="justifyfull">К отдельным категориям граждан, имеющих право '
    'на приобретение земельных участков, относятся граждане из числа лиц:</p>'
)


def test_word_replacement_fuzzy_exact():
    out = apply_word_replacement_fuzzy(
        _PARA, "К отдельным категориям граждан", "1. К отдельным категориям граждан")
    assert out is not None
    assert "1. К отдельным категориям граждан" in out


def test_word_replacement_fuzzy_with_typo():
    """Опечатка OCR в описании («отельным») не мешает найти фразу в HTML."""
    out = apply_word_replacement_fuzzy(
        _PARA, "К отельным категориям граждан", "1. К отдельным категориям граждан")
    assert out is not None
    assert "1. К отдельным категориям граждан" in out


def test_word_replacement_fuzzy_no_match():
    assert find_phrase_raw_range_fuzzy(_PARA, "совершенно другая фраза без совпадений") is None


# --------------------------------------- refine_word_replacement (опечатки ИИ)
def test_refine_replacement_cleans_typo_in_old_phrase():
    """Опечатка в old-фразе ИИ («отельным») заменяется реальным текстом документа."""
    source = '<p>К отдельным категориям граждан, имеющих право …</p>'
    old, new = refine_word_replacement(
        "К отельным категориям граждан",
        "1. К отельным категориям граждан",
        source,
    )
    assert old == "К отдельным категориям граждан"
    assert new == "1. К отдельным категориям граждан"


def test_refine_replacement_keeps_typo_when_phrase_not_in_source():
    """Фраза не найдена в документе — возвращаем исходные (без вмешательства)."""
    old, new = refine_word_replacement(
        "К отельным категориям граждан",
        "1. К отельным категориям граждан",
        '<p>совсем другой текст</p>',
    )
    assert (old, new) == ("К отельным категориям граждан", "1. К отельным категориям граждан")



# --------------------------------------------- защита «префиксной» автоправки
def test_prefix_correction_noop_rejected_when_child_part_exists():
    """Коррекция «дописать 1. в текст», сводящаяся к дублю номера, отклоняется."""
    element = {
        "item_id": "16012_article_3",
        "item_type": "article",
        "item_number": "3",
        "item_children": [
            {"item_id": "16012_article_3_part_1", "item_type": "part", "item_number": "1"},
        ],
        "revisions": [
            {
                "body": [
                    {"type": "paragraph", "html_text": "<p class=\"j\">К отдельным категориям граждан:</p>", "order": 1},
                    {"type": "child_ref", "item_id": "16012_article_3_part_1", "order": 2},
                ],
                "valid_from": _CHANGE_DATE,
                "mod_type": "change",
                "modified_by_id": "46989_article_1_point_1_subpoint_а",
            },
        ],
    }
    result = {"npa_items_revision": [element]}
    corr = {
        "item_id": "16012_article_3",
        "field": "element_html",
        "value": '<p class="j">1. К отдельным категориям граждан:</p>',
    }
    ok, err = _apply_correction(result, corr, _AMENDER, _CHANGE_DATE)
    assert ok is False
    assert "item_number" in err
    body_text = str(element["revisions"][-1]["body"])
    assert "1. К отдельным" not in body_text


def test_prefix_correction_sanitized_and_typo_fixed():
    """Префиксная коррекция с содержательной правкой применяется БЕЗ номера:
    опечатки исправляются, «1.» в текст не попадает (хранится в item_number)."""
    element = {
        "item_id": "16012_article_3_part_1",
        "item_type": "part",
        "item_number": "1",
        "item_children": [
            {"item_id": "16012_article_3_part_1_point_1", "item_type": "point", "item_number": "1)"},
        ],
        "revisions": [
            {
                "body": [
                    {"type": "paragraph",
                     "html_text": "<p class=\"j\">К отельным категориям гражданн, относятся:</p>",
                     "order": 1},
                    {"type": "child_ref", "item_id": "16012_article_3_part_1_point_1", "order": 2},
                ],
                "valid_from": _CHANGE_DATE,
                "mod_type": "change",
                "modified_by_id": "46989_article_1_point_1_subpoint_б",
            },
        ],
    }
    result = {"npa_items_revision": [element]}
    corr = {
        "item_id": "16012_article_3_part_1",
        "field": "element_html",
        "value": '<p class="j">1. К отдельным категориям граждан, относятся:</p>',
    }
    ok, err = _apply_correction(result, corr, _AMENDER, _CHANGE_DATE)
    assert ok is True, err
    body = element["revisions"][-1]["body"]
    first = next(b for b in body if b.get("type") == "paragraph")
    assert "отельным" not in first["html_text"]
    assert "гражданн," not in first["html_text"]
    assert "1. К отдельным" not in first["html_text"]
    assert "отдельным категориям граждан, относятся" in first["html_text"]


def test_empty_value_correction_rejected():
    """Пустая коррекция (value: "") отклоняется — иначе затёрла бы текст."""
    element = {
        "item_id": "16012_article_4_part_2",
        "item_type": "part",
        "item_number": "2",
        "item_children": [],
        "revisions": [
            {
                "body": [{"type": "paragraph", "html_text": "<p>Текст части.</p>", "order": 1}],
                "valid_from": "06.04.2018",
                "modified_by_id": "37687_article_1_point_2_subpoint_б",
            },
        ],
    }
    result = {"npa_items_revision": [element]}
    corr = {"item_id": "16012_article_4_part_2", "field": "element_html", "value": ""}
    ok, err = _apply_correction(result, corr, _AMENDER, _CHANGE_DATE)
    assert ok is False
    assert "пустое исправление" in err
    assert "Текст части." in str(element["revisions"][-1]["body"])


# --------------------------- фильтр устаревших записей трекера (чужие прогоны)
from npazs.revision.post_analysis import _drop_stale_tracker_entries


def _result_with_rev(rev_id, modified_by, not_valid=None, item_id="16012_article_4_part_1_point_2"):
    return {
        "npa_items_revision": [{
            "item_id": item_id,
            "item_type": "point",
            "item_number": "2)",
            "item_children": [],
            "revisions": [{
                "revision_id": rev_id,
                "valid_from": "06.04.2018",
                "valid_to": "",
                "modified_by_id": modified_by,
                "not_valid": not_valid,
                "body": [{"type": "paragraph", "html_text": "<p>текст</p>", "order": 1}],
            }],
        }],
    }


def test_stale_tracker_change_entry_dropped():
    """Запись change чужого прогона (ревизия другого НПА) исключается."""
    result = _result_with_rev("0c755a79", "37687_article_1_point_2_subpoint_а")
    entries = [{
        "change_id": "3a26ea05-c31", "revision_number": "2)->а)",
        "structural_element": "Статья 4 часть 1 пункт 2", "type": "change",
        "status": "verified", "revision_id": "0c755a79",
        "target_item_id": "16012_article_4_part_1_point_2",
    }]
    kept = _drop_stale_tracker_entries(result, entries, "46989", lambda m, l="info": None)
    assert kept == []


def test_own_tracker_change_entry_kept():
    """Запись текущего прогона (ревизия изменяющего НПА) сохраняется."""
    result = _result_with_rev("f336c92c", "46989_article_1_point_1_subpoint_а")
    entries = [{
        "change_id": "f336c92c-38a", "revision_number": "1)->а)",
        "structural_element": "Статья 3 абзац 1", "type": "change",
        "status": "verified", "revision_id": "f336c92c",
        "target_item_id": "16012_article_3",
    }]
    kept = _drop_stale_tracker_entries(result, entries, "46989", lambda m, l="info": None)
    assert len(kept) == 1


def test_tracker_entry_without_revision_kept():
    """Запись без revision_id (правка не доведена до результата) — реальный пробел."""
    entries = [{
        "change_id": "x1", "revision_number": "3)", "type": "add",
        "status": "applied", "revision_id": "", "target_item_id": "16012_article_3_part_2_point_3",
    }]
    kept = _drop_stale_tracker_entries({"npa_items_revision": []}, entries, "46989",
                                       lambda m, l="info": None)
    assert len(kept) == 1


def test_stale_tracker_delete_entry_dropped():
    """delete-запись чужого прогона: закрываемая ревизия помечена not_valid
    ДРУГИМ законом — запись устаревшая."""
    result = _result_with_rev(
        "7373dc7e", "33699_article_1_point_5", not_valid="37687_article_1_point_2_subpoint_б")
    entries = [{
        "change_id": "7d106e02-384", "revision_number": "2)->б)", "type": "delete",
        "status": "verified", "revision_id": "7373dc7e",
        "target_item_id": "16012_article_4_part_1_point_2",
    }]
    kept = _drop_stale_tracker_entries(result, entries, "46989", lambda m, l="info": None)
    assert kept == []


def test_own_tracker_delete_entry_kept():
    """delete-запись текущего прогона: not_valid проставлен изменяющим НПА."""
    result = _result_with_rev(
        "7373dc7e", "33699_article_1_point_5", not_valid="46989_article_1_point_3")
    entries = [{
        "change_id": "d1", "revision_number": "2)->б)", "type": "delete",
        "status": "verified", "revision_id": "7373dc7e",
        "target_item_id": "16012_article_4_part_1_point_2",
    }]
    kept = _drop_stale_tracker_entries(result, entries, "46989", lambda m, l="info": None)
    assert len(kept) == 1


def test_prefix_correction_allowed_without_matching_child():
    """Без дочерней части/пункта с этим номером префиксная коррекция применяется."""
    element = {
        "item_id": "16012_article_4",
        "item_type": "article",
        "item_number": "4",
        "item_children": [],
        "revisions": [
            {
                "body": [
                    {"type": "paragraph", "html_text": "<p class=\"j\">Текст статьи:</p>", "order": 1},
                ],
                "valid_from": _CHANGE_DATE,
                "mod_type": "change",
                "modified_by_id": "46989_article_1_point_2",
            },
        ],
    }
    result = {"npa_items_revision": [element]}
    corr = {
        "item_id": "16012_article_4",
        "field": "element_html",
        "value": '<p class="j">1. Текст статьи:</p>',
    }
    ok, err = _apply_correction(result, corr, _AMENDER, _CHANGE_DATE)
    assert ok is True, err
    assert err == ""


# --------------------------- защита от правок, противоречащих изменяющему НПА
from npazs.revision.post_analysis import _correction_conflicts_with_source

_SOURCE_TEXT = (
    "2. К лицам из отдельных категорий граждан, установленных пунктом 3 части 1 "
    "настоящей статьи, относятся: ... независимо от места дислокации и "
    "выполнявшихся работ, а также лиц начальствующего и рядового состава ..."
)


def test_correction_conflicts_with_source_detects_hallucination():
    """Правка «выполнявшихся → выполняющих» противоречит тексту закона."""
    old_html = '<p>… независимо от места дислокации и выполнявшихся работ, а также …</p>'
    value = '<p>… независимо от места дислокации и выполняющих работ, а также …</p>'
    assert _correction_conflicts_with_source(old_html, value, _SOURCE_TEXT) is True


def test_correction_matching_source_not_conflicting():
    """Обе словоформы в законе — конфликта нет (правка допустима)."""
    source = (
        "… независимо от места дислокации и выполнявшихся работ, а также … "
        "… применительно к выполняющихся работ лицам …"
    )
    old_html = '<p>… выполнявшихся работ …</p>'
    value = '<p>… выполняющихся работ …</p>'
    assert _correction_conflicts_with_source(old_html, value, source) is False


def test_correction_no_source_text_no_conflict():
    assert _correction_conflicts_with_source('<p>а б в</p>', '<p>а б г</p>', '') is False


def test_source_correction_of_law_verbatim_text_rejected():
    """Удаление дословной формулы закона (выполнявшихся → выполняющих) блокируется."""
    element = {
        "item_id": "16012_article_3_part_2_point_2_subpoint_б",
        "item_type": "subpoint",
        "item_number": "б)",
        "item_children": [],
        "revisions": [
            {
                "body": [{"type": "paragraph", "html_text": "<p class=\"j\">… независимо от места дислокации и выполнявшихся работ, а также …</p>", "order": 1}],
                "valid_from": _CHANGE_DATE,
                "mod_type": "add",
                "modified_by_id": "46989_article_1_point_2",
            },
        ],
    }
    result = {"npa_items_revision": [element]}
    corr = {
        "item_id": element["item_id"],
        "field": "element_html",
        "value": '<p class="j">… независимо от места дислокации и выполняющих работ, а также …</p>',
    }
    ok, err = _apply_correction(result, corr, _AMENDER, _CHANGE_DATE,
                                change_text=_SOURCE_TEXT)
    assert ok is False
    assert "изменяющего НПА" in err
    assert "выполнявшихся" in element["revisions"][-1]["body"][0]["html_text"]


# ------------------------- префиксная коррекция для тела без собственных абзацев
def test_prefix_correction_accepted_for_paragraphless_body():
    """Пустое тело (только child_ref): коррекция принимается, номер снимается."""
    element = {
        "item_id": "16012_article_3_part_1",
        "item_type": "part",
        "item_number": "1",
        "item_children": [
            {"item_id": "16012_article_3_part_1_point_1", "item_type": "point", "item_number": "1)"},
        ],
        "revisions": [
            {
                "body": [
                    {"type": "child_ref", "item_id": "16012_article_3_part_1_point_1", "order": 1},
                ],
                "valid_from": _CHANGE_DATE,
                "mod_type": "add",
                "modified_by_id": "46989_article_1_point_1_subpoint_б",
            },
        ],
    }
    result = {"npa_items_revision": [element]}
    corr = {
        "item_id": "16012_article_3_part_1",
        "field": "element_html",
        "value": '<p class="j">1. К отдельным категориям граждан, относятся:</p>',
    }
    ok, err = _apply_correction(result, corr, _AMENDER, _CHANGE_DATE)
    assert ok is True, err
    body = element["revisions"][-1]["body"]
    paras = [b for b in body if b.get("type") == "paragraph"]
    assert len(paras) == 1
    assert "1. К отдельным" not in paras[0]["html_text"]
    assert "К отдельным категориям граждан" in paras[0]["html_text"]
    assert any(b.get("type") == "child_ref" for b in body)


# ----------------------------------- досаливание вводных абзацев (ui_utils)
from npazs.revision.ui_utils import _salvage_missing_own_paragraphs


def test_salvage_adds_intro_paragraph_to_paragraphless_body():
    element = {
        "item_id": "16012_article_3_part_1",
        "item_type": "part",
        "item_number": "1",
        "item_children": [
            {
                "item_id": "16012_article_3_part_1_point_1",
                "item_type": "point",
                "item_number": "1)",
                "revisions": [{"body": [{"type": "paragraph", "html_text": "<p>имеющих трех и более детей;</p>", "order": 1}]}],
            },
        ],
        "revisions": [
            {
                "body": [{"type": "child_ref", "item_id": "16012_article_3_part_1_point_1", "order": 1}],
                "valid_from": _CHANGE_DATE,
                "mod_type": "add",
                "modified_by_id": "46989_article_1_point_1_subpoint_б",
            },
        ],
    }
    new_element = {
        "item_type": "part",
        "item_number": "1",
        "collected_content": ["<p>1. К отдельным категориям граждан, относятся:</p>"],
        "item_children": [],
    }
    _salvage_missing_own_paragraphs(element, new_element)
    body = element["revisions"][0]["body"]
    assert body[0]["type"] == "paragraph"
    assert "1. К отдельным" not in body[0]["html_text"]
    assert "К отдельным категориям граждан" in body[0]["html_text"]
    assert body[1]["type"] == "child_ref"


def test_salvage_skips_element_with_own_paragraphs():
    """Элемент с собственными абзацами не трогается (защита кейса 127<-516)."""
    element = {
        "item_id": "x",
        "item_type": "part",
        "item_number": "1",
        "item_children": [],
        "revisions": [
            {
                "body": [{"type": "paragraph", "html_text": "<p>свой текст</p>", "order": 1}],
                "valid_from": _CHANGE_DATE,
            },
        ],
    }
    new_element = {
        "item_type": "part",
        "collected_content": ["<p>чужой дубликат текста</p>"],
    }
    _salvage_missing_own_paragraphs(element, new_element)
    body = element["revisions"][0]["body"]
    assert len(body) == 1
    assert "свой текст" in body[0]["html_text"]


def test_salvage_skips_duplicate_of_child_text():
    """Абзац, дословно совпадающий с текстом ребёнка, не добавляется."""
    element = {
        "item_id": "x",
        "item_type": "part",
        "item_number": "1",
        "item_children": [
            {
                "item_id": "x_point_1",
                "item_type": "point",
                "revisions": [{"body": [{"type": "paragraph", "html_text": "<p>текст ребёнка</p>", "order": 1}]}],
            },
        ],
        "revisions": [
            {"body": [{"type": "child_ref", "item_id": "x_point_1", "order": 1}], "valid_from": _CHANGE_DATE},
        ],
    }
    new_element = {"item_type": "part", "collected_content": ["<p>текст ребёнка</p>"]}
    _salvage_missing_own_paragraphs(element, new_element)
    body = element["revisions"][0]["body"]
    assert not any(b.get("type") == "paragraph" for b in body)


# ------------------------------- фильтр «номерных» галлюцинаций (post_analysis)
from npazs.revision.post_analysis import _is_numbering_prefix_only_issue


def _work_with_part1():
    return {"npa_items_revision": [
        {
            "item_id": "16012_article_3_part_1",
            "item_type": "part",
            "item_number": "1",
            "item_children": [],
            "revisions": [{
                "body": [
                    {"type": "paragraph", "html_text": "<p class=\"j\">К отдельным категориям граждан, относятся:</p>", "order": 1},
                    {"type": "child_ref", "item_id": "p1", "order": 2},
                ],
                "valid_from": _CHANGE_DATE,
                "mod_type": "add",
                "modified_by_id": "46989_article_1_point_1_subpoint_б",
            }],
        },
    ]}


def _prefix_issue(actual_para="К отдельным категориям граждан, относятся:"):
    para = actual_para
    return {
        "index": 1,
        "path": "Статья 3 > Часть 1",
        "expected": f'<p class="j">1. {para}</p>',
        "actual": f'<p class="j">{para}</p>',
        "corrections": [{
            "item_id": "16012_article_3_part_1",
            "field": "element_html",
            "value": f'<p class="j">1. {para}</p>',
        }],
    }


def test_numbering_prefix_hallucination_filtered():
    """Претензия «нет 1. в тексте части 1» отсеивается (номер в item_number)."""
    assert _is_numbering_prefix_only_issue(_prefix_issue(), _work_with_part1()) is True


def test_numbering_prefix_filter_keeps_real_text_difference():
    """Различие текста beyond префикса — не отсеивается, это реальная проблема."""
    issue = {
        "index": 1,
        "path": "Статья 3 > Часть 1",
        "expected": '<p class="j">1. К отдельным категориям граждан, относятся:</p>',
        "actual": '<p class="j">К иным категориям граждан, относятся:</p>',
        "corrections": [{
            "item_id": "16012_article_3_part_1",
            "field": "element_html",
            "value": '<p class="j">1. К отдельным категориям граждан, относятся:</p>',
        }],
    }
    assert _is_numbering_prefix_only_issue(issue, _work_with_part1()) is False


def test_numbering_prefix_filter_ignores_structural_element_type():
    """Для article (номер не «1») фильтр не применяется."""
    work = _work_with_part1()
    work["npa_items_revision"][0]["item_type"] = "article"
    assert _is_numbering_prefix_only_issue(_prefix_issue(), work) is False


def test_numbering_prefix_filter_requires_prefix_in_expected():
    """Если в expected нет номера — фильтр не срабатывает (другая претензия)."""
    issue = _prefix_issue()
    issue["expected"] = '<p class="j">К отдельным категориям граждан, относятся:</p>'
    issue["actual"] = '<p class="j">Совсем другой текст статьи:</p>'
    assert _is_numbering_prefix_only_issue(issue, _work_with_part1()) is False


def test_numbering_prefix_filter_actual_with_number_not_filtered():
    """Если actual тоже с номером — разница не только в префиксе у коррекции."""
    issue = _prefix_issue()
    issue["actual"] = '<p class="j">1. К отдельным категориям граждан, относятся:</p>'
    assert _is_numbering_prefix_only_issue(issue, _work_with_part1()) is False


def test_numbering_prefix_filter_without_corrections_resolves_by_path():
    """Претензия без corrections отсеивается: элемент найден по path из <changes>."""
    issue = {
        "index": 1,
        "path": "Статья 3 > Часть 1",
        "expected": '<p class="j">1. К отдельным категориям граждан, относятся:</p>',
        "actual": '<p class="j">К отдельным категориям граждан, относятся:</p>',
        "fix": "Добавить «1. » в начало абзаца.",
    }
    path_map = {"Статья 3 > Часть 1": "16012_article_3_part_1"}
    assert _is_numbering_prefix_only_issue(issue, _work_with_part1(), path_map) is True


def test_numbering_prefix_filter_uses_llm_actual_with_typo():
    """Опечатка ИИ в цитате («отельным» вместо «отдельным») не мешает фильтру:
    сравнение идёт с его же `actual` (кейс 444-ЗС → 269-ЗС)."""
    issue = {
        "index": 1,
        "path": "Статья 3 > Часть 1",
        "expected": '<p class="j">1. К отельным категориям граждан, относятся:</p>',
        "actual": '<p class="j">К отельным категориям граждан, относятся:</p>',
        "corrections": [{
            "item_id": "16012_article_3_part_1",
            "field": "element_html",
            "value": '<p class="j">1. К отельным категориям граждан, относятся:</p>',
        }],
    }
    assert _is_numbering_prefix_only_issue(issue, _work_with_part1()) is True


def test_numbering_prefix_filter_uses_real_text_when_actual_missing():
    """ИИ не привёл `actual` — сверяемся с реальным текстом активной ревизии."""
    issue = {
        "index": 1,
        "path": "Статья 3 > Часть 1",
        "expected": '<p class="j">1. К отдельным категориям граждан, относятся:</p>',
        "fix": "Добавить «1. » в начало абзаца.",
    }
    path_map = {"Статья 3 > Часть 1": "16012_article_3_part_1"}
    assert _is_numbering_prefix_only_issue(issue, _work_with_part1(), path_map) is True


def test_numbering_prefix_filter_real_text_mismatch_not_filtered():
    """Реальный текст элемента отличается содержательно — претензия сохраняется."""
    issue = {
        "index": 1,
        "path": "Статья 3 > Часть 1",
        "expected": '<p class="j">1. К отельным категориям граждан, относятся:</p>',
        "fix": "Добавить «1. » в начало абзаца.",
    }
    path_map = {"Статья 3 > Часть 1": "16012_article_3_part_1"}
    assert _is_numbering_prefix_only_issue(issue, _work_with_part1(), path_map) is False



def test_numbering_prefix_filter_ignores_non_text_corrections():
    """Коррекция не по тексту (element_not_valid) — фильтр не применяется."""
    issue = {
        "index": 1,
        "path": "Статья 3 > Часть 1",
        "expected": '<p class="j">1. К отдельным категориям граждан, относятся:</p>',
        "actual": '<p class="j">К отдельным категориям граждан, относятся:</p>',
        "corrections": [{
            "item_id": "16012_article_3_part_1",
            "field": "element_not_valid",
            "value": "23.10.2018",
        }],
    }
    assert _is_numbering_prefix_only_issue(issue, _work_with_part1()) is False


def test_numbering_prefix_filter_keeps_addition_of_other_paragraph():
    """Если претензия о содержательном расхождении — фильтр не срабатывает."""
    issue = {
        "index": 1,
        "path": "Статья 3 > Часть 1",
        "expected": '<p class="j">1. К отдельным категориям граждан, относятся лица:</p>',
        "actual": '<p class="j">К отдельным категориям граждан, относятся:</p>',
        "corrections": [{
            "item_id": "16012_article_3_part_1",
            "field": "element_html",
            "value": '<p class="j">1. К отдельным категориям граждан, относятся лица:</p>',
        }],
    }
    assert _is_numbering_prefix_only_issue(issue, _work_with_part1()) is False
