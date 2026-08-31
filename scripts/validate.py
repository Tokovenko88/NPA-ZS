#!/usr/bin/env python3
"""Валидация JSON НПА и конфигурации (тонкая обёртка над ``npazs validate``)."""

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

from npazs.main import main

if __name__ == "__main__":
    raise SystemExit(main(["validate", *sys.argv[1:]]))
