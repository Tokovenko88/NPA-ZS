"""Разбор аргументов командной строки NPA-ZS.

Единая точка входа — ``npazs <команда>``. Команды соответствуют файлам в
``.kilo/commands/`` и целям в ``Makefile``:

=========  ==============================================================
Команда    Действие
=========  ==============================================================
init       Проверить окружение, создать каталоги ``data/``, показать статус
parse      Запустить GUI парсера HTML -> JSON
revise     Запустить GUI внесения изменений (5-этапный AI-пайплайн)
import     Запустить импортёр JSON -> MySQL
sync       Показать/подготовить артефакты вывода НПА на сайт
validate   Проверить JSON НПА и конфигурацию (без GUI)
report     Собрать отчёт о последнем прогоне
=========  ==============================================================

Модуль занимается только разбором аргументов: сам он ничего не выполняет.
Исполнение — в :mod:`npazs.main`.
"""

from __future__ import annotations

import argparse
from typing import Optional, Sequence

__all__ = ['COMMANDS', 'build_parser', 'parse_args']

#: Список команд: имя -> краткое описание (используется в справке и в report).
COMMANDS = {
    'init': 'Проверить окружение и подготовить каталоги data/',
    'parse': 'GUI парсера: HTML НПА -> каноничный JSON',
    'revise': 'GUI внесения изменений: 5-этапный AI-пайплайн',
    'import': 'Импорт JSON НПА в MySQL',
    'sync': 'Артефакты вывода НПА на сайт (PHP/JS/CSS)',
    'validate': 'Валидация JSON НПА и конфигурации',
    'report': 'Отчёт о последнем прогоне',
}


def build_parser() -> argparse.ArgumentParser:
    """Собрать парсер аргументов верхнего уровня."""
    parser = argparse.ArgumentParser(
        prog='npazs',
        description='NPA-ZS — конвейер обработки нормативных правовых актов',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            'Примеры:\n'
            '  npazs init\n'
            '  npazs validate --input data/base/law/110/110.json\n'
            '  npazs import --file data/output/result_npa.json --dry-run\n'
            '  npazs revise\n'
        ),
    )
    parser.add_argument('--version', action='store_true', help='Показать версию и выйти')
    parser.add_argument(
        '-v', '--verbose', action='store_true', help='Подробный вывод (LOG_LEVEL=DEBUG)'
    )

    subparsers = parser.add_subparsers(dest='command', metavar='<команда>')

    # --- init ---------------------------------------------------------------
    init_parser = subparsers.add_parser(
        'init', help=COMMANDS['init'], description=COMMANDS['init']
    )
    init_parser.add_argument(
        '--check-db', action='store_true', help='Дополнительно проверить подключение к MySQL'
    )

    # --- parse --------------------------------------------------------------
    parse_parser = subparsers.add_parser(
        'parse', help=COMMANDS['parse'], description=COMMANDS['parse']
    )
    parse_parser.add_argument('--input', help='HTML-файл для разбора (иначе выбор в GUI)')
    parse_parser.add_argument('--output', help='Куда сохранить JSON')
    parse_parser.add_argument(
        '--doc-type',
        choices=('law', 'resolution'),
        default='law',
        help='Тип документа (по умолчанию law)',
    )

    # --- revise -------------------------------------------------------------
    revise_parser = subparsers.add_parser(
        'revise', help=COMMANDS['revise'], description=COMMANDS['revise']
    )
    revise_parser.add_argument('--source', help='JSON изменяющего НПА')
    revise_parser.add_argument('--target', help='JSON целевого НПА')
    revise_parser.add_argument('--output', help='Куда сохранить результат')
    revise_parser.add_argument(
        '--backend',
        choices=('ollama', 'kilo_gateway'),
        help='LLM-бэкенд (по умолчанию из LLM_BACKEND)',
    )
    revise_parser.add_argument('--model', help='Имя модели')

    # --- import -------------------------------------------------------------
    import_parser = subparsers.add_parser(
        'import', help=COMMANDS['import'], description=COMMANDS['import']
    )
    import_parser.add_argument('--file', help='JSON НПА для импорта')
    import_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Только проверить данные, не записывать в БД',
    )
    import_parser.add_argument(
        '--replace',
        action='store_true',
        help='Удалить существующие записи НПА перед импортом',
    )

    # --- sync ---------------------------------------------------------------
    sync_parser = subparsers.add_parser(
        'sync', help=COMMANDS['sync'], description=COMMANDS['sync']
    )
    sync_parser.add_argument('--target-dir', help='Каталог, куда копировать PHP/JS/CSS')
    sync_parser.add_argument(
        '--dry-run', action='store_true', help='Показать план без копирования'
    )

    # --- validate -----------------------------------------------------------
    validate_parser = subparsers.add_parser(
        'validate', help=COMMANDS['validate'], description=COMMANDS['validate']
    )
    validate_parser.add_argument('--input', help='JSON НПА для проверки')
    validate_parser.add_argument(
        '--all-base',
        action='store_true',
        help='Проверить все документы в data/base',
    )
    validate_parser.add_argument(
        '--config-only', action='store_true', help='Проверить только конфигурацию'
    )
    validate_parser.add_argument(
        '--strict',
        action='store_true',
        help='Считать предупреждения ошибками (ненулевой код выхода)',
    )

    # --- report -------------------------------------------------------------
    report_parser = subparsers.add_parser(
        'report', help=COMMANDS['report'], description=COMMANDS['report']
    )
    report_parser.add_argument('--output', help='Куда сохранить отчёт (Markdown)')

    return parser


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Разобрать аргументы; при отсутствии команды вернуть ``command=None``."""
    return build_parser().parse_args(argv)
