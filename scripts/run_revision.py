#!/usr/bin/env python3
"""Запуск GUI внесения изменений (5-этапный AI-пайплайн).

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

from npazs.ui.revision_app import App
import tkinter as tk

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
