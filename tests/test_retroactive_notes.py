"""Тесты ретроактивных правил: канонизация путей и resolve_rule_target."""
import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "npazs_bootstrap", _ROOT / "src" / "bootstrap.py"
)
assert _spec is not None and _spec.loader is not None
_bootstrap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bootstrap)
_bootstrap.bootstrap()

from npazs.revision.retroactive_notes import (  # noqa: E402
    _append_item_note,
    _canonical_structural_path,
    _canonical_structural_tokens,
    _structural_path_key,
    _change_created_path_tokens,
    is_propagation_note,
    resolve_rule_target,
    apply_retroactive_rules_to_groups,
)


def _make_tree():
    """Минимальное целевое дерево: статья 2 -> часть 1.4 -> пункт 2."""
    return {
        "npa_items_revision": [
            {
                "item_id": "art_2",
                "item_type": "article",
                "item_number": "2",
                "item_children": [
                    {
                        "item_id": "part_1_4",
                        "item_type": "part",
                        "item_number": "1.4",
                        "item_children": [
                            {
                                "item_id": "point_2",
                                "item_type": "point",
                                "item_number": "2)",
                                "item_children": [],
                            }
                        ],
                    }
                ],
            }
        ]
    }


def _log(s, level=None):
    pass


# ---------------------------------------------------------------------------
# Канонизация путей
# ---------------------------------------------------------------------------
def test_canonical_path_reorders_from_bottom_up():
    assert (
        _canonical_structural_path("часть 1.4 статьи 2")
        == "статья 2 -> часть 1.4"
    )


def test_canonical_path_keeps_top_down():
    assert (
        _canonical_structural_path("статья 2 -> часть 1.4")
        == "статья 2 -> часть 1.4"
    )


def test_canonical_path_handles_typo():
    # ИИ выдал «часть 1.4 стать 2» (опечатка «стать») — должно канонизироваться так же.
    assert (
        _canonical_structural_path("часть 1.4 стать 2")
        == "статья 2 -> часть 1.4"
    )


def test_structural_path_key_is_order_independent():
    key_a = _structural_path_key(_canonical_structural_tokens("часть 1.4 статьи 2"))
    key_b = _structural_path_key(_canonical_structural_tokens("статья 2 -> часть 1.4"))
    assert key_a == key_b == (("article", "2"), ("part", "1.4"))


def test_change_created_path_tokens_equals_rule_key():
    change = {"structural_element": "Статья 2", "new": "часть 1.4"}
    change_key = _structural_path_key(_change_created_path_tokens(change))
    rule_key = _structural_path_key(_canonical_structural_tokens("часть 1.4 статьи 2"))
    assert change_key == rule_key


# ---------------------------------------------------------------------------
# resolve_rule_target
# ---------------------------------------------------------------------------
def test_resolve_scenario_a_inverted_rule():
    tree = _make_tree()
    elem = resolve_rule_target(
        {"structural_element": "часть 1.4 статьи 2"}, tree, None, _log
    )
    assert elem is not None and elem.get("item_id") == "part_1_4"


def test_resolve_scenario_a_canonical_rule():
    tree = _make_tree()
    elem = resolve_rule_target(
        {"structural_element": "статья 2 -> часть 1.4"}, tree, None, _log
    )
    assert elem is not None and elem.get("item_id") == "part_1_4"


def test_resolve_scenario_b_created_by_add():
    # Элемента нет по обычному пути «статья 2 -> часть 1.4», но он присутствует
    # в дереве (orphan) и привязан к add-изменению через _created_item_id.
    tree = {
        "npa_items_revision": [
            {
                "item_id": "art_2",
                "item_type": "article",
                "item_number": "2",
                "item_children": [],
            },
            {
                "item_id": "part_1_4",
                "item_type": "part",
                "item_number": "1.4",
                "item_children": [],
            },
        ]
    }
    changes = [
        {
            "type": "add",
            "structural_element": "Статья 2",
            "new": "часть 1.4",
            "_created_item_id": "part_1_4",
        }
    ]
    elem = resolve_rule_target(
        {"structural_element": "статья 2 -> часть 1.4"}, tree, changes, _log
    )
    assert elem is not None and elem.get("item_id") == "part_1_4"


def test_resolve_none_for_unknown():
    tree = _make_tree()
    elem = resolve_rule_target(
        {"structural_element": "статья 2 -> часть 9.9"}, tree, None, _log
    )
    assert elem is None


# ---------------------------------------------------------------------------
# apply_retroactive_rules_to_groups (полный конвейер)
# ---------------------------------------------------------------------------
def test_apply_target_law_rule_adds_item_note():
    tree = _make_tree()
    changes = [
        {
            "type": "add",
            "structural_element": "Статья 2",
            "new": "часть 1.4",
            "_created_item_id": "part_1_4",
            "_resolved_item_id": "art_2",
        }
    ]
    rules = [
        {
            "applies_to": "target_law",
            "action_type": "retroactive_note",
            "structural_element": "часть 1.4 статьи 2",
            "note_text": "Действие положений части 1.4 статьи 2 распространяется "
                         "на правоотношения, возникшие с 1 января 2023 года.",
            "note_valid_from": "01.01.2023",
        }
    ]
    applied = apply_retroactive_rules_to_groups(
        rules, {"art_2": changes}, tree, date(2023, 3, 2),
        log_callback=_log, change_data=None
    )
    assert applied == 1
    part = tree["npa_items_revision"][0]["item_children"][0]
    notes = part.get("item_notes", [])
    assert len(notes) == 1
    assert notes[0]["valid_from"] == "01.01.2023"
    assert "1 января 2023 года" in notes[0]["text"]


# ---------------------------------------------------------------------------
# Детект примечаний о распространении правоотношений (любые формы слов)
# ---------------------------------------------------------------------------
def test_is_propagation_note_word_forms():
    positives = [
        ("Изменения Закона № 569-ЗС распространяются на правоотношения, "
         "возникшие с 1 января 2020 года"),
        ("Действие положений части 1.7 статьи 2 распространяется "
         "на правоотношения, возникшие с 1 января 2026 года."),
        ("Действие положений части 1.4 статьи 2 распространено "
         "на правоотношения, возникшие с 1 января 2023 года."),
        ("Положения пункта 2 распространены на правоотношения, "
         "возникшие с 1 января 2025 года"),
        ("Действие настоящего Закона подлежит распространению "
         "на правоотношения, возникшие с 1 мая 2024 года"),
        "Оговорка о распространении на правоотношения, возникшие ранее",
        ("На правоотношения, возникшие с 1 января 2026 года, распространяется "
         "действие положений части 1.7 статьи 2"),
        "Изменения распространялись на правоотношения, возникшие до 2021 года",
    ]
    for text in positives:
        assert is_propagation_note(text), text

    negatives = [
        ("Положения настоящего пункта не распространяются на правоотношения, "
         "возникшие до 1 января 2020 года"),
        ("Положения настоящего пункта не были распространены "
         "на правоотношения прошлых периодов"),
        "Налоговая ставка устанавливается в размере 4 процентов",
        "",
        None,
    ]
    for text in negatives:
        assert not is_propagation_note(text), text


# ---------------------------------------------------------------------------
# Хук закрытия старых примечаний (_append_item_note_with_validity)
# ---------------------------------------------------------------------------
def test_hook_closes_old_note_same_relation_date_by_amending_date():
    """Сценарий 931-ЗС: старое примечание (от 907-ЗС) закрывается датой
    вступления в силу изменяющего НПА минус 1 день, хотя даты
    правоотношений у обеих заметок совпадают (01.01.2026)."""
    elem = {
        "item_id": "51528_article_2_part_1_7",
        "item_notes": [
            {
                "text": "Действие положений части 1.7 статьи 2 распространяется "
                        "на правоотношения, возникшие с 1 января 2026 года.",
                "valid_from": "01.01.2026",
                "valid_to": "",
                "source_item_id": "141415_article_2",
            }
        ],
    }
    added = _append_item_note(
        elem,
        "Действие положений части 1.7 статьи 2 распространяется "
        "на правоотношения, возникшие с 1 января 2026 года.",
        "01.01.2026",
        log_callback=_log,
        source_item_id="144372_article_2",
        amending_valid_from="31.08.2026",
    )
    assert added is True
    old, new = elem["item_notes"]
    assert old["source_item_id"] == "141415_article_2"
    assert old["valid_to"] == "30.08.2026"
    assert new["source_item_id"] == "144372_article_2"
    assert new["valid_to"] == ""


def test_hook_same_law_notes_coexist():
    """Примечания, порождённые одним изменяющим НПА (одинаковый npa_id в
    source_item_id), сосуществуют и не закрывают друг друга."""
    elem = {
        "item_id": "51528_article_2_part_1_7",
        "item_notes": [
            {
                "text": "Изменения Закона № 931-ЗС от 31.08.2026 распространяются "
                        "на правоотношения, возникшие с 1 января 2026 года",
                "valid_from": "01.01.2026",
                "valid_to": "",
                "source_item_id": "144372_article_1_point_1",
            }
        ],
    }
    added = _append_item_note(
        elem,
        "Действие положений части 1.7 статьи 2 распространяется "
        "на правоотношения, возникшие с 1 января 2026 года.",
        "01.01.2026",
        log_callback=_log,
        source_item_id="144372_article_2",
        amending_valid_from="31.08.2026",
    )
    assert added is True
    assert len(elem["item_notes"]) == 2
    assert elem["item_notes"][0]["valid_to"] == ""
    assert elem["item_notes"][1]["valid_to"] == ""


def test_hook_legacy_fallback_without_amending_date():
    """Без даты изменяющего НПА сохраняется прежнее поведение:
    valid_to = valid_from новой заметки - 1 день."""
    elem = {
        "item_notes": [
            {
                "text": "Изменения Закона № 569-ЗС распространяются "
                        "на правоотношения, возникшие с 1 января 2020 года",
                "valid_from": "01.01.2020",
                "valid_to": "",
            }
        ],
    }
    added = _append_item_note(
        elem,
        "Действие положений части 1.4 статьи 2 распространяется "
        "на правоотношения, возникшие с 1 января 2023 года.",
        "01.01.2023",
        log_callback=_log,
    )
    assert added is True
    old, new = elem["item_notes"]
    assert old["valid_to"] == "31.12.2022"
    assert new["valid_to"] == ""


def test_hook_skips_note_started_after_close_date():
    """Заметку, начавшую действовать позже даты закрытия, трогать нельзя."""
    elem = {
        "item_notes": [
            {
                "text": "Действие положений части 2 статьи 3 распространяется "
                        "на правоотношения, возникшие с 1 сентября 2026 года.",
                "valid_from": "01.09.2026",
                "valid_to": "",
                "source_item_id": "907_article_3",
            }
        ],
    }
    added = _append_item_note(
        elem,
        "Действие положений части 1.7 статьи 2 распространяется "
        "на правоотношения, возникшие с 1 января 2026 года.",
        "01.01.2026",
        log_callback=_log,
        source_item_id="144372_article_2",
        amending_valid_from="31.08.2026",
    )
    assert added is True
    assert elem["item_notes"][0]["valid_to"] == ""


def test_apply_target_law_rule_closes_old_note_931_scenario():
    """Сквозной сценарий 931-ЗС: правило target_law добавляет примечание к
    части 1.7 (у которой уже есть примечание от 907-ЗС) — старое закрывается
    30.08.2026 (дата вступления 931-ЗС минус 1 день), новое остаётся открытым."""
    tree = {
        "npa_items_revision": [
            {
                "item_id": "51528_article_2",
                "item_type": "article",
                "item_number": "2",
                "item_children": [
                    {
                        "item_id": "51528_article_2_part_1_7",
                        "item_type": "part",
                        "item_number": "1.7",
                        "revisions": [{"valid_from": "17.04.2026", "mod_type": "add"}],
                        "item_children": [],
                        "item_notes": [
                            {
                                "text": "Действие положений части 1.7 статьи 2 "
                                        "распространяется на правоотношения, возникшие "
                                        "с 1 января 2026 года.",
                                "valid_from": "01.01.2026",
                                "valid_to": "",
                                "source_item_id": "141415_article_2",
                            }
                        ],
                    }
                ],
            }
        ]
    }
    change_data = {
        "npa_id": "144372",
        "npa_items_revision": [
            {
                "item_id": "144372_article_2",
                "item_type": "article",
                "item_number": "2",
                "item_children": [],
            }
        ],
    }
    rules = [
        {
            "applies_to": "target_law",
            "action_type": "retroactive_note",
            "structural_element": "статья 2 -> часть 1.7",
            "note_text": "Действие положений части 1.7 статьи 2 распространяется "
                         "на правоотношения, возникшие с 1 января 2026 года.",
            "note_valid_from": "01.01.2026",
        }
    ]
    applied = apply_retroactive_rules_to_groups(
        rules, {}, tree, date(2026, 8, 31),
        log_callback=_log, change_data=change_data
    )
    assert applied == 1
    part = tree["npa_items_revision"][0]["item_children"][0]
    old, new = part["item_notes"]
    assert old["source_item_id"] == "141415_article_2"
    assert old["valid_to"] == "30.08.2026"
    assert new["source_item_id"] == "144372_article_2"
    assert new["valid_to"] == ""