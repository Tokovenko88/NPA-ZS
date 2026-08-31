"""Оркестратор 5-этапного AI-пайплайна NPA-ZS.

Модуль содержит ``AiPipelineMixin`` — класс-примесь, реализующий полный
конвейер внесения изменений из изменяющего НПА в целевой НПА.

Источник: ``npa_processor/processing/ai_pipeline.py`` (перенесён без изменений
логики; обновлены только пути импорта на пространство имён ``npazs``).

Этапы и точки входа
-------------------

======  ==========================================  ==================================
Этап    Метод                                       Модуль-обёртка
======  ==========================================  ==================================
1       ``_stage1_deletion_analysis``                :mod:`npazs.pipeline.stage1_revocation`
2       ``_stage2_dates_analysis``                   :mod:`npazs.pipeline.stage2_dates`
3       ``_stage3_changes_extraction``               :mod:`npazs.pipeline.stage3_extraction`
4       ``apply_grouped_changes`` (+ ``PROMPT_4``)   :mod:`npazs.pipeline.stage4_html`
5       ``_stage5_rebuild``                          :mod:`npazs.pipeline.stage5_rebuild`
======  ==========================================  ==================================

Полный прогон запускается методом :meth:`AiPipelineMixin.run_all`, который
вызывается из GUI (:class:`npazs.ui.revision_app.App`).

Почему это mixin, а не самостоятельный сервис
---------------------------------------------
Пайплайн интерактивен: он умеет останавливаться и спрашивать оператора
(разрешение неоднозначных адресов, конфликты извлечения HTML, ручной маппинг).
Эти вызовы идут через ``self.log``, ``self.root``, ``self.stop_event`` и
диалоги Tk, поэтому пайплайн подмешивается в класс приложения
``App(GuiBuilderMixin, AiPipelineMixin, FileOpsMixin)``.

Не разрывайте эту связь без переноса всего протокола вопросов оператору:
детерминированность результата зависит от подтверждений пользователя.
"""

import os
import sys
import copy
import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, timedelta
import traceback
import re
import json

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
    PROMPT_1,
    PROMPT_2,
    PROMPT_3,
    PROMPT_4,
    TYPE_TO_RUSSIAN,
    save_last_run_log,
)
from json_repair import repair_json
from npazs.revision.text_utils import strip_thinking_tags
from npazs.revision.ai_utils import ask_ollama
from npazs.revision.engine import *
from npazs.revision.tree_utils import _find_target_element, find_item_by_id
from npazs.revision.ui_utils import _correct_change_description, _fetch_source_html_for_change, _add_new_element, _find_existing_element_flexible, _normalize_highlights_positions, _resolve_add_parent_and_deferred, _ensure_path, extract_json_from_text, expand_range_in_new_field, split_range_changes, get_date_for_filename
from npazs.revision.element_finder import narrow_source_id_to_subpoint, find_item_by_revision_number
from npazs.revision.retroactive_notes import (
    apply_retroactive_rules_to_groups,
    _append_item_note,
    _add_npa_note,
    normalize_amending_note_text,
)
from npazs.revision.html_utils import extract_html_for_added_element, _extract_quoted_html, extract_structural_block, extract_text_from_element, get_full_element_html
from npazs.revision.change_pipeline import apply_change_tracked, apply_grouped_changes_tracked, run_verification_stage
from npazs.revision.change_tracker import ChangeTracker, ChangeStatus
from npazs.ui.dialogs.manual_mapping import ManualMappingDialog
from npazs.ui.dialogs.source_mapping import SourceMappingDialog

class AiPipelineMixin:
        def _init_prompt_answers(self):
            self._prompt_answers = {
                "run_info": {
                    "started_at": datetime.now().isoformat(),
                    "model": None,
                    "backend": None,
                },
                "stages": []
            }

        def _collect_prompt_answer(self, stage_num, prompt_text, answer_text, change_info="", metadata=None):
            if not hasattr(self, '_prompt_answers'):
                self._init_prompt_answers()
            stage_entry = {
                "stage": stage_num,
                "timestamp": datetime.now().isoformat(),
                "change_info": change_info,
                "prompt": prompt_text,
                "answer": answer_text,
                "metadata": metadata or {}
            }
            self._prompt_answers["stages"].append(stage_entry)

        def _save_prompt_answers(self, out_dir, change_data, result_data=None):
            if not hasattr(self, '_prompt_answers') or not self._prompt_answers["stages"]:
                return
            change_npa_number = change_data.get('npa_number', '')
            change_doc_type = change_data.get('doc_type', change_data.get('npa_type', 'law'))
            from npazs.revision.file_ops import clean_number_for_filename
            change_clean_num = clean_number_for_filename(change_npa_number)
            filename = f"{change_clean_num}_work.json"
            out_path = os.path.join(out_dir, filename)
            self._prompt_answers["run_info"]["model"] = self.ollama_model.get() if hasattr(self, 'ollama_model') and hasattr(self.ollama_model, 'get') else str(getattr(self, 'ollama_model', None))
            if hasattr(self, 'backend'):
                self._prompt_answers["run_info"]["backend"] = self.backend.get() if hasattr(self.backend, 'get') else str(self.backend)
            self._prompt_answers["run_info"]["change_npa_number"] = change_npa_number
            self._prompt_answers["run_info"]["change_doc_type"] = change_doc_type
            self._prompt_answers["run_info"]["finished_at"] = datetime.now().isoformat()
            try:
                with open(out_path, 'w', encoding='utf-8') as f:
                    json.dump(self._prompt_answers, f, ensure_ascii=False, indent=2)
                self.log(f"Ответы на промпты сохранены в:\n{out_path}", 'result')
            except Exception as e:
                self.log(f"Ошибка сохранения ответов на промпты: {e}", 'error')

        def _stage1_deletion_analysis(self, final_text, model, extra_options, pub_date_str, original_law_number):
            if self.use_stage1_answer.get():
                self.log("Используем вставленный ответ для этапа 1", 'info')
                stage1_text = self.stage1_answer_text.get('1.0', tk.END).strip()
                stage1_text = strip_thinking_tags(stage1_text)
                if stage1_text and stage1_text.lower() not in ('null', ''):
                    try:
                        repaired = repair_json(stage1_text)
                        parsed = json.loads(repaired)
                        if isinstance(parsed, list):
                            return parsed
                        elif isinstance(parsed, dict) and 'changes' in parsed:
                            return parsed['changes']
                    except Exception as e:
                        self.log(f"Ошибка парсинга вставленного ответа этапа 1: {e}", 'error')
                else:
                    self.log("ℹ️ Ответ от ИИ: null — указаний об утрате силы нет.", 'info')
                return []
            if not self.prompt_1:
                self.log("⚠ Промпт 1 не задан, этап 1 пропускается", 'warning')
                return []
            if self.stop_event.is_set():
                return []
            stage1_prompt = (self.prompt_1
                .replace("{final_provisions}", final_text)
                .replace("{doc_text}", final_text)
                .replace("{date_pub}", pub_date_str)
                .replace("{law_number}", original_law_number))
            answer1 = ask_ollama(stage1_prompt, model, self.log, extra_options, self.stop_event, change_info="", backend=self.backend.get(), kilo_gateway_url=self.kilo_gateway_url.get(), api_key=self.kilo_gateway_api_key.get())
            self._collect_prompt_answer(1, stage1_prompt, answer1, change_info="Анализ заключительных положений на утрату силы")
            if answer1 and answer1.lower() != 'null':
                try:
                    repaired = repair_json(answer1)
                    parsed = json.loads(repaired)
                    if isinstance(parsed, list):
                        return parsed
                    elif isinstance(parsed, dict) and 'changes' in parsed:
                        return parsed['changes']
                except Exception as e:
                    self.log(f"Ошибка парсинга ответа этапа 1: {e}", 'error')
            else:
                self.log("ℹ️ Ответ от ИИ: null — указаний об утрате силы нет.", 'info')
            return []

        def _stage2_iso_to_dmy(self, value):
            """Приводит дату из ответа ИИ к формату DD.MM.YYYY.

            Промпт 2 (prompt_2.md) заставляет ИИ возвращать ISO-даты
            (ГГГГ-ММ-ДД), тогда как остальной конвейер работает с DD.MM.YYYY.
            Уже готовые DD.MM.YYYY даты возвращаются без изменений.
            """
            if not isinstance(value, str):
                return value
            s = value.strip()
            if not s:
                return value
            for fmt in ('%Y-%m-%d', '%d.%m.%Y'):
                try:
                    return datetime.strptime(s, fmt).strftime('%d.%m.%Y')
                except ValueError:
                    continue
            return value

        def _stage2_normalize_result(self, parsed, change_data=None):
            """Приводит ответ этапа 2 к внутреннему плоскому списку записей.

            Поддерживаются оба формата, которые может вернуть ИИ/оператор:

            * плоский массив записей (legacy/ручной ввод) — каждая запись уже
              содержит ``action_type``/``applies_to``/``structural_element``;
            * JSON-объект ``{special_valid_from:[...], retroactive_effects:[...]}``
              — текущий формат prompt_2.md. Массив ``retroactive_effects``
              (поля ``corrected_text``/``original_text``/``date``) преобразуется
              в записи ``retroactive_note`` с ``note_text``/``note_valid_from``.

            Даты (``date``/``note_valid_from``) приводятся к DD.MM.YYYY.
            """
            if parsed is None:
                return []
            if isinstance(parsed, dict):
                records = []
                for item in (parsed.get('special_valid_from') or []):
                    if not isinstance(item, dict):
                        continue
                    rec = dict(item)
                    rec.setdefault('action_type', 'special_valid_from')
                    rec.setdefault('applies_to', 'amending_law')
                    if rec.get('date'):
                        rec['date'] = self._stage2_iso_to_dmy(rec['date'])
                    records.append(rec)
                for item in (parsed.get('retroactive_effects') or []):
                    if not isinstance(item, dict):
                        continue
                    note_text = (item.get('corrected_text') or '').strip()
                    if not note_text:
                        continue
                    records.append({
                        'applies_to': 'target_law',
                        'action_type': 'retroactive_note',
                        'structural_element': (item.get('structural_element') or '').strip(),
                        'note_text': note_text,
                        'original_text': item.get('original_text', ''),
                        'note_valid_from': self._stage2_iso_to_dmy(item.get('date') or ''),
                    })
                if records:
                    self.log(
                        f"[STAGE2] объект-ответ преобразован: "
                        f"{sum(1 for r in records if r.get('action_type')=='special_valid_from')} special_valid_from, "
                        f"{sum(1 for r in records if r.get('action_type')=='retroactive_note')} retroactive_note",
                        'info')
                return records
            if isinstance(parsed, list):
                for rec in parsed:
                    if not isinstance(rec, dict):
                        continue
                    if rec.get('date'):
                        rec['date'] = self._stage2_iso_to_dmy(rec['date'])
                    if rec.get('note_valid_from'):
                        rec['note_valid_from'] = self._stage2_iso_to_dmy(rec['note_valid_from'])
                return parsed
            return []

        def _stage2_normalize_amending_notes(self, records, change_data=None):
            """Нормализует note_text для amending_law + retroactive_note записей."""
            change_npa_number = (change_data or {}).get('npa_number', '')
            change_date_pub = (change_data or {}).get('date_pub', '') or (change_data or {}).get('date_signed', '')
            for rec in records:
                if rec.get("applies_to") == "amending_law" and rec.get("action_type") == "retroactive_note":
                    rec["note_text"] = normalize_amending_note_text(
                        rec.get("note_text", ""),
                        log_callback=self.log,
                        amending_law_number=change_npa_number,
                        amending_law_date=change_date_pub,
                    )
            return records

        def _stage2_dates_analysis(self, final_text, target_element, model, extra_options, pub_date_str, original_law_number, change_data=None, base_law_date_pub=''):
            def _parse_stage2(raw_text, label):
                raw_text = strip_thinking_tags(raw_text)
                if not raw_text or raw_text.lower() in ('null', ''):
                    self.log(f"ℹ️ Ответ от ИИ (этап 2): null — дополнительных указаний нет.", 'info')
                    return None
                try:
                    repaired = repair_json(raw_text)
                    return json.loads(repaired)
                except Exception as e:
                    self.log(f"Ошибка парсинга ответа этапа 2 ({label}): {e}", 'error')
                    return None

            if self.use_stage2_answer.get():
                self.log("Используем вставленный ответ для этапа 2", 'info')
                parsed = _parse_stage2(self.stage2_answer_text.get('1.0', tk.END).strip(), "вставленный")
            elif not self.prompt_2:
                self.log("⚠ Промпт 2 не задан, этап 2 пропускается", 'warning')
                return []
            elif self.stop_event.is_set():
                return []
            else:
                article_number_str = target_element.get('item_number', '') if target_element else ''
                change_npa_number = (change_data or {}).get('npa_number', '')
                change_date_pub = (change_data or {}).get('date_pub', '') or (change_data or {}).get('date_signed', '')
                change_valid_from = (change_data or {}).get('valid_from', '').strip()
                if not change_valid_from:
                    change_valid_from = (change_data or {}).get('date_signed', '').strip()
                    if not change_valid_from:
                        change_valid_from = (change_data or {}).get('date_pub', '').strip()
                stage2_prompt = (self.prompt_2
                    .replace("{final_provisions}", final_text)
                    .replace("{doc_text}", final_text)
                    .replace("{date_pub}", base_law_date_pub or pub_date_str)
                    .replace("{law_number}", original_law_number)
                    .replace("{article_number}", article_number_str)
                    .replace("{change_npa_number}", change_npa_number)
                    .replace("{change_date_pub}", change_date_pub)
                    .replace("{change_date_effective}", change_valid_from)
                    .replace("{valid_from}", change_valid_from))
                answer2 = ask_ollama(stage2_prompt, model, self.log, extra_options, self.stop_event, change_info="", backend=self.backend.get(), kilo_gateway_url=self.kilo_gateway_url.get(), api_key=self.kilo_gateway_api_key.get())
                self._collect_prompt_answer(2, stage2_prompt, answer2, change_info="Анализ заключительных положений на даты вступления и правоотношения")
                parsed = _parse_stage2(answer2, "ИИ") if answer2 else None

            if parsed is None:
                return []
            records = self._stage2_normalize_result(parsed, change_data)
            return self._stage2_normalize_amending_notes(records, change_data)

        def _stage3_changes_extraction(self, target_element, model, extra_options, change_data, manual_resolver=None, stop_event=None):
            article_changes = []
            if self.use_stage3_answer.get():
                self.log("Используем вставленный ответ для этапа 3", 'info')
                stage3_text = self.stage3_answer_text.get('1.0', tk.END).strip()
                stage3_text = strip_thinking_tags(stage3_text)
                if stage3_text and stage3_text.lower() not in ('null', ''):
                    try:
                        json_str = extract_json_from_text(stage3_text) or stage3_text
                        repaired = repair_json(json_str)
                        parsed = json.loads(repaired)
                        if isinstance(parsed, list):
                            article_changes = parsed
                        elif isinstance(parsed, dict) and 'changes' in parsed:
                            article_changes = parsed['changes']
                        elif isinstance(parsed, dict) and 'structural_element' in parsed and 'type' in parsed:
                            article_changes = [parsed]
                    except Exception as e:
                        self.log(f"Ошибка парсинга вставленного ответа этапа 3: {e}", 'error')
                else:
                    self.log("ℹ️ Ответ от ИИ: null — изменений нет.", 'info')
            else:
                if not self.prompt_3:
                    self.log("⚠ Промпт 3 не задан, этап 3 пропускается", 'warning')
                    return []
                if self.elementwise_mode.get():
                    if stop_event and stop_event.is_set():
                        return []
                    self.log("  Обработка элемента (как целого)", 'info')
                    self._process_element_for_changes(target_element, model, self.log, extra_options, stop_event, article_changes)
                    for child in target_element.get('item_children', []):
                        self._process_element_for_changes(child, model, self.log, extra_options, stop_event, article_changes)
                else:
                    if stop_event and stop_event.is_set():
                        return []
                    article_json = json.dumps(target_element, ensure_ascii=False, indent=2)
                    stage3_prompt = self.prompt_3.replace("{change_json}", article_json)
                    answer3 = ask_ollama(stage3_prompt, model, self.log, extra_options, stop_event, change_info="", backend=self.backend.get(), kilo_gateway_url=self.kilo_gateway_url.get(), api_key=self.kilo_gateway_api_key.get())
                    self._collect_prompt_answer(3, stage3_prompt, answer3, change_info="Анализ изменений из текста элемента")
                    if answer3 and answer3.lower() != 'null':
                        try:
                            cleaned = strip_thinking_tags(answer3).strip()
                            if cleaned.startswith('```json') and cleaned.endswith('```'):
                                cleaned = cleaned[7:-3].strip()
                            elif cleaned.startswith('```') and cleaned.endswith('```'):
                                cleaned = cleaned[3:-3].strip()
                            repaired = repair_json(cleaned)
                            parsed = json.loads(repaired)
                            if isinstance(parsed, list):
                                article_changes = parsed
                            elif isinstance(parsed, dict) and 'changes' in parsed:
                                article_changes = parsed['changes']
                            elif isinstance(parsed, dict) and 'structural_element' in parsed and 'type' in parsed:
                                article_changes = [parsed]
                        except Exception as e:
                            self.log(f"Ошибка парсинга ответа этапа 3: {e}", 'error')
                            json_str = extract_json_from_text(answer3)
                            if json_str:
                                try:
                                    repaired = repair_json(json_str)
                                    parsed = json.loads(repaired)
                                    article_changes = parsed if isinstance(parsed, list) else []
                                except Exception:
                                    pass
                    else:
                        self.log("ℹ️ Ответ от ИИ: null — изменений нет.", 'info')
                        return []

            for ch in article_changes:
                ch_type = ch.get('type', '')
                if ch_type in ('add', 'new_redaction'):
                    if not ch.get('revision_number'):
                        if ch_type == 'add' and ch.get('description'):
                            continue
                        self.log(f"  ℹ️ {ch_type} без revision_number, будет использован target_element как источник", 'info')
            filtered_by_rev = []
            for ch in article_changes:
                rn = ch.get('revision_number')
                if isinstance(rn, str) and rn.strip() in ('', 'null'):
                    self.log(f"  ⚠ Пропуск изменения с некорректным revision_number '{rn}': {ch.get('structural_element')}", 'warning')
                    continue
                filtered_by_rev.append(ch)
            article_changes = filtered_by_rev

            cleaned_changes = []
            for ch in article_changes:
                ch_type = ch.get('type', '')
                if ch_type == 'add' and not ch.get('revision_number') and ch.get('description'):
                    cleaned_changes.append(ch)
                    continue
                if ch_type == 'new_redaction' and not ch.get('revision_number') and ch.get('description'):
                    cleaned_changes.append(ch)
                    continue
                if ch_type in ('add', 'new_redaction'):
                    if _correct_change_description(ch, change_data, target_element, self.log, manual_resolver, stop_event):
                        cleaned_changes.append(ch)
                    else:
                        self.log(f"  ❌ Изменение '{ch.get('structural_element', '')}' (тип {ch_type}) пропущено после очистки", 'error')
                else:
                    cleaned_changes.append(ch)
            article_changes = cleaned_changes

            expanded_changes = []
            for ch in article_changes:
                if ch.get('type') == 'add' and 'new' in ch:
                    sub_changes = expand_range_in_new_field(ch, self.log, change_data, target_element)
                    expanded_changes.extend(sub_changes)
                else:
                    expanded_changes.append(ch)
            article_changes = expanded_changes

            article_changes = split_range_changes(article_changes, self.log)

            for ch in article_changes:
                if ch.get('type') == 'add' and ch.get('structural_element') == 'Приложение':
                    desc = ch.get('description', '')
                    new_val = ch.get('new', '')
                    article_match = re.search(r'стать[уе]?\s+(\d+)', desc, re.IGNORECASE)
                    if not article_match:
                        article_match = re.search(r'стать[уе]?\s+(\d+)', new_val, re.IGNORECASE)
                    if article_match:
                        article_num = article_match.group(1)
                        ch['structural_element'] = f'Приложение Статья {article_num}'
                        self.log(f"  🔧 Исправлен structural_element: 'Приложение' -> 'Приложение Статья {article_num}'", 'info')

            if not article_changes:
                self.log("ℹ️ Изменений в анализируемом элементе не найдено.", 'info')
            else:
                self.log(f"Этап 3: получено изменений после фильтрации: {len(article_changes)}", 'result')
            return article_changes

        def _process_element_for_changes(self, element, model, log_callback, extra_options, stop_event, changes_list):
            if stop_event and stop_event.is_set():
                return
            element_json = json.dumps(element, ensure_ascii=False, indent=2)
            stage3_prompt = self.prompt_3.replace("{change_json}", element_json)
            answer = ask_ollama(stage3_prompt, model, log_callback, extra_options, stop_event, change_info="", backend=self.backend.get(), kilo_gateway_url=self.kilo_gateway_url.get(), api_key=self.kilo_gateway_api_key.get())
            self._collect_prompt_answer(3, stage3_prompt, answer, change_info=f"Анализ изменений из текста элемента {element.get('item_id')}")
            if answer and answer.lower() != 'null':
                try:
                    cleaned = strip_thinking_tags(answer).strip()
                    if cleaned.startswith('```json') and cleaned.endswith('```'):
                        cleaned = cleaned[7:-3].strip()
                    elif cleaned.startswith('```') and cleaned.endswith('```'):
                        cleaned = cleaned[3:-3].strip()
                    repaired = repair_json(cleaned)
                    parsed = json.loads(repaired)
                    if isinstance(parsed, list):
                        element_changes = parsed
                    elif isinstance(parsed, dict) and 'changes' in parsed:
                        element_changes = parsed['changes']
                    elif isinstance(parsed, dict) and 'structural_element' in parsed and 'type' in parsed:
                        element_changes = [parsed]
                    else:
                        element_changes = []
                    element_changes = split_range_changes(element_changes, log_callback)
                    for ch in element_changes:
                        structural = ch.get('structural_element', '')
                        original_type = ch.get('type', '')
                        if original_type == 'add' and 'нпа' in structural.lower():
                            ch['structural_element'] = 'нпа'
                        changes_list.append(ch)
                except Exception as e:
                    log_callback(f"Ошибка парсинга ответа для элемента {element.get('item_id')}: {e}", 'error')
            else:
                log_callback(f"ℹ️ Для элемента {element.get('item_id')} изменений нет.", 'info')

        # ==================== ИСПРАВЛЕННЫЙ _stage5_rebuild ====================
        def _stage5_rebuild(self, result_data, rebuild_ids, general_valid_from, change_data, tracker=None):
            raw_ids = rebuild_ids
            self.log(f"📊 Статистика: исходных ID: {len(raw_ids)}, уникальных: {len(set(raw_ids))}", 'info')
            unique_ids = list(dict.fromkeys(raw_ids))

            parent_map = {}
            def build_parent_map(items, parent_id=None):
                for item in items:
                    item_id = item.get('item_id')
                    if item_id:
                        parent_map[item_id] = parent_id
                    build_parent_map(item.get('item_children', []), item_id)
            build_parent_map(result_data.get('npa_items_revision', []))

            def is_ancestor_in_list(candidate_id, id_list):
                current_id = candidate_id
                visited = set()
                while current_id and current_id not in visited:
                    visited.add(current_id)
                    parent_id = parent_map.get(current_id)
                    if parent_id in id_list:
                        return True
                    current_id = parent_id
                return False

            filtered_ids = []
            unique_set = set(unique_ids)
            for uid in unique_ids:
                elem = find_item_by_id(result_data, uid)
                if elem and (elem.get('_pending_new_redaction_html') or elem.get('_pending_html')):
                    filtered_ids.append(uid)
                elif not is_ancestor_in_list(uid, unique_set - {uid}):
                    filtered_ids.append(uid)

            self.log(f"📊 после фильтрации: {len(filtered_ids)}", 'info')
            if not filtered_ids:
                self.log("ℹ️ Нет элементов для перестройки", 'info')
                return

            def get_depth(item_id):
                return item_id.count('_')
            filtered_ids_sorted = sorted(filtered_ids, key=lambda x: get_depth(x), reverse=True)

            self.log(f"🔧 Список ID для перестройки (отсортирован по глубине, сначала глубокие): {filtered_ids_sorted}", 'info')
            rebuild_modified_by = str(change_data.get('npa_id', 'unknown'))

            # Вспомогательная функция для получения HTML дочернего элемента из его перестроенной ревизии
            def get_child_html_after_rebuild(child_id):
                child = find_item_by_id(result_data, child_id)
                if not child:
                    return None
                revs = child.get('revisions', [])
                active_rev = None
                for rev in reversed(revs):
                    if rev.get('valid_to') is None:
                        active_rev = rev
                        break
                if not active_rev:
                    return None
                body_parts = []
                for block in active_rev.get('body', []):
                    if block.get('type') == 'paragraph':
                        body_parts.append(block.get('html_text', ''))
                    elif block.get('type') == 'table_fragment':
                        body_parts.append(block.get('html_text', ''))
                if not body_parts:
                    return None
                return '\n'.join(body_parts)

            for element_id in filtered_ids_sorted:
                if self.stop_event.is_set():
                    self.log("Перестройка прервана пользователем", 'warning')
                    break
                element = find_item_by_id(result_data, element_id)
                if not element:
                    self.log(f"⚠️ Элемент {element_id} не найден для перестройки", 'warning')
                    continue

                # Обновляем HTML родителя, используя перестроенные дочерние элементы
                if element.get('_pending_mod_type') in ('change', 'new_redaction'):
                    # Проверяем, есть ли у элемента дочерние элементы с изменениями (ID в rebuild_ids)
                    has_changed_children = False
                    def check_children_for_ids(item):
                        nonlocal has_changed_children
                        for child in item.get('item_children', []):
                            if child.get('item_id') in raw_ids:
                                has_changed_children = True
                                return
                            check_children_for_ids(child)
                    check_children_for_ids(element)

                    if has_changed_children:
                        # Если у элемента есть собственное изменение (_pending_new_redaction_html)
                        if element.get('_pending_new_redaction_html'):
                            base_html = element['_pending_new_redaction_html']
                            from bs4 import BeautifulSoup
                            soup = BeautifulSoup(base_html, 'html.parser')
                            # Собираем ID только прямых потомков элемента, которые есть в raw_ids.
                            # Вложенные элементы (например, пункты внутри новой части) уже
                            # учтены в HTML контейнера через child_ref, поэтому их HTML
                            # добавлять в родителя повторно нельзя.
                            child_ids_to_add = []
                            for child in element.get('item_children', []):
                                if child.get('item_id') in raw_ids:
                                    child_ids_to_add.append(child.get('item_id'))
                            added_any = False
                            for child_id in child_ids_to_add:
                                child_html = get_child_html_after_rebuild(child_id)
                                if not child_html:
                                    continue
                                child_elem = find_item_by_id(result_data, child_id)
                                if not child_elem:
                                    continue
                                child_num = child_elem.get('item_number')
                                child_type = child_elem.get('item_type')
                                if child_type == 'part' and child_num:
                                    child_soup = BeautifulSoup(child_html, 'html.parser')
                                    first_p = child_soup.find('p')
                                    if first_p:
                                        first_p.insert(0, f"{child_num}. ")
                                    soup.append(child_soup)
                                else:
                                    new_p = BeautifulSoup(child_html, 'html.parser')
                                    soup.append(new_p)
                                added_any = True
                            if added_any:
                                element['_pending_new_redaction_html'] = str(soup)
                                self.log(f"  Дополнен HTML для {element_id} HTML-кодами перестроенных дочерних элементов", 'info')
                        else:
                            # Нет собственного изменения – собираем полный HTML из текущего состояния (включая детей)
                            new_html = get_full_element_html(element, use_original_structure=False)
                            if new_html:
                                element['_pending_new_redaction_html'] = new_html
                                self.log(f"  HTML для {element_id} обновлён с учётом изменений дочерних элементов", 'info')

                pending_html = element.get('_pending_new_redaction_html', element.get('_pending_html', ''))
                pending_len = len(pending_html) if isinstance(pending_html, str) else "not a string"
                self.log(f"🔵 Входные данные для перестройки элемента {element_id}: pending_html_length = {pending_len}", 'input')
                input_info = {
                    'item_id': element.get('item_id'),
                    'item_type': element.get('item_type'),
                    'item_number': element.get('item_number'),
                    'pending_html_len': pending_len,
                    'pending_mod_type': element.get('_pending_mod_type'),
                    'pending_modified_by': element.get('_pending_modified_by_id'),
                    'pending_valid_from': element.get('_pending_valid_from'),
                }
                self.log(json.dumps(input_info, ensure_ascii=False, indent=2), 'input')
                new_revision_id = rebuild_element_with_history(
                    result_data,
                    element_id,
                    valid_from=general_valid_from,
                    modified_by_id_str=rebuild_modified_by,
                    doc_type='law',
                    log_callback=self.log,
                    log_queue=self.message_queue,
                    answer_queue=self.answer_queue
                )
                updated_element = find_item_by_id(result_data, element_id)
                if new_revision_id:
                    if updated_element:
                        self.log(f"✅ Элемент {element_id} успешно перестроен.", 'result')
                    else:
                        self.log(f"⚠️ Не удалось найти обновлённый элемент {element_id}", 'warning')
                    if tracker:
                        change_ids_to_update = []
                        if updated_element:
                            if updated_element.get('_pending_changes'):
                                change_ids_to_update = [c['change_id'] for c in updated_element['_pending_changes']]
                            elif updated_element.get('_pending_change_id'):
                                change_ids_to_update = [updated_element['_pending_change_id']]
                        for cid in change_ids_to_update:
                            if not cid:
                                continue
                            current_status = tracker.get_status(cid)
                            if current_status in (ChangeStatus.PREPARED, ChangeStatus.APPLYING, ChangeStatus.PENDING):
                                tracker.mark_applied(cid, revision_id=new_revision_id)
                                self.log(f"  Трекер обновлён: change_id={cid} revision_id={new_revision_id}", 'result')
                            else:
                                self.log(f"  Трекер: change_id={cid} уже в статусе {current_status.value}, пропускаем APPLIED", 'info')
                else:
                    self.log(f"❌ Ошибка перестройки элемента {element_id}", 'error')
                    if tracker:
                        change_ids_to_update = []
                        if updated_element:
                            if updated_element.get('_pending_changes'):
                                change_ids_to_update = [c['change_id'] for c in updated_element['_pending_changes']]
                            elif updated_element.get('_pending_change_id'):
                                change_ids_to_update = [updated_element['_pending_change_id']]
                        for cid in change_ids_to_update:
                            tracker.mark_failed(cid, reason="rebuild failed")

            # Второй проход для оставшихся pending
            def _collect_pending_ids(items, acc):
                for item in items:
                    if item.get('_pending_new_redaction_html') or item.get('_pending_html'):
                        acc.append(item['item_id'])
                    _collect_pending_ids(item.get('item_children', []), acc)
                return acc
            remaining_pending = list(dict.fromkeys(_collect_pending_ids(result_data.get('npa_items_revision', []), [])))
            if remaining_pending:
                remaining_pending_sorted = sorted(remaining_pending, key=lambda x: get_depth(x), reverse=True)
                self.log(f"🔧 Второй проход: перестройка {len(remaining_pending_sorted)} элементов с отложенными изменениями: {remaining_pending_sorted}", 'info')
                for element_id in remaining_pending_sorted:
                    if self.stop_event.is_set():
                        self.log("Перестройка (второй проход) прервана пользователем", 'warning')
                        break
                    element = find_item_by_id(result_data, element_id)
                    if not element:
                        self.log(f"⚠️ Элемент {element_id} (второй проход) не найден", 'warning')
                        continue

                    if element.get('_pending_mod_type') in ('change', 'new_redaction'):
                        has_changed_children = False
                        def check_children_for_ids2(item):
                            nonlocal has_changed_children
                            for child in item.get('item_children', []):
                                if child.get('item_id') in raw_ids:
                                    has_changed_children = True
                                    return
                                check_children_for_ids2(child)
                        check_children_for_ids2(element)

                        if has_changed_children:
                            if element.get('_pending_new_redaction_html'):
                                base_html = element['_pending_new_redaction_html']
                                from bs4 import BeautifulSoup
                                soup = BeautifulSoup(base_html, 'html.parser')
                                child_ids_to_add = []
                                def collect_child_ids2(item):
                                    for child in item.get('item_children', []):
                                        if child.get('item_id') in raw_ids:
                                            child_ids_to_add.append(child.get('item_id'))
                                        collect_child_ids2(child)
                                collect_child_ids2(element)
                                added_any = False
                                for child_id in child_ids_to_add:
                                    child_html = get_child_html_after_rebuild(child_id)
                                    if not child_html:
                                        continue
                                    child_elem = find_item_by_id(result_data, child_id)
                                    if not child_elem:
                                        continue
                                    child_num = child_elem.get('item_number')
                                    child_type = child_elem.get('item_type')
                                    if child_type == 'part' and child_num:
                                        child_soup = BeautifulSoup(child_html, 'html.parser')
                                        first_p = child_soup.find('p')
                                        if first_p:
                                            first_p.insert(0, f"{child_num}. ")
                                        soup.append(child_soup)
                                    else:
                                        new_p = BeautifulSoup(child_html, 'html.parser')
                                        soup.append(new_p)
                                    added_any = True
                                if added_any:
                                    element['_pending_new_redaction_html'] = str(soup)
                                    self.log(f"  Дополнен HTML для {element_id} (второй проход) HTML-кодами перестроенных детей", 'info')
                            else:
                                new_html = get_full_element_html(element, use_original_structure=False)
                                if new_html:
                                    element['_pending_new_redaction_html'] = new_html
                                    self.log(f"  HTML для {element_id} (второй проход) обновлён", 'info')

                    pending_html = element.get('_pending_new_redaction_html', element.get('_pending_html', ''))
                    pending_len = len(pending_html) if isinstance(pending_html, str) else "not a string"
                    self.log(f"🔵 Входные данные для перестройки элемента {element_id} (второй проход): pending_html_length = {pending_len}", 'input')
                    input_info = {
                        'item_id': element.get('item_id'),
                        'item_type': element.get('item_type'),
                        'item_number': element.get('item_number'),
                        'pending_html_len': pending_len,
                        'pending_mod_type': element.get('_pending_mod_type'),
                        'pending_modified_by': element.get('_pending_modified_by_id'),
                        'pending_valid_from': element.get('_pending_valid_from'),
                    }
                    self.log(json.dumps(input_info, ensure_ascii=False, indent=2), 'input')
                    new_revision_id = rebuild_element_with_history(
                        result_data,
                        element_id,
                        valid_from=general_valid_from,
                        modified_by_id_str=rebuild_modified_by,
                        doc_type='law',
                        log_callback=self.log,
                        log_queue=self.message_queue,
                        answer_queue=self.answer_queue
                    )
                    updated_element = find_item_by_id(result_data, element_id)
                    if new_revision_id:
                        self.log(f"✅ Элемент {element_id} (второй проход) успешно перестроен.", 'result')
                        if tracker:
                            change_ids_to_update = []
                            if updated_element:
                                if updated_element.get('_pending_changes'):
                                    change_ids_to_update = [c['change_id'] for c in updated_element['_pending_changes']]
                                elif updated_element.get('_pending_change_id'):
                                    change_ids_to_update = [updated_element['_pending_change_id']]
                            for cid in change_ids_to_update:
                                if not cid:
                                    continue
                                current_status = tracker.get_status(cid)
                                if current_status in (ChangeStatus.PREPARED, ChangeStatus.APPLYING, ChangeStatus.PENDING):
                                    tracker.mark_applied(cid, revision_id=new_revision_id)
                                    self.log(f"  Трекер обновлён: change_id={cid} revision_id={new_revision_id}", 'result')
                                else:
                                    self.log(f"  Трекер: change_id={cid} уже в статусе {current_status.value}, пропускаем APPLIED", 'info')
                    else:
                        self.log(f"❌ Ошибка перестройки элемента {element_id} (второй проход)", 'error')
                        if tracker:
                            change_ids_to_update = []
                            if updated_element:
                                if updated_element.get('_pending_changes'):
                                    change_ids_to_update = [c['change_id'] for c in updated_element['_pending_changes']]
                                elif updated_element.get('_pending_change_id'):
                                    change_ids_to_update = [updated_element['_pending_change_id']]
                            for cid in change_ids_to_update:
                                tracker.mark_failed(cid, reason="rebuild failed (second pass)")

        # ==================== ОЧИСТКА НЕДЕЙСТВИТЕЛЬНЫХ РЕВИЗИЙ ====================
        def _fix_invalid_revisions(self, data, change_data):
            """Удаляет valid_to и not_valid у ревизий, созданных текущим изменяющим законом."""
            modified_by_prefix = str(change_data.get('npa_id', ''))
            if not modified_by_prefix:
                return

            def process_item(item):
                for rev in item.get('revisions', []):
                    mod_by = rev.get('modified_by_id', '')
                    if mod_by and mod_by.startswith(modified_by_prefix):
                        if 'valid_to' in rev:
                            del rev['valid_to']
                        if 'not_valid' in rev:
                            del rev['not_valid']
                for child in item.get('item_children', []):
                    process_item(child)

            for root in data.get('npa_items_revision', []):
                process_item(root)

        # ============== ОСТАЛЬНЫЕ МЕТОДЫ (без изменений) ==============
        def _group_changes(self, remaining_changes, original_data, target_element, general_valid_from, model, extra_options, change_data, ambiguous_callback, tracker=None):
            from collections import defaultdict
            import copy
            import uuid
            SENTINEL_НАИМЕНОВАНИЕ = '__наименование__'
            SENTINEL_ПРЕАМБУЛА = '__преамбула__'
            expanded_changes = []
            for ch in remaining_changes:
                if self.stop_event.is_set():
                    return {}
                if ch.get('type') == 'change' and '|' in ch.get('description', ''):
                    parts = [p.strip() for p in ch['description'].split('|') if p.strip()]
                    if len(parts) > 1:
                        for part in parts:
                            new_ch = copy.deepcopy(ch)
                            new_ch['description'] = part
                            if 'наименование' in part.lower():
                                original_struct = ch.get('structural_element', '').strip()
                                if original_struct:
                                    new_ch['structural_element'] = f"наименование {original_struct}"
                                else:
                                    new_ch['structural_element'] = 'наименование'
                            expanded_changes.append(new_ch)
                        continue
                expanded_changes.append(ch)
            changes_with_target = []
            for ch in expanded_changes:
                if self.stop_event.is_set():
                    return {}
                structural = ch.get('structural_element', '').strip()
                ch_type = ch.get('type', '')
                valid_from = ch.get('valid_from', general_valid_from.strftime('%d.%m.%Y'))
                structural_lower = structural.lower()
                if structural_lower == 'наименование':
                    target_id = SENTINEL_НАИМЕНОВАНИЕ
                    ch['_resolved_item_id'] = SENTINEL_НАИМЕНОВАНИЕ
                elif structural_lower == 'преамбула':
                    target_id = SENTINEL_ПРЕАМБУЛА
                    ch['_resolved_item_id'] = SENTINEL_ПРЕАМБУЛА
                elif structural_lower == 'нпа':
                    ch['_resolved_item_id'] = None
                    target_id = None
                else:
                    if structural_lower.endswith(' наименование'):
                        element_path = structural[:-len(' наименование')].strip()
                        target_elem = _find_existing_element_flexible(original_data, element_path, self.log, ambiguous_callback)
                        if target_elem:
                            ch['structural_element'] = f"наименование {element_path}"
                            ch['_resolved_item_id'] = target_elem['item_id']
                            ch['_resolved_valid_from'] = valid_from
                            self.log(f"  Найден элемент для наименования '{element_path}': ID {target_elem['item_id']}", 'info')
                            changes_with_target.append(ch)
                            continue
                        else:
                            self.log(f"⚠️ Не найден элемент для наименования: {element_path}. Открываем ручное сопоставление...", 'warning')
                            manual_target, manual_struct, new_desc, new_type = self.resolve_change_manually(ch, original_data, self.stop_event)
                            if self.stop_event.is_set():
                                return {}
                            if manual_target is not None:
                                ch['_resolved_item_id'] = manual_target
                                ch['_resolved_valid_from'] = valid_from
                                if manual_struct:
                                    ch['structural_element'] = manual_struct
                                if new_desc is not None:
                                    ch['description'] = new_desc
                                if new_type is not None:
                                    ch['type'] = new_type
                                self.log(f"  → Зафиксирован resolved_item_id={manual_target} для {ch.get('structural_element')}", 'result')
                                changes_with_target.append(ch)
                                continue
                            else:
                                if tracker:
                                    change_id = tracker.register_change(ch)
                                    tracker.mark_user_cancelled(change_id, "Пользователь отменил выбор адреса")
                                self.log(f"  -> Изменение наименования '{structural}' будет пропущено", 'warning')
                                continue
                    para_match = re.search(r'\s+абзац\s+(\d+|первый|второй|третий|четвертый|пятый|шестой|седьмой|восьмой|девятый|десятый)$', structural, re.IGNORECASE)
                    if para_match:
                        num_str = para_match.group(1)
                        if num_str.isdigit():
                            para_num = int(num_str)
                        else:
                            numbers = {'первый':1,'второй':2,'третий':3,'четвертый':4,'пятый':5,
                                    'шестой':6,'седьмой':7,'восьмой':8,'девятый':9,'десятый':10}
                            para_num = numbers.get(num_str.lower())
                        if para_num:
                            base_structural = structural[:para_match.start()].strip()
                            target_elem = _find_existing_element_flexible(original_data, base_structural, self.log, ambiguous_callback)
                            if target_elem:
                                target_id = target_elem['item_id']
                                ch['_resolved_item_id'] = target_id
                                ch['_paragraph_num'] = para_num
                                ch['_paragraph_parent_id'] = target_id
                                self.log(f"  Найден родитель для абзаца {para_num}: {base_structural} (ID {target_id})", 'info')
                            else:
                                self.log(f"⚠️ Не найден родительский элемент для абзаца: {base_structural}", 'warning')
                                manual_target, manual_struct, new_desc, new_type = self.resolve_change_manually(ch, original_data, self.stop_event)
                                if self.stop_event.is_set():
                                    return {}
                                if manual_target is not None:
                                    ch['_resolved_item_id'] = manual_target
                                    ch['_resolved_valid_from'] = valid_from
                                    target_id = manual_target
                                    if manual_struct:
                                        ch['structural_element'] = manual_struct
                                    if new_desc is not None:
                                        ch['description'] = new_desc
                                    if new_type is not None:
                                        ch['type'] = new_type
                                    self.log(f"  → Зафиксирован resolved_item_id={manual_target} для {ch.get('structural_element')}. Точечная правка абзаца отключена.", 'result')
                                else:
                                    if tracker:
                                        change_id = tracker.register_change(ch)
                                        tracker.mark_user_cancelled(change_id, "Пользователь отменил выбор адреса")
                                    self.log(f"  -> Изменение абзаца '{structural}' будет пропущено", 'warning')
                                    continue
                        else:
                            self.log(f"  Не удалось распознать номер абзаца в '{structural}'", 'warning')
                            continue
                    else:
                        if structural_lower.startswith('наименование '):
                            element_path = structural[len('наименование '):].strip()
                            target_elem_named = _find_existing_element_flexible(original_data, element_path, self.log, ambiguous_callback)
                            if target_elem_named:
                                ch['_resolved_item_id'] = target_elem_named['item_id']
                                self.log(f"  Найден элемент для наименования '{element_path}': ID {target_elem_named['item_id']}", 'info')
                            else:
                                self.log(f"⚠️ Не найден элемент для наименования '{element_path}', открываем ручное сопоставление...", 'warning')
                                manual_target, manual_struct, new_desc, new_type = self.resolve_change_manually(ch, original_data, self.stop_event)
                                if self.stop_event.is_set():
                                    return {}
                                if manual_target is not None:
                                    ch['_resolved_item_id'] = manual_target
                                    if manual_struct:
                                        ch['structural_element'] = manual_struct
                                    if new_desc is not None:
                                        ch['description'] = new_desc
                                    if new_type is not None:
                                        ch['type'] = new_type
                                    self.log(f"  → Зафиксирован resolved_item_id={manual_target} для наименования '{element_path}'", 'result')
                                else:
                                    if tracker:
                                        change_id = tracker.register_change(ch)
                                        tracker.mark_user_cancelled(change_id, "Пользователь отменил выбор адреса")
                                    self.log(f"  -> Изменение наименования '{element_path}' будет пропущено", 'warning')
                                    continue
                            ch['_resolved_valid_from'] = valid_from
                            changes_with_target.append(ch)
                            continue
                        try:
                            if ch.get('type') == 'add':
                                resolved_parent, deferred_tokens = _resolve_add_parent_and_deferred(
                                    original_data, structural, ch.get('new', ''), self.log, ambiguous_callback
                                )
                                if resolved_parent is not None:
                                    target_id = resolved_parent['item_id']
                                    ch['_resolved_item_id'] = target_id
                                    if deferred_tokens:
                                        ch['_deferred_create_path'] = deferred_tokens
                                        self.log(
                                            f"  add: родитель '{structural}' ещё не существует в целевом НПА. "
                                            f"Разрешён предок '{resolved_parent.get('item_type')} {resolved_parent.get('item_number', '')}' "
                                            f"(ID {target_id}), недостающая цепочка будет создана при применении: "
                                            f"{' -> '.join(t[0] + ' ' + str(t[1]) for t in deferred_tokens)}",
                                            'info'
                                        )
                                    else:
                                        self.log(f"  add: найден существующий родитель '{structural}' (ID {target_id})", 'info')
                                    ch['_resolved_valid_from'] = valid_from
                                    changes_with_target.append(ch)
                                    continue
                            target_elem = _find_existing_element_flexible(original_data, structural, self.log, ambiguous_callback)
                            if target_elem:
                                target_id = target_elem['item_id']
                                ch['_resolved_item_id'] = target_id
                            else:
                                self.log(f"⚠️ Не найден ID для элемента: {structural}. Открываем ручное сопоставление...", 'warning')
                                manual_target, manual_struct, new_desc, new_type = self.resolve_change_manually(ch, original_data, self.stop_event)
                                if self.stop_event.is_set():
                                    return {}
                                if manual_target is not None:
                                    ch['_resolved_item_id'] = manual_target
                                    ch['_resolved_valid_from'] = valid_from
                                    target_id = manual_target
                                    if manual_struct:
                                        ch['structural_element'] = manual_struct
                                    if new_desc is not None:
                                        ch['description'] = new_desc
                                    if new_type is not None:
                                        ch['type'] = new_type
                                    self.log(f"  → Зафиксирован resolved_item_id={manual_target} для {ch.get('structural_element')}", 'result')
                                else:
                                    if tracker:
                                        change_id = tracker.register_change(ch)
                                        tracker.mark_user_cancelled(change_id, "Пользователь отменил выбор адреса")
                                    self.log(f"  -> Изменение '{structural}' будет пропущено", 'warning')
                                    continue
                        except Exception as e:
                            self.log(f"Ошибка при поиске элемента: {e}", 'error')
                            continue
                    ch['_resolved_valid_from'] = valid_from
                ch['_resolved_valid_from'] = valid_from
                changes_with_target.append(ch)
            groups_by_target = defaultdict(list)
            for ch in changes_with_target:
                target_id = ch.get('_resolved_item_id')
                if target_id is None and ch.get('structural_element', '').lower().startswith('наименование '):
                    target_id = '__наименование__'
                valid_from = ch['_resolved_valid_from']
                ch_type = ch.get('type', '')
                if ch_type == 'new_redaction' and '_paragraph_num' not in ch:
                    group_key = (target_id, valid_from, 'new_redaction_' + str(uuid.uuid4()))
                else:
                    group_key = (target_id, valid_from)
                groups_by_target[group_key].append(ch)
            final_groups = defaultdict(list)
            for (target_id, valid_from, *_), ch_list in groups_by_target.items():
                if len(ch_list) == 1 and any(kw in str(target_id) for kw in ('new_redaction',)):
                    final_groups[target_id].extend(ch_list)
                    continue
                change_items = [c for c in ch_list if c.get('type') == 'change' and 'абзац' not in c.get('structural_element', '').lower() and '_paragraph_num' not in c]
                other_items = [c for c in ch_list if c not in change_items]
                if change_items:
                    combined_desc = "\n".join(f"Изменение {i+1} :\n{c.get('description','')}" for i,c in enumerate(change_items))
                    rev_numbers = set()
                    for c in change_items:
                        rn = c.get('revision_number')
                        if rn and rn != 'null':
                            if isinstance(rn, list):
                                rev_numbers.update(rn)
                            else:
                                rev_numbers.add(rn)
                    merged_change = {
                        'type': 'change',
                        'structural_element': change_items[0].get('structural_element'),
                        'description': combined_desc,
                        'valid_from': valid_from,
                        '_resolved_item_id': target_id,
                        '_resolved_valid_from': valid_from
                    }
                    if rev_numbers:
                        merged_change['revision_number'] = list(rev_numbers) if len(rev_numbers) > 1 else next(iter(rev_numbers))
                    if '_paragraph_num' in change_items[0]:
                        merged_change['_paragraph_num'] = change_items[0]['_paragraph_num']
                    if '_quoted_html' in change_items[0]:
                        merged_change['_quoted_html'] = change_items[0]['_quoted_html']
                    final_groups[target_id].append(merged_change)

                for ch in other_items:
                    ch_copy = copy.deepcopy(ch)
                    final_groups[target_id].append(ch_copy)

            return final_groups

        def _apply_changes(self, groups_by_target_id, result_data, change_data, law_ref, general_valid_from,
                          target_element, model, extra_options, rebuild_ids, manual_resolver, ambiguous_callback,
                          tracker: ChangeTracker = None):
            SENTINEL_НАИМЕНОВАНИЕ = '__наименование__'
            SENTINEL_ПРЕАМБУЛА = '__преамбула__'
            success_count = 0
            fail_count = 0
            add_count = 0
            error_occurred = False

            def _handle_needs_user_address(change, change_id, source_item_id):
                self.log(f"⚠️ Требуется ручной выбор адреса для: {change.get('structural_element')} (тип: {change.get('type')})", 'warning')
                manual_target, manual_struct, new_desc, new_type = self.resolve_change_manually(change, result_data, self.stop_event)
                if self.stop_event.is_set():
                    return None
                if manual_target is not None:
                    change['_resolved_item_id'] = manual_target
                    if manual_struct:
                        change['structural_element'] = manual_struct
                    if new_desc is not None:
                        change['description'] = new_desc
                    if new_type is not None:
                        change['type'] = new_type
                    self.log(f"  → Зафиксирован resolved_item_id={manual_target} для {change.get('structural_element')}", 'result')
                    return apply_change_tracked(
                        change=change,
                        change_id=change_id,
                        tracker=tracker,
                        data=result_data,
                        change_data=change_data,
                        law_ref=law_ref,
                        general_valid_from=general_valid_from,
                        log_callback=self.log,
                        source_item_id=source_item_id,
                        model=model,
                        prompt4=self.prompt_4,
                        rebuild_ids=rebuild_ids,
                        doc_type='law',
                        extra_options=extra_options,
                        stop_event=self.stop_event,
                        manual_resolver=manual_resolver,
                        source_context_root=target_element,
                        ambiguous_callback=ambiguous_callback,
                        prompt_answer_callback=self._collect_prompt_answer,
                    )
                else:
                    if tracker:
                        tracker.mark_user_cancelled(change_id, "Пользователь отменил выбор адреса")
                    self.log(f"  -> Пользователь отменил выбор адреса для {change.get('structural_element')}", 'warning')
                    return None

            def get_depth(key):
                if isinstance(key, str):
                    return key.count('_')
                elif isinstance(key, tuple) and key:
                    return key[0].count('_') if isinstance(key[0], str) else 0
                return 0

            sorted_target_ids = sorted(groups_by_target_id.keys(), key=get_depth, reverse=True)

            for target_id in sorted_target_ids:
                changes = groups_by_target_id[target_id]
                if self.stop_event.is_set():
                    self.log("Обработка прервана пользователем", 'warning')
                    error_occurred = True
                    break
                if target_id is None:
                    for ch in changes:
                        self.log(f"Применение добавления в корень документа: {ch.get('structural_element')} (тип: {ch.get('type')})", 'info')
                        change_id = tracker.register_change(ch) if tracker else None
                        ok = apply_change_tracked(
                            change=ch,
                            change_id=change_id,
                            tracker=tracker,
                            data=result_data,
                            change_data=change_data,
                            law_ref=law_ref,
                            general_valid_from=general_valid_from,
                            log_callback=self.log,
                            source_item_id=target_element.get('item_id') if target_element else None,
                            model=model,
                            prompt4=self.prompt_4,
                            rebuild_ids=rebuild_ids,
                            doc_type='law',
                            extra_options=extra_options,
                            stop_event=self.stop_event,
                            manual_resolver=manual_resolver,
                            source_context_root=target_element,
                            ambiguous_callback=ambiguous_callback,
                            prompt_answer_callback=self._collect_prompt_answer,
                        ) if tracker else apply_change(
                            change=ch,
                            data=result_data,
                            change_data=change_data,
                            law_ref=law_ref,
                            general_valid_from=general_valid_from,
                            log_callback=self.log,
                            source_item_id=target_element.get('item_id') if target_element else None,
                            model=model,
                            prompt4=self.prompt_4,
                            rebuild_ids=rebuild_ids,
                            doc_type='law',
                            extra_options=extra_options,
                            stop_event=self.stop_event,
                            manual_resolver=manual_resolver,
                            source_context_root=target_element,
                            ambiguous_callback=ambiguous_callback
                        )
                        if ok and ok.get('status') == 'NEEDS_USER_ADDRESS':
                            resolved_ok = _handle_needs_user_address(ch, change_id, target_element.get('item_id') if target_element else None)
                            if resolved_ok and resolved_ok.get('status') in ('APPLIED', 'PREPARED'):
                                success_count += 1
                                self.log(f"✅ Добавление в корень применено после ручного выбора", 'result')
                            else:
                                fail_count += 1
                                self.log(f"❌ Не удалось применить добавление в корень после ручного выбора", 'error')
                                error_occurred = True
                                break
                        elif ok:
                            success_count += 1
                            self.log(f"✅ Добавление в корень применено", 'result')
                        else:
                            fail_count += 1
                            self.log(f"❌ Не удалось применить добавление в корень", 'error')
                            error_occurred = True
                            break
                    continue
                if target_id in (SENTINEL_НАИМЕНОВАНИЕ, SENTINEL_ПРЕАМБУЛА):
                    source_id = target_element.get('item_id') if target_element else None
                    for ch in changes:
                        self.log(f"Применение изменения «{ch.get('structural_element')}» (тип: {ch.get('type')})", 'info')
                        change_id = tracker.register_change(ch) if tracker else None
                        ok = apply_change_tracked(
                            change=ch,
                            change_id=change_id,
                            tracker=tracker,
                            data=result_data,
                            change_data=change_data,
                            law_ref=law_ref,
                            general_valid_from=general_valid_from,
                            log_callback=self.log,
                            source_item_id=source_id,
                            model=model,
                            prompt4=self.prompt_4,
                            rebuild_ids=rebuild_ids,
                            doc_type='law',
                            extra_options=extra_options,
                            stop_event=self.stop_event,
                            manual_resolver=manual_resolver,
                            source_context_root=target_element,
                            ambiguous_callback=ambiguous_callback,
                            prompt_answer_callback=self._collect_prompt_answer,
                        ) if tracker else apply_change(
                            change=ch,
                            data=result_data,
                            change_data=change_data,
                            law_ref=law_ref,
                            general_valid_from=general_valid_from,
                            log_callback=self.log,
                            source_item_id=source_id,
                            model=model,
                            prompt4=self.prompt_4,
                            rebuild_ids=rebuild_ids,
                            doc_type='law',
                            extra_options=extra_options,
                            stop_event=self.stop_event,
                            manual_resolver=manual_resolver,
                            source_context_root=target_element,
                            ambiguous_callback=ambiguous_callback
                        )
                        if ok and ok.get('status') == 'NEEDS_USER_ADDRESS':
                            resolved_ok = _handle_needs_user_address(ch, change_id, source_id)
                            if resolved_ok and resolved_ok.get('status') in ('APPLIED', 'PREPARED'):
                                success_count += 1
                                self.log(f"✅ Изменение применено после ручного выбора", 'result')
                            else:
                                fail_count += 1
                                self.log(f"❌ Не удалось применить изменение после ручного выбора", 'error')
                                error_occurred = True
                                break
                        elif ok:
                            success_count += 1
                            self.log(f"✅ Изменение применено", 'result')
                        else:
                            fail_count += 1
                            self.log(f"❌ Не удалось применить изменение", 'error')
                            error_occurred = True
                            break
                    continue
                element, parent = find_element_and_parent(result_data, target_id)
                if not element:
                    self.log(f"❌ Элемент с ID {target_id} не найден", 'error')
                    fail_count += 1
                    error_occurred = True
                    continue
                if parent and parent.get('item_type') == 'structured_table':
                    element['_is_table_child'] = True
                valid_from_str = changes[0].get('valid_from', general_valid_from.strftime('%d.%m.%Y'))
                try:
                    valid_from_date = datetime.strptime(valid_from_str, '%d.%m.%Y').date()
                except ValueError:
                    valid_from_date = general_valid_from
                self.log(f"Применение группы из {len(changes)} правок к {target_id} ({element.get('item_type')} {element.get('item_number', '')})", 'info')
                to_update = [
                    c for c in changes
                    if c.get('type') != 'add'
                    or 'абзац' in c.get('structural_element', '').lower()
                    or '_paragraph_num' in c
                ]
                to_add = [
                    c for c in changes
                    if c.get('type') == 'add'
                    and 'абзац' not in c.get('structural_element', '').lower()
                    and '_paragraph_num' not in c
                ]
                head_changes = [c for c in to_update
                                if c.get('structural_element', '').lower().startswith('наименование ')]
                body_changes = [c for c in to_update
                                if not c.get('structural_element', '').lower().startswith('наименование ')]
                target_failed = False
                for h_ch in head_changes:
                    self.log(f"Применение изменения наименования «{h_ch.get('structural_element')}» (тип: {h_ch.get('type')})", 'info')
                    change_id = tracker.register_change(h_ch) if tracker else None
                    ok_h = apply_change_tracked(
                        change=h_ch,
                        change_id=change_id,
                        tracker=tracker,
                        data=result_data,
                        change_data=change_data,
                        law_ref=law_ref,
                        general_valid_from=general_valid_from,
                        log_callback=self.log,
                        source_item_id=target_element.get('item_id') if target_element else None,
                        model=model,
                        prompt4=self.prompt_4,
                        rebuild_ids=rebuild_ids,
                        doc_type='law',
                        extra_options=extra_options,
                        stop_event=self.stop_event,
                        manual_resolver=manual_resolver,
                        source_context_root=target_element,
                        ambiguous_callback=ambiguous_callback,
                        prompt_answer_callback=self._collect_prompt_answer,
                    ) if tracker else apply_change(
                        change=h_ch,
                        data=result_data,
                        change_data=change_data,
                        law_ref=law_ref,
                        general_valid_from=general_valid_from,
                        log_callback=self.log,
                        source_item_id=target_element.get('item_id') if target_element else None,
                        model=model,
                        prompt4=self.prompt_4,
                        rebuild_ids=rebuild_ids,
                        doc_type='law',
                        extra_options=extra_options,
                        stop_event=self.stop_event,
                        manual_resolver=manual_resolver,
                        source_context_root=target_element,
                        ambiguous_callback=ambiguous_callback
                    )
                    if ok_h:
                        success_count += 1
                        self.log(f"✅ Наименование обновлено", 'result')
                    elif ok_h and ok_h.get('status') == 'NEEDS_USER_ADDRESS':
                        resolved_ok = _handle_needs_user_address(h_ch, change_id, target_element.get('item_id') if target_element else None)
                        if resolved_ok and resolved_ok.get('status') in ('APPLIED', 'PREPARED'):
                            success_count += 1
                            self.log(f"✅ Наименование обновлено после ручного выбора", 'result')
                        else:
                            fail_count += 1
                            self.log(f"❌ Не удалось обновить наименование после ручного выбора", 'error')
                            error_occurred = True
                            target_failed = True
                            break
                    else:
                        fail_count += 1
                        self.log(f"❌ Не удалось обновить наименование", 'error')
                        error_occurred = True
                        target_failed = True
                        break
                if target_failed:
                    continue
                delete_element_changes = [
                    c for c in body_changes
                    if c.get('type') == 'delete' and 'абзац' not in c.get('structural_element', '').lower() and '_paragraph_num' not in c
                ]
                other_body_changes = [
                    c for c in body_changes
                    if not (c.get('type') == 'delete' and 'абзац' not in c.get('structural_element', '').lower() and '_paragraph_num' not in c)
                ]
                for del_ch in delete_element_changes:
                    self.log(f"Применение удаления элемента {del_ch.get('structural_element')} (тип delete)", 'info')
                    change_id = tracker.register_change(del_ch) if tracker else None
                    ok = apply_change_tracked(
                        change=del_ch,
                        change_id=change_id,
                        tracker=tracker,
                        data=result_data,
                        change_data=change_data,
                        law_ref=law_ref,
                        general_valid_from=general_valid_from,
                        log_callback=self.log,
                        source_item_id=target_element.get('item_id') if target_element else None,
                        model=model,
                        prompt4=self.prompt_4,
                        rebuild_ids=rebuild_ids,
                        doc_type='law',
                        extra_options=extra_options,
                        stop_event=self.stop_event,
                        manual_resolver=manual_resolver,
                        source_context_root=target_element,
                        ambiguous_callback=ambiguous_callback,
                        prompt_answer_callback=self._collect_prompt_answer,
                    ) if tracker else apply_change(
                        change=del_ch,
                        data=result_data,
                        change_data=change_data,
                        law_ref=law_ref,
                        general_valid_from=general_valid_from,
                        log_callback=self.log,
                        source_item_id=target_element.get('item_id') if target_element else None,
                        model=model,
                        prompt4=self.prompt_4,
                        rebuild_ids=rebuild_ids,
                        doc_type='law',
                        extra_options=extra_options,
                        stop_event=self.stop_event,
                        manual_resolver=manual_resolver,
                        source_context_root=target_element,
                        ambiguous_callback=ambiguous_callback
                    )
                    if ok and ok.get('status') == 'NEEDS_USER_ADDRESS':
                        resolved_ok = _handle_needs_user_address(del_ch, change_id, target_element.get('item_id') if target_element else None)
                        if resolved_ok and resolved_ok.get('status') in ('APPLIED', 'PREPARED'):
                            success_count += 1
                            self.log(f"✅ Удаление элемента применено после ручного выбора", 'result')
                        else:
                            fail_count += 1
                            self.log(f"❌ Не удалось применить удаление после ручного выбора", 'error')
                            error_occurred = True
                            target_failed = True
                            break
                    elif ok:
                        success_count += 1
                        self.log(f"✅ Удаление элемента применено", 'result')
                    else:
                        fail_count += 1
                        self.log(f"❌ Не удалось применить удаление", 'error')
                        error_occurred = True
                        target_failed = True
                        break
                if target_failed:
                    continue
                if other_body_changes:
                    change_ids = [tracker.register_change(c) for c in other_body_changes] if tracker else None
                    success = apply_grouped_changes_tracked(
                        element=element,
                        changes=other_body_changes,
                        change_ids=change_ids,
                        tracker=tracker,
                        valid_from=valid_from_date,
                        data=result_data,
                        change_data=change_data,
                        model=model,
                        prompt4=self.prompt_4,
                        log_callback=self.log,
                        rebuild_ids=rebuild_ids,
                        extra_options=extra_options,
                        source_item_id=target_element.get('item_id') if target_element else None,
                        stop_event=self.stop_event,
                        manual_resolver=manual_resolver,
                        source_context_root=target_element,
                        backend=self.backend.get(),
                        kilo_gateway_url=self.kilo_gateway_url.get(),
                        api_key=self.kilo_gateway_api_key.get(),
                        prompt_answer_callback=self._collect_prompt_answer,
                    ) if tracker else apply_grouped_changes(
                        element=element,
                        changes=other_body_changes,
                        valid_from=valid_from_date,
                        data=result_data,
                        change_data=change_data,
                        model=model,
                        prompt4=self.prompt_4,
                        log_callback=self.log,
                        rebuild_ids=rebuild_ids,
                        extra_options=extra_options,
                        source_item_id=target_element.get('item_id') if target_element else None,
                        stop_event=self.stop_event,
                        manual_resolver=manual_resolver,
                        source_context_root=target_element,
                        change_ids=change_ids,
                        backend=self.backend.get(),
                        kilo_gateway_url=self.kilo_gateway_url.get(),
                        api_key=self.kilo_gateway_api_key.get(),
                    )
                    if not success:
                        needs_address = any(r.get('status') == 'NEEDS_USER_ADDRESS' for r in success) if isinstance(success, list) else False
                        if needs_address and tracker and change_ids:
                            resolved = True
                            for i, r in enumerate(success):
                                if r.get('status') == 'NEEDS_USER_ADDRESS':
                                    ch = other_body_changes[i]
                                    cid = change_ids[i]
                                    resolved_ok = _handle_needs_user_address(ch, cid, target_element.get('item_id') if target_element else None)
                                    if not resolved_ok or resolved_ok.get('status') not in ('APPLIED', 'PREPARED'):
                                        resolved = False
                                        break
                            if resolved:
                                error_occurred = False
                            else:
                                error_occurred = True
                                fail_count += 1
                        else:
                            error_occurred = True
                            fail_count += 1
                        continue
                for add_ch in to_add:
                    change_id = tracker.register_change(add_ch) if tracker else None
                    if '_quoted_html' not in add_ch:
                        self.log(f"  add: отсутствует _quoted_html, пытаемся получить заново", 'warning')
                        source_html = None
                        rev_num = add_ch.get('revision_number')
                        if not rev_num or rev_num == 'null':
                            amending_items = change_data.get('npa_items_revision', []) if change_data else []
                            for it in amending_items:
                                if it.get('item_type') == 'article':
                                    txt = extract_text_from_element(it).lower()
                                    if 'внести в статью' in txt or 'изменить статью' in txt or 'дополнить' in txt:
                                        source_html = get_full_element_html(it, include_header=False)
                                        if source_html:
                                            self.log(f"  add: revision_number=null, берём HTML изменяющей статьи (ID {it.get('item_id')})", 'info')
                                        break
                        if not source_html:
                            source_html = _fetch_source_html_for_change(add_ch, change_data, target_element, self.log)
                        if source_html:
                            extracted = _extract_quoted_html(source_html, self.log)
                            add_ch['_quoted_html'] = extracted if extracted else source_html
                        else:
                            self.log(f"  Не удалось получить HTML для add, изменение пропущено", 'error')
                            fail_count += 1
                            error_occurred = True
                            if tracker:
                                tracker.mark_failed(change_id, reason="Failed to fetch source HTML")
                            break
                    if 'new' in add_ch:
                        ru_type, child_num = parse_add_new_field(add_ch['new'])
                        if not ru_type or not child_num:
                            self.log(f"  Не удалось разобрать new: {add_ch.get('new')}", 'error')
                            fail_count += 1
                            error_occurred = True
                            if tracker:
                                tracker.mark_failed(change_id, reason=f"Failed to parse new field: {add_ch.get('new')}")
                            break
                        sys_type = None
                        for eng, rus in TYPE_TO_RUSSIAN.items():
                            if rus.lower() == ru_type:
                                sys_type = eng
                                break
                        if not sys_type:
                            self.log(f"  Неизвестный тип: {ru_type}", 'error')
                            fail_count += 1
                            error_occurred = True
                            if tracker:
                                tracker.mark_failed(change_id, reason=f"Unknown type: {ru_type}")
                            break
                        src_id = target_element.get('item_id') if target_element else None
                        rev_num = add_ch.get('revision_number')
                        if rev_num and rev_num != 'null' and (not isinstance(rev_num, list) or rev_num):
                            resolved = find_item_by_revision_number(change_data, rev_num, context_root=target_element)
                            if resolved:
                                src_id = narrow_source_id_to_subpoint(
                                    resolved, add_ch.get('structural_element', ''), change_data, self.log
                                )
                        if not src_id:
                            self.log(f"  Не удалось определить modified_by_id для добавляемого элемента", 'error')
                            fail_count += 1
                            error_occurred = True
                            if tracker:
                                tracker.mark_failed(change_id, reason="Cannot determine modified_by_id")
                            break

                        source_html = add_ch['_quoted_html']
                        range_str = add_ch.get('description', '').strip()

                        normalized_source = source_html

                        structural_html = extract_structural_block(
                            normalized_source,
                            sys_type,
                            child_num,
                            self.log
                        )
                        if structural_html:
                            cleaned_html = structural_html
                            self.log(f"  add: используется полный структурный блок для {sys_type} {child_num}", 'info')
                        else:
                            cleaned_html = extract_html_for_added_element(normalized_source, range_str, child_num, self.log)
                            if not cleaned_html and range_str:
                                self.log(f"  Не удалось извлечь абзацы по диапазону '{range_str}' для add", 'error')
                                fail_count += 1
                                error_occurred = True
                                if tracker:
                                    tracker.mark_failed(change_id, reason=f"Failed to extract paragraphs by range: {range_str}")
                                break
                            if not cleaned_html:
                                cleaned_html = normalized_source

                        if not validate_quote_extraction(cleaned_html, sys_type, child_num, self.log):
                            self.log(f"  add: повреждённый HTML для {sys_type} {child_num} (несбалансированные кавычки), изменение не применяется", 'error')
                            fail_count += 1
                            error_occurred = True
                            if tracker:
                                tracker.mark_failed(change_id, reason="Unbalanced quotes in HTML")
                            break

                        add_parent = element
                        if add_ch.get('_deferred_create_path'):
                            try:
                                add_parent = _ensure_path(
                                    result_data, add_ch['_deferred_create_path'],
                                    valid_from_date, src_id, self.log,
                                    context_parent=element, ambiguous_callback=ambiguous_callback
                                )
                                self.log(
                                    f"  add: создана недостающая цепочка родителя под '{element.get('item_type')} {element.get('item_number', '')}': "
                                    f"{' -> '.join(t[0] + ' ' + str(t[1]) for t in add_ch['_deferred_create_path'])}",
                                    'result'
                                )
                            except Exception as e:
                                self.log(f"  Ошибка при создании недостающей цепочки родителя для add: {e}", 'error')
                                fail_count += 1
                                error_occurred = True
                                if tracker:
                                    tracker.mark_failed(change_id, reason=f"Error creating parent path: {e}")
                                break

                        if tracker:
                            tracker.mark_applying(change_id)
                        new_id = _add_new_element(add_parent, sys_type, child_num, cleaned_html,
                                                src_id, valid_from_date, result_data, self.log, rebuild_ids, ambiguous_callback,
                                                change_id=add_ch.get('change_id'), skip_chapter_section_heuristic=True)
                        if new_id is None:
                            fail_count += 1
                            error_occurred = True
                            if tracker:
                                tracker.mark_failed(change_id, reason="_add_new_element returned None")
                            break
                        add_ch['_created_item_id'] = new_id
                        success_count += 1
                        add_count += 1
                        if tracker:
                            tracker.mark_prepared(change_id, target_item_id=new_id)
                        self.log(f"  Добавлен новый элемент {sys_type} {child_num}", 'result')
                    else:
                        structural = add_ch.get('structural_element', '')
                        tokens = parse_structural_tokens(structural)
                        if not tokens:
                            self.log(f"  Не удалось распарсить добавляемый элемент: {structural}", 'error')
                            fail_count += 1
                            error_occurred = True
                            if tracker:
                                tracker.mark_failed(change_id, reason=f"Failed to parse structural tokens: {structural}")
                            break
                        sys_type, child_num = tokens[-1]
                        if not sys_type or child_num is None:
                            self.log(f"  Не удалось определить тип/номер добавляемого элемента: {structural}", 'error')
                            fail_count += 1
                            error_occurred = True
                            if tracker:
                                tracker.mark_failed(change_id, reason=f"Failed to determine type/number: {structural}")
                            break
                        src_id = target_element.get('item_id') if target_element else None
                        rev_num = add_ch.get('revision_number')
                        if rev_num and rev_num != 'null' and (not isinstance(rev_num, list) or rev_num):
                            resolved = find_item_by_revision_number(change_data, rev_num, context_root=target_element)
                            if resolved:
                                src_id = narrow_source_id_to_subpoint(resolved, structural, change_data, self.log)
                        if not src_id:
                            self.log(f"  Не удалось определить modified_by_id для добавляемого элемента", 'error')
                            fail_count += 1
                            error_occurred = True
                            if tracker:
                                tracker.mark_failed(change_id, reason="Cannot determine modified_by_id")
                            break

                        source_html = add_ch['_quoted_html']
                        range_str = add_ch.get('description', '').strip()

                        normalized_source = source_html

                        structural_html = extract_structural_block(
                            normalized_source,
                            sys_type,
                            child_num,
                            self.log
                        )
                        if structural_html:
                            cleaned_html = structural_html
                            self.log(f"  add: используется полный структурный блок для {sys_type} {child_num}", 'info')
                        else:
                            cleaned_html = extract_html_for_added_element(normalized_source, range_str, child_num, self.log)
                            if not cleaned_html and range_str:
                                self.log(f"  Не удалось извлечь абзацы по диапазону '{range_str}' для add", 'error')
                                fail_count += 1
                                error_occurred = True
                                if tracker:
                                    tracker.mark_failed(change_id, reason=f"Failed to extract paragraphs by range: {range_str}")
                                break
                            if not cleaned_html:
                                cleaned_html = normalized_source

                        if not validate_quote_extraction(cleaned_html, sys_type, child_num, self.log):
                            self.log(f"  add: повреждённый HTML для {sys_type} {child_num} (несбалансированные кавычки), изменение не применяется", 'error')
                            fail_count += 1
                            error_occurred = True
                            if tracker:
                                tracker.mark_failed(change_id, reason="Unbalanced quotes in HTML")
                            break

                        add_parent = element
                        if add_ch.get('_deferred_create_path'):
                            try:
                                add_parent = _ensure_path(
                                    result_data, add_ch['_deferred_create_path'],
                                    valid_from_date, src_id, self.log,
                                    context_parent=element, ambiguous_callback=ambiguous_callback
                                )
                                self.log(
                                    f"  add: создана недостающая цепочка родителя под '{element.get('item_type')} {element.get('item_number', '')}': "
                                    f"{' -> '.join(t[0] + ' ' + str(t[1]) for t in add_ch['_deferred_create_path'])}",
                                    'result'
                                )
                            except Exception as e:
                                self.log(f"  Ошибка при создании недостающей цепочки родителя для add: {e}", 'error')
                                fail_count += 1
                                error_occurred = True
                                if tracker:
                                    tracker.mark_failed(change_id, reason=f"Error creating parent path: {e}")
                                break

                        if tracker:
                            tracker.mark_applying(change_id)
                        new_id = _add_new_element(add_parent, sys_type, child_num, cleaned_html,
                                                src_id, valid_from_date, result_data, self.log, rebuild_ids, ambiguous_callback,
                                                change_id=add_ch.get('change_id'), skip_chapter_section_heuristic=True)
                        if new_id is None:
                            fail_count += 1
                            error_occurred = True
                            if tracker:
                                tracker.mark_failed(change_id, reason="_add_new_element returned None")
                            break
                        add_ch['_created_item_id'] = new_id
                        success_count += 1
                        add_count += 1
                        if tracker:
                            tracker.mark_prepared(change_id, target_item_id=new_id)
                        self.log(f"  Добавлен новый элемент {sys_type} {child_num}", 'result')
            return success_count, fail_count, add_count, error_occurred

        def _save_failed_run(self, result_data, orig_file, change_data, tracker):
            try:
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
                from npazs.revision.file_ops import clean_number_for_filename, get_date_for_filename
                orig_clean_num = clean_number_for_filename(orig_npa_number)
                orig_doc_type = result_data.get('doc_type', result_data.get('npa_type', 'law'))
                orig_date = get_date_for_filename(result_data, orig_doc_type)

                change_npa_number = change_data.get('npa_number', '')
                change_doc_type = change_data.get('doc_type', change_data.get('npa_type', 'law'))
                change_clean_num = clean_number_for_filename(change_npa_number)
                change_date = get_date_for_filename(change_data, change_doc_type)

                filename = f"FAILED_{orig_clean_num}_{orig_date}_izm_{change_clean_num}_{change_date}.json"
                out_dir = os.path.dirname(orig_file)
                out_path = os.path.join(out_dir, filename)

                report = tracker.get_run_status_report()
                result_data['_failed_run_report'] = report

                with open(out_path, 'w', encoding='utf-8') as f:
                    json.dump(result_data, f, ensure_ascii=False, indent=2)
                self.log(f"FAILED результат сохранён в:\n{out_path}", 'error')
            except Exception as e:
                self.log(f"Ошибка сохранения FAILED результата: {e}", 'error')

        def _apply_special_valid_from_overrides(self, article_changes, target_special_dates,
                                                amending_special_dates, amending_special_dates_by_id,
                                                change_data, target_element):
            for ch in article_changes:
                struct_lower = ch.get('structural_element', '').lower().strip()
                rev_num = ch.get('revision_number')
            
                for t_struct, t_date in target_special_dates.items():
                    if struct_lower.startswith(t_struct):
                        ch['valid_from'] = t_date
                        self.log(f"Переопределена дата вступления для '{struct_lower}' на {t_date}", 'info')
                        break
            
                if isinstance(rev_num, str):
                    resolved_id = find_item_by_revision_number(change_data, rev_num, context_root=target_element)
                    if resolved_id and resolved_id in amending_special_dates_by_id:
                        ch['valid_from'] = amending_special_dates_by_id[resolved_id]
                        self.log(f"[VALID_FROM] modified_by_id={resolved_id} special_date={amending_special_dates_by_id[resolved_id]} selected_date={amending_special_dates_by_id[resolved_id]}", 'info')
                    else:
                        norm_rev = rev_num.lower().strip().replace(" -> ", "->")
                        if norm_rev in amending_special_dates:
                            ch['valid_from'] = amending_special_dates[norm_rev]
                            self.log(f"Переопределена дата для изменения (источник: {rev_num}) на {amending_special_dates[norm_rev]}", 'info')
                        else:
                            for am_path, am_date in amending_special_dates.items():
                                if am_path in norm_rev or norm_rev in am_path:
                                    ch['valid_from'] = am_date
                                    self.log(f"Переопределена дата для изменения (источник: {rev_num}) на {am_date} (частичное совпадение)", 'info')
                                    break

        def run_all(self):
            def manual_resolver(rev, stop_event=None, change_info=""):
                return self.resolve_revision_manually(rev, change_data, self.log, stop_event, change_info)

            def ambiguous_callback(item_type, item_number, candidates, structural_path, revision_number=None):
                return self.resolve_ambiguous_element(item_type, item_number, candidates, structural_path, revision_number)

            self.manual_mapping_cache.clear()
            self._init_prompt_answers()
            orig_file = self.original_path.get().strip()
            change_file = self.change_path.get().strip()
            law_ref = self.law_ref.get().strip()
            original_law_number = self.original_law_ref.get().strip()
            model = self.ollama_model.get().strip()
            extra_options_str = self.extra_options.get().strip()
        
            if not orig_file or not change_file or not law_ref or not original_law_number or not model:
                messagebox.showerror("Ошибка", "Заполните все поля (дата вступления будет взята из JSON изменений).")
                return
            
            extra_options = {}
            if extra_options_str:
                try:
                    extra_options = json.loads(extra_options_str)
                    self.log(f"Дополнительные параметры: {extra_options}", 'info')
                except json.JSONDecodeError as e:
                    self.log(f"Ошибка парсинга дополнительных параметров: {e}. Используются стандартные параметры.", 'error')
                    extra_options = {}
                
            try:
                with open(orig_file, 'r', encoding='utf-8') as f:
                    original_data = json.load(f)
            except Exception as e:
                messagebox.showerror("Ошибка чтения оригинального JSON", str(e))
                return
            
            try:
                with open(change_file, 'r', encoding='utf-8') as f:
                    change_data = json.load(f)
            except Exception as e:
                messagebox.showerror("Ошибка чтения JSON изменений", str(e))
                return
            
            valid_from_str = change_data.get('valid_from', '').strip()
            if not valid_from_str:
                valid_from_str = change_data.get('date_signed', '').strip()
                if not valid_from_str:
                    valid_from_str = change_data.get('date_pub', '').strip()
                    if not valid_from_str:
                        messagebox.showerror("Ошибка", "В JSON изменений не найдена дата вступления в силу (нужны поля valid_from, date_signed или date_pub в формате ДД.ММ.ГГГГ).")
                        return
                else:
                    self.log("Внимание: в JSON изменений отсутствует поле valid_from, используется date_signed как дата вступления в силу.", 'warning')
                
            try:
                general_valid_from = datetime.strptime(valid_from_str, '%d.%m.%Y').date()
            except ValueError:
                messagebox.showerror("Ошибка", f"Неверный формат даты вступления в силу: {valid_from_str} (ожидается ДД.ММ.ГГГГ)")
                return
            
            pub_date_str = change_data.get('date_pub', '')
            if not pub_date_str:
                pub_date_str = change_data.get('date_signed', '')
            
            if pub_date_str:
                self.log(f"Дата публикации изменяющего закона: {pub_date_str}", 'info')
            else:
                self.log("Дата публикации изменяющего закона не указана в JSON", 'info')
            
            self.log(f"Дата вступления в силу изменяющего закона: {general_valid_from.strftime('%d.%m.%Y')}", 'result')
            self.run_btn.config(state='disabled')
            self.cancel_btn.config(state='normal')
            self.log_text.delete(1.0, tk.END)
            self.stop_event.clear()
        
            def process():
                error_occurred = False
                try:
                    self.log("=== Поиск элемента с номером исходного закона ===", 'info')
                    doc_type_change = change_data.get('doc_type', change_data.get('npa_type', 'law'))
                    if doc_type_change == 'regulation':
                        doc_type_change = 'regulation'
                    else:
                        doc_type_change = 'law'
                    
                    original_law_number = original_data.get('npa_number', '')
                    if not original_law_number:
                        original_law_number = self.original_law_ref.get().strip()
                    
                    base_law_date_pub = original_data.get('date_reg', '') or original_data.get('date_signed', '') or original_data.get('date_pub', '')
                    if base_law_date_pub:
                        self.log(f"Дата публикации базового закона: {base_law_date_pub}", 'info')
                    
                    self.log(f"Поиск номера '{original_law_number}' в изменяющем документе", 'info')
                    target_element = _find_target_element(change_data, original_data, self.log, doc_type_change, ambiguous_callback)
                
                    if not target_element:
                        self.log("⚠️ Элемент не найден программно. Предлагаем выбрать вручную...", 'warning')
                        target_element = self.resolve_target_element_manually(change_data, self.stop_event)
                        if target_element:
                            self.log(f"✅ Пользователь выбрал элемент ID {target_element.get('item_id')}, тип {target_element.get('item_type')} {target_element.get('item_number')}", 'result')
                        else:
                            self.log("⚠️ Ручной выбор пропущен. Запрос к ИИ...", 'warning')
                            target_element = find_target_element_via_ai(change_data, original_data, self.log, model, extra_options, self.stop_event, doc_type_change, backend=self.backend.get(), kilo_gateway_url=self.kilo_gateway_url.get(), api_key=self.kilo_gateway_api_key.get())
                            if not target_element:
                                self.log("❌ Элемент с номером исходного закона не найден ни вручную, ни через ИИ. Дальнейшая обработка невозможна.", 'error')
                                return
                            self.log("✅ Элемент найден через ИИ.", 'result')
                        
                    items = change_data.get('npa_items_revision', [])
                    if not items:
                        self.log("❌ В изменяющем законе нет структурных элементов.", 'error')
                        return
                    
                    final_text = ""
                    for item in items:
                        final_text += extract_text_from_element(item) + "\n"
                    
                    self.log("=== ЭТАП 1: Анализ заключительных положений на утрату силы ===", 'info')
                    deletion_changes = self._stage1_deletion_analysis(final_text, model, extra_options, pub_date_str, original_law_number)
                    if self.stop_event.is_set():
                        self.log("Процесс прерван пользователем.", 'warning')
                        return

                    if deletion_changes:
                        self.log("Обнаружена утрата силы. Применяем изменения и завершаем обработку...", 'result')
                        result_data = copy.deepcopy(original_data)
                        rebuild_ids = []
                    
                        law_invalidated = False
                        mapped_changes = []
                        for change in deletion_changes:
                            if change.get('structural_element_for_delete') == 'law':
                                valid_from = change.get('valid_from')
                                if valid_from:
                                    try:
                                        valid_date = datetime.strptime(valid_from, '%d.%m.%Y').date()
                                    except ValueError:
                                        valid_date = general_valid_from
                                else:
                                    valid_date = general_valid_from
                                result_data['not_valid'] = valid_date.strftime('%d.%m.%Y')
                                result_data['not_valid_npa'] = str(change_data.get('npa_id', ''))
                                if change.get('item_id_for_note'):
                                    result_data['not_valid_note'] = change.get('item_id_for_note')
                                else:
                                    result_data.pop('not_valid_note', None)
                                self.log(f"Закон полностью помечен как утративший силу с {result_data['not_valid']}.", 'result')
                                law_invalidated = True
                            else:
                                element_to_delete = change.get('structural_element_for_delete')
                                if element_to_delete:
                                    mapped_change = {
                                        'type': 'delete',
                                        'structural_element': element_to_delete,
                                        'valid_from': change.get('valid_from') or general_valid_from.strftime('%d.%m.%Y'),
                                        'description': f'Признать утратившим силу: {element_to_delete}',
                                        'revision_number': change.get('structural_element')
                                    }
                                    mapped_changes.append(mapped_change)
                                    self.log(f"Подготовлена утрата силы для: {element_to_delete}", 'info')

                        if mapped_changes:
                            groups_by_target_id = self._group_changes(mapped_changes, result_data, target_element, general_valid_from, model, extra_options, change_data, ambiguous_callback, tracker=None)
                            self._apply_changes(groups_by_target_id, result_data, change_data, law_ref, general_valid_from, target_element, model, extra_options, rebuild_ids, manual_resolver, ambiguous_callback)
                            self._stage5_rebuild(result_data, rebuild_ids, general_valid_from, change_data, tracker=tracker)

                        if change_data.get('npa_id'):
                            rev_info = {
                                'revision_id': change_data['npa_id'],
                                'revision_number': change_data.get('npa_number', ''),
                            }
                            doc_type_change_for_rev = change_data.get('doc_type', change_data.get('npa_type', 'law'))
                            if doc_type_change_for_rev == 'law':
                                rev_info['revision_date_reg'] = change_data.get('date_signed', '')
                            rev_info['revision_date_valid'] = general_valid_from.strftime('%d.%m.%Y')
                            rev_info['revision_url'] = change_data.get('npa_url', '')
                            if 'revision_info' not in result_data:
                                result_data['revision_info'] = []
                            if not any(r.get('revision_id') == rev_info['revision_id'] for r in result_data['revision_info']):
                                result_data['revision_info'].append(rev_info)
                                self.log(f"Добавлена информация об изменяющем законе в revision_info", 'result')

                        remove_empty_children(result_data)
                        self._save_result(result_data, orig_file, change_data)
                        self._save_prompt_answers(os.path.dirname(orig_file), change_data, result_data)
                        self.root.after(0, lambda: messagebox.showinfo("Готово", "Обработка завершена. Применена утрата силы, остальные этапы пропущены."))
                        return

                    self.log("=== ЭТАП 2: Анализ заключительных положений на даты вступления и правоотношения ===", 'info')
                    stage2_records = self._stage2_dates_analysis(final_text, target_element, model, extra_options, pub_date_str, original_law_number, change_data, base_law_date_pub)
                    if self.stop_event.is_set():
                        self.log("Процесс прерван пользователем.", 'warning')
                        return

                    amending_special_dates = {}
                    target_special_dates = {}
                    pending_retroactive_rules = []

                    if stage2_records:
                        self.log(f"Найдено записей на этапе 2: {len(stage2_records)}", 'info')
                        for rec in stage2_records:
                            action_type = rec.get("action_type")
                            applies_to = rec.get("applies_to")
                            structural_element = rec.get("structural_element", "").strip()
                        
                            if action_type == "retroactive_note":
                                note_text = rec.get("note_text", "")
                                general_from_str = general_valid_from.strftime('%d.%m.%Y') if general_valid_from else ""
                                note_valid_from = rec.get("note_valid_from") or general_from_str or None
                            
                                if applies_to == "amending_law":
                                    pending_retroactive_rules.append(dict(rec))
                                    self.log(f"Detected retroactive rule: applies_to={applies_to} scope={rec.get('scope')} date={note_valid_from}", 'info')
                                    self.log(
                                        f"[RETRO DEBUG] applies_to={applies_to} scope={rec.get('scope')} "
                                        f"structural_element={structural_element!r} note_valid_from={note_valid_from}",
                                        'info')
                                    continue

                                if not note_text:
                                    continue

                                if structural_element.lower() == "law":
                                    source_item_id = None
                                    if change_data:
                                        try:
                                            source_elem = _find_existing_element_flexible(change_data, structural_element, self.log, ambiguous_callback)
                                            if source_elem:
                                                source_item_id = source_elem.get("item_id")
                                        except Exception:
                                            pass
                                    _add_npa_note(original_data, note_text, note_valid_from, self.log, source_item_id=source_item_id)
                                else:
                                    # Defer target_law retroactive_note for specific
                                    # structural elements. Resolution happens after
                                    # Stage 4/5 via resolve_rule_target(), which can
                                    # find both pre-existing elements and elements
                                    # created by add changes in the same amending NPA.
                                    pending_retroactive_rules.append(dict(rec))
                                    self.log(
                                        f"⏳ Отложено правило retroactive_note для '{structural_element}'",
                                        'info')
                                    
                            elif action_type == "special_valid_from":
                                date = rec.get("date")
                                if not date:
                                    continue
                                if applies_to == "amending_law":
                                    norm_path = structural_element.lower().replace(" -> ", "->")
                                    amending_special_dates[norm_path] = date
                                    self.log(f"Особая дата для изменяющего закона [{structural_element}]: {date}", 'info')
                                elif applies_to == "target_law":
                                    target_special_dates[structural_element.lower()] = date
                                    self.log(f"Особая дата для целевого закона [{structural_element}]: {date}", 'info')

                    amending_special_dates_by_id = {}
                    for norm_path, date in amending_special_dates.items():
                        for rec in stage2_records:
                            if rec.get("action_type") != "special_valid_from" or rec.get("applies_to") != "amending_law":
                                continue
                            structural_element = rec.get("structural_element", "").strip()
                            if structural_element.lower().replace(" -> ", "->") == norm_path:
                                elem = _find_existing_element_flexible(change_data, structural_element, self.log)
                                if elem:
                                    amending_special_dates_by_id[elem['item_id']] = date
                                    self.log(f"[VALID_FROM] amending_special_dates_by_id[{elem['item_id']}] = {date}", 'info')
                                break

                    if pending_retroactive_rules:
                        self.log(f"[RETRO DEBUG] detected rules: {len(pending_retroactive_rules)} "
                                 f"(amending_law, будут применены после этапа 4/5)", 'info')

                    self.log("=== ЭТАП 3: Анализ изменений из текста элемента ===", 'info')
                    article_changes = self._stage3_changes_extraction(
                        target_element, model, extra_options, change_data,
                        manual_resolver=manual_resolver, stop_event=self.stop_event
                    )
                    if self.stop_event.is_set():
                        self.log("Процесс прерван пользователем.", 'warning')
                        return

                    self.log(f"[RETRO DEBUG] Stage 3 changes: {len(article_changes)}", 'info')

                    self._apply_special_valid_from_overrides(
                        article_changes, target_special_dates,
                        amending_special_dates, amending_special_dates_by_id,
                        change_data, target_element
                    )

                    self.log("=== Группировка изменений по элементу и дате вступления в силу ===", 'info')
                    all_changes_raw = article_changes
                    remaining_changes = []
                    for change in all_changes_raw:
                        if change.get('type') == 'delete_law':
                            valid_from = change.get('valid_from')
                            if valid_from:
                                try:
                                    valid_date = datetime.strptime(valid_from, '%d.%m.%Y').date()
                                except ValueError:
                                    valid_date = general_valid_from
                            else:
                                valid_date = general_valid_from
                            original_data['not_valid'] = valid_date.strftime('%d.%m.%Y')
                            original_data['not_valid_npa'] = str(change_data.get('npa_id', ''))
                            if change.get('item_id_for_note'):
                                original_data['not_valid_note'] = change.get('item_id_for_note')
                            else:
                                original_data.pop('not_valid_note', None)
                            self.log(
                                f"Закон помечен как утратившим силу с {original_data['not_valid']}, "
                                f"НПА: {original_data['not_valid_npa']}, "
                                f"примечание: {original_data.get('not_valid_note', '')}",
                                'result'
                            )
                        else:
                            remaining_changes.append(change)

                    tracker = ChangeTracker(log_callback=self.log)
                    self.log(f"CHANGE TRACKER: инициализирован для отслеживания изменений", 'info')

                    groups_by_target_id = self._group_changes(remaining_changes, original_data, target_element, general_valid_from, model, extra_options, change_data, ambiguous_callback, tracker=tracker)
                    self.log(f"Сформировано групп изменений: {len(groups_by_target_id)}", 'info')

                    for _gid, _ch_list in groups_by_target_id.items():
                        for _ch in _ch_list:
                            if self.stop_event.is_set():
                                break
                            self.log(
                                f"[RETRO DEBUG] revision={_ch.get('revision_number')} "
                                f"structural_element={_ch.get('structural_element')!r} "
                                f"resolved_target_item_id={_ch.get('_resolved_item_id')}",
                                'debug')
                    if pending_retroactive_rules:
                        self.log(f"[RETRO DEBUG] применение amending-law правил к "
                                 f"{len(groups_by_target_id)} группам изменений после этапа 4/5", 'info')

                    self.log("=== ЭТАП 4: Применение изменений к JSON ===", 'info')
                    result_data = copy.deepcopy(original_data)
                    rebuild_ids = []

                    success_count, fail_count, add_count, error_occurred = self._apply_changes(
                        groups_by_target_id, result_data, change_data, law_ref, general_valid_from,
                        target_element, model, extra_options, rebuild_ids, manual_resolver, ambiguous_callback,
                        tracker=tracker
                    )
                    self.log(f"Результат применения: успешно {success_count}, ошибок {fail_count}, новых элементов добавлено {add_count}", 'result')

                    self.log("=== ЭТАП 5: Перестройка элементов ===", 'info')
                    self._stage5_rebuild(result_data, rebuild_ids, general_valid_from, change_data, tracker=tracker)

                    self._fix_invalid_revisions(result_data, change_data)

                    if pending_retroactive_rules:
                        applied_retro = apply_retroactive_rules_to_groups(
                            pending_retroactive_rules, groups_by_target_id, result_data,
                            general_valid_from, log_callback=self.log, change_data=change_data
                        )
                        self.log(f"[RETRO DEBUG] retroactive note applied to {applied_retro} target items (final JSON)", 'info')

                    self.log("=== ЭТАП 6: Верификация изменений ===", 'info')
                    all_verified = run_verification_stage(tracker, result_data, change_data, self.log)

                    run_status = tracker.compute_run_status()
                    tracker.print_summary()

                    if run_status == "FAILED":
                        self.log(f"❌ RUN STATUS: FAILED — не все изменения применены/проверены", 'error')
                        self._save_failed_run(result_data, orig_file, change_data, tracker)
                        self._save_prompt_answers(os.path.dirname(orig_file), change_data, result_data)
                        self.root.after(0, lambda: messagebox.showerror(
                            "Ошибка обработки",
                            f"Обработка завершена с ошибками.\n"
                            f"Успешно: {success_count} из {tracker.expected_count}\n"
                            f"Ошибок: {fail_count}\n"
                            f"Сохранён FAILED результат для анализа."
                        ))
                        error_occurred = True
                        return

                    self.log(f"✅ RUN STATUS: SUCCESS — все {tracker.expected_count} изменений применены и проверены", 'result')

                    if change_data.get('npa_id'):
                        rev_info = {
                            'revision_id': change_data['npa_id'],
                            'revision_number': change_data.get('npa_number', ''),
                        }
                        doc_type_change_for_rev = change_data.get('doc_type', change_data.get('npa_type', 'law'))
                        if doc_type_change_for_rev == 'law':
                            rev_info['revision_date_reg'] = change_data.get('date_signed', '')
                        rev_info['revision_date_valid'] = general_valid_from.strftime('%d.%m.%Y')
                        rev_info['revision_url'] = change_data.get('npa_url', '')
                        if 'revision_info' not in result_data:
                            result_data['revision_info'] = []
                        if not any(r.get('revision_id') == rev_info['revision_id'] for r in result_data['revision_info']):
                            result_data['revision_info'].append(rev_info)
                            self.log(f"Добавлена информация об изменяющем законе в revision_info", 'result')

                    remove_empty_children(result_data)
                    self._save_result(result_data, orig_file, change_data)
                    self.root.after(0, lambda: messagebox.showinfo(
                        "Готово",
                        f"Обработка завершена успешно.\n"
                        f"Применено: {success_count} из {tracker.expected_count}"
                    ))
                except Exception as e:
                    self.log(f"Критическая ошибка в процессе: {e}", 'error')
                    traceback.print_exc()
                finally:
                    try:
                        log_content = self.log_text.get('1.0', tk.END)
                        save_last_run_log(log_content)
                    except Exception:
                        pass
                    self._export_debug_run(orig_file, change_file)
                    self._save_prompt_answers(os.path.dirname(orig_file), change_data, result_data if 'result_data' in dir() else None)
                    self.message_queue.put({
                        'type': 'done',
                        'success': not error_occurred
                    })
                    self.root.after(0, lambda: self.run_btn.config(state='normal'))
                    self.root.after(0, lambda: self.cancel_btn.config(state='disabled'))
                
            self.thread = threading.Thread(target=process, daemon=True)
            self.thread.start()