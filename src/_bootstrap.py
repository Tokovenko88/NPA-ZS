"""Внутренний bootstrap: гарантирует, что корень проекта есть в ``sys.path``.

Исторический аналог — ``npa_processor/_bootstrap.py``. Функция вызывается на
верхнем уровне «тяжёлых» модулей (парсер, AI-пайплайн, GUI), которые могут быть
запущены как скрипт, а не как часть пакета.

Корень проекта определяется по маркерам: каталог ``src`` + файл
``pyproject.toml`` (или ``requirements.txt``). Это устойчиво к запуску из
подкаталогов и к сборке через PyInstaller.
"""

import os
import sys

_MARKER_DIRS = ("src",)
_MARKER_FILES = ("pyproject.toml", "requirements.txt")


def find_project_root(start=None):
    """Вернуть путь к корню проекта NPA-ZS."""
    current_dir = os.path.abspath(start or os.path.dirname(__file__))
    candidate = current_dir
    while True:
        has_dirs = all(os.path.isdir(os.path.join(candidate, d)) for d in _MARKER_DIRS)
        has_file = any(os.path.isfile(os.path.join(candidate, f)) for f in _MARKER_FILES)
        if has_dirs and has_file:
            return candidate
        parent = os.path.dirname(candidate)
        if parent == candidate:
            # Маркеры не найдены — откатываемся на каталог самого пакета.
            return os.path.dirname(current_dir)
        candidate = parent


def _bootstrap_project_root():
    """Добавить корень проекта в ``sys.path`` (идемпотентно)."""
    project_root = find_project_root()
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    return project_root


# Обратная совместимость с историческим именем.
bootstrap_project_root = _bootstrap_project_root

__all__ = ["find_project_root", "_bootstrap_project_root", "bootstrap_project_root"]
