"""Test DB importer."""
import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "npazs_bootstrap", _ROOT / "src" / "bootstrap.py"
)
_bootstrap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bootstrap)
_bootstrap.bootstrap()

def test_connection_config():
    from npazs.db.connection import DB_DEFAULTS, DB_CONFIG
    assert "host" in DB_CONFIG
    assert "port" in DB_CONFIG

def test_parse_date():
    from npazs.db.connection import parse_date
    d = parse_date("30.12.2022")
    assert d is not None
    assert d.year == 2022
