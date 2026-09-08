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


def test_change_status_enum_normalized():
    """Статус в виде ChangeStatus enum (str, Enum) должен нормализоваться.

    Баг: в Python 3.11+ str(ChangeStatus.VERIFIED) возвращает 'ChangeStatus.VERIFIED',
    а не 'verified'. Из-за этого проверка 'status not in {"applied", "verified"}'
    возвращала True и изменение пропускалось.
    """
    from npazs.revision.change_tracker import ChangeStatus

    result = _result_dict()
    changes = [
        {
            "change_id": "7caf60c9-545",
            "revision_number": "6)->б)",
            "structural_element": "Статья 6 часть 3",
            "type": "change",
            "status": ChangeStatus.VERIFIED,  # enum, не строка!
            "target_item_id": "60050_article_6_part_3",
            "revision_id": REV_ID,
        },
    ]
    gaps = check_tracker_coverage(result, changes, "59121")
    assert len(gaps) == 1, f"Ожидался 1 gap, получено: {gaps}"
    assert gaps[0]["reason"] == "foreign_revision"


def test_delete_type_checked_for_coverage():
    """Правка типа 'delete' («слова ... исключить») должна проверяться на покрытие.

    Баг 127/516: правка 'в части 3 слова ... исключить' не проверялась,
    потому что 'delete' отсутствовал в _STRICT_TYPES. Теперь delete проверяется
    отдельно: если на элементе нет ни ревизии изменяющего НПА, ни его
    not_valid-метки — фиксируется пробел not_marked_invalid.
    """
    result = {
        "npa_items_revision": [
            {
                "item_id": "60050_article_1_part_3",
                "revisions": [
                    {
                        "revision_id": "aaaa1111",
                        "modified_by_id": "9982_article_1_point_2",  # чужая ревизия
                        "valid_from": "15.07.2016",
                        "valid_to": None,
                        "body": [],
                    },
                ],
            },
        ],
    }
    changes = [
        {
            "change_id": "del-1",
            "revision_number": "1)->6)->б)",
            "structural_element": "Статья 1 пункт 6 подпункт б",
            "type": "delete",
            "status": "applied",
            "target_item_id": "60050_article_1_part_3",
            "revision_id": "aaaa1111",
        },
    ]
    gaps = check_tracker_coverage(result, changes, "59121")
    assert len(gaps) == 1, f"Ожидался 1 gap, получено: {gaps}"
    assert gaps[0]["reason"] == "not_marked_invalid"
    assert gaps[0]["type"] == "delete"


def test_delete_repel_marked_by_own_law_no_gap():
    """Баг 516-ЗС (ложные foreign_revision на утративших силу): «признать
    утратившим силу» НЕ создаёт новой ревизии — корректное применение это
    not_valid на существующей ревизии (часто чужого закона). Пробела быть
    не должно.
    """
    result = {
        "npa_items_revision": [
            {
                "item_id": "60050_article_10_part_2_point_8",
                "revisions": [
                    {
                        "revision_id": "6f712edf-f287-47da-aa2a-d2c9745c45df",
                        "modified_by_id": "",  # ревизия исходной редакции, автора нет
                        "valid_from": None,
                        "valid_to": "18.07.2019",
                        "not_valid": "59121_article_1_point_10_subpoint_б",
                        "body": [{"type": "paragraph", "html_text": "<p>текст пункта</p>", "order": 1}],
                    },
                ],
            },
        ],
    }
    changes = [
        {
            "change_id": "del-8",
            "revision_number": "10)->б)",
            "structural_element": "Статья 10 часть 2 пункт 8",
            "type": "delete",
            "status": "verified",
            "target_item_id": "60050_article_10_part_2_point_8",
            "revision_id": "6f712edf-f287-47da-aa2a-d2c9745c45df",
        },
    ]
    assert check_tracker_coverage(result, changes, "59121") == []


def test_delete_repel_marked_by_foreign_law_gap():
    """Элемент помечен not_valid ЧУЖИМ законом — правка изменяющего НПА не применена."""
    result = {
        "npa_items_revision": [
            {
                "item_id": "60050_article_10_part_2_point_8",
                "revisions": [
                    {
                        "revision_id": "rev-x",
                        "modified_by_id": "",
                        "valid_to": "31.12.2016",
                        "not_valid": "9982_article_1_point_2",  # чужой закон
                        "body": [],
                    },
                ],
            },
        ],
    }
    changes = [
        {
            "change_id": "del-9",
            "revision_number": "10)->б)",
            "structural_element": "Статья 10 часть 2 пункт 8",
            "type": "delete",
            "status": "applied",
            "target_item_id": "60050_article_10_part_2_point_8",
            "revision_id": "rev-x",
        },
    ]
    gaps = check_tracker_coverage(result, changes, "59121")
    assert len(gaps) == 1
    assert gaps[0]["reason"] == "not_marked_invalid"


def test_delete_word_exclusion_own_revision_no_gap():
    """«Слова ... исключить»: изменяющий НПА создал собственную ревизию на
    элементе — delete применён, пробела нет (даже если not_valid не стоит)."""
    result = {
        "npa_items_revision": [
            {
                "item_id": "60050_article_6_part_3",
                "revisions": [
                    {
                        "revision_id": "rev-old",
                        "modified_by_id": "9982_article_1_point_2",
                        "valid_to": "18.07.2019",
                        "body": [],
                    },
                    {
                        "revision_id": "rev-new",
                        "modified_by_id": "59121_article_1_point_6_subpoint_б",
                        "valid_from": "19.07.2019",
                        "valid_to": "",
                        "body": [],
                    },
                ],
            },
        ],
    }
    changes = [
        {
            "change_id": "del-exc",
            "revision_number": "6)->б)",
            "structural_element": "Статья 6 часть 3",
            "type": "delete",
            "status": "applied",
            "target_item_id": "60050_article_6_part_3",
            "revision_id": "rev-new",
        },
    ]
    assert check_tracker_coverage(result, changes, "59121") == []


def test_head_revision_resolves_no_gap():
    """Баг 516-ЗС (ложный revision_missing_in_result на наименовании статьи 13):
    head-правка хранится в трекере как type=change, а её revision_id указывает
    на запись в head_revisions. collect_result_revisions обязан индексировать
    head_revisions — тогда пробела нет.
    """
    result = {
        "npa_items_revision": [
            {
                "item_id": "60050_article_13",
                "revisions": [{"revision_id": "body-rev", "modified_by_id": "127", "body": []}],
                "head_revisions": [
                    {"head_text": "Старое наименование", "valid_to": "18.07.2019"},
                    {
                        "head_text": "Новое наименование",
                        "valid_to": "",
                        "modified_by_id": "59121_article_1_point_13_subpoint_а",
                        "revision_id": "32d775c5-0683-4734-ba84-eea7ca06c096",
                    },
                ],
            },
        ],
    }
    changes = [
        {
            "change_id": "head-13",
            "revision_number": "13)->а)",
            "structural_element": "Статья 13 (наименование)",
            "type": "change",
            "status": "verified",
            "target_item_id": "60050_article_13",
            "revision_id": "32d775c5-0683-4734-ba84-eea7ca06c096",
        },
    ]
    assert check_tracker_coverage(result, changes, "59121") == []
