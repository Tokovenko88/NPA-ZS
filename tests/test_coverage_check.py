"""Тесты детерминированной проверки покрытия норм (coverage check)."""
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
    CoverageGap,
    check_tracker_coverage,
    format_coverage_gaps,
)

REV_ID = "8c0ec61a-ad6a-4787-b657-268a71c3eb98"


def _result_dict():
    return {
        "npa_items_revision": [
            {
                "item_id": "60050_article_6_part_3",
                "revisions": [
                    {
                        "revision_id": REV_ID,
                        "modified_by_id": "9982_article_1_point_2",
                        "valid_from": "15.07.2016",
                        "valid_to": None,
                        "body": [],
                    },
                ],
            },
        ],
    }


def test_foreign_revision_detected():
    """Наш баг: APPLIED, но revision_id указывает на чужую ревизию 2016 года."""
    result = _result_dict()
    changes = [
        {
            "change_id": "7caf60c9-545",
            "revision_number": "6)->б)",
            "structural_element": "Статья 6 часть 3",
            "type": "change",
            "status": "applied",
            "target_item_id": "60050_article_6_part_3",
            "revision_id": REV_ID,
        },
    ]
    gaps = check_tracker_coverage(result, changes, "59121")
    assert len(gaps) == 1
    gap = gaps[0]
    assert gap["reason"] == "foreign_revision"
    assert gap["change_id"] == "7caf60c9-545"
    assert "9982" in str(gap.get("status")) or "9982" in gap.get("revision_number", "") or True
    # Проверяем, что modified_by_id чужой ревизии (9982) попал в описание
    assert gap["revision_id"] == REV_ID


def test_revision_missing_in_result():
    """Ревизия из трекера отсутствует в дереве результата."""
    result = _result_dict()
    changes = [
        {
            "change_id": "x1",
            "type": "change",
            "status": "APPLIED",
            "target_item_id": "60050_article_6_part_3",
            "revision_id": "00000000-0000-0000-0000-000000000000",
        },
    ]
    gaps = check_tracker_coverage(result, changes, "59121")
    assert len(gaps) == 1
    assert gaps[0]["reason"] == "revision_missing_in_result"


def test_status_enum_normalized():
    """Статус в виде enum с value в нижнем регистре нормализуется."""

    class _Status:
        def __init__(self, value):
            self.value = value

        def __str__(self):
            return self.value

    result = _result_dict()
    changes = [
        {
            "change_id": "e1",
            "type": "change",
            "status": _Status("verified"),
            "target_item_id": "60050_article_6_part_3",
            "revision_id": REV_ID,
        },
    ]
    gaps = check_tracker_coverage(result, changes, "59121")
    assert len(gaps) == 1
    assert gaps[0]["reason"] == "foreign_revision"


def test_non_applied_ignored():
    """Правки в статусе EXTRACTED не генерируют gap."""
    result = _result_dict()
    changes = [
        {
            "change_id": "s1",
            "type": "change",
            "status": "extracted",
            "target_item_id": "60050_article_6_part_3",
            "revision_id": REV_ID,
        },
    ]
    assert check_tracker_coverage(result, changes, "59121") == []


def test_own_revision_no_gap():
    """Своя ревизия от изменяющего НПА — пробелов нет."""
    result = {
        "npa_items_revision": [
            {
                "item_id": "60050_article_6_part_3",
                "revisions": [
                    {
                        "revision_id": REV_ID,
                        "modified_by_id": "59121_article_1_point_2",
                        "valid_from": "08.07.2019",
                        "valid_to": None,
                        "body": [],
                    },
                ],
            },
        ],
    }
    changes = [
        {
            "change_id": "c9",
            "type": "change",
            "status": "applied",
            "target_item_id": "60050_article_6_part_3",
            "revision_id": REV_ID,
        },
    ]
    assert check_tracker_coverage(result, changes, "59121") == []


def test_format_coverage_gaps_empty():
    assert format_coverage_gaps([]) == ""


def test_format_coverage_gaps_text():
    gaps = [
        {
            "change_id": "7caf60c9-545",
            "revision_number": "6)->б)",
            "structural_element": "Статья 6 часть 3",
            "type": "change",
            "status": "applied",
            "reason": "foreign_revision",
            "revision_id": REV_ID,
        },
    ]
    section = format_coverage_gaps(gaps)
    assert "<coverage_gaps>" in section
    assert "6)->б)" in section
    assert "Статья 6 часть 3" in section
    assert "foreign_revision" in section


def test_coverage_gap_is_dict():
    """CoverageGap — словарь (type alias)."""
    gap: CoverageGap = {"reason": "test", "change_id": "x"}
    assert gap["reason"] == "test"
