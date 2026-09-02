"""Regression tests: применение delete-изменений через apply_change.

Рефакторинг (commit c58cf97) убрал wildcard-импорт `revision_utils`, из-за чего
в change_applier пропали имена ask_ollama / clean_and_unwrap_html /
adjust_punctuation_after_deletion и параметры backend/kilo_gateway_url/api_key.
Запуск внесения 768-ЗС в 110-ЗС (2026-09-01) падал с NameError на каждой
delete-операции. Эти тесты фиксируют работоспособность ветки delete и
сквозную передачу параметров ИИ-бэкенда.
"""
import importlib.util
import inspect
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "npazs_bootstrap", _ROOT / "src" / "bootstrap.py"
)
_bootstrap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bootstrap)
_bootstrap.bootstrap()


def _make_document():
    return {
        "npa_id": "51528",
        "npa_items_revision": [
            {
                "item_id": "51528_article_2",
                "item_type": "article",
                "item_number": "2",
                "item_children": [
                    {
                        "item_id": "51528_article_2_part_1_1",
                        "item_type": "part",
                        "item_number": "1.1",
                        "revisions": [
                            {
                                "revision_id": "rev-1-1",
                                "valid_from": "01.01.2023",
                                "valid_to": None,
                                "body": [
                                    {
                                        "type": "paragraph",
                                        "html_text": "<p>Ставка три процента;</p>",
                                        "order": 1,
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "item_id": "51528_article_2_part_1_2",
                        "item_type": "part",
                        "item_number": "1.2",
                        "revisions": [
                            {
                                "revision_id": "rev-1-2",
                                "valid_from": "01.01.2023",
                                "valid_to": None,
                                "mod_type": "change",
                                "modified_by_id": "93188_article_1_point_2_subpoint_г",
                                "body": [
                                    {
                                        "type": "paragraph",
                                        "html_text": "<p>Ставка один процент.</p>",
                                        "order": 1,
                                    }
                                ],
                            }
                        ],
                    },
                ],
            }
        ],
    }


def test_delete_change_applies_without_nameerror():
    from npazs.revision.change_applier import apply_change

    data = _make_document()
    change = {
        "change_id": "t1",
        "type": "delete",
        "structural_element": "Статья 2 часть 1.2",
        "_resolved_item_id": "51528_article_2_part_1_2",
        "description": "часть 1.2 признать утратившей силу",
        "valid_from": "27.06.2023",
    }

    result = apply_change(
        change=change,
        data=data,
        change_data={"npa_id": "115751"},
        law_ref="",
        general_valid_from=date(2023, 6, 27),
        log_callback=lambda *_args, **_kwargs: None,
    )

    assert result.get("status") == "APPLIED", result
    assert result.get("revision_id") == "rev-1-2"

    parts = data["npa_items_revision"][0]["item_children"]
    deleted = next(p for p in parts if p["item_number"] == "1.2")
    assert deleted["revisions"][0]["valid_to"] == "26.06.2023"
    assert deleted["revisions"][0]["not_valid"] == "115751"

    # Регрессия: при утрате силы информация о предыдущем изменении (mod_type,
    # modified_by_id) НЕ затирается — она описывает происхождение редакции.
    assert deleted["revisions"][0]["mod_type"] == "change"
    assert deleted["revisions"][0]["modified_by_id"] == "93188_article_1_point_2_subpoint_г"
    assert deleted["revisions"][0]["revision_id"] == "rev-1-2"

    # Регрессия: пунктуация нового последнего элемента скорректирована (';' -> '.')
    sibling = next(p for p in parts if p["item_number"] == "1.1")
    assert sibling["revisions"][0]["body"][0]["html_text"] == "<p>Ставка три процента.</p>"


def test_delete_base_revision_without_mod_type_assigns_revision_id():
    from npazs.revision.change_applier import apply_change

    data = _make_document()
    change = {
        "change_id": "t2",
        "type": "delete",
        "structural_element": "Статья 2 часть 1.1",
        "_resolved_item_id": "51528_article_2_part_1_1",
        "description": "часть 1.1 признать утратившей силу",
        "valid_from": "27.06.2023",
    }

    result = apply_change(
        change=change,
        data=data,
        change_data={"npa_id": "115751"},
        law_ref="",
        general_valid_from=date(2023, 6, 27),
        log_callback=lambda *_args, **_kwargs: None,
    )

    assert result.get("status") == "APPLIED", result
    parts = data["npa_items_revision"][0]["item_children"]
    deleted = next(p for p in parts if p["item_number"] == "1.1")
    assert deleted["revisions"][0]["valid_to"] == "26.06.2023"
    assert deleted["revisions"][0]["not_valid"] == "115751"
    assert deleted["revisions"][0]["revision_id"] == "rev-1-1"


def test_backend_params_threaded_through_apply_chain():
    from npazs.revision.change_applier import (
        _apply_change_impl,
        _apply_change_to_element_content,
        apply_change,
    )
    from npazs.revision.change_pipeline import apply_change_tracked

    for func in (apply_change, _apply_change_impl, _apply_change_to_element_content):
        params = inspect.signature(func).parameters
        assert {"backend", "kilo_gateway_url", "api_key"} <= set(params), func.__name__

    assert "backend" in inspect.signature(apply_change_tracked).parameters
    # change снова доступен в _apply_change_to_element_content (иначе TypeError
    # на `'_quoted_html' in change` в ветке new_redaction)
    assert "change" in inspect.signature(_apply_change_to_element_content).parameters


def test_paragraph_new_redaction_sets_parent_mod_type_change():
    """Paragraph-level new_redaction must produce mod_type='change' on the parent
    structural element, and the verifier must accept it."""
    from npazs.revision.change_applier import apply_grouped_changes
    from npazs.revision.change_pipeline import verify_change_applied

    element = {
        "item_id": "part_1_7",
        "item_type": "part",
        "item_number": "1.7",
        "revisions": [
            {
                "revision_id": "rev-old",
                "valid_from": "01.01.2026",
                "valid_to": None,
                "body": [
                    {
                        "type": "paragraph",
                        "html_text": "<p>старый текст</p>",
                        "order": 1,
                    }
                ],
            }
        ],
    }
    changes = [
        {
            "change_id": "c1",
            "type": "new_redaction",
            "structural_element": "Статья 2 часть 1.7 абзац 1",
            "revision_number": "1)",
            "description": "",
            "_quoted_html": "<p>новый текст</p>",
            "_resolved_item_id": "part_1_7",
        }
    ]
    rebuild_ids = []
    logs = []
    result = apply_grouped_changes(
        element=element,
        changes=changes,
        valid_from=date(2026, 8, 31),
        change_data={"npa_id": "931-ЗС"},
        data={"npa_items_revision": [element]},
        model=None,
        prompt4=None,
        log_callback=lambda msg, level="info": logs.append((msg, level)),
        rebuild_ids=rebuild_ids,
        extra_options={},
        source_item_id="src_art_1",
        change_ids=["c1"],
    )
    if result[0]["status"] != "PREPARED":
        print("LOGS:", logs)
        print("RESULT:", result)
    assert result[0]["status"] == "PREPARED"
    assert element["_pending_mod_type"] == "change"
    assert element["_pending_new_redaction_html"] == "<p>новый текст</p>"

    # Simulate rebuild: create a new revision with mod_type='change'
    from datetime import timedelta
    valid_to_prev = (date(2026, 8, 31) - timedelta(days=1)).strftime("%d.%m.%Y")
    element["revisions"][0]["valid_to"] = valid_to_prev
    element["revisions"].append(
        {
            "revision_id": "rev-new",
            "valid_from": "31.08.2026",
            "valid_to": None,
            "mod_type": "change",
            "body": [{"type": "paragraph", "html_text": "<p>новый текст</p>", "order": 1}],
        }
    )
    element.pop("_pending_mod_type", None)
    element.pop("_pending_new_redaction_html", None)

    verified = verify_change_applied(
        change=changes[0],
        data={"npa_items_revision": [element]},
        change_data={"npa_id": "931-ЗС"},
        log_callback=lambda *_a, **_k: None,
        expected_revision_id="rev-new",
    )
    assert verified is True
