#!/usr/bin/env python3
"""Синхронизация артефактов вывода НПА на сайт (PHP/JS/CSS).

Каноническая логика вынесена в ``npazs.main._cmd_sync`` и доступна как
``npazs sync``. Скрипт — тонкая обёртка с bootstrap.
"""

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

from npazs.main import main

if __name__ == "__main__":
    raise SystemExit(main(["sync", *sys.argv[1:]]))
