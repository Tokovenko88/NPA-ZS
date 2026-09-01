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
_bootstrap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bootstrap)
_bootstrap.bootstrap()

from npazs.revision.retroactive_notes import (  # noqa: E402
    _canonical_structural_path,
    _canonical_structural_tokens,
    _structural_path_key,
    _change_created_path_tokens,
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