#!/usr/bin/env python3
"""Запуск внесения изменений в НПА (5-этапный AI-пайплайн).

Поддерживает два режима:
1. GUI (по умолчанию): ``python scripts/run_revision.py``
2. Пакетный режим: ``python scripts/run_revision.py --source change.json --target original.json [--output result.json] [--backend ollama|kilo_gateway] [--model model_name]``

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
            sys.argv.insert(1, 'revise')
        sys.exit(main())
    else:
        from npazs.ui.revision_app import App
        import tkinter as tk
        root = tk.Tk()
        app = App(root)
        root.mainloop()
