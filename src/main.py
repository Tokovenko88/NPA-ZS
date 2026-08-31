"""Точка входа NPA-ZS.

Запуск::

    python -m npazs <команда>       # после pip install -e .
    python scripts/run_revision.py  # без установки пакета

Разбор аргументов — в :mod:`npazs.cli`; здесь только исполнение команд.
GUI-приложения импортируются лениво, внутри обработчиков: ``npazs validate``
должна работать в CI, где нет ни Tk, ни MySQL.
"""

from __future__ import annotations

import os
import sys
from typing import Optional, Sequence

__all__ = ['main']

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2


def _print_err(message: str) -> None:
    print(message, file=sys.stderr)


# ------------------------------------------------------------------ init
def _cmd_init(args) -> int:
    from npazs import __version__
    from npazs.bootstrap import PATHS, ensure_runtime_dirs
    from npazs.config import ENV_PATH, get_settings
    from npazs.pipeline.prompts import prompt_status

    ensure_runtime_dirs()

    print(f'NPA-ZS {__version__}')
    print(f'Корень проекта : {PATHS["root"]}')
    print(f'Файл окружения : {ENV_PATH} {"(найден)" if ENV_PATH.exists() else "(ОТСУТСТВУЕТ)"}')
    print()

    print('Каталоги данных:')
    for key in ('prompts', 'input', 'output', 'stage_answers', 'debug_runs', 'logs', 'base'):
        path = PATHS[key]
        print(f'  {key:<14} {path} {"ok" if path.exists() else "НЕТ"}')
    print()

    print('Промпты:')
    for stage, loaded in prompt_status().items():
        print(f'  prompt_{stage}.md  {"загружен" if loaded else "ПУСТ/ОТСУТСТВУЕТ"}')
    print()

    settings = get_settings()
    print('Конфигурация:')
    print(f'  LLM_BACKEND    {settings.llm_backend}')
    print(f'  OLLAMA_BASE_URL {settings.ollama_base_url}')
    print(f'  DB_HOST        {settings.db_host or "(не задан)"}')
    print(f'  DB_NAME        {settings.db_name or "(не задан)"}')
    print(f'  LOG_LEVEL      {settings.log_level}')

    if not ENV_PATH.exists():
        print()
        _print_err('Подсказка: скопируйте .env.example в .env и заполните значения.')

    if getattr(args, 'check_db', False):
        print()
        return _check_db()

    return EXIT_OK


def _check_db() -> int:
    from npazs.config.db import get_db_config, missing_db_settings

    missing = missing_db_settings()
    if missing:
        _print_err('Проверка БД: не заданы переменные ' + ', '.join(missing))
        return EXIT_ERROR
    try:
        import pymysql

        config = get_db_config()
        connection = pymysql.connect(
            host=config['host'],
            port=config['port'],
            user=config['user'],
            password=config['password'],
            database=config['database'],
            charset=config['charset'],
            connect_timeout=10,
        )
        connection.close()
        print(f'Проверка БД: подключение к {config["host"]}/{config["database"]} успешно')
        return EXIT_OK
    except Exception as error:  # noqa: BLE001 - показываем причину пользователю
        _print_err(f'Проверка БД: ошибка подключения — {error}')
        return EXIT_ERROR


# ------------------------------------------------------------------ parse
def _cmd_parse(args) -> int:
    from npazs.ui.parser_app import main as parser_main

    if getattr(args, 'input', None):
        print(
            'Пакетный разбор из командной строки пока не реализован: '
            'парсер требует интерактивных решений по приложениям и таблицам. '
            'Открываю GUI.'
        )
    return parser_main()


# ------------------------------------------------------------------ revise
def _cmd_revise(args) -> int:
    if getattr(args, 'backend', None):
        os.environ['LLM_BACKEND'] = args.backend
    if getattr(args, 'model', None):
        os.environ['KILO_GATEWAY_DEFAULT_MODEL'] = args.model
        os.environ['OLLAMA_DEFAULT_MODEL'] = args.model

    from npazs.ui.revision_app import main as revision_main

    revision_main()
    return EXIT_OK


# ------------------------------------------------------------------ import
def _cmd_import(args) -> int:
    if getattr(args, 'dry_run', False):
        target = getattr(args, 'file', None)
        if not target:
            _print_err('Для --dry-run укажите --file <путь к JSON>')
            return EXIT_USAGE
        return _validate_files([target], strict=False)

    from npazs.db.importer import ImporterApp

    app = ImporterApp()
    app.mainloop()
    return EXIT_OK


# ------------------------------------------------------------------ sync
def _cmd_sync(args) -> int:
    import shutil
    from pathlib import Path

    from npazs.bootstrap import PATHS

    site_dir = PATHS['site']
    assets = {
        'php': sorted((site_dir / 'php').glob('*.php')),
        'js': sorted((site_dir / 'js').glob('*.js')),
        'css': sorted((site_dir / 'css').glob('*.css')),
        'templates': sorted((site_dir / 'templates').glob('*')),
    }

    print('Артефакты вывода НПА на сайт:')
    for kind, files in assets.items():
        print(f'  {kind}:')
        for path in files:
            size_kb = path.stat().st_size / 1024 if path.is_file() else 0
            print(f'    {path.name} ({size_kb:.1f} КБ)')

    target_dir = getattr(args, 'target_dir', None)
    if not target_dir:
        print()
        print('Каталог назначения не указан (--target-dir). Копирование не выполнялось.')
        print('Инструкция по установке на сайт: docs/site_output.md')
        return EXIT_OK

    destination = Path(target_dir)
    if getattr(args, 'dry_run', False):
        print()
        print(f'План копирования в {destination} (--dry-run, ничего не записано):')
        for files in assets.values():
            for path in files:
                print(f'  {path} -> {destination / path.name}')
        return EXIT_OK

    destination.mkdir(parents=True, exist_ok=True)
    copied = 0
    for files in assets.values():
        for path in files:
            if path.is_file():
                shutil.copy2(path, destination / path.name)
                copied += 1
    print()
    print(f'Скопировано файлов: {copied} -> {destination}')
    return EXIT_OK


# ------------------------------------------------------------------ validate
def _validate_files(paths: Sequence[str], *, strict: bool) -> int:
    from npazs.utils.file_ops import read_json
    from npazs.utils.validation import validate_document

    exit_code = EXIT_OK
    for path in paths:
        try:
            document = read_json(path)
        except Exception as error:  # noqa: BLE001
            _print_err(f'{path}: не удалось прочитать JSON — {error}')
            exit_code = EXIT_ERROR
            continue
        if document is None:
            _print_err(f'{path}: файл не найден')
            exit_code = EXIT_ERROR
            continue

        report = validate_document(document)
        print(f'{path}: {report.summary()}')
        for issue in report.errors:
            print(f'  {issue}')
        if strict:
            for issue in report.warnings:
                print(f'  {issue}')
        if report.errors or (strict and report.warnings):
            exit_code = EXIT_ERROR
    return exit_code


def _validate_config(strict: bool) -> int:
    from npazs.config import ENV_PATH
    from npazs.config.db import missing_db_settings
    from npazs.pipeline.prompts import prompt_status

    exit_code = EXIT_OK

    if not ENV_PATH.exists():
        _print_err(f'Конфигурация: {ENV_PATH} отсутствует (скопируйте .env.example)')
        exit_code = EXIT_ERROR
    else:
        print(f'Конфигурация: {ENV_PATH} найден')

    missing_prompts = [stage for stage, loaded in prompt_status().items() if not loaded]
    if missing_prompts:
        _print_err(
            'Промпты: отсутствуют или пусты — '
            + ', '.join(f'prompt_{stage}.md' for stage in missing_prompts)
        )
        exit_code = EXIT_ERROR
    else:
        print('Промпты: все четыре загружены')

    missing_db = missing_db_settings()
    if missing_db:
        message = 'БД: не заданы ' + ', '.join(missing_db)
        if strict:
            _print_err(message)
            exit_code = EXIT_ERROR
        else:
            print(f'{message} (предупреждение)')
    else:
        print('БД: реквизиты заданы')

    return exit_code


def _cmd_validate(args) -> int:
    strict = bool(getattr(args, 'strict', False))

    if getattr(args, 'config_only', False):
        return _validate_config(strict)

    exit_code = _validate_config(strict)
    print()

    if getattr(args, 'all_base', False):
        from npazs.utils.file_ops import iter_base_documents

        paths = [str(path) for path in iter_base_documents()]
        if not paths:
            print('data/base: JSON-документы не найдены')
            return exit_code
        print(f'Проверка {len(paths)} документов в data/base ...')
        return max(exit_code, _validate_files(paths, strict=strict))

    target = getattr(args, 'input', None)
    if target:
        return max(exit_code, _validate_files([target], strict=strict))

    from npazs.constants import OUTPUT_DIR

    default_output = os.path.join(OUTPUT_DIR, 'result_npa.json')
    if os.path.exists(default_output):
        return max(exit_code, _validate_files([default_output], strict=strict))

    print('JSON для проверки не указан (--input / --all-base).')
    return exit_code


# ------------------------------------------------------------------ report
def _cmd_report(args) -> int:
    from npazs.constants import LAST_RUN_LOG_FILE, WORK_TOOLS_DIR
    from npazs.utils.reporting import RunReport

    report_path = getattr(args, 'output', None) or os.path.join(WORK_TOOLS_DIR, 'report.md')

    report = RunReport()
    if os.path.exists(LAST_RUN_LOG_FILE):
        report.note(f'Журнал последнего прогона: {LAST_RUN_LOG_FILE}')
    else:
        report.note('Журнал последнего прогона отсутствует — прогонов ещё не было.')

    saved = report.save(report_path)
    print(f'Отчёт сохранён: {saved}')
    return EXIT_OK


# ------------------------------------------------------------------ dispatch
_HANDLERS = {
    'init': _cmd_init,
    'parse': _cmd_parse,
    'revise': _cmd_revise,
    'import': _cmd_import,
    'sync': _cmd_sync,
    'validate': _cmd_validate,
    'report': _cmd_report,
}


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Разобрать аргументы и выполнить команду. Возвращает код выхода."""
    from npazs.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(argv)

    if getattr(args, 'version', False):
        from npazs import __version__

        print(f'NPA-ZS {__version__}')
        return EXIT_OK

    if getattr(args, 'verbose', False):
        os.environ['LOG_LEVEL'] = 'DEBUG'

    command = getattr(args, 'command', None)
    if not command:
        parser.print_help()
        return EXIT_USAGE

    handler = _HANDLERS.get(command)
    if handler is None:  # pragma: no cover - argparse не пропустит
        _print_err(f'Неизвестная команда: {command}')
        return EXIT_USAGE

    try:
        return handler(args)
    except KeyboardInterrupt:
        _print_err('\nПрервано пользователем.')
        return EXIT_ERROR


if __name__ == '__main__':
    raise SystemExit(main())
