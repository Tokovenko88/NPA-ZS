"""Оркестратор модуля сравнения редакций НПА.

Связывает конвертеры, нормализацию, дифф, агента и отчёт:

1. чтение двух документов (:mod:`npazs.compare.converters`);
2. отделение примечаний и построение структурных элементов
   (:mod:`npazs.compare.normalizer`, :mod:`npazs.compare.tree`);
3. посимвольное сравнение (:mod:`npazs.compare.differ`);
4. классификация причин расхождений — ИИ-агент или механический фолбэк
   (:mod:`npazs.compare.agent_compare`) с подтягиванием текстов изменений
   из JSON-базы (:mod:`npazs.compare.npa_resolver`);
5. сборка Markdown-отчёта (:mod:`npazs.compare.report_builder`).

Возобновление после сбоя: состояние различий сохраняется в чекпойнт
``<отчёт>.checkpoint.json`` после каждого обработанного пакета. Повторный
запуск с теми же файлами (проверка по отпечатку путей/размеров/времени
модификации) продолжает работу с первого необработанного различия —
агент не начинает сравнение заново.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from npazs.constants import LOGS_DIR, OUTPUT_DIR, PROMPTS_DIR

from .agent_compare import DEFAULT_PROMPT, classify_diffs, mechanical_resolve
from .converters import Document, read_document
from .differ import DiffRecord, compare_elements
from .normalizer import extract_notes, parse_note
from .npa_resolver import get_original_element_text
from .report_builder import build_notes_report, build_report
from .tree import build_elements

__all__ = [
    'COMPARE_OUTPUT_DIR',
    'COMPARE_PROMPT_FILE',
    'CompareOptions',
    'CompareResult',
    'run_compare',
]

#: Каталог отчётов сравнения: ``data/output/compare``.
COMPARE_OUTPUT_DIR = os.path.join(OUTPUT_DIR, 'compare')
#: Файл промпта агента (переопределяет DEFAULT_PROMPT из agent_compare).
COMPARE_PROMPT_FILE = os.path.join(PROMPTS_DIR, 'compare_prompt.md')
#: Суффикс файла чекпойнта (создаётся рядом с отчётом).
CHECKPOINT_SUFFIX = '.checkpoint.json'

_ZS_RE = re.compile(r'№\s*(\d{1,4})\s*[-–—]\s*ЗС', re.IGNORECASE)
_ZS_RE_FALLBACK = re.compile(r'\b(\d{1,4})\s*[-–—]\s*ЗС\b', re.IGNORECASE)


@dataclass
class CompareOptions:
    """Параметры запуска сравнения."""

    #: Документ, сформированный нашим проектом (RTF/DOCX/DOC/HTML/TXT).
    ours_path: str = ''
    #: Документ, сформированный правовой системой.
    theirs_path: str = ''
    #: Куда сохранить отчёт (по умолчанию — ``data/output/compare``).
    output_path: str = ''
    #: Номер целевого НПА; пусто — определить автоматически по тексту.
    target_number: str = ''
    #: ``agent`` — классификация причин через LLM; ``mechanical`` — без ИИ.
    mode: str = 'agent'
    #: LLM-бэкенд (пусто — из конфигурации).
    backend: str = ''
    #: Имя модели (пусто — из конфигурации).
    model: str = ''
    #: Сколько различий отправлять модели за один запрос.
    batch_size: int = 1
    #: Продолжать с чекпойнта при повторном запуске.
    resume: bool = True


@dataclass
class CompareResult:
    """Итог выполнения сравнения."""

    output_path: str = ''
    log_path: str = ''
    diffs_count: int = 0
    notes_count: int = 0
    diff_stats: Dict[str, int] = field(default_factory=dict)
    stopped: bool = False
    resumed: bool = False


_HEADER_STOP_RE = re.compile(
    r'\b(Статья\s*\d|Примечани|Глава\s*[IVXLC\d]|Раздел\s*[IVXLC\d])', re.IGNORECASE
)


def _guess_target_number(
    ours_doc: Document, theirs_doc: Document, options: CompareOptions
) -> str:
    """Определить номер целевого НПА.

    Сначала — шапка документа (до первого «Статья/Примечание/…», поэтому
    ссылки на изменяющие НПА из примечаний не учитываются), затем цифры
    в имени файла.
    """
    for doc in (ours_doc, theirs_doc):
        head = doc.text[:1200]
        stop = _HEADER_STOP_RE.search(head)
        if stop:
            head = head[:stop.start()]
        m = _ZS_RE.search(head) or _ZS_RE_FALLBACK.search(head)
        if m:
            return f'{m.group(1)}-ЗС'
    m = re.match(r'(\d{1,4})', Path(options.ours_path).stem)
    return f'{m.group(1)}-ЗС' if m else ''


def _wrap_logger(user_log: Optional[Callable], log_path: str) -> Callable:
    """Обернуть пользовательский лог записью в файл ``data/logs``."""

    def log(msg: str, level: str = 'info') -> None:
        try:
            with open(log_path, 'a', encoding='utf-8') as fh:
                stamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                fh.write(f'{stamp} [{level}] {msg}\n')
        except OSError:
            pass
        if user_log:
            user_log(msg, level)

    return log


def _collect_notes_by_path(elements) -> Dict[str, List[dict]]:
    """Собрать примечания по структурным элементам (контекст для агента).

    Принимает элементы, построенные из ПОЛНЫХ блоков документа (до
    ``extract_notes``), — иначе примечания уже вырезаны и связь
    «элемент -> изменяющий НПА» теряется. Ключ — путь элемента в формате
    отчёта (``diff.path``), значение — список словарей с текстом примечания,
    номерами связанных НПА и датами.
    """
    notes_by_path: Dict[str, List[dict]] = {}
    for el in elements:
        text = el.text or ''
        if 'примечан' not in text.lower():
            continue
        note = parse_note(text, order=el.order)
        if not note.text:
            continue
        notes_by_path.setdefault(el.path_text, []).append(
            {
                'text': note.text[:300],
                'npa_numbers': note.npa_numbers,
                'dates': note.dates,
                'valid_from': note.valid_from,
            }
        )
    return notes_by_path


def _make_original_getter() -> Callable[[str, tuple], str]:
    """Получить текст элемента из исходной редакции НПА (с защитой от сбоев)."""

    def _get(target_number: str, path_key: tuple) -> str:
        if not target_number:
            return ''
        try:
            return get_original_element_text(target_number, path_key)
        except Exception:
            return ''

    return _get


def _load_prompt_template() -> str:
    """Прочитать промпт агента из ``data/prompts/compare_prompt.md``."""
    try:
        if os.path.isfile(COMPARE_PROMPT_FILE):
            text = Path(COMPARE_PROMPT_FILE).read_text(encoding='utf-8').strip()
            if text:
                return text
    except OSError:
        pass
    return ''


def _default_output_path(options: CompareOptions) -> str:
    ours = Path(options.ours_path).stem or 'ours'
    theirs = Path(options.theirs_path).stem or 'theirs'
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return os.path.join(COMPARE_OUTPUT_DIR, f'{ours}_vs_{theirs}_{stamp}.md')


def _fingerprint(options: CompareOptions, target_number: str) -> str:
    """Отпечаток запуска: пути, размеры, mtime файлов + параметры режима."""
    digest = hashlib.sha256()
    for path in (options.ours_path, options.theirs_path):
        stat = os.stat(path)
        digest.update(str(path).encode('utf-8'))
        digest.update(str(stat.st_size).encode())
        digest.update(str(int(stat.st_mtime)).encode())
    digest.update(
        f'{target_number}|{options.mode}|{options.model}'.encode()
    )
    return digest.hexdigest()[:16]


def _diffs_to_json(diffs: List[DiffRecord]) -> List[dict]:
    payload = []
    for diff in diffs:
        data = asdict(diff)
        data['path_key'] = [list(step) for step in diff.path_key]
        payload.append(data)
    return payload


def _diffs_from_json(items) -> List[DiffRecord]:
    allowed = set(DiffRecord.__dataclass_fields__)
    diffs: List[DiffRecord] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        data = {key: value for key, value in item.items() if key in allowed}
        if 'path_key' in data:
            data['path_key'] = tuple(tuple(step) for step in data['path_key'])
        try:
            diffs.append(DiffRecord(**data))
        except TypeError:
            continue
    return diffs


def _save_checkpoint(
    path: str,
    fingerprint: str,
    diffs: List[DiffRecord],
    processed: int,
    started_at: str,
) -> None:
    """Атомарно сохранить чекпойнт рядом с отчётом."""
    payload = {
        'fingerprint': fingerprint,
        'started_at': started_at,
        'processed': processed,
        'total': len(diffs),
        'diffs': _diffs_to_json(diffs),
    }
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _load_checkpoint(path: str) -> Optional[dict]:
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def run_compare(
    options: CompareOptions,
    log: Optional[Callable] = None,
    stop_event=None,
) -> CompareResult:
    """Выполнить полное сравнение и сохранить отчёт.

    ``log(msg, level)`` — колбэк журнала; ``stop_event`` — потокобезопасное
    событие отмены. При остановке (или сбое между пакетами) повторный вызов
    с теми же ``options`` продолжит классификацию с чекпойнта.
    """
    if not options.ours_path or not options.theirs_path:
        raise ValueError('Не заданы пути к сравниваемым документам')

    started_at = datetime.now()
    started_str = started_at.isoformat(timespec='seconds')

    output_path = options.output_path or _default_output_path(options)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)
    log_path = os.path.join(LOGS_DIR, f'compare_{started_at:%Y%m%d_%H%M%S}.log')
    log = _wrap_logger(log, log_path)

    result = CompareResult(output_path=output_path, log_path=log_path)
    log(f'Документ проекта: {options.ours_path}')
    log(f'Документ правовой системы: {options.theirs_path}')

    ours_doc = read_document(options.ours_path)
    theirs_doc = read_document(options.theirs_path)
    for warning in ours_doc.warnings:
        log(f'Конвертер (проект): {warning}', 'warning')
    for warning in theirs_doc.warnings:
        log(f'Конвертер (правовая система): {warning}', 'warning')
    log(
        f'Форматы: {ours_doc.fmt} / {theirs_doc.fmt}; '
        f'блоков: {len(ours_doc.blocks)} / {len(theirs_doc.blocks)}'
    )

    ours_body, ours_notes = extract_notes(ours_doc.blocks)
    theirs_body, theirs_notes = extract_notes(theirs_doc.blocks)
    notes_records, notes_table = build_notes_report(ours_notes, theirs_notes)
    result.notes_count = len(ours_notes) + len(theirs_notes)
    log(f'Примечаний: {len(ours_notes)} / {len(theirs_notes)}')

    ours_elements = build_elements(ours_body)
    theirs_elements = build_elements(theirs_body)
    log(f'Структурных элементов: {len(ours_elements)} / {len(theirs_elements)}')

    diffs, stats = compare_elements(ours_elements, theirs_elements)
    result.diff_stats = stats
    result.diffs_count = sum(stats.values())
    log(
        f"Различий: {result.diffs_count} "
        f"(замена={stats.get('change', 0)}, только проект={stats.get('add', 0)}, "
        f"только правовая система={stats.get('remove', 0)})"
    )

    target_number = (options.target_number or '').strip() or (
        _guess_target_number(ours_doc, theirs_doc, options)
    )
    if target_number:
        log(f'Целевой НПА: {target_number}')
    else:
        log('Целевой НПА не определён — сверка с оригиналом недоступна', 'warning')

    notes_by_path = _collect_notes_by_path(
        build_elements(ours_doc.blocks)
    )
    fingerprint = _fingerprint(options, target_number)

    processed = 0
    checkpoint_path = output_path + CHECKPOINT_SUFFIX
    if options.resume:
        checkpoint = _load_checkpoint(checkpoint_path)
        if checkpoint and checkpoint.get('fingerprint') == fingerprint:
            stored = _diffs_from_json(checkpoint.get('diffs', []))
            if len(stored) == len(diffs):
                diffs = stored
                processed = max(
                    0, min(int(checkpoint.get('processed', 0) or 0), len(diffs))
                )
                result.resumed = processed > 0
                if result.resumed:
                    log(f'Чекпойнт: продолжаю с различия {processed + 1} из {len(diffs)}')
            else:
                log('Чекпойнт устарел (набор различий изменился) — начинаю заново', 'warning')

    if processed < len(diffs) and not (stop_event is not None and stop_event.is_set()):
        if options.mode == 'mechanical':
            log('Механический режим: классификация без ИИ (по примечаниям и базе)')
            get_original = _make_original_getter()
            while processed < len(diffs):
                if stop_event is not None and stop_event.is_set():
                    break
                mechanical_resolve(
                    diffs[processed], notes_by_path, target_number, get_original
                )
                processed += 1
                if processed % 25 == 0:
                    _save_checkpoint(
                        checkpoint_path, fingerprint, diffs, processed, started_str
                    )
        else:
            template = _load_prompt_template() or DEFAULT_PROMPT
            log(
                f"Агентный режим (бэкенд: {options.backend or 'из конфигурации'}, "
                f"модель: {options.model or 'из конфигурации'})"
            )
            classify_diffs(
                diffs[processed:],
                notes_by_path=notes_by_path,
                target_number=target_number,
                log=log,
                stop_event=stop_event,
                prompt_template=template,
                backend=options.backend or None,
                model=options.model or None,
                batch_size=max(1, int(options.batch_size or 1)),
            )
            processed = sum(1 for diff in diffs if diff.reason)

    _save_checkpoint(checkpoint_path, fingerprint, diffs, processed, started_str)

    if processed < len(diffs):
        result.stopped = True
        log(
            f'Остановлено на различии {processed + 1} из {len(diffs)}; '
            'чекпойнт сохранён — повторный запуск продолжит с этого места',
            'warning',
        )
    else:
        try:
            os.remove(checkpoint_path)
        except OSError:
            pass

    warnings = list(ours_doc.warnings) + list(theirs_doc.warnings)
    report = build_report(
        ours_path=options.ours_path,
        theirs_path=options.theirs_path,
        ours_fmt=ours_doc.fmt,
        theirs_fmt=theirs_doc.fmt,
        mode='agent' if options.mode == 'agent' else 'mechanical',
        target_number=target_number,
        notes_records=notes_records,
        notes_table=notes_table,
        diffs=diffs,
        diff_stats=stats,
        warnings=warnings,
        started_at=started_at,
    )
    with open(output_path, 'w', encoding='utf-8') as fh:
        fh.write(report)
    log('Отчёт сохранён: ' + output_path, 'success')
    log('Журнал: ' + log_path)
    return result
