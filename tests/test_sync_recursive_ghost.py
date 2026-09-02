"""Regression tests: sync_structural_element_recursive must not clobber a child
element that was already reconstructed earlier in the same run.

Reproduces the 127 <- 516 (amendment 6->г) ghost revision bug: when a parent
part is rebuilt, the parent's re-parsed HTML can hold a *stale duplicate* of a
child point (old text concatenated with the new redaction). Without a guard,
``sync_structural_element_recursive`` re-derives the child body from that stale
HTML, closes the already-correct child revision (e.g. ``ec820ed3``) and creates
a ghost ``change`` revision carrying the OLD body and no highlights, which then
becomes the active revision and masks the proper amendment.
"""
import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "npazs_bootstrap", _ROOT / "src" / "bootstrap.py"
)
_bootstrap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bootstrap)
_bootstrap.bootstrap()


_CHANGE_DATE = "19.07.2019"
_GOVERNOR = "в Законодательное Собрание города Севастополя"
_OLD_TEXT = (
    "письменное заявление кандата о согласии на внесение его кандидатуры "
    "для назначения на должность Уполномоченного, в котором указываются:"
)
_NEW_TEXT = _OLD_TEXT.replace(
    "внесение его кандидатуры для назначения",
    f"внесение его кандидатуры {_GOVERNOR} для назначения",
)


def _make_point_1_previously_revised():
    """point_1 as it exists right after its own CONTENT_REBUILD succeeded:
    an expired base revision plus one active amendment revision dated the
    current change date, carrying the governor sentence + a highlight."""
    return {
        "item_id": "60050_article_6_part_5_point_1",
        "item_type": "point",
        "item_number": "1)",
        "revisions": [
            {
                "revision_id": "rev-old",
                "body": [{"type": "paragraph", "html_text": f"<p>{_OLD_TEXT}</p>", "order": 1}],
                "valid_from": "05.01.2016",
                "valid_to": "18.07.2019",
                "mod_type": "new_redaction",
                "modified_by_id": "9982_article_1_point_2",
            },
            {
                "revision_id": "ec820ed3-repro",
                "body": [{"type": "paragraph", "html_text": f"<p>{_NEW_TEXT}</p>", "order": 1}],
                "mod_type": "change",
                "modified_by_id": "59121_article_1_point_6_subpoint_г",
                "valid_from": _CHANGE_DATE,
                "highlights": {
                    "previous_edition": {"deletion": [], "addition": [], "difference": []},
                    "current_edition": {
                        "deletion": [],
                        "addition": [[_GOVERNOR, "1-1"]],
                        "difference": [],
                    },
                },
            },
        ],
    }


def _stale_parent_repased_child():
    """The same point_1 as it appears when re-parsed from the PARENT part's
    stale pending_html (old text, without the governor sentence)."""
    return {
        "item_type": "point",
        "item_number": "1)",
        "revisions": [
            {
                "body": [{"type": "paragraph", "html_text": f"<p>{_OLD_TEXT}</p>", "order": 1}],
            }
        ],
    }


def test_sync_preserves_already_revised_child_from_stale_parent_repase():
    from npazs.revision.ui_utils import sync_structural_element_recursive

    point_1 = _make_point_1_previously_revised()
    stale_repase = _stale_parent_repased_child()

    sync_structural_element_recursive(
        old_element=point_1,
        new_element=stale_repase,
        change_date=_CHANGE_DATE,
        modified_by_id="59121_article_1_point_6_subpoint_г-root",
        data_context=None,
        log_callback=lambda *_a, **_k: None,
        is_top_level=False,
        override_mod_type="new_redaction",
        highlights=None,
    )

    revs = point_1["revisions"]
    # The correct amendment revision must remain active (not closed) ...
    ec = next(r for r in revs if r["revision_id"] == "ec820ed3-repro")
    assert ec.get("valid_to") is None
    assert ec["valid_from"] == _CHANGE_DATE
    body_text = ec["body"][0]["html_text"]
    assert _GOVERNOR in body_text, "amendment text must survive the parent sync"
    assert ec.get("highlights"), "amendment highlights must survive the parent sync"
    # ... and NO ghost revision was appended.
    ghost = [r for r in revs if r["revision_id"] != "ec820ed3-repro" and r["revision_id"] != "rev-old"]
    assert ghost == [], f"unexpected ghost revision(s): {ghost}"
    assert len(revs) == 2


def test_sync_still_revisions_child_from_previous_era_when_text_changes():
    """A child whose active revision predates the current run is NOT protected
    by the guard: a genuine text change (coming from a correct parent re-parse)
    must still produce a new revision."""
    from npazs.revision.ui_utils import sync_structural_element_recursive

    point_1 = _make_point_1_previously_revised()
    # Make the base revision the active one again (clear the amendment rev) and
    # give it an earlier valid_from so the guard does not fire.
    point_1["revisions"][1]["valid_to"] = "18.07.2019"  # close the amendment rev
    # re-add an active base rev dated before the change date
    point_1["revisions"].append(
        {
            "revision_id": "rev-old-active",
            "body": [{"type": "paragraph", "html_text": f"<p>{_OLD_TEXT}</p>", "order": 1}],
            "valid_from": "05.01.2016",
        }
    )

    correct_repase = {
        "item_type": "point",
        "item_number": "1)",
        "revisions": [
            {
                "body": [{"type": "paragraph", "html_text": f"<p>{_NEW_TEXT}</p>", "order": 1}],
            }
        ],
    }

    sync_structural_element_recursive(
        old_element=point_1,
        new_element=correct_repase,
        change_date=_CHANGE_DATE,
        modified_by_id="59121_article_1_point_6_subpoint_г-root",
        data_context=None,
        log_callback=lambda *_a, **_k: None,
        is_top_level=False,
        override_mod_type="new_redaction",
        highlights=None,
    )

    active = [r for r in point_1["revisions"] if r.get("valid_to") is None]
    assert len(active) == 1
    assert _GOVERNOR in active[0]["body"][0]["html_text"]
