"""Verification bridge for deterministic extraction versus Stage 3 content."""

from __future__ import annotations

import inspect
import re
import threading

from bs4 import BeautifulSoup

from npazs.revision.quote_extraction import (
    extraction_results_equal,
    extract_quoted_html_robust,
    extract_paragraphs_by_indices_robust,
    _find_final_outer_quote,
    _strip_trailing_empty_inline,
)
from npazs.ui.dialogs.extraction_conflict import resolve_extraction_conflict

_PATCHED = False


def _clean_ai_content(content: str) -> str:
    content = (content or "").strip()
    if not content:
        return ""
    if content.startswith("«"):
        extracted = extract_quoted_html_robust(content)
        if extracted:
            return extracted.strip()
    return content


def _log_extraction_block(log_callback, label, html):
    """Log the exact HTML block at extraction boundaries for diagnosis."""
    if not log_callback:
        return
    html = html or ""
    log_callback(
        f"  [EXTRACT DEBUG] ===== {label} =====\n"
        f"  [EXTRACT DEBUG] length={len(html)}\n"
        f"  [EXTRACT DEBUG] BEGIN\n{html}\n"
        f"  [EXTRACT DEBUG] END\n"
        f"  [EXTRACT DEBUG] ===== END {label} =====",
        "info",
    )


def _source_for_change(change, change_data, source_context_root, log_callback):
    source = change.get("_quoted_html")
    if source:
        _log_extraction_block(log_callback, "SOURCE _quoted_html", source)
        return source
    try:
        from npazs.revision.ui_utils import _fetch_source_html_for_change
        source = _fetch_source_html_for_change(change, change_data, source_context_root, log_callback)
        _log_extraction_block(log_callback, "SOURCE fetched", source)
        return source
    except Exception:
        return None


def _remove_first_outer_add_quote(block):
    """Remove only the service-level opening quote from an ADD block."""
    text = block.get_text(strip=True)
    if not text.startswith("«"):
        return False
    for node in block.find_all(string=True):
        value = str(node)
        stripped = value.lstrip()
        offset = len(value) - len(stripped)
        if stripped.startswith("«"):
            node.replace_with(value[:offset] + value[offset + 1:])
            return True
    return False


def _remove_last_outer_add_quote(blocks):
    """Remove the service-level closing quote only when it is the true outer quote."""
    if not blocks:
        return False
    text = blocks[-1].get_text(strip=True)
    tail = re.sub(r"[\s;,.!?…]+$", "", text)
    if not tail.endswith("»"):
        return False

    candidate = _find_final_outer_quote(blocks)
    if candidate is None:
        return False
    node, quote_pos = candidate

    value = str(node)
    suffix = value[quote_pos + 1:]
    if suffix.strip(" \t\r\n;,.!?…"):
        return False
    nodes = list(blocks[-1].find_all(string=True))
    node.replace_with(value[:quote_pos])
    for following in nodes[nodes.index(node) + 1:]:
        if str(following).strip(" \t\r\n;,.!?…") == "":
            try:
                following.replace_with("")
            except Exception:
                pass
    _strip_trailing_empty_inline(blocks[-1])
    return True


def _unwrap_add_candidate(html, log_callback, label):
    """Remove ADD's service-level quote markers without touching inner quotes."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    blocks = [
        child for child in soup.children
        if getattr(child, "name", None) in {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "table", "tr"}
    ]
    if not blocks:
        return html.strip()

    changed = False
    for block in blocks:
        if _remove_first_outer_add_quote(block):
            changed = True
            break
    changed = _remove_last_outer_add_quote(blocks) or changed

    result = "\n".join(str(block) for block in blocks if str(block).strip()).strip()
    if changed:
        _log_extraction_block(log_callback, f"{label} after ADD boundary-quote removal", result)
    return result


def _program_candidate(change, source_html, log_callback):
    if not source_html:
        return ""
    ch_type = change.get("type", "")
    if ch_type == "new_redaction":
        candidate = extract_paragraphs_by_indices_robust(
            source_html, str(change.get("description", "") or ""), log_callback
        )
        candidate = candidate.strip() if candidate else source_html.strip()
        _log_extraction_block(log_callback, "PROGRAM CANDIDATE new_redaction", candidate)
        return candidate

    if ch_type == "add":
        try:
            from npazs.revision.ui_utils import parse_add_new_field
            from npazs.revision.html_utils import extract_structural_block
            from npazs.constants import TYPE_TO_RUSSIAN
            ru_type, child_num = parse_add_new_field(change.get("new", ""))
            sys_type = next(
                (eng for eng, rus in TYPE_TO_RUSSIAN.items() if rus.lower() == (ru_type or "").lower()),
                None,
            )
            if sys_type and child_num:
                structural = extract_structural_block(source_html, sys_type, child_num, log_callback)
                _log_extraction_block(log_callback, f"PROGRAM STRUCTURAL add {sys_type} {child_num}", structural)
                if structural:
                    return _unwrap_add_candidate(structural, log_callback, f"PROGRAM STRUCTURAL add {sys_type} {child_num}")
        except Exception as exc:
            if log_callback:
                log_callback(f"  [EXTRACT VERIFY] structural candidate error: {exc}", "warning")
        candidate = extract_paragraphs_by_indices_robust(
            source_html, str(change.get("description", "") or ""), log_callback
        )
        candidate = candidate.strip() if candidate else source_html.strip()
        candidate = _unwrap_add_candidate(candidate, log_callback, "PROGRAM RANGE FALLBACK add")
        _log_extraction_block(log_callback, "PROGRAM RANGE FALLBACK add", candidate)
        return candidate
    return ""


def _owner(log_callback):
    return getattr(log_callback, "__self__", None)


def _owner_root(log_callback):
    owner = _owner(log_callback)
    return getattr(owner, "root", None) if owner is not None else None


def _owner_stop_event(log_callback):
    owner = _owner(log_callback)
    return getattr(owner, "stop_event", None)


def _ask_user(log_callback, change, program_html, ai_html):
    root = _owner_root(log_callback)
    stop_event = _owner_stop_event(log_callback)
    if root is None:
        if log_callback:
            log_callback("  [EXTRACT VERIFY] РАСХОЖДЕНИЕ, но Tk root недоступен; автоматически выбран программный кандидат", "warning")
        return program_html if program_html else ai_html
    if stop_event is not None and stop_event.is_set():
        return None

    result = {}
    done = threading.Event()
    context = (
        f"Тип изменения: {change.get('type', '')}\n"
        f"revision_number: {change.get('revision_number', '')}\n"
        f"structural_element: {change.get('structural_element', '')}\n"
        f"description / диапазон: {change.get('description', '')}\n"
        f"new: {change.get('new', '')}\n\n"
        "Варианты ниже редактируемые. Выберите итоговый вариант после проверки."
    )

    def show():
        try:
            if stop_event is not None and stop_event.is_set():
                return
            result["html"] = resolve_extraction_conflict(
                root,
                title="Конфликт извлечения: программа ↔ ИИ",
                context=context,
                program_html=program_html,
                ai_html=ai_html,
                stop_event=stop_event,
            )
        finally:
            done.set()

    root.after(0, show)
    while not done.wait(0.1):
        if stop_event is not None and stop_event.is_set():
            dlg = getattr(root, "_extraction_conflict_dialog", None)
            if dlg is not None:
                root.after(0, dlg.destroy)
            return None
    return result.get("html")


def _store_verified_candidate(change, html):
    """Make the verified result the exact payload consumed by the applier."""
    html = (html or "").strip()
    change["_verified_extracted_html"] = html
    change["_quoted_html"] = html
    change["description"] = "all"
    return html


def _verify_one(change, change_data, source_context_root, log_callback):
    if change.get("type") not in ("add", "new_redaction"):
        return True

    ai_raw = change.get("content", "")
    _log_extraction_block(log_callback, "AI RAW content", ai_raw)
    ai_html = _clean_ai_content(ai_raw)
    _log_extraction_block(log_callback, "AI CLEANED candidate", ai_html)

    # Missing content is an extraction failure, not a successful result.
    # Previously the empty value returned True here, bypassing the verifier and
    # allowing ADD to consume the raw structural source with its outer quotes.
    content_missing = not ai_html
    if content_missing and log_callback:
        log_callback(
            "  [EXTRACT VERIFY] ОШИБКА: ИИ не вернул обязательное поле content; "
            "запускаем контроль извлечения",
            "warning",
        )

    source_html = _source_for_change(change, change_data, source_context_root, log_callback)
    if not source_html:
        if content_missing and log_callback:
            log_callback(
                "  [EXTRACT VERIFY] нет исходного HTML для контроля отсутствующего content — обработка остановлена",
                "error",
            )
            return False
        return True

    stop_event = _owner_stop_event(log_callback)
    if stop_event is not None and stop_event.is_set():
        return False

    program_html = _program_candidate(change, source_html, log_callback)
    if not program_html:
        if content_missing and log_callback:
            log_callback(
                "  [EXTRACT VERIFY] программный кандидат не построен — обработка остановлена",
                "error",
            )
            return False
        return True

    equal = extraction_results_equal(program_html, ai_html) if ai_html else False
    if equal:
        if log_callback:
            log_callback(
                f"  [EXTRACT VERIFY] OK: {change.get('type')} / {change.get('structural_element')}",
                "info",
            )
        _store_verified_candidate(change, program_html)
        return True

    if log_callback:
        reason = "ИИ не вернул content" if content_missing else "расхождение HTML"
        log_callback(
            f"  [EXTRACT VERIFY] РАСХОЖДЕНИЕ ({reason}): {change.get('type')} / "
            f"{change.get('structural_element')} — требуется решение пользователя",
            "warning",
        )
        _log_extraction_block(log_callback, "PROGRAM vs AI — PROGRAM", program_html)
        _log_extraction_block(log_callback, "PROGRAM vs AI — AI", ai_html)
    chosen = _ask_user(log_callback, change, program_html, ai_html)
    chosen = (chosen or "").strip()
    if not chosen:
        if log_callback:
            log_callback("  [EXTRACT VERIFY] итоговый вариант пуст — изменение остановлено, fallback к исходным кавычкам запрещён", "error")
        return False
    _log_extraction_block(log_callback, "USER CHOSEN final", chosen)
    _store_verified_candidate(change, chosen)
    change["_extraction_conflict_resolved"] = True
    return True


def _verify_changes(changes, change_data, source_context_root, log_callback):
    for change in changes or []:
        if not _verify_one(change, change_data, source_context_root, log_callback):
            return False
    return True


def patch_change_applier(change_applier_module):
    """Install a compatibility gate for callers that invoke change_applier directly."""
    global _PATCHED
    if _PATCHED:
        return

    original_grouped = change_applier_module.apply_grouped_changes
    original_apply = change_applier_module.apply_change
    grouped_signature = inspect.signature(original_grouped)
    apply_signature = inspect.signature(original_apply)

    def _make_verification_failed_result(change):
        return {
            "status": "FAILED",
            "change_id": change.get("change_id", ""),
            "revision_id": None,
            "error": "Extraction conflict was not resolved by user",
        }

    def verified_grouped_changes(*args, **kwargs):
        bound = grouped_signature.bind_partial(*args, **kwargs)
        values = bound.arguments
        changes = values.get("changes")
        if not _verify_changes(
            changes,
            values.get("change_data"),
            values.get("source_context_root"),
            values.get("log_callback"),
        ):
            return [_make_verification_failed_result(c) for c in (changes or [])]
        return original_grouped(*args, **kwargs)

    def verified_apply_change(*args, **kwargs):
        bound = apply_signature.bind_partial(*args, **kwargs)
        values = bound.arguments
        change = values.get("change")
        if change is not None and not _verify_one(
            change,
            values.get("change_data"),
            values.get("source_context_root"),
            values.get("log_callback"),
        ):
            return _make_verification_failed_result(change)
        return original_apply(*args, **kwargs)

    verified_grouped_changes.__name__ = original_grouped.__name__
    verified_apply_change.__name__ = original_apply.__name__
    change_applier_module.apply_grouped_changes = verified_grouped_changes
    change_applier_module.apply_change = verified_apply_change
    _PATCHED = True
