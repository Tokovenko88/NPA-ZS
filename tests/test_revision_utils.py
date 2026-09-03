"""Test revision utilities."""
import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "npazs_bootstrap", _ROOT / "src" / "bootstrap.py"
)
assert _spec is not None and _spec.loader is not None
_bootstrap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bootstrap)
_bootstrap.bootstrap()

def test_text_utils():
    from npazs.revision.text_utils import normalize_number_string, clean_head_text
    assert normalize_number_string("1") == "1"

def test_tree_utils():
    from npazs.revision.tree_utils import find_item_by_id
    sample = {"npa_items_revision": [{"item_id": "root", "item_children": [{"item_id": "child"}]}]}
    assert find_item_by_id(sample, "child") is not None
