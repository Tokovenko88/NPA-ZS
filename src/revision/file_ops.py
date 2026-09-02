"""Mixin для файловых операций приложения."""

import os
import sys
import copy
import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, timedelta
import traceback
import json
import time
import json
import time
import shutil

from npazs._bootstrap import _bootstrap_project_root

_bootstrap_project_root()

from npazs.constants import (
    settings,
    _ollama_base_url,
    DEFAULT_EXTRA_OPTIONS,
    DEFAULT_OLLAMA_MODEL,
    LAST_PATHS_FILE,
    STAGE_ANSWERS_FILE,
    LAST_RUN_LOG_FILE,
    DEBUG_RUNS_DIR,
    PROMPT_1,
    PROMPT_2,
    PROMPT_3,
    PROMPT_4,
    TYPE_TO_RUSSIAN,
)
from npazs.revision.ui_utils import clean_number_for_filename, get_date_for_filename
from npazs.revision.engine import *
from npazs.ui.dialogs.manual_mapping import ManualMappingDialog
from npazs.ui.dialogs.source_mapping import SourceMappingDialog

class FileOpsMixin:
        def _save_result(self, result_data, orig_file, change_data):
            def clean_head_revisions_valid_from(data):
                def clean(item):
                    if 'head_revisions' in item:
                        for rev in item['head_revisions']:
                            rev.pop('valid_from', None)
                    for child in item.get('item_children', []):
                        clean(child)
                for item in data.get('npa_items_revision', []):
                    clean(item)
                if 'head_revision' in data and isinstance(data['head_revision'], list):
                    for rev in data['head_revision']:
                        rev.pop('valid_from', None)
            clean_head_revisions_valid_from(result_data)

            orig_id = result_data.get('npa_id', 'unknown')
            change_id = change_data.get('npa_id', 'unknown')
            date_signed = change_data.get('date_signed', '')
            if date_signed:
                try:
                    dt = datetime.strptime(date_signed, '%d.%m.%Y')
                    date_part = f"{dt.year:04d}_{dt.month:02d}_{dt.day:02d}"
                except ValueError:
                    date_part = datetime.now().strftime('%Y_%m_%d')
            else:
                date_part = datetime.now().strftime('%Y_%m_%d')

            orig_npa_number = result_data.get('npa_number', '')
            orig_doc_type = result_data.get('doc_type', result_data.get('npa_type', 'law'))
            orig_clean_num = clean_number_for_filename(orig_npa_number)
            orig_date = get_date_for_filename(result_data, orig_doc_type)

            change_npa_number = change_data.get('npa_number', '')
            change_doc_type = change_data.get('doc_type', change_data.get('npa_type', 'law'))
            change_clean_num = clean_number_for_filename(change_npa_number)
            change_date = get_date_for_filename(change_data, change_doc_type)

            filename = f"{orig_clean_num}_{orig_date}_izm_{change_clean_num}_{change_date}.json"
            out_dir = os.path.dirname(orig_file)
            out_path = os.path.join(out_dir, filename)

            max_attempts = 3
            for attempt in range(1, max_attempts + 1):
                try:
                    if os.path.exists(out_path):
                        os.remove(out_path)
                    with open(out_path, 'w', encoding='utf-8') as f:
                        json.dump(result_data, f, ensure_ascii=False, indent=2)
                    self.log(f"Результат сохранён в:\n{out_path}", 'result')
                    return
                except PermissionError as e:
                    self.log(f"Ошибка доступа (попытка {attempt}/{max_attempts}): {e}", 'error')
                    if attempt < max_attempts:
                        self.log("Возможно, файл открыт в другой программе. Закройте его и подождите...", 'warning')
                        time.sleep(1.5)
                    else:
                        answer = messagebox.askyesno(
                            "Не удалось перезаписать файл",
                            f"Не удалось записать файл:\n{out_path}\n\n"
                            f"Причина: {e}\n\n"
                            "Хотите выбрать другой каталог для сохранения?"
                        )
                        if answer:
                            new_dir = filedialog.askdirectory(title="Выберите папку для сохранения")
                            if new_dir:
                                out_path = os.path.join(new_dir, filename)
                                try:
                                    with open(out_path, 'w', encoding='utf-8') as f:
                                        json.dump(result_data, f, ensure_ascii=False, indent=2)
                                    self.log(f"Результат сохранён в:\n{out_path}", 'result')
                                    return
                                except Exception as e2:
                                    self.log(f"Не удалось сохранить даже в выбранную папку: {e2}", 'error')
                                    messagebox.showerror("Ошибка", f"Не удалось сохранить файл: {e2}")
                                    return
                        else:
                            self.log("Сохранение отменено пользователем.", 'warning')
                            return
                except Exception as e:
                    self.log(f"Неожиданная ошибка при сохранении (попытка {attempt}/{max_attempts}): {e}", 'error')
                    if attempt == max_attempts:
                        messagebox.showerror("Ошибка", f"Не удалось сохранить файл:\n{e}")
                    else:
                        time.sleep(0.5)

        def _export_debug_run(self, orig_file, change_file):
            try:
                timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                run_dir = os.path.join(DEBUG_RUNS_DIR, timestamp)
                os.makedirs(run_dir, exist_ok=True)

                if orig_file and os.path.exists(orig_file):
                    shutil.copy2(orig_file, os.path.join(run_dir, 'target_npa.json'))

                if change_file and os.path.exists(change_file):
                    shutil.copy2(change_file, os.path.join(run_dir, 'change_npa.json'))

                if os.path.exists(LAST_RUN_LOG_FILE):
                    shutil.copy2(LAST_RUN_LOG_FILE, os.path.join(run_dir, 'run_log.txt'))

                stage1_text = self.stage1_answer_text.get('1.0', tk.END).strip()
                stage2_text = self.stage2_answer_text.get('1.0', tk.END).strip()
                stage3_text = self.stage3_answer_text.get('1.0', tk.END).strip()

                if stage1_text:
                    with open(os.path.join(run_dir, 'stage_1_answer.json'), 'w', encoding='utf-8') as f:
                        f.write(stage1_text)

                if stage2_text:
                    with open(os.path.join(run_dir, 'stage_2_answer.json'), 'w', encoding='utf-8') as f:
                        f.write(stage2_text)

                if stage3_text:
                    with open(os.path.join(run_dir, 'stage_3_answer.json'), 'w', encoding='utf-8') as f:
                        f.write(stage3_text)

                self.log(f"Отладочная папка сохранена: {run_dir}", 'info')
            except Exception as e:
                self.log(f"Ошибка сохранения отладочной папки: {e}", 'warning')

        def _normalize_log_level(self, tag):
            """Привести тег уровня лога к верхнему регистру (INFO/WARNING/ERROR/...)."""
            if not tag:
                return 'INFO'
            return str(tag).upper()

        def _dump_tk_log(self, log_text):
            """Вернуть ``[(level, text)]`` из Tk Text через ``dump``.

            ``self.log`` в GUI откладывает запись в виджет через ``root.after``,
            поэтому чтение виджета из фонового потока может быть неполным.
            Метод обёрнут в try/except и используется только как fallback,
            когда ``self.logs`` недоступен.
            """
            level_tags = ('error', 'warning', 'info', 'input', 'result', 'source', 'debug')
            try:
                items = log_text.dump('1.0', 'end', all=True) or []
            except Exception:
                items = []
            active = []
            lines = []
            buf = []
            current = 'INFO'

            def _level():
                for t in reversed(active):
                    if t in level_tags:
                        return t.upper()
                return 'INFO'

            for item in items:
                kind = item[1] if len(item) > 1 else ''
                if kind == 'tagon':
                    active.append(item[2])
                    current = _level()
                elif kind == 'tagoff':
                    tag = item[2]
                    if tag in active:
                        active.remove(tag)
                    current = _level()
                elif kind == 'text':
                    text = item[2] if len(item) > 2 else ''
                    parts = text.split('\n')
                    for i, part in enumerate(parts):
                        if part:
                            buf.append(part)
                        if i < len(parts) - 1:
                            line = ''.join(buf).rstrip()
                            if line:
                                lines.append((current, line))
                            buf = []
                            current = _level()
            line = ''.join(buf).rstrip()
            if line:
                lines.append((current, line))
            return lines

        def _collect_work_log_entries(self):
            """Собрать записи журнала работы как список кортежей ``(level, text)``.

            Предпочитает потокобезопасный ``self.logs`` (список ``(tag, message)``),
            поддерживаемый как GUI, так и headless‑режимом. Если список пуст или
            отсутствует, выполняет fallback на чтение виджета ``self.log_text``.
            """
            logs = getattr(self, 'logs', None)
            if isinstance(logs, list) and logs:
                return [(self._normalize_log_level(tag), msg) for tag, msg in logs]

            log_text = getattr(self, 'log_text', None)
            if log_text is None:
                return []
            entries = []
            try:
                entries = self._dump_tk_log(log_text)
            except Exception:
                entries = []
            if entries:
                return entries
            try:
                raw = log_text.get('1.0', tk.END)
            except Exception:
                raw = ''
            return [('INFO', ln) for ln in raw.splitlines() if ln.strip()]

        def _save_work_log(self, out_dir, change_data, result_data=None, tracker=None):
            """Сохранить журнал работы программы в ``<номер_НПА_изменения>_log.md``.

            Файл рядом с ``<number>_work.json`` и результатом ``_izm_...json``.
            Содержит: метаданные прогона, сводку трекера изменений и полный
            текстовый журнал операций.
            """
            change_npa_number = (change_data or {}).get('npa_number', '')
            change_clean_num = clean_number_for_filename(change_npa_number)
            if not change_clean_num:
                change_clean_num = 'unknown'
            filename = f"{change_clean_num}_log.md"
            out_path = os.path.join(out_dir, filename)

            orig_npa_number = (result_data or {}).get('npa_number', '')
            run_info = {}
            answers = getattr(self, '_prompt_answers', None)
            if isinstance(answers, dict):
                run_info = answers.get('run_info', {}) or {}

            lines = []
            lines.append("# Журнал работы программы")
            lines.append("")
            lines.append(f"**Изменяющий НПА:** `{change_npa_number or '—'}`")
            lines.append(f"**Целевой НПА:** `{orig_npa_number or '—'}`")
            if run_info.get('started_at'):
                lines.append(f"**Запуск:** `{run_info.get('started_at')}`")
            if run_info.get('finished_at'):
                lines.append(f"**Завершение:** `{run_info.get('finished_at')}`")
            if run_info.get('model'):
                lines.append(f"**Модель:** `{run_info.get('model')}`")
            if run_info.get('backend'):
                lines.append(f"**Бэкенд:** `{run_info.get('backend')}`")
            lines.append("")

            if tracker is not None:
                report = None
                try:
                    report = tracker.get_run_status_report()
                except Exception:
                    report = None
                if report:
                    summary = report.get('summary', {}) or {}
                    status = report.get('run_status', '')
                    lines.append("## Сводка применения изменений")
                    lines.append("")
                    lines.append(f"**Статус прогона:** `{status or '—'}`")
                    lines.append("")
                    lines.append("| Метрика | Значение |")
                    lines.append("|---|---|")
                    for key, value in summary.items():
                        lines.append(f"| {key} | {value} |")
                    lines.append("")
                    failed = report.get('failed_changes', []) or []
                    pending = report.get('pending_changes', []) or []
                    prepared = report.get('prepared_changes', []) or []
                    unverified = report.get('unverified_changes', []) or []
                    user_cancelled = report.get('user_cancelled_changes', []) or []
                    if prepared:
                        lines.append("### Подготовлены, но не применены")
                        lines.append("")
                        for c in prepared:
                            lines.append(f"- `[{c.get('revision_number', '')}] {c.get('structural_element', '')} ({c.get('type', '')})`")
                        lines.append("")
                    if failed:
                        lines.append("### Не удалось применить")
                        lines.append("")
                        for c in failed:
                            lines.append(f"- `[{c.get('revision_number', '')}] {c.get('structural_element', '')} ({c.get('type', '')}): {c.get('reason', '')}`")
                        lines.append("")
                    if pending:
                        lines.append("### Отложены")
                        lines.append("")
                        for c in pending:
                            lines.append(f"- `[{c.get('revision_number', '')}] {c.get('structural_element', '')} ({c.get('type', '')}): {c.get('reason', '')}`")
                        lines.append("")
                    if unverified:
                        lines.append("### Применены, но не проверены")
                        lines.append("")
                        for c in unverified:
                            lines.append(f"- `[{c.get('revision_number', '')}] {c.get('structural_element', '')} ({c.get('type', '')})`")
                        lines.append("")
                    if user_cancelled:
                        lines.append("### Отменены пользователем")
                        lines.append("")
                        for c in user_cancelled:
                            lines.append(f"- `[{c.get('revision_number', '')}] {c.get('structural_element', '')} ({c.get('type', '')}): {c.get('reason', '')}`")
                        lines.append("")

            entries = self._collect_work_log_entries()
            lines.append("## Полный журнал операций")
            lines.append("")
            if entries:
                lines.append("```")
                for level, text in entries:
                    text = text.replace('\r\n', '\n').replace('\r', '\n')
                    for ln in text.split('\n'):
                        ln = ln.rstrip()
                        if not ln:
                            continue
                        lines.append(f"[{level}] {ln}")
                lines.append("```")
            else:
                lines.append("_Журнал пуст._")
            lines.append("")

            try:
                with open(out_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(lines))
                self.log(f"Журнал работы сохранён в:\n{out_path}", 'result')
            except Exception as e:
                self.log(f"Ошибка сохранения журнала работы: {e}", 'error')
