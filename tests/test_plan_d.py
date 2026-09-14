"""Проверка изменения D: revision_info для наименования НПА."""

import json
import copy
from datetime import date
from pathlib import Path
import importlib.util
import pytest


_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("npazs_bootstrap", _ROOT / "src" / "bootstrap.py")
_bootstrap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bootstrap)
_bootstrap.bootstrap()

from npazs.revision.change_applier import apply_change


@pytest.fixture
def result_data():
    result_path = r"D:\Base\law\269\269_2016_07_27_izm_380_2017_12_04.json"
    with open(result_path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def change_data():
    change_path = r"D:\Base\law\269\380.json"
    with open(change_path, encoding="utf-8") as f:
        return json.load(f)


def test_revision_info_npa_head_added(result_data, change_data):
    """План D: после применения new_redaction для наименования в revision_info
    появляется запись с structural_element == 'НПА'."""
    # structural_element == 'наименование' → _apply_change_to_head → План D
    ci = {
        "change_id": "test-d-1",
        "revision_number": "1)",
        "type": "new_redaction",
        "structural_element": "наименование",
        "description": "",
        "_resolved_item_id": "__наименование__",
        # Для new_redaction нужен источник HTML (заголовок)
        "_quoted_html": "<p>Оptestовый заголовок закона</p>",
    }

    data = copy.deepcopy(result_data)
    log_lines = []

    def log_callback(msg, level='info'):
        log_lines.append(f"[{level}] {msg}")

    apply_change(
        ci, data, change_data, "dummy", date(2024, 1, 1), log_callback,
        None, None, None, None, None, None, None, None, None, None
    )

    revision_info = data.get("revision_info", [])
    npa_entries = [
        e for e in revision_info
        if e.get("structural_element") == "НПА"
    ]

    assert len(npa_entries) >= 1, (
        "В revision_info должна появиться запись для наименования НПА"
    )
    entry = npa_entries[0]
    assert entry.get("type") == "new_redaction", "Тип ревизии должен быть new_redaction"
    assert entry.get("revision_number") == "1)", "Номер ревизии должен совпадать"
    print(f"  revision_info count: {len(revision_info)}")
    print(f"  NPA entries: {len(npa_entries)}")
    print(f"  entry: {json.dumps(entry, ensure_ascii=False)}")