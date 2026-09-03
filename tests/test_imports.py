"""Test imports."""
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

def test_core_imports():
    import npazs.core.html_parser
    import npazs.core.modx_processor
    import npazs.revision.engine
    import npazs.db.importer
    import npazs.ui.revision_app
