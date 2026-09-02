#!/usr/bin/env python3
"""Запуск модуля сравнения редакций НПА (наш RTF против документа правовой системы).

Поддерживает два режима:
1. GUI (по умолчанию): ``python scripts/run_compare.py``
2. Пакетный режим: ``python scripts/run_compare.py --ours ours.rtf --theirs theirs.docx [--output report.md] [--mode mechanical]``

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
_bootstrap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bootstrap)
_bootstrap.bootstrap()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        from npazs.main import main

        if sys.argv[1] not in (
            'init', 'parse', 'revise', 'import', 'sync', 'validate',
            'report', 'compare',
        ):
            sys.argv.insert(1, 'compare')
        sys.exit(main())
    else:
        from npazs.compare.gui import main

        main()
