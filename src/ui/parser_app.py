"""GUI парсера НПА: HTML -> каноничный JSON.

Модуль — точка входа для второго крупного приложения проекта (первое —
:mod:`npazs.ui.revision_app`). Само окно реализовано классом
``MODXProcessorGUI`` в :mod:`npazs.core.modx_gui`; здесь собрана обвязка
запуска и проверка окружения.

Что делает приложение
---------------------
1. подключается к MODX (SSH + MySQL) и показывает список ресурсов НПА;
2. выгружает HTML выбранного ресурса;
3. прогоняет его через ``NpaToJsonGenerator`` (:mod:`npazs.core.html_parser`);
4. сохраняет результат в ``data/output/`` или в ``data/base/{law,resolution}/``.

Запуск::

    python scripts/run_parser.py
    python -m npazs --parser
"""

from __future__ import annotations

import sys

__all__ = ['check_environment', 'build_app', 'main']

#: Минимальная версия Python (ниже не работают f-строки/типы, используемые в ядре).
MIN_PYTHON = (3, 8)


def check_environment() -> list[str]:
    """Проверить окружение. Вернуть список сообщений об ошибках (пустой — всё ок)."""
    problems: list[str] = []

    if sys.version_info < MIN_PYTHON:
        problems.append(
            f'Требуется Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} или выше, '
            f'установлен {sys.version_info.major}.{sys.version_info.minor}'
        )

    try:
        import tkinter  # noqa: F401
    except ImportError:
        problems.append(
            'Tkinter не установлен. '
            'Ubuntu/Debian: sudo apt-get install python3-tk; '
            'macOS: brew install python-tk; '
            'Windows: переустановите Python с опцией "tcl/tk and IDLE"'
        )

    for module_name, hint in (
        ('bs4', 'beautifulsoup4'),
        ('paramiko', 'paramiko'),
        ('pymysql', 'pymysql'),
    ):
        try:
            __import__(module_name)
        except ImportError:
            problems.append(f'Не установлен пакет "{hint}" (pip install -r requirements.txt)')

    return problems


def build_app():
    """Создать экземпляр GUI парсера (``MODXProcessorGUI``) без запуска цикла."""
    from npazs.core.modx_gui import MODXProcessorGUI

    return MODXProcessorGUI()


def main() -> int:
    """Запустить GUI парсера. Возвращает код выхода процесса."""
    problems = check_environment()
    if problems:
        for problem in problems:
            print(f'Ошибка окружения: {problem}', file=sys.stderr)
        return 1

    app = build_app()
    app.run()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
