"""Публичный bootstrap NPA-ZS: регистрация пакета ``npazs`` и путей проекта.

Модуль решает одну задачу: сделать так, чтобы код можно было запускать
и без установки пакета (``pip install -e .``), и после установки — одинаково.

Типовое использование в скриптах ``scripts/*.py``::

    import importlib.util, sys
    from pathlib import Path

    _ROOT = Path(__file__).resolve().parents[1]
    _spec = importlib.util.spec_from_file_location(
        "npazs_bootstrap", _ROOT / "src" / "bootstrap.py"
    )
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    _mod.bootstrap()

После вызова :func:`bootstrap` доступны обычные импорты ``npazs.*``.

Модуль также централизует все пути проекта (см. :data:`PATHS` и
:func:`ensure_runtime_dirs`), чтобы каталоги ``data/`` создавались из одного
места, а не разрозненно по коду.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

PACKAGE_NAME = "npazs"

_MARKER_DIRS = ("src",)
_MARKER_FILES = ("pyproject.toml", "requirements.txt")


def find_project_root(start: str | os.PathLike | None = None) -> Path:
    """Найти корень проекта по маркерам ``src/`` + ``pyproject.toml``."""
    current = Path(start or __file__).resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        has_dirs = all((candidate / d).is_dir() for d in _MARKER_DIRS)
        has_file = any((candidate / f).is_file() for f in _MARKER_FILES)
        if has_dirs and has_file:
            return candidate
    return current.parent


PROJECT_ROOT = find_project_root()
SRC_DIR = PROJECT_ROOT / "src"
DATA_DIR = PROJECT_ROOT / "data"

PATHS = {
    "root": PROJECT_ROOT,
    "src": SRC_DIR,
    "data": DATA_DIR,
    "prompts": DATA_DIR / "prompts",
    "input": DATA_DIR / "input",
    "output": DATA_DIR / "output",
    "stage_answers": DATA_DIR / "stage_answers",
    "work_tools": DATA_DIR / "work_tools",
    "debug_runs": DATA_DIR / "debug_runs",
    "logs": DATA_DIR / "logs",
    "base": DATA_DIR / "base",
    "base_law": DATA_DIR / "base" / "law",
    "base_resolution": DATA_DIR / "base" / "resolution",
    "docs": PROJECT_ROOT / "docs",
    "site": SRC_DIR / "site",
    "dist": PROJECT_ROOT / "dist",
}

# Каталоги, которые обязаны существовать во время выполнения.
_RUNTIME_DIRS = (
    "input",
    "output",
    "stage_answers",
    "work_tools",
    "debug_runs",
    "logs",
)


def ensure_runtime_dirs() -> None:
    """Создать каталоги времени выполнения в ``data/`` (идемпотентно)."""
    for key in _RUNTIME_DIRS:
        PATHS[key].mkdir(parents=True, exist_ok=True)


def register_package() -> object:
    """Зарегистрировать каталог ``src`` как пакет ``npazs`` в ``sys.modules``.

    Возвращает загруженный модуль пакета. Повторные вызовы безопасны.
    """
    existing = sys.modules.get(PACKAGE_NAME)
    if existing is not None:
        return existing

    init_file = SRC_DIR / "__init__.py"
    if not init_file.is_file():
        raise RuntimeError(f"Не найден {init_file}: структура проекта повреждена")

    spec = importlib.util.spec_from_file_location(
        PACKAGE_NAME,
        init_file,
        submodule_search_locations=[str(SRC_DIR)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Не удалось создать spec для пакета {PACKAGE_NAME}")

    module = importlib.util.module_from_spec(spec)
    # Регистрируем ДО exec_module, чтобы относительные импорты внутри пакета
    # уже видели себя в sys.modules.
    sys.modules[PACKAGE_NAME] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(PACKAGE_NAME, None)
        raise
    return module


def bootstrap(create_dirs: bool = True) -> object:
    """Полная подготовка окружения: ``sys.path`` + пакет ``npazs`` + каталоги."""
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    if create_dirs:
        ensure_runtime_dirs()
    return register_package()


__all__ = [
    "PACKAGE_NAME",
    "PROJECT_ROOT",
    "SRC_DIR",
    "DATA_DIR",
    "PATHS",
    "find_project_root",
    "ensure_runtime_dirs",
    "register_package",
    "bootstrap",
]
