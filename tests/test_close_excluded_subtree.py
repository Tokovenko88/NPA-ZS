"""Regression tests: children EXCLUDED by a parent's new_redaction must be
closed as revoked (valid_to + not_valid), not left hanging as active norms.

Case 380-ЗС -> 269-ЗС: the new redaction of article 7 dropped parts 8-11, but
their revisions stayed active with ``valid_to=None`` — the site rendered the
revoked text as current law and the deterministic post-analysis raised
``orphan_child_not_closed`` for every such child.
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

from npazs.revision.coverage_check import check_orphan_children

_CHANGE_DATE = "15.12.2017"
_VALID_TO_PREV = "14.12.2017"
_AMENDER = "33699_article_1_point_5"
_OLD_PAR = "<p>Часть, исключённая новой редакцией.</p>"


def _make_excluded_child(number="8"):
    """Old child part with one active base revision (no provenance stamp)."""
    return {
        "item_id": f"16012_article_7_part_{number}",
        "item_type": "part",
        "item_number": number,
        "item_children": [
            {
                "item_id": f"16012_article_7_part_{number}_point_1",
                "item_type": "point",
                "item_number": "1)",
                "revisions": [
                    {
                        "body": [{"type": "paragraph", "html_text": _OLD_PAR, "order": 1}],
                        "valid_from": "05.01.2016",
                    }
                ],
            }
        ],
        "revisions": [
            {
                "body": [{"type": "paragraph", "html_text": _OLD_PAR, "order": 1}],
                "valid_from": "05.01.2016",
            }
        ],
    }


def _make_parent(old_children):
    return {
        "item_id": "16012_article_7",
        "item_type": "article",
        "item_number": "7",
        "head_revisions": [{"head_text": "Статья 7"}],
        "item_children": old_children,
        "revisions": [
            {
                "body": [{"type": "paragraph", "html_text": "<p>Старая вводная часть.</p>", "order": 1}],
                "valid_from": "05.01.2016",
            }
        ],
    }


def _make_new_parent():
    return {
        "item_id": "16012_article_7",
        "item_type": "article",
        "item_number": "7",
        "head_revisions": [{"head_text": "Статья 7"}],
        "item_children": [],
        "revisions": [
            {
                "body": [{"type": "paragraph", "html_text": "<p>НОВАЯ редакция вводной части.</p>", "order": 1}],
            }
        ],
    }


def _active(rev):
    return rev.get("valid_to") in (None, "") and not rev.get("not_valid")


def test_sync_closes_excluded_child_subtree():
    from npazs.revision.ui_utils import sync_structural_element_recursive

    child = _make_excluded_child()
    parent = _make_parent([child])
    sync_structural_element_recursive(
        old_element=parent,
        new_element=_make_new_parent(),
        change_date=_CHANGE_DATE,
        modified_by_id=_AMENDER,
        data_context=None,
        log_callback=lambda *_a, **_k: None,
        is_top_level=True,
        override_mod_type="new_redaction",
        highlights=None,
    )

    for element in (child, child["item_children"][0]):
        revs = element["revisions"]
        assert not any(_active(r) for r in revs), "excluded norm must not stay active"
        closed = [r for r in revs if r.get("valid_to") == _VALID_TO_PREV]
        assert closed, "active revision must be closed the day before the amendment"
        assert all(r.get("not_valid") == _AMENDER for r in closed)


def test_sync_keeps_child_already_revised_this_run():
    from npazs.revision.ui_utils import sync_structural_element_recursive

    child = _make_excluded_child()
    # The child got its own amendment revision earlier in this run — the guard
    # must not let the excluded-subtree closer stamp it as revoked.
    child["revisions"].append(
        {
            "body": [{"type": "paragraph", "html_text": "<p>Уже перестроено.</p>", "order": 1}],
            "valid_from": _CHANGE_DATE,
            "mod_type": "change",
            "modified_by_id": _AMENDER,
        }
    )
    parent = _make_parent([child])
    sync_structural_element_recursive(
        old_element=parent,
        new_element=_make_new_parent(),
        change_date=_CHANGE_DATE,
        modified_by_id=_AMENDER,
        data_context=None,
        log_callback=lambda *_a, **_k: None,
        is_top_level=True,
        override_mod_type="new_redaction",
        highlights=None,
    )

    amendment = child["revisions"][-1]
    assert amendment.get("valid_to") in (None, "")
    assert not amendment.get("not_valid")


def test_close_excluded_subtree_skips_already_marked_and_closed():
    from npazs.revision.ui_utils import _close_excluded_subtree

    element = {
        "item_id": "x",
        "revisions": [
            {"body": [], "valid_from": "05.01.2016", "valid_to": _VALID_TO_PREV},
            {"body": [], "valid_from": "05.01.2016", "not_valid": "other_npa"},
            {"body": [], "valid_from": "05.01.2016"},
        ],
        "item_children": [],
    }
    closed = _close_excluded_subtree(element, _VALID_TO_PREV, _AMENDER)
    assert closed is True
    assert element["revisions"][0].get("not_valid") is None  # untouched
    assert element["revisions"][1]["not_valid"] == "other_npa"  # untouched
    assert element["revisions"][2]["valid_to"] == _VALID_TO_PREV
    assert element["revisions"][2]["not_valid"] == _AMENDER
    assert element["revisions"][2].get("revision_id")  # id assigned for traceability


def test_coverage_check_passes_after_close():
    """The deterministic gap check (orphan_child_not_closed) must accept a
    child whose active revision carries not_valid from the amending NPA."""
    from npazs.revision.coverage_check import check_orphan_children

    child = _make_excluded_child()
    # Mirror the real 269-ЗС data: base revisions carry NO valid_from
    # (publication date is implicit) — exactly the shape the gap check flags.
    for rev in child["revisions"]:
        rev.pop("valid_from", None)
    for rev in child["item_children"][0]["revisions"]:
        rev.pop("valid_from", None)
    parent = _make_parent([child])
    # The check only inspects parents whose active revision was created by the
    # amending NPA (new_redaction) — stamp it accordingly.
    parent["revisions"][0]["mod_type"] = "new_redaction"
    parent["revisions"][0]["modified_by_id"] = _AMENDER
    result = {"npa_items_revision": [parent]}
    gaps_before = check_orphan_children(result, "33699")
    assert gaps_before, "precondition: excluded child is a gap while active"

    from npazs.revision.ui_utils import _close_excluded_subtree
    _close_excluded_subtree(child, _VALID_TO_PREV, _AMENDER)

    gaps_after = check_orphan_children(result, "33699")
    assert gaps_after == []


def _make_carried_over_result(child):
    """Родитель, пересозданный изменяющим НПА, чья новая ревизия ПО-ПРЕЖНЕМУ
    ссылается на ребёнка (child_ref): ребёнок перенесён новой редакцией
    без изменений, поэтому его старая ревизия осталась открытой сознательно.
    Реальный кейс: 380-ЗС п. 9 излагает статью 7 269-ЗС в новой редакции,
    где текст части 7 идентичен прежнему — новая ревизия не нужна."""
    parent = _make_parent([child])
    # Прошлая редакция родителя закрыта, новая — от изменяющего НПА.
    parent["revisions"][0]["valid_to"] = _VALID_TO_PREV
    parent["revisions"].append({
        "body": [{"type": "child_ref", "item_id": child["item_id"], "order": 1}],
        "valid_from": _CHANGE_DATE,
        "mod_type": "new_redaction",
        "modified_by_id": _AMENDER,
    })
    # Ребёнок перенесён как есть: базовая ревизия без дат, без not_valid.
    for rev in child["revisions"]:
        rev.pop("valid_from", None)
    return {"npa_items_revision": [parent]}


def test_carried_over_unchanged_child_is_not_orphan():
    """Ребёнок, перенесённый новой редакцией без изменений (child_ref жив,
    старая ревизия открыта), НЕ должен поднимать orphan_child_not_closed —
    иначе пост-анализ ложным incorrect'ом помечает корректный прогон
    (кейс 380-ЗС -> 269-ЗС, часть 7 статьи 7)."""
    child = _make_excluded_child()
    child["item_id"] = "16012_article_7_part_7"
    result = _make_carried_over_result(child)
    assert check_orphan_children(result, "33699") == []


def test_hanging_excluded_child_without_ref_still_gap():
    """Исходный баг должен оставаться детектируемым: ребёнок исключён новой
    редакцией (child_ref убран), но его ревизия осталась активной — сирота."""
    child = _make_excluded_child()
    result = _make_carried_over_result(child)
    # Убираем child_ref из новой ревизии родителя — ребёнок «повис».
    result["npa_items_revision"][0]["revisions"][1]["body"] = []
    gaps = check_orphan_children(result, "33699")
    assert len(gaps) == 1
    assert gaps[0]["reason"] == "orphan_child_not_closed"
    assert gaps[0]["target_item_id"] == child["item_id"]


def test_referenced_but_closed_child_is_gap():
    """Если родитель ссылается на ребёнка, но его активная ревизия закрыта —
    на сайте норма отрендерится пустой: это пробел, а не перенос."""
    child = _make_excluded_child()
    result = _make_carried_over_result(child)
    for rev in child["revisions"]:
        if rev.get("valid_to") in (None, ""):
            rev["valid_to"] = _VALID_TO_PREV
    gaps = check_orphan_children(result, "33699")
    assert len(gaps) == 1
    assert gaps[0]["reason"] == "orphan_child_not_closed"
