"""Точка входа NPA-ZS.

Запуск::

    python -m npazs <команда>       # после pip install -e .
    python scripts/run_revision.py  # без установки пакета

Разбор аргументов — в :mod:`npazs.cli`; здесь только исполнение команд.
GUI-приложения импортируются лениво, внутри обработчиков: ``npazs validate``
должна работать в CI, где нет ни Tk, ни MySQL.
"""

from __future__ import annotations

import json
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
def _parse_batch(args) -> int:
    import logging
    from npazs.core.html_parser import NpaToJsonGenerator

    input_file = getattr(args, 'input')
    if not input_file or not os.path.exists(input_file):
        _print_err(f'Файл не найден: {input_file}')
        return EXIT_ERROR

    output_file = getattr(args, 'output')
    if not output_file:
        base, _ = os.path.splitext(input_file)
        output_file = base + '.json'

    doc_type = getattr(args, 'doc_type', 'law') or 'law'

    print(f'Пакетный разбор: {input_file} -> {output_file}')

    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            html_content = f.read()
    except Exception as e:
        _print_err(f'Не удалось прочитать файл: {e}')
        return EXIT_ERROR

    try:
        generator = NpaToJsonGenerator(html_content, doc_type=doc_type, batch_mode=True)
        generator.logger.setLevel(logging.DEBUG)
        toc_structure, ambiguous_elements = generator.generate_toc()
    except Exception as e:
        _print_err(f'Ошибка парсинга: {e}')
        return EXIT_ERROR

    if generator.errors:
        for err in generator.errors:
            _print_err(f'Ошибка парсера: {err}')
        return EXIT_ERROR

    if ambiguous_elements:
        print(f'Предупреждение: {len(ambiguous_elements)} неоднозначных элементов (используются эвристики)')

    head_revision = [{"npa_head": generator.doc_title or "Без названия"}]
    root_object = {
        "npa_id": getattr(generator, 'document_id', '') or "",
        "npa_type": doc_type,
        "npa_number": generator.npa_number or "",
        "npa_author": "",
        "npa_npa_committee": "",
        "pub_info": "",
        "pub_filepath": "",
        "npa_url": "",
        "date_reg": generator.date_signed or generator.date_passed or "",
        "date_cons": "",
        "date_1st_reading": "",
        "date_passed": generator.date_passed or "",
        "date_signed": generator.date_signed or "",
        "date_pub": generator.date_signed or generator.date_passed or "",
        "valid_from": generator.date_signed or generator.date_passed or "",
        "npa_signer_post": generator.governor_post_html or "",
        "npa_signer": generator.governor_name or "",
        "term_number": generator.term_number or "",
        "session_number": generator.session_number or "",
        "date_format": generator.date_format or 1,
        "head_revision": head_revision,
        "npa_items_revision": toc_structure,
    }

    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(root_object, f, ensure_ascii=False, indent=2)
    except Exception as e:
        _print_err(f'Не удалось записать файл: {e}')
        return EXIT_ERROR

    print(f'Готово. Файл сохранён: {output_file}')
    if hasattr(generator, 'no_name_parents') and generator.no_name_parents:
        print(f'Элементы без названия: {", ".join(generator.no_name_parents)}')
    return EXIT_OK


def _cmd_parse(args) -> int:
    if getattr(args, 'input', None):
        return _parse_batch(args)

    from npazs.ui.parser_app import main as parser_main
    return parser_main()


# ------------------------------------------------------------------ revise
def _revise_headless(args) -> int:
    import threading
    from npazs.pipeline.orchestrator import AiPipelineMixin
    from npazs.revision.file_ops import FileOpsMixin
    from npazs.revision.engine import rebuild_element_with_history
    from npazs.revision.change_pipeline import apply_change_tracked, apply_grouped_changes_tracked, run_verification_stage
    from npazs.revision.change_tracker import ChangeTracker, ChangeStatus
    from npazs.revision.element_finder import narrow_source_id_to_subpoint, find_item_by_revision_number
    from npazs.revision.ui_utils import _correct_change_description, _fetch_source_html_for_change, _add_new_element, _find_existing_element_flexible, _normalize_highlights_positions, _resolve_add_parent_and_deferred, _ensure_path, extract_json_from_text, expand_range_in_new_field, split_range_changes, get_date_for_filename
    from npazs.revision.tree_utils import _find_target_element, find_item_by_id
    from npazs.revision.html_utils import extract_html_for_added_element, _extract_quoted_html, extract_structural_block, extract_text_from_element, get_full_element_html
    from npazs.revision.retroactive_notes import (
        apply_retroactive_rules_to_groups,
        _append_item_note,
        _add_npa_note,
        normalize_amending_note_text,
    )
    from npazs.constants import (
        settings,
        _ollama_base_url,
        DEFAULT_EXTRA_OPTIONS,
        DEFAULT_OLLAMA_MODEL,
        DEFAULT_KILO_GATEWAY_URL,
        DEFAULT_KILO_GATEWAY_MODEL,
        DEFAULT_BACKEND,
        PROMPT_1,
        PROMPT_2,
        PROMPT_3,
        PROMPT_4,
        TYPE_TO_RUSSIAN,
        save_last_run_log,
    )
    from npazs.revision.text_utils import strip_thinking_tags, safe_re_sub
    from npazs.revision.ai_utils import ask_ollama
    from json_repair import repair_json

    source_file = getattr(args, 'source')
    target_file = getattr(args, 'target')
    output_file = getattr(args, 'output')
    backend = getattr(args, 'backend', None) or os.environ.get('LLM_BACKEND', 'kilo_gateway')
    model = getattr(args, 'model', None) or os.environ.get('KILO_GATEWAY_DEFAULT_MODEL', DEFAULT_KILO_GATEWAY_MODEL)

    if not source_file or not target_file:
        _print_err('Укажите --source и --target для пакетного внесения изменений.')
        return EXIT_USAGE
    if not os.path.exists(source_file):
        _print_err(f'Файл изменений не найден: {source_file}')
        return EXIT_ERROR
    if not os.path.exists(target_file):
        _print_err(f'Цевой файл не найден: {target_file}')
        return EXIT_ERROR

    import json
    with open(target_file, 'r', encoding='utf-8') as f:
        original_data = json.load(f)
    with open(source_file, 'r', encoding='utf-8') as f:
        change_data = json.load(f)

    valid_from_str = change_data.get('valid_from', '').strip() or change_data.get('date_signed', '').strip() or change_data.get('date_pub', '').strip()
    if not valid_from_str:
        _print_err('В JSON изменений не найдена дата вступления в силу.')
        return EXIT_ERROR
    try:
        general_valid_from = datetime.strptime(valid_from_str, '%d.%m.%Y').date()
    except ValueError:
        _print_err(f'Неверный формат даты: {valid_from_str}')
        return EXIT_ERROR

    pub_date_str = change_data.get('date_pub', '') or change_data.get('date_signed', '')

    class _Var:
        def __init__(self, value):
            self._value = value
        def get(self):
            return self._value
        def set(self, value):
            self._value = value

    class _HeadlessApp(AiPipelineMixin, FileOpsMixin):
        def __init__(self):
            self.original_path = _Var(target_file)
            self.change_path = _Var(source_file)
            self.law_ref = _Var(change_data.get('npa_number', ''))
            self.original_law_ref = _Var(original_data.get('npa_number', ''))
            self.ollama_model = _Var(model)
            self.backend = _Var(backend)
            self.kilo_gateway_url = _Var(settings.kilo_gateway_base_url)
            self.kilo_gateway_api_key = _Var(settings.kilo_gateway_api_key or '')
            self.extra_options = _Var(json.dumps(DEFAULT_EXTRA_OPTIONS))
            self.prompt_1 = PROMPT_1
            self.prompt_2 = PROMPT_2
            self.prompt_3 = PROMPT_3
            self.prompt_4 = PROMPT_4
            self.use_stage1_answer = _Var(False)
            self.use_stage2_answer = _Var(False)
            self.use_stage3_answer = _Var(False)
            self.stage1_answer_text = _Var('')
            self.stage2_answer_text = _Var('')
            self.stage3_answer_text = _Var('')
            self.stop_event = threading.Event()
            self.message_queue = None
            self.answer_queue = None
            self.manual_mapping_cache = {}
            self.logs = []

        def log(self, message, tag=None):
            self.logs.append((tag, message))
            print(f'[{tag or "INFO"}] {message}' if tag else message)

        def resolve_revision_manually(self, revision_number, change_data, log_callback, stop_event=None, change_info=""):
            log_callback(f"Автовыбор для revision_number={revision_number} (headless)", 'warning')
            return None

        def resolve_ambiguous_element(self, item_type, item_number, candidates, structural_path, revision_number=None, change_info=None, target_element_id=None):
            log_callback = self.log
            log_callback(f"Автовыбор для неоднозначного элемента {item_type} {item_number} (headless)", 'warning')
            return None

        def resolve_target_element_manually(self, change_data, stop_event=None):
            self.log("Автовыбор целевого элемента (headless)", 'warning')
            return None

        def resolve_change_manually(self, change, original_data, stop_event=None):
            self.log("Автовыбор изменения (headless)", 'warning')
            return None, None, None, None

        def _save_result(self, result_data, orig_file, change_data):
            if not output_file:
                base, _ = os.path.splitext(target_file)
                output_file_path = f"{base}_revised.json"
            else:
                output_file_path = output_file
            FileOpsMixin._save_result(self, result_data, target_file, change_data)
            with open(output_file_path, 'w', encoding='utf-8') as f:
                json.dump(result_data, f, ensure_ascii=False, indent=2)
            self.log(f"Результат сохранён: {output_file_path}", 'result')

    try:
        app = _HeadlessApp()
        app.run_all()
        return EXIT_OK
    except Exception as e:
        _print_err(f'Ошибка headless revise: {e}')
        import traceback
        traceback.print_exc()
        return EXIT_ERROR


def _cmd_revise(args) -> int:
    if getattr(args, 'backend', None):
        os.environ['LLM_BACKEND'] = args.backend
    if getattr(args, 'model', None):
        os.environ['KILO_GATEWAY_DEFAULT_MODEL'] = args.model
        os.environ['OLLAMA_DEFAULT_MODEL'] = args.model

    if getattr(args, 'source', None) and getattr(args, 'target', None):
        return _revise_headless(args)

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
