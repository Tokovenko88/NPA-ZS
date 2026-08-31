"""Применение изменений к документу."""

import os
import sys
import re
import json
import time
import copy
import uuid
from datetime import datetime, timedelta, date
from bs4 import BeautifulSoup

from npazs.revision.revision_utils import *
from npazs.revision.element_finder import _resolve_modified_by_ids, find_item_by_revision_number, _extract_paragraph_order
from npazs.revision.ui_utils import (
    _add_new_element,
    _close_revision,
    _make_new_revision,
    _fetch_source_html_for_change,
    _ensure_path,
    _find_existing_element_flexible,
)
from npazs.revision.html_utils import _correct_table_highlights
from npazs.constants import TYPE_TO_RUSSIAN


def _assign_revision_id(revision):
    if revision is not None and 'revision_id' not in revision:
        revision['revision_id'] = str(uuid.uuid4())
    return revision.get('revision_id') if revision is not None else None


def _make_success_result(change_id, revision=None, target_item_id=None):
    rev_id = _assign_revision_id(revision)
    return {
        "status": "APPLIED",
        "change_id": change_id,
        "revision_id": rev_id,
    }


def _make_needs_user_address_result(change_id, error="Address resolution required"):
    return {
        "status": "NEEDS_USER_ADDRESS",
        "change_id": change_id,
        "revision_id": None,
        "error": error,
    }


def _make_failed_result(change_id, error="Unknown application error"):
    return {
        "status": "FAILED",
        "change_id": change_id,
        "revision_id": None,
        "error": error,
    }


def _make_prepared_result(change_id):
    return {
        "status": "PREPARED",
        "change_id": change_id,
        "revision_id": None,
    }

def _get_change_id(change):
    cid = change.get("change_id")
    if not cid:
        cid = str(uuid.uuid4())[:12]
        change["change_id"] = cid
    return cid


def apply_grouped_changes(element, changes, valid_from, change_data, data, model, prompt4,
                          log_callback, rebuild_ids, extra_options, source_item_id=None,
                          stop_event=None, manual_resolver=None, source_context_root=None,
                          change_ids=None, backend="ollama", kilo_gateway_url=None, api_key=None,
                          prompt_answer_callback=None):
    from npazs.revision.revision_builder import _merge_highlights_with_paragraph_prefix
    if stop_event and stop_event.is_set():
        if log_callback:
            log_callback("  apply_grouped_changes: остановка", 'warning')
            return [_make_failed_result(cid, "operation failed") for cid in (change_ids or [""])]
    if log_callback:
        log_callback(f"Применение группы из {len(changes)} изменений к элементу {element.get('item_id')}", 'info')
    if any(c.get('type') == 'new_redaction' for c in changes):
        if not any('абзац' in c.get('structural_element', '').lower() for c in changes):
            ch = changes[0]
            rev_number = ch.get('revision_number')
            if '_quoted_html' in ch:
                source_html = ch['_quoted_html']
                if log_callback:
                    log_callback(f"  Используем ранее извлечённый HTML из _quoted_html", 'info')
            else:
                source_html = _fetch_source_html_for_change(ch, change_data, source_context_root, log_callback)
                if not source_html:
                    if log_callback:
                        log_callback(f"  Не удалось получить HTML из элемента-источника по revision_number {rev_number}", 'error')
                    return [_make_failed_result(cid, "operation failed") for cid in (change_ids or [""])]
            range_str = ch.get('description', '').strip()
            final_html = extract_paragraphs_by_indices(source_html, range_str, log_callback)
            if not final_html and range_str:
                if log_callback:
                    log_callback(f"  Не удалось извлечь абзацы по диапазону '{range_str}' из HTML", 'error')
                return [_make_failed_result(cid, "operation failed") for cid in (change_ids or [""])]
            if not final_html:
                final_html = source_html
            cleaned_html = clean_description_html(final_html)
            if log_callback:
                preview = cleaned_html[:30000] + ('...' if len(cleaned_html) > 30000 else '')
                log_callback(f"  Для new_redaction извлечён HTML: {preview}", 'source')
            modified_by_id_str = _resolve_modified_by_ids(
                rev_number, change_data, None, source_item_id, log_callback,
                structural_element=ch.get('structural_element', ''),
                manual_resolver=manual_resolver, stop_event=stop_event,
                context_root=source_context_root
            )
            if modified_by_id_str is None:
                modified_by_id_str = str(change_data.get('npa_id', 'unknown'))
            is_table_child = element.get('_is_table_child', False)
            cleaned_html = clean_and_unwrap_html(cleaned_html, is_table_child=is_table_child)
            if element.get('item_type') in ('part', 'point', 'subpoint'):
                cleaned_html = remove_leading_number_from_html(
                    cleaned_html,
                    str(element.get('item_number', ''))
                )
            element['_pending_new_redaction_html'] = cleaned_html
            element['_pending_modified_by_id'] = modified_by_id_str
            element['_pending_valid_from'] = valid_from.strftime('%d.%m.%Y')
            element['_pending_mod_type'] = 'new_redaction'
            element['_pending_highlights'] = None
            if change_ids:
                if len(change_ids) == 1:
                    element['_pending_change_id'] = change_ids[0]
                else:
                    element['_pending_changes'] = [
                        {
                            "change_id": cid,
                            "mod_type": 'new_redaction',
                            "new_html": cleaned_html,
                            "modified_by_id": modified_by_id_str,
                            "valid_from": valid_from.strftime('%d.%m.%Y')
                        }
                        for cid in change_ids
                    ]
            if element['item_id'] not in rebuild_ids:
                rebuild_ids.append(element['item_id'])
            if log_callback:
                log_callback("  new_redaction структурного элемента -> pending", 'result')
            return [_make_prepared_result(cid) for cid in (change_ids or [""] * len(changes))]
    paragraph_ops = []
    text_changes = []
    for ch in changes:
        ch_type = ch.get('type', '')
        if '_paragraph_num' in ch:
            paragraph_ops.append(ch)
            continue
        structural = ch.get('structural_element', '').lower()
        if 'абзац' in structural and ch_type in ('new_redaction', 'add', 'delete', 'change'):
            paragraph_ops.append(ch)
        else:
            text_changes.append(ch)
    revisions = element.setdefault('revisions', [])
    active_rev = None
    for rev in reversed(revisions):
        if rev.get('valid_to') is None:
            active_rev = rev
            break
    if not active_rev and revisions:
        active_rev = revisions[-1]
    if not active_rev:
        if log_callback:
            log_callback("  Нет активной ревизии у элемента", 'error')
        return [_make_failed_result(cid, "no active revision") for cid in (change_ids or [""] * len(changes))]
    ai_paragraphs = []
    combined_highlights = None
    if text_changes:
        current_html = get_full_element_html(element, include_header=False)
        if not current_html.strip():
            if log_callback:
                log_callback(f"  Не удалось получить HTML-содержимое элемента {element.get('item_id')}. Изменения типа 'change' невозможны.", 'error')
            return [_make_failed_result(cid, "operation failed") for cid in (change_ids or [""])]
        for ch in text_changes:
            desc = ch.get('description', '')
            structural = ch.get('structural_element', '')
            para_num = None
            if 'абзац' in structural.lower():
                para_num = _extract_paragraph_order(structural)
            if para_num is not None:
                desc = f"абзац {para_num}: {desc}"
            stage4_prompt = prompt4.replace("{element_html}", current_html).replace("{description}", desc)
            if log_callback:
                log_callback(f"  Отправка запроса к ИИ для изменения: {desc[:80]}...", 'info')
            answer = ask_ollama(stage4_prompt, model, log_callback, extra_options, stop_event, change_info=desc, backend=backend, kilo_gateway_url=kilo_gateway_url, api_key=api_key)
            if prompt_answer_callback:
                prompt_answer_callback(4, stage4_prompt, answer, change_info=desc)
            if not answer:
                if log_callback:
                    log_callback("  Не удалось получить ответ от ИИ", 'error')
                return [_make_failed_result(cid, "operation failed") for cid in (change_ids or [""])]
            answer_html, ai_highlights = parse_ai_response_for_prompt4(answer, desc, log_callback)
            if not answer_html:
                if log_callback:
                    log_callback("  Не удалось извлечь HTML из ответа ИИ", 'error')
                return [_make_failed_result(cid, "operation failed") for cid in (change_ids or [""])]
            answer_html = safe_re_sub(r'(?i)^\s*<target_html>\s*', '', answer_html)
            answer_html = safe_re_sub(r'(?i)\s*</target_html>\s*$', '', answer_html)
            answer_html = safe_re_sub(r'^\s*<p[^>]*>\s*<strong>[^<]*</strong>\s*</p>\s*', '', answer_html, flags=re.DOTALL)
            if element.get('item_type') in ('part', 'point', 'subpoint'):
                answer_html = remove_leading_number_from_html(answer_html, str(element.get('item_number', '')))
            
            if element.get('_is_table_child', False) or element.get('item_type') == 'structured_table':
                old_html_for_diff = get_full_element_html(element, include_header=False)
                corrected = _correct_table_highlights(old_html_for_diff, answer_html, ai_highlights, log_callback)
                if corrected:
                    ai_highlights = corrected

            current_html = answer_html
            if ai_highlights:
                combined_highlights = _merge_highlights_with_paragraph_prefix(combined_highlights, ai_highlights, 1)
        ai_paragraphs = split_html_to_paragraphs(current_html)
        if not ai_paragraphs:
            ai_paragraphs = [current_html] if current_html.strip() else []
        if log_callback:
            log_callback("  Текстовые изменения ИИ применены", 'result')
    else:
        current_html = get_full_element_html(element, include_header=False)
        if not current_html.strip():
            if log_callback:
                log_callback(f"  Не удалось получить HTML-содержимое элемента {element.get('item_id')} для базовой ревизии.", 'error')
            return [_make_failed_result(cid, "operation failed") for cid in (change_ids or [""])]
        current_html = strip_number_from_element_html(current_html, str(element.get('item_number', '')), element.get('item_type', ''))
        ai_paragraphs = split_html_to_paragraphs(current_html)
        if not ai_paragraphs:
            ai_paragraphs = [current_html] if current_html.strip() else []
    pending_paragraph_ops = []
    for op in paragraph_ops:
        structural = op.get('structural_element', '')
        ch_type = op.get('type', '')
        para_num = op.get('_paragraph_num')
        if para_num is None:
            para_num = _extract_paragraph_order(structural)
        if para_num is None:
            if log_callback:
                log_callback(f"  Не удалось извлечь номер абзаца из '{structural}'", 'error')
            continue
        if ch_type == 'delete':
            if 1 <= para_num <= len(ai_paragraphs):
                text_before = ai_paragraphs[para_num - 1]
                del ai_paragraphs[para_num - 1]
                combined_highlights = adjust_highlights_for_paragraph_change(
                    combined_highlights, 'delete', para_num, text_before=text_before
                )
                if log_callback:
                    log_callback(f"  Абзац {para_num} удалён", 'result')
            else:
                if log_callback:
                    log_callback(f"  Абзац {para_num} не найден для удаления", 'warning')
        else:
            pending_paragraph_ops.append({
                'type': ch_type,
                'target_idx': para_num,
                'op': op
            })
    for op in pending_paragraph_ops:
        op_type = op.get('type')
        target_idx = op.get('target_idx')
        original_op = op.get('op')
        if op_type == 'new_redaction':
            if '_quoted_html' in original_op:
                source_html = original_op['_quoted_html']
            else:
                source_html = _fetch_source_html_for_change(original_op, change_data, source_context_root, log_callback)
                if not source_html:
                    if log_callback:
                        log_callback(f"  Не удалось получить HTML для замены абзаца {target_idx} из источника", 'error')
                    return [_make_failed_result(cid, "operation failed") for cid in (change_ids or [""])]
            range_str = original_op.get('description', '').strip()
            new_html = extract_paragraphs_by_indices(source_html, range_str, log_callback)
            if not new_html and range_str:
                if log_callback:
                    log_callback(f"  Не удалось извлечь абзацы по диапазону '{range_str}' для абзаца {target_idx}", 'error')
                return [_make_failed_result(cid, "operation failed") for cid in (change_ids or [""])]
            if not new_html:
                new_html = source_html
            new_html = clean_description_html(new_html)
            if element.get('item_type') in ('part', 'point', 'subpoint'):
                new_html = remove_leading_number_from_html(new_html, str(element.get('item_number', '')))
            if 1 <= target_idx <= len(ai_paragraphs):
                old_html = ai_paragraphs[target_idx - 1]
                ai_paragraphs[target_idx - 1] = new_html
                combined_highlights = adjust_highlights_for_paragraph_change(
                    combined_highlights, 'new_redaction', target_idx,
                    text_before=old_html, text_after=new_html,
                    item_number=element.get('item_number'), item_type=element.get('item_type')
                )
                if log_callback:
                    log_callback(f"  Абзац {target_idx} заменён", 'result')
            else:
                insert_idx = target_idx - 1
                if insert_idx < 0:
                    insert_idx = 0
                if insert_idx > len(ai_paragraphs):
                    insert_idx = len(ai_paragraphs)
                ai_paragraphs.insert(insert_idx, new_html)
                combined_highlights = adjust_highlights_for_paragraph_change(
                    combined_highlights, 'add', insert_idx + 1,
                    text_after=new_html,
                    item_number=element.get('item_number'), item_type=element.get('item_type')
                )
                if log_callback:
                    log_callback(f"  Абзац {target_idx} вставлен", 'result')
        elif op_type == 'change':
            if 1 <= target_idx <= len(ai_paragraphs):
                old_html = ai_paragraphs[target_idx - 1]
                stage4_prompt = prompt4.replace("{element_html}", old_html).replace("{description}", original_op.get('description', ''))
                if log_callback:
                    log_callback(f"  Отправка запроса к ИИ для изменения абзаца {target_idx}...", 'info')
                answer = ask_ollama(stage4_prompt, model, log_callback, extra_options, stop_event, change_info=original_op.get('description', ''), backend=backend, kilo_gateway_url=kilo_gateway_url, api_key=api_key)
                if prompt_answer_callback:
                    prompt_answer_callback(4, stage4_prompt, answer, change_info=original_op.get('description', ''))
                if answer:
                    new_html, ai_highlights = parse_ai_response_for_prompt4(answer, log_callback)
                    if new_html:
                        ai_paragraphs[target_idx - 1] = new_html
                        if ai_highlights:
                            combined_highlights = _merge_highlights_with_paragraph_prefix(combined_highlights, ai_highlights, target_idx)
                        if log_callback:
                            log_callback(f"  Абзац {target_idx} изменён через ИИ", 'result')
                    else:
                        if log_callback:
                            log_callback(f"  Не удалось извлечь HTML для абзаца {target_idx}", 'error')
                else:
                    if log_callback:
                        log_callback(f"  Не удалось получить ответ ИИ для абзаца {target_idx}", 'error')
            else:
                if log_callback:
                    log_callback(f"  Абзац {target_idx} не существует для изменения", 'warning')
        elif op_type == 'add':
            if '_quoted_html' in original_op:
                source_html = original_op['_quoted_html']
            else:
                source_html = _fetch_source_html_for_change(original_op, change_data, source_context_root, log_callback)
                if not source_html:
                    if log_callback:
                        log_callback(f"  Не удалось получить HTML для добавления абзаца {target_idx} из источника", 'error')
                    return [_make_failed_result(cid, "operation failed") for cid in (change_ids or [""])]
            range_str = original_op.get('description', '').strip()
            new_html = extract_paragraphs_by_indices(source_html, range_str, log_callback)
            if not new_html and range_str:
                if log_callback:
                    log_callback(f"  Не удалось извлечь абзацы по диапазону '{range_str}' для добавления абзаца {target_idx}", 'error')
                return [_make_failed_result(cid, "operation failed") for cid in (change_ids or [""])]
            if not new_html:
                new_html = source_html
            new_html = clean_description_html(new_html)
            insert_idx = target_idx - 1
            if insert_idx < 0:
                insert_idx = 0
            if insert_idx > len(ai_paragraphs):
                insert_idx = len(ai_paragraphs)
            ai_paragraphs.insert(insert_idx, new_html)
            combined_highlights = adjust_highlights_for_paragraph_change(
                combined_highlights, 'add', insert_idx + 1,
                text_after=new_html,
                item_number=element.get('item_number'), item_type=element.get('item_type')
            )
            if log_callback:
                log_callback(f"  Абзац {target_idx} добавлен", 'result')
    final_html = '\n'.join(ai_paragraphs)
    final_html = strip_number_from_element_html(final_html, str(element.get('item_number', '')), element.get('item_type'))
    if element.get('_is_table_child', False) and not re.search(r'<table|<tr|<td|<th', final_html, re.IGNORECASE):
        log_callback(
            f"  Результат обработки ИИ для табличного элемента {element.get('item_id')} "
            f"не содержит табличной разметки. Изменение не будет применено.",
            'error'
        )
        return [_make_failed_result(cid, "operation failed") for cid in (change_ids or [""])]
    modified_by_id_str = _resolve_modified_by_ids(
        changes[0].get('revision_number'), change_data, None, source_item_id, log_callback,
        structural_element=changes[0].get('structural_element', ''),
        manual_resolver=manual_resolver, stop_event=stop_event,
        context_root=source_context_root
    )
    if modified_by_id_str is None:
        modified_by_id_str = str(change_data.get('npa_id', 'unknown'))
        if log_callback:
            log_callback(f"  Использован ID изменяющего закона: {modified_by_id_str}", 'info')
    is_table_child = element.get('_is_table_child', False)
    final_html = clean_and_unwrap_html(final_html.strip(), is_table_child=is_table_child)
    is_number_change = False
    change_types = set()
    for ch in changes:
        structural = ch.get('structural_element', '').lower()
        if 'раздел' in structural or 'глава' in structural or 'статья' in structural:
            is_number_change = True
        change_types.add(ch.get('type', ''))
    if 'change' in change_types:
        mod_type = 'change'
    elif 'new_redaction' in change_types:
        mod_type = 'new_redaction'
    else:
        mod_type = 'change'
    if is_number_change and element.get('_is_table_child', False):
        element['_pending_mod_type'] = mod_type
    else:
        element['_pending_mod_type'] = mod_type
        element['_pending_new_redaction_html'] = final_html
        element['_pending_modified_by_id'] = modified_by_id_str
        element['_pending_valid_from'] = valid_from.strftime('%d.%m.%Y')
        element['_pending_highlights'] = combined_highlights
        if change_ids:
            if len(change_ids) == 1:
                element['_pending_change_id'] = change_ids[0]
            else:
                element['_pending_changes'] = [
                    {
                        "change_id": cid,
                        "mod_type": mod_type,
                        "new_html": final_html,
                        "modified_by_id": modified_by_id_str,
                        "valid_from": valid_from.strftime('%d.%m.%Y')
                    }
                    for cid in change_ids
                ]
        if element['item_id'] not in rebuild_ids:
            rebuild_ids.append(element['item_id'])
        if log_callback:
            log_callback("  Группа изменений применена: pending для перестройки", 'result')
        return [_make_prepared_result(cid) for cid in (change_ids or [""] * len(changes))]


def _apply_change_impl(change, data, change_data, law_ref, general_valid_from, log_callback,
                 source_item_id=None, model=None, prompt4=None, rebuild_ids=None,
                 doc_type='law', extra_options=None, stop_event=None, manual_resolver=None,
                 source_context_root=None, ambiguous_callback=None, prompt_answer_callback=None):
    if rebuild_ids is None:
        rebuild_ids = []
    if '_resolved_item_id' in change:
        resolved_target_id = change['_resolved_item_id']
        if resolved_target_id == '__наименование__':
            return _apply_change_to_head(change, data, change_data, general_valid_from, change.get('revision_number'),
                                         None, source_item_id, log_callback, model, prompt4, extra_options, stop_event,
                                         manual_resolver, source_context_root, prompt_answer_callback=prompt_answer_callback)
        elif resolved_target_id == '__преамбула__':
            return _apply_change_to_preamble(change, data, change_data, general_valid_from, change.get('revision_number'),
                                              None, source_item_id, log_callback, model, prompt4, extra_options, stop_event,
                                              manual_resolver, source_context_root, rebuild_ids, prompt_answer_callback=prompt_answer_callback)
        elif resolved_target_id is None:
            structural = change.get('structural_element', '').strip()
            ch_type = change.get('type', '').strip()
            if ch_type == 'add':
                new_spec = change.get('new', '')
                if not new_spec:
                    log_callback(f"  ADD: отсутствует поле new", 'error')
                    return False
                ru_type, child_num = parse_add_new_field(new_spec)
                if not ru_type or not child_num:
                    log_callback(f"  Не удалось разобрать new: {new_spec}", 'error')
                    return False
                sys_type = None
                for eng, rus in TYPE_TO_RUSSIAN.items():
                    if rus.lower() == ru_type:
                        sys_type = eng
                        break
                if not sys_type:
                    log_callback(f"  Неизвестный тип: {ru_type}", 'error')
                    return False
                parent_element = None
                parent_structural = change.get('structural_element', '').strip()
                if parent_structural and parent_structural.lower() != 'нпа':
                    parent_element = _find_existing_element_flexible(data, parent_structural, log_callback, ambiguous_callback)
                    if not parent_element:
                        log_callback(f"  ADD parent not found: {parent_structural}", 'error')
                        return _make_needs_user_address_result(change.get('change_id') or _get_change_id(change), f"ADD parent not found: {parent_structural}")
                if '_quoted_html' in change:
                    source_html = change['_quoted_html']
                else:
                    source_html = _fetch_source_html_for_change(change, change_data, source_context_root, log_callback)
                    if not source_html:
                        log_callback(f"  Не удалось получить HTML для add", 'error')
                        return False
                range_str = change.get('description', '').strip()
                cleaned_html = extract_paragraphs_by_indices(source_html, range_str, log_callback)
                if not cleaned_html and range_str:
                    log_callback(f"  Не удалось извлечь абзацы по диапазону '{range_str}' для add", 'error')
                    return False
                if not cleaned_html:
                    cleaned_html = source_html
                modified_by_id_str = _resolve_modified_by_ids(change.get('revision_number'), change_data, None, source_item_id, log_callback, structural_element=structural, manual_resolver=manual_resolver, stop_event=stop_event, context_root=source_context_root)
                if modified_by_id_str is None:
                    modified_by_id_str = str(change_data.get('npa_id', 'unknown'))
                valid_from_date = general_valid_from
                valid_from_str = change.get('valid_from')
                if valid_from_str:
                    try:
                        valid_from_date = datetime.strptime(valid_from_str, '%d.%m.%Y').date()
                    except:
                        valid_from_date = general_valid_from
                new_id = _add_new_element(parent_element, sys_type, child_num, cleaned_html, modified_by_id_str, valid_from_date, data, log_callback, rebuild_ids, ambiguous_callback, change_id=change.get('change_id'), skip_chapter_section_heuristic=True)
                return new_id is not None
            else:
                log_callback(f"  Не поддерживается изменение типа '{ch_type}' для НПА", 'error')
                return _make_needs_user_address_result(change.get('change_id') or _get_change_id(change), f"Unsupported change type for NPA: {ch_type}")
        else:
            target_element = find_item_by_id(data, resolved_target_id)
            if not target_element:
                log_callback(f"Элемент {resolved_target_id} не найден в данных", 'error')
                return _make_needs_user_address_result(change.get('change_id') or _get_change_id(change), f"Element {resolved_target_id} not found")
            ch_type = change.get('type', '').strip()
            structural = change.get('structural_element', '').strip()
            if ch_type == 'new_redaction' and '_paragraph_num' not in change:
                tokens = parse_structural_tokens(structural)
                if tokens:
                    last_type, last_num = tokens[-1]
                    child = find_child_by_type_and_number(target_element, last_type, last_num, ambiguous_callback)
                    if child:
                        log_callback(f"  Для new_redaction найден дочерний элемент {last_type} {last_num} внутри {target_element.get('item_id')}", 'info')
                        target_element = child
                    else:
                        log_callback(f"  Для new_redaction не найден дочерний элемент {last_type} {last_num} внутри {target_element.get('item_id')}, применяем к родителю", 'warning')
            description = change.get('description', '')
            rev_number = change.get('revision_number', None)
            valid_from_str = change.get('valid_from', None)
            if valid_from_str:
                try:
                    valid_from = datetime.strptime(valid_from_str, '%d.%m.%Y').date()
                except:
                    valid_from = general_valid_from
            else:
                valid_from = general_valid_from
            modified_by_id_str = _resolve_modified_by_ids(rev_number, change_data, None, source_item_id, log_callback, structural_element=structural, manual_resolver=manual_resolver, stop_event=stop_event, context_root=source_context_root)
            if not modified_by_id_str:
                modified_by_id_str = str(change_data.get('npa_id', 'unknown'))
            structural_lower_check = structural.lower()
            if structural_lower_check.startswith('наименование ') or structural_lower_check.endswith(' наименование'):
                source_element_local = find_item_by_id(change_data, source_item_id) if source_item_id else None
                return _apply_change_to_element_head(change, data, change_data, valid_from, rev_number,
                                                    source_element_local, source_item_id, log_callback, model,
                                                    prompt4, extra_options, stop_event, manual_resolver,
                                                    source_context_root, rebuild_ids, prompt_answer_callback=prompt_answer_callback)
            
            return _apply_change_to_element_content(target_element, ch_type, description, valid_from, modified_by_id_str, model, prompt4, extra_options, stop_event, log_callback, rebuild_ids, structural, source_context_root, change_data, data, None, source_item_id, rev_number, manual_resolver, change_id=change.get('change_id'), prompt_answer_callback=prompt_answer_callback)
    structural = change.get('structural_element', '').strip()
    ch_type = change.get('type', '').strip()
    description = change.get('description', '')
    rev_number = change.get('revision_number', None)
    valid_from_str = change.get('valid_from', None)
    if valid_from_str:
        try:
            valid_from = datetime.strptime(valid_from_str, '%d.%m.%Y').date()
        except:
            valid_from = general_valid_from
    else:
        valid_from = general_valid_from
    if not structural or not ch_type:
        log_callback("  Некорректное изменение", 'error')
        return False
    log_callback(f"  Тип: {ch_type} | Элемент: {structural}", 'info')
    source_element = None
    if source_item_id:
        source_element = find_item_by_id(change_data, source_item_id)
    structural_lower = structural.lower()
    if structural_lower.endswith(' префикс'):
        return _apply_change_to_appendix_prefix(change, data, change_data, valid_from, rev_number,
                                                 source_element, source_item_id, log_callback, model,
                                                 prompt4, extra_options, stop_event, manual_resolver,
                                                 source_context_root, rebuild_ids, prompt_answer_callback=prompt_answer_callback)
    if structural_lower == "наименование":
        return _apply_change_to_head(change, data, change_data, valid_from, rev_number, source_element, source_item_id, log_callback, model, prompt4, extra_options, stop_event, manual_resolver, source_context_root, prompt_answer_callback=prompt_answer_callback)
    if structural_lower.endswith(' наименование') and not structural_lower == 'наименование':
        element_part = structural[:-len(' наименование')].strip()
        change_copy = change.copy()
        change_copy['structural_element'] = f"наименование {element_part}"
        return _apply_change_to_element_head(change_copy, data, change_data, valid_from, rev_number, source_element, source_item_id, log_callback, model, prompt4, extra_options, stop_event, manual_resolver, source_context_root, rebuild_ids, prompt_answer_callback=prompt_answer_callback)
    if structural_lower.startswith('наименование '):
        return _apply_change_to_element_head(change, data, change_data, valid_from, rev_number, source_element, source_item_id, log_callback, model, prompt4, extra_options, stop_event, manual_resolver, source_context_root, rebuild_ids, prompt_answer_callback=prompt_answer_callback)
    if structural_lower == "преамбула":
        return _apply_change_to_preamble(change, data, change_data, valid_from, rev_number, source_element, source_item_id, log_callback, model, prompt4, extra_options, stop_event, manual_resolver, source_context_root, rebuild_ids, prompt_answer_callback=prompt_answer_callback)
    if ch_type == 'add':
        new_spec = change.get('new', '')
        if not new_spec:
            log_callback(f"  ADD: отсутствует поле new", 'error')
            return False
        ru_type, child_num = parse_add_new_field(new_spec)
        if not ru_type or not child_num:
            log_callback(f"  Не удалось разобрать new: {new_spec}", 'error')
            return False
        sys_type = None
        for eng, rus in TYPE_TO_RUSSIAN.items():
            if rus.lower() == ru_type:
                sys_type = eng
                break
        if not sys_type:
            log_callback(f"  Неизвестный тип: {ru_type}", 'error')
            return False
        parent_element = None
        parent_structural = change.get('structural_element', '').strip()
        if parent_structural and parent_structural.lower() != 'нпа':
            parent_element = _find_existing_element_flexible(data, parent_structural, log_callback, ambiguous_callback)
            if not parent_element:
                log_callback(f"  ADD parent not found: {parent_structural}", 'error')
                return _make_needs_user_address_result(change.get('change_id') or _get_change_id(change), f"ADD parent not found: {parent_structural}")
        if '_quoted_html' in change:
            source_html = change['_quoted_html']
        else:
            source_html = _fetch_source_html_for_change(change, change_data, source_context_root, log_callback)
            if not source_html:
                log_callback(f"  Не удалось получить HTML для add", 'error')
                return False
        range_str = change.get('description', '').strip()
        cleaned_html = extract_paragraphs_by_indices(source_html, range_str, log_callback)
        if not cleaned_html and range_str:
            log_callback(f"  Не удалось извлечь абзацы по диапазону '{range_str}' для add", 'error')
            return False
        if not cleaned_html:
            cleaned_html = source_html
        modified_by_id_str = _resolve_modified_by_ids(rev_number, change_data, source_element, source_item_id, log_callback, structural_element=structural, manual_resolver=manual_resolver, stop_event=stop_event, context_root=source_context_root)
        if modified_by_id_str is None:
            modified_by_id_str = str(change_data.get('npa_id', 'unknown'))
        valid_from_date = general_valid_from
        valid_from_str = change.get('valid_from')
        if valid_from_str:
            try:
                valid_from_date = datetime.strptime(valid_from_str, '%d.%m.%Y').date()
            except:
                valid_from_date = general_valid_from
        new_id = _add_new_element(parent_element, sys_type, child_num, cleaned_html, modified_by_id_str, valid_from_date, data, log_callback, rebuild_ids, ambiguous_callback, change_id=change.get('change_id'), skip_chapter_section_heuristic=True)
        return new_id is not None
    target_element = _find_existing_element_flexible(data, structural, log_callback, ambiguous_callback)
    if target_element is None:
        log_callback(f"  Не найден или неоднозначен элемент для изменения: {structural}. Изменение пропущено.", 'warning')
        return _make_needs_user_address_result(change.get('change_id') or _get_change_id(change), f"Element not found: {structural}")
    modified_by_id_str = _resolve_modified_by_ids(rev_number, change_data, source_element, source_item_id, log_callback, structural_element=structural, manual_resolver=manual_resolver, stop_event=stop_event, context_root=source_context_root)
    if not modified_by_id_str:
        modified_by_id_str = str(change_data.get('npa_id', 'unknown'))
    return _apply_change_to_element_content(target_element, ch_type, description, valid_from, modified_by_id_str, model, prompt4, extra_options, stop_event, log_callback, rebuild_ids, structural, source_context_root, change_data, data, source_element, source_item_id, rev_number, manual_resolver, change_id=change.get('change_id'), prompt_answer_callback=prompt_answer_callback)


def apply_change(change, data, change_data, law_ref, general_valid_from, log_callback,
                 source_item_id=None, model=None, prompt4=None, rebuild_ids=None,
                 doc_type='law', extra_options=None, stop_event=None, manual_resolver=None,
                 source_context_root=None, ambiguous_callback=None, prompt_answer_callback=None):
    change_id = _get_change_id(change)
    if rebuild_ids is None:
        rebuild_ids = []

    result = _apply_change_impl(
        change, data, change_data, law_ref, general_valid_from, log_callback,
        source_item_id, model, prompt4, rebuild_ids, doc_type, extra_options,
        stop_event, manual_resolver, source_context_root, ambiguous_callback,
        prompt_answer_callback=prompt_answer_callback
    )

    if isinstance(result, dict):
        return result

    if result is False:
        return _make_failed_result(change_id, "operation failed")

    ch_type = change.get('type', '')
    if ch_type == 'delete':
        target_id = change.get('_resolved_item_id')
        if target_id:
            target = find_item_by_id(data, target_id)
            if target:
                revisions = target.get('revisions', [])
                for rev in reversed(revisions):
                    if rev.get('not_valid') and rev.get('revision_id'):
                        return _make_success_result(change_id, revision=rev)
        def find_preamble_item(items):
            for item in items:
                if item.get('item_type') == 'preamble':
                    return item
                if 'item_children' in item:
                    found = find_preamble_item(item['item_children'])
                    if found:
                        return found
            return None
        preamble = find_preamble_item(data.get('npa_items_revision', []))
        if preamble:
            revisions = preamble.get('revisions', [])
            for rev in reversed(revisions):
                if rev.get('not_valid') and rev.get('revision_id'):
                    return _make_success_result(change_id, revision=rev)
        return _make_failed_result(change_id, "revision was not created")

    if _has_pending_fields(data, change):
        return _make_prepared_result(change_id)

    new_rev = _find_new_revision(data, change)
    if new_rev:
        _assign_revision_id(new_rev)
        return _make_success_result(change_id, revision=new_rev)

    return _make_failed_result(change_id, "revision was not created")


def _has_pending_fields(data, change):
    target_id = change.get('_resolved_item_id')
    if target_id:
        target = find_item_by_id(data, target_id)
        if target and (target.get('_pending_new_redaction_html') or target.get('_pending_html')):
            return True
    created_id = change.get('_created_item_id')
    if created_id:
        target = find_item_by_id(data, created_id)
        if target and (target.get('_pending_new_redaction_html') or target.get('_pending_html')):
            return True
    # Also check if any element has pending fields (for add operations)
    def has_pending_recursive(items):
        for item in items:
            if item.get('_pending_new_redaction_html') or item.get('_pending_html'):
                return True
            if has_pending_recursive(item.get('item_children', [])):
                return True
        return False
    if has_pending_recursive(data.get('npa_items_revision', [])):
        return True
    return False


def _find_new_revision(data, change):
    target_id = change.get('_resolved_item_id')
    ch_type = change.get('type', '')

    if target_id:
        target = find_item_by_id(data, target_id)
        if target:
            revisions = target.get('revisions', [])
            for rev in reversed(revisions):
                if rev.get('revision_id') and rev.get('valid_to') is None:
                    if ch_type in ('new_redaction', 'change', 'delete', 'add'):
                        return rev

            head_revisions = target.get('head_revisions', [])
            for rev in reversed(head_revisions):
                if rev.get('revision_id') and rev.get('valid_to') is None:
                    return rev

            if target.get('item_type') == 'appendix':
                prefix_revs = target.get('item_prefix_revisions', [])
                for rev in reversed(prefix_revs):
                    if rev.get('revision_id') and rev.get('valid_to') is None:
                        return rev

    # Check head_revision (top-level document head)
    head_rev = data.get('head_revision', [])
    for rev in reversed(head_rev):
        if rev.get('revision_id') and rev.get('valid_to') is None:
            return rev

    return None



def _apply_change_to_appendix_prefix(change, data, change_data, valid_from, rev_number,
                                      source_element, source_item_id, log_callback, model,
                                      prompt4, extra_options, stop_event, manual_resolver,
                                      source_context_root, rebuild_ids, prompt_answer_callback=None):
    structural = change.get('structural_element', '')
    ch_type = change.get('type', '')
    description = change.get('description', '')
    highlights = change.get('highlights', None)
    app_match = re.search(r'приложение\s+(\d+(?:\.\d+)?)', structural.lower())
    if app_match:
        app_number = app_match.group(1)
        app_element = find_appendix_by_number(data, app_number)
    else:
        app_element = _find_existing_element_flexible(data, 'приложение', log_callback, ambiguous_callback)
    if not app_element:
        log_callback(f"  Приложение для изменения префикса не найдено: {structural}", 'error')
        return False
    if app_element.get('item_type') != 'appendix':
        log_callback(f"  Элемент {app_element.get('item_id')} не является приложением", 'error')
        return False
    prefix_revs = app_element.setdefault('item_prefix_revisions', [])
    active_idx = -1
    for i, rev in enumerate(prefix_revs):
        if rev.get('valid_to') is None:
            active_idx = i
            break
    if active_idx == -1 and prefix_revs:
        active_idx = len(prefix_revs) - 1
    current_prefix = prefix_revs[active_idx].get('prefix_text', '') if active_idx >= 0 else ''
    new_prefix = None
    if ch_type == 'new_redaction':
        if '_quoted_html' in change:
            source_html = change['_quoted_html']
        else:
            source_html = _fetch_source_html_for_change(change, change_data, source_context_root, log_callback)
            if not source_html:
                log_callback(f"  Не удалось получить HTML из элемента-источника", 'error')
                return False
        range_str = change.get('description', '').strip()
        new_prefix = extract_paragraphs_by_indices(source_html, range_str, log_callback)
        if not new_prefix and range_str:
            log_callback(f"  Не удалось извлечь префикс по диапазону '{range_str}'", 'error')
            return False
        if not new_prefix:
            new_prefix = source_html
        if log_callback:
            log_callback(f"  Префикс извлечён из кавычек: '{new_prefix}'", 'source')
    elif ch_type == 'change':
        if not model or not prompt4:
            log_callback("  Для изменения префикса нужны model и prompt4", 'error')
            return False
        wrapped = f"<p>{current_prefix}</p>"
        stage4_prompt = prompt4.replace("{element_html}", wrapped).replace("{description}", description)
        answer = ask_ollama(stage4_prompt, model, log_callback, extra_options, stop_event, change_info=description, backend=backend, kilo_gateway_url=kilo_gateway_url, api_key=api_key)
        if prompt_answer_callback:
            prompt_answer_callback(4, stage4_prompt, answer, change_info=description)
        if answer:
            answer_html, _ = parse_ai_response_for_prompt4(answer, log_callback)
            match = re.search(r'<p>(.*?)</p>', answer_html, re.DOTALL)
            new_prefix = match.group(1).strip() if match else answer_html.strip()
    elif ch_type == 'delete':
        new_prefix = None
    elif ch_type == 'add':
        new_prefix = description.strip() if description else ''
    if new_prefix == current_prefix:
        log_callback(f"  Префикс приложения не изменился: '{current_prefix}'", 'info')
        return True
    valid_to_str = (valid_from - timedelta(days=1)).strftime('%d.%m.%Y')
    if active_idx >= 0:
        prefix_revs[active_idx]['valid_to'] = valid_to_str
    if ch_type == 'add' and not current_prefix:
        mod_type = 'add'
    elif ch_type == 'delete' and current_prefix:
        mod_type = 'delete'
    else:
        mod_type = 'change'
    modified_by_id_str = _resolve_modified_by_ids(
        rev_number, change_data, source_element, source_item_id, log_callback,
        structural_element=structural, manual_resolver=manual_resolver, stop_event=stop_event,
        context_root=source_context_root
    )
    if not modified_by_id_str:
        modified_by_id_str = str(change_data.get('npa_id', 'unknown'))
    new_rev = {
        'prefix_text': new_prefix if new_prefix is not None else '',
        'mod_type': mod_type,
        'modified_by_id': modified_by_id_str,
        'revision_id': str(uuid.uuid4())
    }
    if mod_type == 'add' and new_prefix:
        new_rev['valid_from'] = valid_from.strftime('%d.%m.%Y')
    if highlights is not None and not is_highlights_empty(highlights):
        new_rev['highlights'] = highlights
    prefix_revs.append(new_rev)
    log_callback(f"  Префикс приложения обновлён: '{current_prefix}' -> '{new_prefix}'", 'result')
    return _make_success_result(change.get('change_id') or _get_change_id(change), revision=new_rev)


def _apply_change_to_head(change, data, change_data, valid_from, rev_number,
                          source_element, source_item_id, log_callback, model,
                          prompt4, extra_options, stop_event, manual_resolver,
                          source_context_root, prompt_answer_callback=None):
    ch_type = change.get('type')
    highlights = change.get('highlights', None)
    head_rev = data.get('head_revision', [])
    if not head_rev:
        if log_callback:
            log_callback("  В JSON отсутствует head_revision", 'error')
        return None
    active_idx = -1
    for i, rev in enumerate(head_rev):
        if rev.get('valid_to') in (None, ''):
            active_idx = i
            break
    if active_idx == -1 and head_rev:
        active_idx = len(head_rev) - 1
    active = head_rev[active_idx]
    current_head = active.get('npa_head', '')
    if ch_type == 'change':
        if not model or not prompt4:
            if log_callback:
                log_callback("  Для типа 'change' необходимы model и prompt4", 'error')
            return None
        if log_callback:
            log_callback(f"  Текущий заголовок: {current_head}", 'input')
        wrapped_head = f"<p>{current_head}</p>"
        stage4_prompt = prompt4.replace("{element_html}", wrapped_head).replace("{description}", change.get('description', ''))
        if log_callback:
            log_callback("  Запрос к ИИ для нового заголовка...", 'info')
        answer = ask_ollama(stage4_prompt, model, log_callback, extra_options, stop_event, change_info=change.get('description', ''), backend=backend, kilo_gateway_url=kilo_gateway_url, api_key=api_key)
        if prompt_answer_callback:
            prompt_answer_callback(4, stage4_prompt, answer, change_info=change.get('description', ''))
        if answer is None:
            if log_callback:
                log_callback("  Не удалось получить ответ от ИИ для заголовка", 'error')
            return None
        answer_html, highlights = parse_ai_response_for_prompt4(answer, log_callback)
        if not answer_html:
            if log_callback:
                log_callback("  Не удалось извлечь HTML из ответа ИИ", 'error')
            return None
        match = re.search(r'<p[^>]*>(.*?)</p>', answer_html, re.DOTALL)
        new_head = match.group(1).strip() if match else safe_re_sub(r'<[^>]+>', '', answer_html).strip()
        if not new_head:
            if log_callback:
                log_callback("  Получен пустой заголовок", 'error')
            return None
        if log_callback:
            log_callback(f"  Новый заголовок: {new_head}", 'result')
    elif ch_type == 'new_redaction':
        if '_quoted_html' in change:
            source_html = change['_quoted_html']
        else:
            source_html = _fetch_source_html_for_change(change, change_data, source_context_root, log_callback)
            if not source_html:
                if log_callback:
                    log_callback(f"  Не удалось получить HTML из элемента-источника по revision_number {rev_number}", 'error')
                return None
        range_str = change.get('description', '').strip()
        new_head = extract_paragraphs_by_indices(source_html, range_str, log_callback)
        if not new_head and range_str:
            if log_callback:
                log_callback(f"  Не удалось извлечь заголовок по диапазону '{range_str}'", 'error')
            return None
        if not new_head:
            new_head = source_html
        new_head = safe_re_sub(r'<[^>]+>', ' ', new_head)
        new_head = new_head.replace('&laquo;', '«').replace('&raquo;', '»')
        new_head = new_head.replace('&nbsp;', ' ').replace('&amp;', '&')
        new_head = ' '.join(new_head.split())
        if log_callback:
            log_callback(f"  Заголовок извлечён из кавычек: {new_head}", 'source')
    else:
        if log_callback:
            log_callback(f"  Неизвестный тип для наименования: {ch_type}", 'warning')
        return None
    valid_to_str = (valid_from - timedelta(days=1)).strftime('%d.%m.%Y')
    modified_by_id_str = _resolve_modified_by_ids(
        rev_number, change_data, source_element, source_item_id, log_callback,
        structural_element=change.get('structural_element', ''), manual_resolver=manual_resolver, stop_event=stop_event,
        context_root=source_context_root)
    if modified_by_id_str is None:
        if log_callback:
            log_callback(f"  Не удалось определить modified_by_id для заголовка", 'error')
        return None
    _close_revision(head_rev[active_idx], valid_to_str)
    new_rev = {
        'npa_head': new_head,
        'mod_type': ch_type,
        'modified_by_id': modified_by_id_str,
        'revision_id': str(uuid.uuid4())
    }
    if highlights is not None and not is_highlights_empty(highlights):
        new_rev['highlights'] = highlights
    head_rev.append(new_rev)
    data['head_revision'] = head_rev
    if log_callback:
        log_callback(f"  Заголовок обновлён: {new_head}", 'result')
    return _make_success_result(change.get('change_id') or _get_change_id(change), revision=new_rev)

def _apply_change_to_element_head(change, data, change_data, valid_from, rev_number,
                                   source_element, source_item_id, log_callback, model,
                                   prompt4, extra_options, stop_event, manual_resolver,
                                   source_context_root, rebuild_ids, prompt_answer_callback=None):
    structural = change.get('structural_element', '').strip()
    ch_type = change.get('type', '').strip()
    highlights = change.get('highlights', None)
    element_structural = structural[len('наименование '):].strip()
    resolved_id = change.get('_resolved_item_id')
    if resolved_id:
        target_element = find_item_by_id(data, resolved_id)
        if not target_element:
            log_callback(f"  Элемент с _resolved_item_id {resolved_id} не найден в данных", 'error')
            return False
    else:
        target_element = _find_existing_element_flexible(data, element_structural, log_callback, ambiguous_callback)
    if not target_element:
        log_callback(f"  Не найден элемент для изменения наименования: {element_structural}", 'error')
        return False
    item_type_head = target_element.get('item_type', '')
    if item_type_head not in ('article', 'chapter', 'section', 'appendix'):
        log_callback(f"  Тип '{item_type_head}' не поддерживает поле наименования", 'warning')
        return False
    modified_by_id_str = _resolve_modified_by_ids(
        rev_number, change_data, source_element, source_item_id, log_callback,
        structural_element=structural, manual_resolver=manual_resolver, stop_event=stop_event,
        context_root=source_context_root)
    if modified_by_id_str is None:
        log_callback(f"  Не удалось определить modified_by_id для наименования элемента", 'error')
        return False
    head_revisions = target_element.setdefault('head_revisions', [])
    active_idx = -1
    for i, rev in enumerate(head_revisions):
        if rev.get('valid_to') is None:
            active_idx = i
            break
    if active_idx == -1 and head_revisions:
        active_idx = len(head_revisions) - 1
    valid_to_str = (valid_from - timedelta(days=1)).strftime('%d.%m.%Y')
    new_head = None
    if ch_type == 'new_redaction':
        if '_quoted_html' in change:
            source_html = change['_quoted_html']
        else:
            source_html = _fetch_source_html_for_change(change, change_data, source_context_root, log_callback)
            if not source_html:
                if log_callback:
                    log_callback(f"  Не удалось получить HTML из элемента-источника по revision_number {rev_number}", 'error')
                return False
        range_str = change.get('description', '').strip()
        new_head = extract_paragraphs_by_indices(source_html, range_str, log_callback)
        if not new_head and range_str:
            if log_callback:
                log_callback(f"  Не удалось извлечь заголовок по диапазону '{range_str}'", 'error')
            return False
        if not new_head:
            new_head = source_html
        if log_callback:
            log_callback(f"  Заголовок извлечён из кавычек: {new_head}", 'source')
    elif ch_type == 'change':
        if not model or not prompt4:
            log_callback("  Для типа 'change' необходимы model и prompt4", 'error')
            return False
        current_head = get_current_head(target_element)
        log_callback(f"Текущее наименование: {current_head}", 'input')
        wrapped_head = f"<p>{current_head}</p>"
        stage4_prompt = prompt4.replace("{element_html}", wrapped_head).replace("{description}", change.get('description', ''))
        log_callback("  Запрос к ИИ для изменения наименования...", 'info')
        answer_head = ask_ollama(stage4_prompt, model, log_callback, extra_options, stop_event, change_info=change.get('description', ''), backend=backend, kilo_gateway_url=kilo_gateway_url, api_key=api_key)
        if prompt_answer_callback:
            prompt_answer_callback(4, stage4_prompt, answer_head, change_info=change.get('description', ''))
        if answer_head is None:
            log_callback("  Не удалось получить ответ от ИИ для наименования", 'error')
            return False
        answer_html, highlights = parse_ai_response_for_prompt4(answer_head, log_callback)
        if not answer_html:
            log_callback("  Не удалось извлечь HTML из ответа ИИ", 'error')
            return False
        head_match = re.search(r'<p[^>]*>(.*?)</p>', answer_html, re.DOTALL)
        new_head = head_match.group(1).strip() if head_match else safe_re_sub(r'<[^>]+>', '', answer_html).strip()
        if not new_head:
            log_callback("  Получено пустое наименование", 'error')
            return False
    else:
        log_callback(f"  Неподдерживаемый тип для наименования элемента: {ch_type}", 'warning')
        return False
    item_number = target_element.get('item_number', '')
    new_head = clean_head_text(new_head, item_type_head, str(item_number))
    if log_callback:
        log_callback(f"  Заголовок после очистки: '{new_head}'", 'info')
    if active_idx >= 0:
        head_revisions[active_idx]['valid_to'] = valid_to_str
    new_rev = {
        'head_text': new_head,
        'mod_type': ch_type,
        'modified_by_id': modified_by_id_str,
        'revision_id': str(uuid.uuid4())
    }
    if highlights is not None and not is_highlights_empty(highlights):
        new_rev['highlights'] = highlights
    head_revisions.append(new_rev)
    log_callback(f"  Наименование элемента обновлено: {new_head}", 'result')
    return _make_success_result(change.get('change_id') or _get_change_id(change), revision=new_rev)

def _apply_change_to_preamble(change, data, change_data, valid_from, rev_number,
                               source_element, source_item_id, log_callback, model,
                               prompt4, extra_options, stop_event, manual_resolver,
                               source_context_root, rebuild_ids, prompt_answer_callback=None):
    from npazs.revision.revision_builder import extract_child_refs_from_revision
    ch_type = change.get('type', '').strip()
    description = change.get('description', '')
    highlights = change.get('highlights', None)
    def find_preamble_item(items):
        for item in items:
            if item.get('item_type') == 'preamble':
                return item
            if 'item_children' in item:
                found = find_preamble_item(item['item_children'])
                if found:
                    return found
        return None
    preamble_item = find_preamble_item(data.get('npa_items_revision', []))
    if not preamble_item:
        if log_callback:
            log_callback("  Элемент преамбулы не найден в структуре", 'error')
        return False
    element = preamble_item
    if 'revisions' not in element:
        element['revisions'] = [{'body': []}]
    revisions = element['revisions']
    active_idx = -1
    for i, rev in enumerate(revisions):
        if rev.get('valid_to') in (None, ''):
            active_idx = i
            break
    if active_idx == -1 and revisions:
        active_idx = len(revisions) - 1
    old_rev = revisions[active_idx] if active_idx >= 0 else None
    modified_by_id_str = _resolve_modified_by_ids(
        rev_number, change_data, source_element, source_item_id, log_callback,
        structural_element=change.get('structural_element', ''), manual_resolver=manual_resolver, stop_event=stop_event,
        context_root=source_context_root)
    if modified_by_id_str is None:
        if log_callback:
            log_callback(f"  Не удалось определить modified_by_id для преамбулы", 'error')
        return False
    valid_to_str = (valid_from - timedelta(days=1)).strftime('%d.%m.%Y')
    if ch_type == 'delete':
        if active_idx >= 0:
            revisions[active_idx]['valid_to'] = valid_to_str
            revisions[active_idx]['not_valid'] = modified_by_id_str
            revisions[active_idx].pop('mod_type', None)
            revisions[active_idx].pop('modified_by_id', None)
            if 'revision_id' not in revisions[active_idx]:
                revisions[active_idx]['revision_id'] = str(uuid.uuid4())
        if log_callback:
            log_callback(f"  Преамбула помечена как удалённая", 'result')
        return True
    elif ch_type == 'change':
        if not model or not prompt4:
            if log_callback:
                log_callback("  Для типа 'change' необходимы model и prompt4", 'error')
            return False
        current_html = get_full_element_html(element, include_header=False)
        if log_callback:
            log_callback(f"  Текущий HTML преамбулы (длина {len(current_html)} символов)", 'input')
        stage4_prompt = prompt4.replace("{element_html}", current_html).replace("{description}", description)
        if log_callback:
            log_callback("  Запрос к ИИ для изменения преамбулы...", 'info')
        answer = ask_ollama(stage4_prompt, model, log_callback, extra_options, stop_event, change_info=description, backend=backend, kilo_gateway_url=kilo_gateway_url, api_key=api_key)
        if prompt_answer_callback:
            prompt_answer_callback(4, stage4_prompt, answer, change_info=description)
        if answer is None:
            if log_callback:
                log_callback("  Не удалось получить ответ от ИИ", 'error')
            return False
        answer_html, highlights = parse_ai_response_for_prompt4(answer, log_callback)
        if not answer_html:
            if log_callback:
                log_callback("  Не удалось извлечь HTML из ответа ИИ", 'error')
            return False
        answer_html = safe_re_sub(r'(?i)^\s*<target_html>\s*', '', answer_html)
        answer_html = safe_re_sub(r'(?i)\s*</target_html>\s*$', '', answer_html)
        answer_html = remove_leading_number_from_html(answer_html, element.get('item_number', ''))
        answer_html = safe_re_sub(r'^\s*<p[^>]*>\s*<strong>[^<]*</strong>\s*</p>\s*', '', answer_html, flags=re.DOTALL)
        new_body = build_new_body_preserving_child_refs(old_rev, answer_html)
        if active_idx >= 0:
            revisions[active_idx]['valid_to'] = valid_to_str
        new_revision = _make_new_revision(new_body, mod_type='change', modified_by_id=modified_by_id_str, highlights=highlights)
        revisions.append(new_revision)
        if log_callback:
            log_callback(f"  Получен новый HTML от ИИ для преамбулы", 'result')
        return _make_success_result(change.get('change_id') or _get_change_id(change), revision=new_revision)
    elif ch_type == 'new_redaction':
        if '_quoted_html' in change:
            source_html = change['_quoted_html']
        else:
            source_html = _fetch_source_html_for_change(change, change_data, source_context_root, log_callback)
            if not source_html:
                if log_callback:
                    log_callback(f"  Не удалось получить HTML из элемента-источника по revision_number {rev_number}", 'error')
                return False
        range_str = change.get('description', '').strip()
        final_html = extract_paragraphs_by_indices(source_html, range_str, log_callback)
        if not final_html and range_str:
            if log_callback:
                log_callback(f"  Не удалось извлечь абзацы по диапазону '{range_str}' для преамбулы", 'error')
            return False
        if not final_html:
            final_html = source_html
        if log_callback:
            preview = final_html[:30000] + ('...' if len(final_html) > 30000 else '')
            log_callback(f"  Для преамбулы извлечён HTML из кавычек: {preview}", 'source')
        cleaned_html = remove_leading_number_from_html(final_html, element.get('item_number', ''))
        is_table_child = preamble_item.get('_is_table_child', False)
        cleaned_html = clean_and_unwrap_html(cleaned_html, is_table_child=is_table_child)
        new_body = [{'type': 'paragraph', 'html_text': cleaned_html, 'order': 1}] if cleaned_html else []
        old_child_refs = extract_child_refs_from_revision(old_rev) if old_rev else []
        if old_child_refs:
            for i, ref in enumerate(old_child_refs):
                new_ref = copy.deepcopy(ref)
                new_ref['order'] = len(new_body) + i + 1
                new_body.append(new_ref)
        if active_idx >= 0:
            revisions[active_idx]['valid_to'] = valid_to_str
        new_revision = _make_new_revision(new_body, mod_type='new_redaction', modified_by_id=modified_by_id_str, highlights=highlights)
        revisions.append(new_revision)
        if log_callback:
            log_callback(f"  Преамбула заменена новой редакцией (источник)", 'result')
        return _make_success_result(change.get('change_id') or _get_change_id(change), revision=new_revision)
    else:
        if log_callback:
            log_callback(f"  Неизвестный тип для преамбулы: {ch_type}", 'warning')
        return False

def _apply_change_to_element_content(element, ch_type, description, valid_from,
                                      modified_by_id_str, model, prompt4, extra_options,
                                      stop_event, log_callback, rebuild_ids,
                                      structural, source_context_root, change_data, data,
                                      source_element, source_item_id, rev_number,
                                      manual_resolver=None, change_id=None, prompt_answer_callback=None):
    from npazs.revision.revision_builder import extract_child_refs_from_revision
    if 'revisions' not in element:
        element['revisions'] = [{'body': []}]
    revisions = element['revisions']
    active_idx = -1
    for i, rev in enumerate(revisions):
        if rev.get('valid_to') in (None, ''):
            active_idx = i
            break
    if active_idx == -1 and revisions:
        active_idx = len(revisions) - 1
    old_rev = revisions[active_idx] if active_idx >= 0 else None
    if active_idx >= 0:
        valid_to_str = (valid_from - timedelta(days=1)).strftime('%d.%m.%Y')
    if ch_type == 'delete':
        if modified_by_id_str is None:
            if log_callback:
                log_callback(f"  Не удалось определить modified_by_id для удаления", 'error')
            return False
        if active_idx >= 0:
            revisions[active_idx]['valid_to'] = valid_to_str
            revisions[active_idx]['not_valid'] = modified_by_id_str
            revisions[active_idx].pop('mod_type', None)
            revisions[active_idx].pop('modified_by_id', None)
            if 'revision_id' not in revisions[active_idx]:
                revisions[active_idx]['revision_id'] = str(uuid.uuid4())
        if log_callback:
            log_callback(f"  Элемент '{structural}' помечен как удалённый", 'result')
        def find_parent(data, target_id):
            def recurse(items, parent=None):
                for item in items:
                    if item.get('item_id') == target_id:
                        return parent
                    found = recurse(item.get('item_children', []), item)
                    if found:
                        return found
                return None
            return recurse(data.get('npa_items_revision', []))
        parent = find_parent(data, element.get('item_id'))
        adjust_punctuation_after_deletion(parent, element, log_callback)
        return True
    elif ch_type == 'add':
        if log_callback:
            log_callback("  Добавление структурного элемента обрабатывается в блоке add", 'warning')
        return False
    elif ch_type == 'change':
        if not model or not prompt4:
            if log_callback:
                log_callback("  Для типа 'change' нужны model и prompt4", 'error')
            return False
        if modified_by_id_str is None:
            if log_callback:
                log_callback(f"  Не удалось определить modified_by_id для изменения", 'error')
            return False
        has_children = bool(element.get('item_children'))
        if has_children:
            old_child_refs = extract_child_refs_from_revision(old_rev) if old_rev else []
            current_html = get_full_element_html(element, include_header=False)
            if log_callback:
                log_callback(f"  Текущий HTML элемента (длина {len(current_html)} символов)", 'input')
            if " ; " in description and not description.startswith("1. "):
                parts = [p.strip() for p in description.split(" ; ")]
                formatted_desc = "\n".join(f"{i+1}. {p}" for i, p in enumerate(parts))
                if log_callback:
                    log_callback(f"  Преобразовано описание в нумерованный список", 'info')
                description = formatted_desc
            stage4_prompt = prompt4.replace("{element_html}", current_html).replace("{description}", description)
            if log_callback:
                log_callback("  Запрос к ИИ для изменения элемента (с дочерними)...", 'info')
            answer = ask_ollama(stage4_prompt, model, log_callback, extra_options, stop_event, change_info=description, backend=backend, kilo_gateway_url=kilo_gateway_url, api_key=api_key)
            if prompt_answer_callback:
                prompt_answer_callback(4, stage4_prompt, answer, change_info=description)
            if answer is None:
                if log_callback:
                    log_callback("  Не удалось получить ответ от ИИ", 'error')
                return False
            answer_html, highlights = parse_ai_response_for_prompt4(answer, log_callback)
            if not answer_html:
                if log_callback:
                    log_callback("  Не удалось извлечь HTML из ответа ИИ", 'error')
                return False
            paragraphs = split_html_to_paragraphs(answer_html)
            if not paragraphs:
                paragraphs = [answer_html] if answer_html.strip() else []
            if paragraphs and element.get('item_type') in ('part', 'point', 'subpoint'):
                paragraphs[0] = remove_leading_number_from_html(paragraphs[0], str(element.get('item_number', '')))
            new_body = []
            for idx, para in enumerate(paragraphs, start=1):
                new_body.append({'type': 'paragraph', 'html_text': para, 'order': idx})
            if old_child_refs:
                last_paragraph_idx = -1
                for idx, block in enumerate(new_body):
                    if block.get('type') == 'paragraph':
                        last_paragraph_idx = idx
                insert_pos = last_paragraph_idx + 1 if last_paragraph_idx != -1 else len(new_body)
                for i, ref in enumerate(old_child_refs):
                    new_ref = copy.deepcopy(ref)
                    new_ref['order'] = insert_pos + i + 1
                    new_body.insert(insert_pos + i, new_ref)
                for idx, block in enumerate(new_body, start=1):
                    block['order'] = idx
            if active_idx >= 0:
                revisions[active_idx]['valid_to'] = valid_to_str
            new_rev = _make_new_revision(new_body, mod_type='change', modified_by_id=modified_by_id_str, highlights=highlights)
            new_rev['valid_from'] = valid_from.strftime('%d.%m.%Y')
            revisions.append(new_rev)
            rebuild_ids.append(element['item_id'])
            if log_callback:
                log_callback(f"  Элемент обновлён через ИИ (сохранён HTML для перестройки)", 'result')
            return True
        else:
            is_table_child = element.get('_is_table_child', False)
            if is_table_child:
                current_html = get_full_element_html(element, include_header=False)
                if log_callback:
                    log_callback(f"  Элемент является дочерним для структурированной таблицы, сохраняем HTML как есть", 'info')
                new_html = description
                if not new_html:
                    if '_quoted_html' in change:
                        source_html = change['_quoted_html']
                    else:
                        source_html = _fetch_source_html_for_change(change, change_data, source_context_root, log_callback)
                        if source_html:
                            pass
                    range_str = change.get('description', '').strip()
                    new_html = extract_paragraphs_by_indices(source_html, range_str, log_callback)
                    if not new_html and range_str:
                        if log_callback:
                            log_callback(f"  Не удалось извлечь абзацы по диапазону '{range_str}' для табличного элемента", 'error')
                        return False
                    if not new_html:
                        new_html = source_html
                if new_html:
                    new_html = clean_description_html(new_html)
                    if element.get('item_type') in ('part', 'point', 'subpoint'):
                        new_html = remove_leading_number_from_html(new_html, str(element.get('item_number', '')))
                    is_table_child = element.get('_is_table_child', False)
                    new_html = clean_and_unwrap_html(new_html, is_table_child=is_table_child)
                    new_body = [{'type': 'table_fragment', 'html_text': new_html, 'order': 1}]
                    old_child_refs = extract_child_refs_from_revision(old_rev) if old_rev else []
                    if old_child_refs:
                        for i, ref in enumerate(old_child_refs):
                            new_ref = copy.deepcopy(ref)
                            new_ref['order'] = len(new_body) + i + 1
                            new_body.append(new_ref)
                    if active_idx >= 0:
                        revisions[active_idx]['valid_to'] = valid_to_str
                    new_rev = _make_new_revision(new_body, mod_type='change', modified_by_id=modified_by_id_str, highlights=highlights)
                    revisions.append(new_rev)
                    rebuild_ids.append(element['item_id'])
                    if log_callback:
                        log_callback(f"  Элемент таблицы обновлён (сохранён фрагмент)", 'result')
                    return True
                else:
                    log_callback(f"  Не удалось получить HTML для табличного элемента", 'error')
                    return False
            else:
                current_html = get_full_element_html(element, include_header=False)
                if log_callback:
                    log_callback(f"  Текущий HTML элемента (длина {len(current_html)} символов)", 'input')
                if " ; " in description and not description.startswith("1. "):
                    parts = [p.strip() for p in description.split(" ; ")]
                    formatted_desc = "\n".join(f"{i+1}. {p}" for i, p in enumerate(parts))
                    if log_callback:
                        log_callback(f"  Преобразовано описание в нумерованный список", 'info')
                    description = formatted_desc
                stage4_prompt = prompt4.replace("{element_html}", current_html).replace("{description}", description)
                if log_callback:
                    log_callback("  Запрос к ИИ (промпт 4)...", 'info')
                answer = ask_ollama(stage4_prompt, model, log_callback, extra_options, stop_event, change_info=description, backend=backend, kilo_gateway_url=kilo_gateway_url, api_key=api_key)
                if answer is None:
                    if log_callback:
                        log_callback("  Не удалось получить ответ от ИИ", 'error')
                    return False
                answer_html, highlights = parse_ai_response_for_prompt4(answer, log_callback)
                if not answer_html:
                    if log_callback:
                        log_callback("  Не удалось извлечь HTML из ответа ИИ", 'error')
                    return False
                answer_html = safe_re_sub(r'(?i)^\s*<target_html>\s*', '', answer_html)
                answer_html = safe_re_sub(r'(?i)\s*</target_html>\s*$', '', answer_html)
                answer_html = safe_re_sub(r'^\s*<p[^>]*>\s*<strong>[^<]*</strong>\s*</p>\s*', '', answer_html, flags=re.DOTALL)
                if element.get('item_type') in ('part', 'point', 'subpoint'):
                    answer_html = remove_leading_number_from_html(answer_html, str(element.get('item_number', '')))
                is_table_child = element.get('_is_table_child', False)
                answer_html = clean_and_unwrap_html(answer_html, is_table_child=is_table_child)
                old_child_refs = extract_child_refs_from_revision(old_rev) if old_rev else []
                new_body = build_new_body_preserving_child_refs(old_rev, answer_html)
                if active_idx >= 0:
                    revisions[active_idx]['valid_to'] = valid_to_str
                new_revision = _make_new_revision(new_body, mod_type='change', modified_by_id=modified_by_id_str, highlights=highlights)
                revisions.append(new_revision)
                rebuild_ids.append(element['item_id'])
                if log_callback:
                    log_callback(f"  Получен новый HTML от ИИ (длина {len(answer_html)} символов)", 'result')
                return True
    elif ch_type == 'new_redaction':
        if modified_by_id_str is None:
            if log_callback:
                log_callback(f"  Не удалось определить modified_by_id для замены", 'error')
            return False
        is_table_child = element.get('_is_table_child', False)
        if is_table_child:
            if '_quoted_html' in change:
                source_html = change['_quoted_html']
            else:
                source_html = None
                if rev_number and rev_number != 'null':
                    rev_list = rev_number if isinstance(rev_number, list) else [rev_number]
                    for rn in rev_list:
                        source_id = find_item_by_revision_number(change_data, rn, context_root=source_context_root)
                        if source_id:
                            source_elem = find_item_by_id(change_data, source_id)
                            if source_elem:
                                source_html = get_full_element_html(source_elem, include_header=False)
                                if source_html:
                                    if log_callback:
                                        preview = source_html[:30000] + ('...' if len(source_html) > 30000 else '')
                                        log_callback(f"  HTML для новой редакции взят из элемента-источника (ID {source_id}): {preview}", 'source')
                                    break
                else:
                    if source_context_root:
                        source_html = get_full_element_html(source_context_root, include_header=False)
                        if log_callback:
                            log_callback(f"  revision_number == null, берём HTML из target_element (ID {source_context_root.get('item_id')})", 'info')
                    else:
                        log_callback(f"  revision_number == null, но target_element не передан", 'error')
                        return False
                if not source_html:
                    if log_callback:
                        log_callback(f"  Не удалось получить HTML для новой редакции табличного элемента", 'error')
                    return False
            range_str = change.get('description', '').strip()
            cleaned_html = extract_paragraphs_by_indices(source_html, range_str, log_callback)
            if not cleaned_html and range_str:
                if log_callback:
                    log_callback(f"  Не удалось извлечь абзацы по диапазону '{range_str}' для табличного элемента", 'error')
                return False
            if not cleaned_html:
                cleaned_html = source_html
            if not re.search(r'<table|<tr|<td|<th', cleaned_html, re.IGNORECASE):
                log_callback(
                    f"  Новая редакция для табличного элемента (ID {element.get('item_id')}) "
                    f"не содержит табличной разметки. Изменение не будет применено.",
                    'error'
                )
                return False
            if element.get('item_type') in ('part', 'point', 'subpoint'):
                cleaned_html = remove_leading_number_from_html(cleaned_html, str(element.get('item_number', '')))
            if active_idx >= 0:
                valid_to_str = (valid_from - timedelta(days=1)).strftime('%d.%m.%Y')
                _close_revision(revisions[active_idx], valid_to_str)
            is_table_child = element.get('_is_table_child', False)
            cleaned_html = clean_and_unwrap_html(cleaned_html, is_table_child=is_table_child)
            element['_pending_new_redaction_html'] = cleaned_html
            element['_pending_modified_by_id'] = modified_by_id_str
            element['_pending_valid_from'] = valid_from.strftime('%d.%m.%Y')
            element['_pending_mod_type'] = 'new_redaction'
            if change_id:
                element['_pending_change_id'] = change_id
            rebuild_ids.append(element['item_id'])
            if log_callback:
                log_callback(f"  Элемент таблицы '{structural}' заменён новой редакцией (сохранён фрагмент)", 'result')
            return None
        else:
            if '_quoted_html' in change:
                source_html = change['_quoted_html']
            else:
                source_html = None
                if rev_number and rev_number != 'null':
                    rev_list = rev_number if isinstance(rev_number, list) else [rev_number]
                    for rn in rev_list:
                        source_id = find_item_by_revision_number(change_data, rn, context_root=source_context_root)
                        if source_id:
                            source_elem = find_item_by_id(change_data, source_id)
                            if source_elem:
                                source_html = get_full_element_html(source_elem, include_header=False)
                                if source_html:
                                    if log_callback:
                                        preview = source_html[:30000] + ('...' if len(source_html) > 30000 else '')
                                        log_callback(f"  HTML для новой редакции взят из элемента-источника (ID {source_id}): {preview}", 'source')
                                    break
                else:
                    if source_context_root:
                        source_html = get_full_element_html(source_context_root, include_header=False)
                        if log_callback:
                            log_callback(f"  revision_number == null, берём HTML из target_element (ID {source_context_root.get('item_id')})", 'info')
                    else:
                        log_callback(f"  revision_number == null, но target_element не передан", 'error')
                        return False
                if not source_html:
                    if log_callback:
                        log_callback(f"  Не удалось получить HTML для новой редакции", 'error')
                    return False
            range_str = change.get('description', '').strip()
            cleaned_html = extract_paragraphs_by_indices(source_html, range_str, log_callback)
            if not cleaned_html and range_str:
                if log_callback:
                    log_callback(f"  Не удалось извлечь абзацы по диапазону '{range_str}' для новой редакции", 'error')
                return False
            if not cleaned_html:
                cleaned_html = source_html
            if element.get('item_type') in ('part', 'point', 'subpoint'):
                cleaned_html = remove_leading_number_from_html(cleaned_html, str(element.get('item_number', '')))
            if element.get('item_type') in ('article', 'chapter', 'section') and not re.search(r'<[^>]+>', cleaned_html):
                lines = [line.strip() for line in cleaned_html.split('\n') if line.strip()]
                html_parts = []
                for line in lines:
                    html_parts.append(f'<p>{line}</p>')
                cleaned_html = '\n'.join(html_parts)
                if log_callback:
                    log_callback(f"  Преобразованный HTML для new_redaction: {cleaned_html[:200]}...", 'info')
            if active_idx >= 0:
                valid_to_str = (valid_from - timedelta(days=1)).strftime('%d.%m.%Y')
                _close_revision(revisions[active_idx], valid_to_str)
            is_table_child = element.get('_is_table_child', False)
            cleaned_html = clean_and_unwrap_html(cleaned_html, is_table_child=is_table_child)
            element['_pending_new_redaction_html'] = cleaned_html
            element['_pending_modified_by_id'] = modified_by_id_str
            element['_pending_valid_from'] = valid_from.strftime('%d.%m.%Y')
            element['_pending_mod_type'] = 'new_redaction'
            if change_id:
                element['_pending_change_id'] = change_id
            rebuild_ids.append(element['item_id'])
            if log_callback:
                log_callback(f"  Элемент '{structural}' заменён новой редакцией (запрос на перестройку)", 'result')
            return None
    else:
        if log_callback:
            log_callback(f"  Неизвестный тип: {ch_type}", 'warning')
        return False

