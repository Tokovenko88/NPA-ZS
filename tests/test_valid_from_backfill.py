"""Regression tests: closed/rebuilt revisions of nested elements must never
stay "bare" (no ``valid_from``).

Case 269-ЗС <- 380-ЗС: the pipeline closed the base revisions of nested
elements (article 3 point 1, article 4, ...) without a ``valid_from``, so the
DB importer had to guess the start date and logged
«Ревизии вложенных элементов без valid_from/mod_type …». The reference
(repo) JSON keeps the closed base revision stamped with the root document date
(08.08.2016). ``backfill_revision_valid_from`` restores exactly that, using the
importer convention (``compute_valid_from``: prev revision ``valid_to`` + 1
day, otherwise the root document date).
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

from npazs.revision.ui_utils import backfill_revision_valid_from

_ROOT_DATE = "08.08.2016"
_CHANGE_DATE = "15.12.2017"
_VALID_TO_PREV = "14.12.2017"
_AMENDER = "33699_article_1_point_4"


def _par(text):
    return [{"type": "paragraph", "html_text": f"<p>{text}</p>", "order": 1}]


def _bare_closed_rev():
    """Base revision closed by the amendment but never stamped with valid_from."""
    return {
        "body": _par("Старый текст нормы."),
        "valid_to": _VALID_TO_PREV,
    }


def _amendment_rev():
    return {
        "body": _par("Новый текст нормы."),
        "valid_from": _CHANGE_DATE,
        "mod_type": "new_redaction",
        "modified_by_id": _AMENDER,
    }


def _make_data(items):
    return {
        "npa_id": 16012,
        "valid_from": _ROOT_DATE,
        "npa_items_revision": items,
    }


def _nested_element(revisions):
    return {
        "item_id": "16012_article_3_point_1",
        "item_type": "point",
        "item_number": "1",
        "revisions": revisions,
    }


def test_closed_bare_revision_gets_root_date():
    """Кейс 269 <- 380: закрытая базовая ревизия пункта получает дату корня."""
    element = _nested_element([_bare_closed_rev(), _amendment_rev()])
    filled = backfill_revision_valid_from(_make_data([element]))
    assert filled == 1
    assert element["revisions"][0]["valid_from"] == _ROOT_DATE
    # Проштампованная ревизия изменяющего НПА не переписывается.
    assert element["revisions"][1]["valid_from"] == _CHANGE_DATE


def test_backfill_chain_follows_prev_valid_to():
    """Последующие ревизии начинаются на день позже valid_to предыдущей."""
    element = _nested_element([
        {"body": _par("Ред. 1."), "valid_from": "01.01.2016", "valid_to": "10.06.2016"},
        _bare_closed_rev(),
        {"body": _par("Действующая."), "mod_type": "change", "valid_from": _CHANGE_DATE},
    ])
    filled = backfill_revision_valid_from(_make_data([element]))
    assert filled == 1
    assert element["revisions"][1]["valid_from"] == "11.06.2016"


def test_active_bare_revision_gets_chain_date():
    """Активная «голая» ревизия тоже заполняется — импортёр предупреждал и для неё."""
    element = _nested_element([
        {"body": _par("Ред. 1."), "valid_from": "01.01.2016", "valid_to": "10.06.2016"},
        {"body": _par("Действующая без даты.")},
    ])
    filled = backfill_revision_valid_from(_make_data([element]))
    assert filled == 1
    assert element["revisions"][1]["valid_from"] == "11.06.2016"


def test_first_rev_without_root_date_stays_bare():
    """Без корневой даты и без предыдущей ревизии якоря нет — не трогаем."""
    element = _nested_element([{"body": _par("Текст.")}])
    data = {"npa_id": 16012, "npa_items_revision": [element]}
    filled = backfill_revision_valid_from(data)
    assert filled == 0
    assert "valid_from" not in element["revisions"][0]


def test_head_number_prefix_revisions_untouched():
    """head/number/prefix ревизии импортёр считает по своим цепочкам — не трогаем."""
    element = {
        "item_id": "16012_article_3",
        "item_type": "article",
        "item_number": "3",
        "head_revisions": [{"head_text": "Статья 3", "valid_to": _VALID_TO_PREV}],
        "number_revisions": [{"number_text": "3", "valid_to": _VALID_TO_PREV}],
        "item_prefix_revisions": [{"prefix_text": "Приложение", "valid_to": _VALID_TO_PREV}],
        "revisions": [_bare_closed_rev()],
    }
    filled = backfill_revision_valid_from(_make_data([element]))
    assert filled == 1
    assert "valid_from" not in element["head_revisions"][0]
    assert "valid_from" not in element["number_revisions"][0]
    assert "valid_from" not in element["item_prefix_revisions"][0]
    assert element["revisions"][0]["valid_from"] == _ROOT_DATE


def test_backfill_walks_children_recursively():
    """Ревизии внуков (пункт внутри части внутри статьи) тоже восстанавливаются."""
    point = {
        "item_id": "16012_article_4_part_1_point_1",
        "item_type": "point",
        "item_number": "1",
        "revisions": [_bare_closed_rev()],
    }
    part = {
        "item_id": "16012_article_4_part_1",
        "item_type": "part",
        "item_number": "1",
        "item_children": [point],
        "revisions": [_amendment_rev()],
    }
    article = {
        "item_id": "16012_article_4",
        "item_type": "article",
        "item_number": "4",
        "item_children": [part],
        "revisions": [_bare_closed_rev()],
    }
    filled = backfill_revision_valid_from(_make_data([article]))
    assert filled == 2
    assert article["revisions"][0]["valid_from"] == _ROOT_DATE
    assert point["revisions"][0]["valid_from"] == _ROOT_DATE


def test_iso_valid_to_parsed_for_chain():
    """valid_to в формате 'YYYY-MM-DD' тоже служит якорем для следующей ревизии."""
    element = _nested_element([
        {"body": _par("Ред. 1."), "valid_from": "2016-01-01", "valid_to": "2017-12-14"},
        {"body": _par("Действующая без даты.")},
    ])
    filled = backfill_revision_valid_from(_make_data([element]))
    assert filled == 1
    assert element["revisions"][1]["valid_from"] == _CHANGE_DATE


def test_log_callback_reports_filled_count():
    element = _nested_element([_bare_closed_rev(), _amendment_rev()])
    messages = []
    backfill_revision_valid_from(
        _make_data([element]),
        log_callback=lambda msg, tag="info": messages.append((msg, tag)),
    )
    assert messages, "backfill must report what it filled"
    msg, tag = messages[0]
    assert "1" in msg and "16012_article_3_point_1" in msg
    assert tag == "info"


def test_simulated_269_case_matches_reference_state():
    """Полный сценарий 269 <- 380: результат совпадает с эталонным JSON (repo)."""
    article_3_point_1 = _nested_element([_bare_closed_rev(), _amendment_rev()])
    article_4 = {
        "item_id": "16012_article_4",
        "item_type": "article",
        "item_number": "4",
        "revisions": [
            _bare_closed_rev(),
            {
                "body": [],
                "valid_from": _CHANGE_DATE,
                "mod_type": "new_redaction",
                "modified_by_id": "33699_article_1_point_5",
            },
        ],
        "item_children": [],
    }
    backfill_revision_valid_from(_make_data([article_3_point_1, article_4]))
    # Эталон: rev#0 закрыт с valid_from корневой редакции, rev#1 — штамп 380-ЗС.
    assert article_3_point_1["revisions"][0]["valid_from"] == _ROOT_DATE
    assert article_4["revisions"][0]["valid_from"] == _ROOT_DATE
