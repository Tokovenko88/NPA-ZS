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

    # Регрессия: пунктуация нового последнего элемента скорректирована (';' -> '.')
    sibling = next(p for p in parts if p["item_number"] == "1.1")
    assert sibling["revisions"][0]["body"][0]["html_text"] == "<p>Ставка три процента.</p>"


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
