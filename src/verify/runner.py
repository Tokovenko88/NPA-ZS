"""Standalone-запуск AI-пост-анализа на основе готового результата."""

from __future__ import annotations

import json
import os
import re
import threading
from collections.abc import Callable

from npazs.constants import BASE_LAW_DIR, PRODUCTION_BASE_LAW_DIR
from npazs.revision.post_analysis import run_post_analysis

from .models import PostAnalysisOptions, PostAnalysisResult

__all__ = ['PostAnalysisOptions', 'PostAnalysisResult', 'run_post_analysis_standalone']


def _resolve_base_dirs() -> list[str]:
    dirs = [BASE_LAW_DIR]
    if PRODUCTION_BASE_LAW_DIR and os.path.isdir(PRODUCTION_BASE_LAW_DIR):
        dirs.append(PRODUCTION_BASE_LAW_DIR)
    return dirs


def _find_in_base(npa_number: str, base_dirs: list[str]) -> str | None:
    clean = re.sub(r'[^0-9a-zA-Z]', '', str(npa_number or ''))
    for base in base_dirs:
        candidate = os.path.join(base, clean, f'{clean}.json')
        if os.path.isfile(candidate):
            return candidate
    return None


def _find_related_paths(result_path: str) -> dict[str, str | None]:
    base_dirs = _resolve_base_dirs()
    result_dir = os.path.dirname(os.path.abspath(result_path))
    stem = os.path.splitext(os.path.basename(result_path))[0]

    work_path = os.path.join(result_dir, stem.split('_izm_')[0] + '_work.json') if '_izm_' in stem else None
    if not work_path or not os.path.isfile(work_path):
        for name in os.listdir(result_dir):
            if name.endswith('_work.json') and stem.startswith(name.replace('_work.json', '')):
                work_path = os.path.join(result_dir, name)
                break

    m = re.match(r'^(.+?)_izm_(.+)$', stem)
    orig_num = ''
    change_num = ''
    if m:
        orig_num = m.group(1)
        change_num = m.group(2)
    else:
        parts = stem.split('_')
        if len(parts) >= 2:
            change_num = parts[-1]
            orig_num = parts[0]

    # Work-файл оркестратор сохраняет по номеру изменяющего НПА
    # (правило 7 AGENTS.md): <изменяющий>_work.json, например 516_work.json.
    change_lead = re.match(r'^([0-9]+)', change_num)
    if change_lead:
        candidate = os.path.join(result_dir, change_lead.group(1) + '_work.json')
        if os.path.isfile(candidate):
            work_path = candidate

    def _find_npa(num: str) -> str | None:
        """Рядом с результатом → каноническая база → номер без суффиксов.

        Приоритет у папки результата: там лежат входные файлы прогона
        (127.json, 516.json), и именно к ним относится проверяемый результат.
        База ищется следом (полный номер, затем старшие цифры).
        """
        if not num:
            return None
        lead = re.match(r'^([0-9]+)', num)
        candidates = [os.path.join(result_dir, num + '.json')]
        if lead:
            # Оригинал «127_2015_04_17» → 127.json; изменяющий
            # «516_2019_07_08» → 516.json (вход прогона рядом с целью).
            candidates.append(os.path.join(result_dir, f'{lead.group(1)}.json'))
        candidates.append(os.path.join(result_dir,
                                       re.sub(r'[^0-9a-zA-Z]', '', num) + '.json'))
        candidates.append(_find_in_base(num, base_dirs))
        if lead:
            for base in base_dirs:
                candidates.append(os.path.join(base, lead.group(1),
                                               f'{lead.group(1)}.json'))
        for candidate in candidates:
            if candidate and os.path.isfile(candidate):
                return candidate
        return None

    orig_path = _find_npa(orig_num)
    change_path = _find_npa(change_num)

    return {
        'work': work_path if work_path and os.path.isfile(work_path) else None,
        'original': orig_path,
        'change': change_path,
        'result': result_path,
    }


def _load_json(path: str) -> dict | None:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _extract_instructions_from_work(work_data: dict) -> list[str] | None:
    if not isinstance(work_data, dict):
        return None
    stages = work_data.get('stages', [])
    if not isinstance(stages, list):
        return None
    parts: list[str] = []
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        if stage.get('stage') != 3:
            continue
        answer = stage.get('answer', '')
        if not answer:
            continue
        text = re.sub(r'```json\n?', '', str(answer)).strip()
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict):
                        desc = str(item.get('description', '')).strip()
                        if desc:
                            parts.append(desc)
        except (json.JSONDecodeError, TypeError):
            pass
    return parts if parts else None


def run_post_analysis_standalone(
    options: PostAnalysisOptions,
    log: Callable | None = None,
    stop_event: threading.Event | None = None,
) -> PostAnalysisResult:
    def _log(msg: str, level: str = 'info') -> None:
        if log:
            log(msg, level)

    result = PostAnalysisResult()

    result_path = options.result_path
    if not result_path or not os.path.isfile(result_path):
        result.errors.append('Не задан или не найден файл результата (izm_...json).')
        return result

    paths = _find_related_paths(result_path)

    original_path = options.original_path or paths.get('original', '') or ''
    change_path = options.change_path or paths.get('change', '') or ''
    work_path = options.work_json_path or paths.get('work', '') or ''

    result_data = _load_json(result_path)
    if not isinstance(result_data, dict):
        result.errors.append('Не удалось прочитать файл результата как JSON.')
        return result

    change_data = None
    if change_path and os.path.isfile(change_path):
        change_data = _load_json(change_path)
    if not isinstance(change_data, dict):
        result.errors.append('Не найден/не удалось прочитать JSON изменяющего НПА.')
        return result

    if not original_path or not os.path.isfile(original_path):
        result.errors.append('Не найден оригинальный НПА (--original).')
        return result

    extra_options = None
    if options.extra_options.strip():
        try:
            extra_options = json.loads(options.extra_options)
        except json.JSONDecodeError:
            _log('Некорректный JSON в дополнительных параметрах; используются значения по умолчанию.', 'warning')

    extracted_instructions = None
    tracker_snapshot = None
    if work_path and os.path.isfile(work_path):
        work_data = _load_json(work_path)
        if isinstance(work_data, dict):
            extracted_instructions = _extract_instructions_from_work(work_data)
            # Снимок трекера, сохранённый оркестратором при прогоне, — нужен для
            # детерминированной проверки покрытия норм (правка не применена, но
            # трекер закрыл её чужой ревизией).
            snapshot = work_data.get('tracker_changes')
            if isinstance(snapshot, list) and snapshot:
                tracker_snapshot = snapshot
                _log(f'Снимок трекера из work-файла: {len(snapshot)} изменений')

    _log(f'Файл результата: {result_path}')
    _log(f'Оригинальный НПА: {original_path}')
    _log(f'Изменяющий НПА: {change_path}')
    if work_path:
        _log(f'Файл работы: {work_path}')

    try:
        final = run_post_analysis(
            orig_file=original_path,
            result_data=result_data,
            change_data=change_data,
            model=options.model.strip() or None,
            extra_options=extra_options,
            stop_event=stop_event,
            log_callback=_log,
            backend=options.backend.strip() or None,
            extracted_instructions=extracted_instructions,
            tracker_snapshot=tracker_snapshot,
        )
    except Exception as e:  # noqa: BLE001 - предотвращаем падение GUI
        result.errors.append(f'Ошибка пост-анализа: {e}')
        return result

    if not isinstance(final, dict):
        result.errors.append('Пост-анализ вернул невалидный результат.')
        return result

    result.status = str(final.get('status', ''))
    result.checked = int(final.get('checked', 0))
    result.issues = int(final.get('issues', 0))
    result.report_path = str(final.get('report_path', '') or '')
    result.corrected_path = str(final.get('corrected_path', '') or '')

    if options.output_path:
        try:
            from .report_builder import build_post_analysis_report
            report = build_post_analysis_report(result, final)
            os.makedirs(os.path.dirname(os.path.abspath(options.output_path)), exist_ok=True)
            with open(options.output_path, 'w', encoding='utf-8') as f:
                f.write(report)
            result.output_path = options.output_path
            _log(f'Отчёт сохранён: {options.output_path}', 'success')
        except Exception as e:  # noqa: BLE001
            result.errors.append(f'Не удалось сохранить отчёт: {e}')

    return result
