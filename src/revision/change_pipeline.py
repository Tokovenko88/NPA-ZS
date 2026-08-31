"""Пайплайн применения изменений с отслеживанием статуса.

Гарантирует, что каждое изменение проходит через:
  extracted -> applying -> prepared -> applied -> verified

И обеспечивает fail-closed поведение: если хотя бы одно изменение
не удалось применить, запуск завершается с FAILED статусом.
"""

import copy
from typing import Any, Callable, Dict, List, Optional, Tuple

from npazs.revision.change_applier import apply_change, apply_grouped_changes
from npazs.revision.change_tracker import ChangeTracker, ChangeStatus
from npazs.revision.html_utils import (
    _extract_quoted_html,
    extract_html_for_added_element,
    extract_structural_block,
    parse_structural_tokens,
    unwrap_outer_legal_quotes,
    validate_quote_extraction,
)
from npazs.revision.ui_utils import _fetch_source_html_for_change
from npazs.revision.tree_utils import find_item_by_id, find_child_by_type_and_number
from npazs.revision.extraction_verifier import _verify_one


def _verify_before_apply(change, change_data, source_context_root, log_callback):
    """Run the AI-vs-program extraction gate on the actual change object.

    This is deliberately done here, immediately before calling the imported
    apply_* functions.  change_pipeline imports those functions by value, so
    monkey-patching change_applier after this module is loaded cannot reliably
    intercept the real execution path.
    """
    if change.get('type') not in ('add', 'new_redaction'):
        return True
    return _verify_one(change, change_data, source_context_root, log_callback)


def apply_change_tracked(
    change: Dict[str, Any],
    change_id: str,
    tracker: ChangeTracker,
    data: Dict[str, Any],
    change_data: Dict[str, Any],
    law_ref: str,
    general_valid_from: Any,
    log_callback: Callable,
    source_item_id: str = None,
    model: str = None,
    prompt4: str = None,
    rebuild_ids: List[str] = None,
    doc_type: str = 'law',
    extra_options: Dict[str, Any] = None,
    stop_event: Any = None,
    manual_resolver: Callable = None,
    source_context_root: Dict[str, Any] = None,
    ambiguous_callback: Callable = None,
    prompt_answer_callback: Callable = None,
) -> Dict[str, Any]:
    """Применяет одно изменение с отслеживанием статуса."""
    if rebuild_ids is None:
        rebuild_ids = []

    structural = change.get('structural_element', '')
    target_item_id = change.get('_resolved_item_id')

    tracker.mark_applying(change_id, target_item_id=target_item_id)

    try:
        if not _verify_before_apply(change, change_data, source_context_root, log_callback):
            tracker.mark_failed(change_id, reason="Extraction conflict was not resolved by user")
            return {"status": "FAILED", "change_id": change_id, "revision_id": None,
                    "error": "Extraction conflict was not resolved by user"}

        result = apply_change(
            change=change,
            data=data,
            change_data=change_data,
            law_ref=law_ref,
            general_valid_from=general_valid_from,
            log_callback=log_callback,
            source_item_id=source_item_id,
            model=model,
            prompt4=prompt4,
            rebuild_ids=rebuild_ids,
            doc_type=doc_type,
            extra_options=extra_options,
            stop_event=stop_event,
            manual_resolver=manual_resolver,
            source_context_root=source_context_root,
            ambiguous_callback=ambiguous_callback,
            prompt_answer_callback=prompt_answer_callback,
        )

        if not isinstance(result, dict):
            result = {"status": "FAILED", "change_id": change_id, "revision_id": None,
                      "error": "apply_change returned non-dict"}

        status = result.get("status", "FAILED")
        revision_id = result.get("revision_id")
        error = result.get("error")

        if status == "PREPARED":
            tracker.mark_prepared(change_id, target_item_id=target_item_id)
        elif status == "APPLIED":
            if not revision_id:
                tracker.mark_failed(change_id, "apply_change returned APPLIED without revision_id")
            else:
                tracker.mark_applied(change_id, revision_id=revision_id, target_item_id=target_item_id)
        elif status == "NEEDS_USER_ADDRESS":
            tracker.mark_needs_user_address(change_id, reason=error or "address resolution required")
        elif status == "FAILED":
            tracker.mark_failed(change_id, reason=error or "apply_change returned FAILED")
        else:
            tracker.mark_failed(change_id, f"Unknown apply status: {status}")

        return result
    except Exception as e:
        tracker.mark_failed(change_id, reason=str(e))
        if log_callback:
            log_callback(f"CHANGE [{change.get('revision_number')}] exception: {e}", 'error')
        return {"status": "FAILED", "change_id": change_id, "revision_id": None, "error": str(e)}


def apply_grouped_changes_tracked(
    element: Dict[str, Any],
    changes: List[Dict[str, Any]],
    change_ids: List[str],
    tracker: ChangeTracker,
    valid_from: Any,
    data: Dict[str, Any],
    change_data: Dict[str, Any],
    model: str,
    prompt4: str,
    log_callback: Callable,
    rebuild_ids: List[str],
    extra_options: Dict[str, Any],
    source_item_id: str = None,
    stop_event: Any = None,
    manual_resolver: Callable = None,
    source_context_root: Dict[str, Any] = None,
    backend: str = "ollama",
    kilo_gateway_url: str = None,
    api_key: str = None,
    prompt_answer_callback: Callable = None,
) -> List[Dict[str, Any]]:
    """Применяет группу изменений с отслеживанием статуса."""
    if not changes:
        return []

    target_item_id = element.get('item_id')

    for change_id in change_ids:
        tracker.mark_applying(change_id, target_item_id=target_item_id)

    try:
        for change in changes:
            if not _verify_before_apply(change, change_data, source_context_root, log_callback):
                results = []
                for cid in change_ids:
                    tracker.mark_failed(cid, reason="Extraction conflict was not resolved by user")
                    results.append({
                        "status": "FAILED",
                        "change_id": cid,
                        "revision_id": None,
                        "error": "Extraction conflict was not resolved by user",
                    })
                return results

        results = apply_grouped_changes(
            element=element,
            changes=changes,
            valid_from=valid_from,
            data=data,
            change_data=change_data,
            model=model,
            prompt4=prompt4,
            log_callback=log_callback,
            rebuild_ids=rebuild_ids,
            extra_options=extra_options,
            source_item_id=source_item_id,
            stop_event=stop_event,
            manual_resolver=manual_resolver,
            source_context_root=source_context_root,
            change_ids=change_ids,
            backend=backend,
            kilo_gateway_url=kilo_gateway_url,
            api_key=api_key,
            prompt_answer_callback=prompt_answer_callback,
        )

        if not isinstance(results, list):
            results = [{"status": "FAILED", "revision_id": None, "error": "apply_grouped_changes returned non-list"}]

        for i, change_id in enumerate(change_ids):
            result = results[i] if i < len(results) else {"status": "FAILED", "revision_id": None, "error": "missing result"}
            status = result.get("status", "FAILED")
            revision_id = result.get("revision_id")
            error = result.get("error")

            if status == "PREPARED":
                tracker.mark_prepared(change_id, target_item_id=target_item_id)
            elif status == "APPLIED":
                if not revision_id:
                    tracker.mark_failed(change_id, "apply_grouped_changes returned APPLIED without revision_id")
                else:
                    tracker.mark_applied(change_id, revision_id=revision_id, target_item_id=target_item_id)
            elif status == "NEEDS_USER_ADDRESS":
                tracker.mark_needs_user_address(change_id, reason=error or "address resolution required")
            elif status == "FAILED":
                tracker.mark_failed(change_id, reason=error or "apply_grouped_changes returned FAILED")
            else:
                tracker.mark_failed(change_id, f"Unknown apply status: {status}")

        return results
    except Exception as e:
        for change_id in change_ids:
            tracker.mark_failed(change_id, reason=str(e))
        if log_callback:
            log_callback(f"GROUP [{changes[0].get('revision_number')}] exception: {e}", 'error')
        return [{"status": "FAILED", "change_id": cid, "revision_id": None, "error": str(e)} for cid in change_ids]


def verify_change_applied(
    change: Dict[str, Any],
    data: Dict[str, Any],
    change_data: Dict[str, Any],
    log_callback: Callable = None,
    expected_revision_id: str = None,
) -> bool:
    """Проверяет, что изменение действительно применено к данным."""
    ch_type = change.get('type', '')
    structural = change.get('structural_element', '')
    revision_number = change.get('revision_number', '')
    valid_from = change.get('valid_from', '')

    if ch_type == 'delete':
        return _verify_delete(change, data, log_callback, expected_revision_id)
    elif ch_type == 'add':
        return _verify_add(change, data, log_callback, expected_revision_id)
    elif ch_type in ('new_redaction', 'change'):
        return _verify_modification(change, data, log_callback, expected_revision_id)

    if log_callback:
        log_callback(f"  verify: неизвестный тип '{ch_type}' для '{structural}', считаем verified", 'warning')
    return True


def _verify_delete(change: Dict[str, Any], data: Dict[str, Any], log_callback: Callable = None, expected_revision_id: str = None) -> bool:
    """Проверяет, что элемент удалён (помечен as not_valid) в конкретной revision."""
    structural = change.get('structural_element', '')
    target_id = change.get('_resolved_item_id')

    if not target_id:
        if log_callback:
            log_callback(f"  verify delete: нет _resolved_item_id для '{structural}'", 'warning')
        return False
    element = find_item_by_id(data, target_id)
    if not element:
        if log_callback:
            log_callback(f"  verify delete: элемент {target_id} не найден", 'error')
        return False
    revisions = element.get('revisions', [])
    if expected_revision_id:
        for rev in revisions:
            if rev.get('revision_id') == expected_revision_id:
                if rev.get('not_valid'):
                    return True
                if log_callback:
                    log_callback(f"  verify delete: revision {expected_revision_id} не помечена как удалённая", 'error')
                return False
        if log_callback:
            log_callback(f"  verify delete: revision {expected_revision_id} не найдена у элемента {target_id}", 'error')
        return False
    if log_callback:
        log_callback(f"  verify delete: нет expected_revision_id для '{structural}', верификация невозможна", 'error')
    return False


def _verify_add(change: Dict[str, Any], data: Dict[str, Any], log_callback: Callable = None, expected_revision_id: str = None) -> bool:
    """Проверяет, что элемент добавлен (существует в дереве) и имеет ожидаемую revision."""
    structural = change.get('structural_element', '')
    created_id = change.get('_created_item_id')
    element = None

    if created_id:
        element = find_item_by_id(data, created_id)
        if not element and log_callback:
            log_callback(f"  verify add: созданный элемент {created_id} не найден по ID после перестройки, ищем по структурному пути '{structural}'", 'warning')

    if not element and structural:
        tokens = parse_structural_tokens(structural)
        if tokens:
            last_type, last_num = tokens[-1]
            parent_tokens = tokens[:-1]
            current_level = data.get('npa_items_revision', [])
            parent_element = None
            for pt_type, pt_num in parent_tokens:
                found = None
                for item in current_level:
                    if item.get('item_type') == pt_type and str(item.get('item_number', '')) == str(pt_num):
                        found = item
                        break
                if found:
                    parent_element = found
                    current_level = found.get('item_children', [])
                else:
                    parent_element = None
                    break
            if parent_element:
                element = find_child_by_type_and_number(parent_element, last_type, last_num, ambiguous_callback=None)
                if element and log_callback:
                    log_callback(f"  verify add: найден элемент по структурному пути: {last_type} {last_num} (ID {element.get('item_id')})", 'info')
                elif not element and log_callback:
                    log_callback(f"  verify add: элемент не найден по структурному пути '{structural}'", 'warning')

    if not element:
        if log_callback:
            log_callback(f"  verify add: элемент не найден для '{structural}'", 'error')
        return False
    if expected_revision_id:
        revisions = element.get('revisions', [])
        if not any(rev.get('revision_id') == expected_revision_id for rev in revisions):
            if log_callback:
                log_callback(f"  verify add: revision {expected_revision_id} не найдена у элемента {element.get('item_id')}", 'error')
            return False
    return True


def _verify_modification(change: Dict[str, Any], data: Dict[str, Any], log_callback: Callable = None, expected_revision_id: str = None) -> bool:
    """Проверяет, что элемент изменён (есть новая ревизия) с конкретным revision_id."""
    structural = change.get('structural_element', '')
    target_id = change.get('_resolved_item_id')
    ch_type = change.get('type', '')
    if not target_id:
        if log_callback:
            log_callback(f"  verify {ch_type}: нет _resolved_item_id для '{structural}'", 'warning')
        return False

    # Специальная обработка для наименования и преамбулы — они хранятся вне дерева элементов
    if target_id == '__наименование__':
        revisions = data.get('head_revision', [])
        return _verify_revision_exists(revisions, expected_revision_id, ch_type, structural, log_callback)
    if target_id == '__преамбула__':
        revisions = data.get('preamble_revision', [])
        return _verify_revision_exists(revisions, expected_revision_id, ch_type, structural, log_callback)

    element = find_item_by_id(data, target_id)
    if not element:
        if log_callback:
            log_callback(f"  verify {ch_type}: элемент {target_id} не найден", 'error')
        return False
    revisions = element.get('revisions', [])
    return _verify_revision_exists(revisions, expected_revision_id, ch_type, structural, log_callback)


def _verify_revision_exists(revisions, expected_revision_id, ch_type, structural, log_callback):
    """Проверяет наличие ревизии с ожидаемым ID в списке ревизий."""
    if expected_revision_id:
        for rev in revisions:
            if rev.get('revision_id') == expected_revision_id:
                if rev.get('valid_to') is not None:
                    if log_callback:
                        log_callback(f"  verify {ch_type}: revision {expected_revision_id} уже закрыта (valid_to={rev.get('valid_to')})", 'error')
                    return False
                mod_type = rev.get('mod_type', '')
                if ch_type == 'new_redaction' and mod_type == 'new_redaction':
                    return True
                if ch_type == 'change' and mod_type in ('change', 'new_redaction'):
                    return True
                if log_callback:
                    log_callback(f"  verify {ch_type}: revision {expected_revision_id} имеет неверный mod_type='{mod_type}'", 'error')
                return False
        if log_callback:
            log_callback(f"  verify {ch_type}: revision {expected_revision_id} не найдена для '{structural}'", 'error')
        return False
    if log_callback:
        log_callback(f"  verify {ch_type}: нет expected_revision_id для '{structural}', верификация невозможна", 'error')
    return False


def run_verification_stage(
    tracker: ChangeTracker,
    data: Dict[str, Any],
    change_data: Dict[str, Any],
    log_callback: Callable = None,
) -> bool:
    """Запускает этап верификации всех применённых изменений."""
    if log_callback:
        log_callback("=== ЭТАП ВЕРИФИКАЦИИ: Проверка применённых изменений ===", 'info')

    all_changes = tracker.get_all_changes()
    all_verified = True

    for change_id, change_info in all_changes.items():
        status = change_info['status']
        if status in (ChangeStatus.PREPARED, ChangeStatus.PENDING, ChangeStatus.APPLYING):
            tracker.mark_failed(change_id, "Change was not converted to APPLIED before verification")
            all_verified = False
            if log_callback:
                log_callback(
                    f"  ❌ [{change_info['revision_number']}] {change_info['structural_element']} "
                    f"— не APPLIED перед верификацией (status={status.value})",
                    'error'
                )
            continue
        if status not in (ChangeStatus.APPLIED, ChangeStatus.VERIFIED):
            continue

        source_change = change_info.get('source_change', {})
        structural = change_info.get('structural_element', '')
        revision_number = change_info.get('revision_number', '')
        revision_id = change_info.get('revision_id')
        try:
            verified = verify_change_applied(
                source_change, data, change_data, log_callback,
                expected_revision_id=revision_id
            )
            if verified:
                tracker.mark_verified(change_id)
                if log_callback:
                    log_callback(f"  ✅ [{change_id}] {structural} — верификация пройдена", 'result')
            else:
                tracker.mark_failed(change_id, reason="Post-apply verification failed")
                all_verified = False
                if log_callback:
                    log_callback(f"  ❌ [{change_id}] {structural} — верификация НЕ пройдена", 'error')
        except Exception as e:
            tracker.mark_failed(change_id, reason=f"Verification exception: {e}")
            all_verified = False
            if log_callback:
                log_callback(f"  ❌ [{change_id}] {structural} — ошибка верификации: {e}", 'error')

    return all_verified
