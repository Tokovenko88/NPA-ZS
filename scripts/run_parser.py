#!/usr/bin/env python3
"""Запуск парсера HTML НПА -> JSON.

Поддерживает два режима:
1. GUI (по умолчанию): ``python scripts/run_parser.py``
2. Пакетный разбор: ``python scripts/run_parser.py --input file.html [--output out.json] [--doc-type law|resolution]``

Работает и без ``pip install -e .``: загружает bootstrap, который регистрирует
пакет ``npazs`` в ``sys.modules``.
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

if __name__ == "__main__":
    if len(sys.argv) > 1:
        from npazs.main import main
        if sys.argv[1] not in ('parse', 'revise', 'import', 'sync', 'validate', 'report', 'init'):
            sys.argv.insert(1, 'parse')
        sys.exit(main())
    else:
        from npazs.core.modx_gui import MODXProcessorGUI
        app = MODXProcessorGUI()
        app.run()
