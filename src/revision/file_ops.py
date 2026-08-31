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
from npazs.revision.revision_utils import *
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
                except:
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
