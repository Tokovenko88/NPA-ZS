"""Processing package compatibility hooks."""

# Keep the mature html_utils module API intact while replacing only the two
# quote-sensitive extraction functions with the deterministic implementation.
# This file is imported before processing submodules, so their ``from ...
# html_utils import ...`` statements receive the patched functions.
from npazs.revision import html_utils as _html_utils
from npazs.revision.quote_extraction import (
    extract_quoted_html_robust,
    extract_paragraphs_by_indices_robust,
)

_html_utils._extract_quoted_html = extract_quoted_html_robust
_html_utils.extract_paragraphs_by_indices = extract_paragraphs_by_indices_robust


# ADD changes are applied by a dedicated loop in ai_pipeline.py rather than
# through change_pipeline.apply_change_tracked(), so they historically missed
# the extraction-verification gate. Install a narrow compatibility hook at the
# package boundary: register_change remembers the current ADD change and the
# first structural extraction for that ADD runs the same verifier used by
# new_redaction. The verifier itself remains in extraction_verifier.py.
_pending_add_verification = None
_failed_add_verification = None
_verification_in_progress = False

try:
    from npazs.revision.change_tracker import ChangeTracker
    from npazs.revision.extraction_verifier import _verify_one

    _original_register_change = ChangeTracker.register_change

    def _register_change_with_add_verification(self, change):
        global _pending_add_verification, _failed_add_verification
        change_id = _original_register_change(self, change)
        _failed_add_verification = None
        if change.get("type") == "add":
            _pending_add_verification = (change, getattr(self, "_log_callback", None))
        else:
            _pending_add_verification = None
        return change_id

    ChangeTracker.register_change = _register_change_with_add_verification

    _original_extract_structural_block = _html_utils.extract_structural_block
    _original_extract_html_for_added_element = _html_utils.extract_html_for_added_element

    def _verify_pending_add(html, structural_type, structural_number, log_callback=None):
        global _pending_add_verification, _failed_add_verification, _verification_in_progress
        pending = _pending_add_verification
        if pending is None or _verification_in_progress:
            return html, True

        change, tracker_log = pending
        if change.get("type") != "add":
            _pending_add_verification = None
            return html, True

        _pending_add_verification = None
        _verification_in_progress = True
        try:
            ok = _verify_one(
                change,
                None,
                None,
                tracker_log or log_callback,
            )
        finally:
            _verification_in_progress = False

        if not ok:
            change["_extraction_verification_failed"] = True
            _failed_add_verification = change
            return "", False

        # _verify_one stores the exact user-confirmed/program-confirmed HTML in
        # _verified_extracted_html/_quoted_html. Use that result for the actual
        # ADD extraction instead of the pre-verification local source copy.
        verified_html = change.get("_verified_extracted_html") or change.get("_quoted_html")
        return (verified_html or html), True

    def _verified_extract_structural_block(html, structural_type, structural_number, log_callback=None):
        checked_html, ok = _verify_pending_add(
            html, structural_type, structural_number, log_callback
        )
        if not ok:
            return ""
        return _original_extract_structural_block(
            checked_html, structural_type, structural_number, log_callback
        )

    def _verified_extract_html_for_added_element(source_html, range_str, child_number, log_callback=None):
        global _failed_add_verification
        # If verification was cancelled/rejected, force the existing ADD
        # extraction failure path instead of silently falling back to an
        # unverified extraction. Consume the failure marker so it cannot leak
        # into subsequent non-ADD processing.
        if _failed_add_verification is not None:
            _failed_add_verification = None
            return ""
        return _original_extract_html_for_added_element(
            source_html, range_str, child_number, log_callback
        )

    _html_utils.extract_structural_block = _verified_extract_structural_block
    _html_utils.extract_html_for_added_element = _verified_extract_html_for_added_element
except Exception:
    # Compatibility hooks must never make the processing package unloadable.
    pass


# Retroactive propagation notes are temporal records, not unconditional tags.
# When a new note says that rights/relations "распространяются ... правоотношения",
# every older still-open propagation note on the same structural element must end
# on the day BEFORE the AMENDING law enters into force: the old redaction (and its
# propagation clause) stops being effective then —
# ``valid_to = дата вступления в силу изменяющего НПА - 1 день``.
# Notes produced by the SAME amending NPA (identical npa_id prefix of
# source_item_id) coexist and are never closed by each other. When the amending
# date is unknown, fall back to the legacy rule "valid_from новой заметки - 1 день".
# Keep this as a narrow wrapper so the existing note API and target-law/NPA
# invariants remain unchanged.
try:
    from datetime import datetime, timedelta
    from npazs.revision import retroactive_notes as _retroactive_notes

    _original_append_item_note = _retroactive_notes._append_item_note
    _is_propagation_note = _retroactive_notes.is_propagation_note

    def _parse_note_date(value):
        try:
            return datetime.strptime(str(value).strip(), "%d.%m.%Y").date()
        except (TypeError, ValueError, AttributeError):
            return None

    def _append_item_note_with_validity(
        element, text, valid_from, log_callback=None, element_label="",
        source_item_id=None, amending_valid_from=None,
    ):
        added = _original_append_item_note(
            element, text, valid_from, log_callback, element_label, source_item_id
        )
        if not valid_from or not _is_propagation_note(text):
            return added

        new_date = _parse_note_date(valid_from)
        if new_date is None:
            return added

        # Дата закрытия старых примечаний: приоритет у даты вступления в силу
        # изменяющего НПА, без неё — прежнее поведение «valid_from новой - 1 день».
        amending_date = _parse_note_date(amending_valid_from)
        close_dt = (amending_date or new_date) - timedelta(days=1)
        close_date = close_dt.strftime("%d.%m.%Y")

        # npa_id изменяющего НПА из source_item_id («144372_article_2» -> «144372»):
        # примечания одного и того же изменяющего НПА сосуществуют.
        new_npa = str(source_item_id or "").split("_", 1)[0]

        notes = element.get("item_notes") or []
        # Только что добавленное примечание — последний элемент item_notes
        # (оригинальная функция делает list.append); его закрывать нельзя.
        new_note = notes[-1] if added and notes else None

        closed = 0
        for note in notes:
            if note is new_note:
                continue
            if note.get("valid_to") not in (None, ""):
                continue
            if not _is_propagation_note(note.get("text", "")):
                continue
            old_source = str(note.get("source_item_id") or "")
            old_npa = old_source.split("_", 1)[0]
            if new_npa and old_npa and old_npa == new_npa:
                continue
            old_date = _parse_note_date(note.get("valid_from"))
            if old_date is None or old_date > close_dt:
                # Нельзя закрыть заметку раньше, чем она начала действовать.
                continue
            note["valid_to"] = close_date
            closed += 1

        if closed and log_callback:
            label = element_label or str(element.get("item_id", ""))
            log_callback(
                f"Закрыто {closed} предыдущее примечание о распространении правоотношений "
                f"для {label}: valid_to={close_date}",
                "result",
            )
        return added

    _retroactive_notes._append_item_note = _append_item_note_with_validity
except Exception:
    # The temporal-note hook must not make the processing package unloadable.
    pass

__all__ = []
