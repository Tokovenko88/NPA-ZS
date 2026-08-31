"""Фасад для обратной совместимости. Реэкспортирует все функции из подмодулей."""

from npazs.revision.element_finder import *
from npazs.revision.change_applier import *
from npazs.revision.revision_builder import *

# Stage 3 supplies deterministic HTML in ``content`` for add/new_redaction.
# Install the deterministic extractor BEFORE ai_pipeline imports html_utils
# with ``from ...html_utils import _extract_quoted_html, ...``. Wildcard
# imports in revision_utils/change_applier otherwise retain old references.
from npazs.revision import html_utils as _html_utils
from npazs.revision import revision_utils as _revision_utils
from npazs.revision import change_applier as _change_applier
from npazs.revision.quote_extraction import (
    extract_quoted_html_robust as _extract_quoted_html_robust,
    extract_paragraphs_by_indices_robust as _extract_paragraphs_by_indices_robust,
)
from npazs.revision.extraction_verifier import patch_change_applier as _patch_change_applier

# Patch the defining module first. Later direct imports from html_utils
# (notably ai_pipeline) therefore receive the robust implementation.
_html_utils._extract_quoted_html = _extract_quoted_html_robust
_html_utils.extract_paragraphs_by_indices = _extract_paragraphs_by_indices_robust

# Patch aliases already copied by ``from revision_utils import *``.
_revision_utils._extract_quoted_html = _extract_quoted_html_robust
_revision_utils.extract_paragraphs_by_indices = _extract_paragraphs_by_indices_robust
_change_applier._extract_quoted_html = _extract_quoted_html_robust
_change_applier.extract_paragraphs_by_indices = _extract_paragraphs_by_indices_robust

# Install the AI-vs-program extraction verification gate.
_patch_change_applier(_change_applier)
apply_grouped_changes = _change_applier.apply_grouped_changes
apply_change = _change_applier.apply_change


# ---------------------------------------------------------------------------
# REBUILD MODES
# ---------------------------------------------------------------------------
#
# A content change to an already existing structural element and a structural
# operation (add/delete) are deliberately different operations.
#
# CONTENT_REBUILD:
#   Rebuild only the element whose own text was changed/re-edited. The parent
#   must NOT be reconstructed merely because a descendant changed.
#
# STRUCTURE_REBUILD:
#   Rebuild the element which was structurally added. Parent bodies are updated
#   by the structural operation itself (child_ref), but an unchanged parent is
#   not reparsed into a new revision.
#
# An element with pending HTML but without an operation type is not a valid
# rebuild request. Such state is an artefact of parent-promotion logic and is
# explicitly rejected below.

CONTENT_REBUILD = "CONTENT_REBUILD"
STRUCTURE_REBUILD = "STRUCTURE_REBUILD"


def get_rebuild_mode(item):
    """Return the explicit rebuild mode for a pending element."""
    if not item:
        return None

    explicit = item.get("_rebuild_mode")
    if explicit in (CONTENT_REBUILD, STRUCTURE_REBUILD):
        return explicit

    mod_type = item.get("_pending_mod_type")
    if mod_type in ("change", "new_redaction"):
        return CONTENT_REBUILD
    if mod_type == "add":
        return STRUCTURE_REBUILD

    return None


_original_rebuild_element_with_history = rebuild_element_with_history


def rebuild_element_with_history(
    data,
    element_id,
    valid_from,
    modified_by_id_str,
    doc_type="law",
    log_callback=None,
    log_queue=None,
    answer_queue=None,
):
    """Rebuild exactly the requested element, without implicit parent rebuilds."""
    element = find_item_by_id(data, element_id)
    mode = get_rebuild_mode(element)

    if mode is None:
        if log_callback:
            log_callback(
                f"⏭️ SKIP REBUILD: {element_id} не имеет собственного изменения "
                f"(нет _pending_mod_type). Родительская реконструкция запрещена.",
                "info",
            )
        # Stage 5 treats a non-empty return as a successful no-op. This prevents
        # a synthetic parent candidate from being reported as a rebuild error
        # while, importantly, creating no revision and changing no structure.
        return f"SKIPPED_PARENT_REBUILD:{element_id}"

    if log_callback:
        log_callback(
            f"🔧 {mode}: {element_id} "
            f"(mod_type={element.get('_pending_mod_type') if element else None})",
            "info",
        )

    return _original_rebuild_element_with_history(
        data,
        element_id,
        valid_from,
        modified_by_id_str,
        doc_type=doc_type,
        log_callback=log_callback,
        log_queue=log_queue,
        answer_queue=answer_queue,
    )
