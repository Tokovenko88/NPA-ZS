"""Deterministic extraction of externally quoted Russian HTML."""

from __future__ import annotations
import re
from copy import copy
from bs4 import BeautifulSoup

from npazs.revision.guillemet_extractor import (
    GuillemetExtractor,
    _top_level_blocks,
    extract_quoted_html_robust,
    _parse_requested_indices,
)


_BLOCK_TAGS = ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "table", "tr")

_INLINE_EMPTY_TAGS = {
    "span", "i", "em", "b", "strong", "a", "u", "sub", "sup", "small", "font",
    "code", "mark",
}


def _strip_trailing_empty_inline(block):
    """Remove empty text nodes and inline elements at the tail of a block.

    A closing quote may live in its own inline node (``<span>»</span>``); after
    the quote is stripped the wrapper and the punctuation node are left empty
    (``<span></span>`` / ``""``) and must not survive into the extracted HTML.
    """
    if block is None:
        return
    while block.contents:
        last = block.contents[-1]
        name = getattr(last, "name", None)
        if name is None:
            # Empty text node produced by replacing a punct/quote node with "".
            if str(last) == "":
                last.extract()
                continue
            break
        if name in _INLINE_EMPTY_TAGS and not last.get_text(strip=True):
            last.decompose()
            continue
        break


def _text_nodes_in_order(block):
    return list(block.find_all(string=True))


def _remove_first_opening(block):
    """Remove `«` only when it is the first non-whitespace text character."""
    for node in _text_nodes_in_order(block):
        value = str(node)
        pos = next((i for i, ch in enumerate(value) if not ch.isspace()), None)
        if pos is None:
            continue
        if value[pos] != "«":
            return False
        node.replace_with(value[:pos] + value[pos + 1:])
        return True
    return False


def _find_final_outer_quote(selected):
    """Find the one final `»` eligible for removal.

    The candidate is the LAST `»` in the final selected block. Characters
    after it (such as `;`, `.`, whitespace, or HTML closing tags) do not stop
    it from being the candidate. Starting immediately before that candidate,
    scan backwards through the selected text stream. If the first quote found
    is `«`, the candidate is an inner closing quote and nothing is removed at
    the end. If the first quote found is `»`, the candidate is the outer
    closing quote. If there is no earlier quote, it is also removable.
    """
    final_node = None
    final_pos = None
    for node in reversed(_text_nodes_in_order(selected[-1])):
        value = str(node)
        pos = value.rfind("»")
        if pos >= 0:
            final_node, final_pos = node, pos
            break
    if final_node is None:
        return None

    nodes = []
    for block in selected:
        nodes.extend(_text_nodes_in_order(block))
    try:
        idx = nodes.index(final_node)
    except ValueError:
        return None

    value = str(final_node)
    for pos in range(final_pos - 1, -1, -1):
        if value[pos] in ("«", "»"):
            return None if value[pos] == "«" else (final_node, final_pos)

    for node in reversed(nodes[:idx]):
        text = str(node)
        for pos in range(len(text) - 1, -1, -1):
            if text[pos] in ("«", "»"):
                return None if text[pos] == "«" else (final_node, final_pos)

    return final_node, final_pos


def _remove_last_closing_and_suffix(selected):
    candidate = _find_final_outer_quote(selected)
    if candidate is None:
        return False

    node, quote_pos = candidate
    value = str(node)
    following_nodes = list(_text_nodes_in_order(selected[-1]))

    # Remove EXACTLY ONE character: the selected final outer `»`.
    # Everything before it, including every inner `»` and punctuation, remains.
    # Everything after it is removed as text; HTML tags themselves remain.
    node.replace_with(value[:quote_pos])
    after = False
    for text_node in following_nodes:
        if text_node is node:
            after = True
            continue
        if after:
            text_node.replace_with("")
    _strip_trailing_empty_inline(selected[-1])
    return True


def _strip_selected_boundaries(selected):
    if not selected:
        return
    _remove_first_opening(selected[0])
    _remove_last_closing_and_suffix(selected)


def _strip_attributes(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(True):
        tag.attrs = {}
    return str(soup)


def normalize_html_for_extraction_compare(html):
    if not html:
        return ()
    html = _strip_attributes(html)
    html = html.replace("\n", " ").replace("\r", " ")
    html = re.sub(r">\s+<", "><", html)
    html = re.sub(r"\s+", " ", html)
    soup = BeautifulSoup(html, "html.parser")
    blocks = [c for c in soup.children if getattr(c, "name", None) in _BLOCK_TAGS]
    if not blocks:
        blocks = soup.find_all(list(_BLOCK_TAGS))
    if not blocks:
        blocks = [soup]
    return tuple(
        (block.name or "root", str(block).strip()) for block in blocks
    )


def extraction_results_equal(program_html, ai_html):
    return normalize_html_for_extraction_compare(program_html) == normalize_html_for_extraction_compare(ai_html)


def patch_legacy_html_utils():
    from npazs.revision import html_utils
    html_utils._extract_quoted_html = extract_quoted_html_robust
    html_utils.extract_paragraphs_by_indices = extract_paragraphs_by_indices_robust
    return html_utils


def extract_paragraphs_by_indices_robust(html, range_str, log_callback=None):
    if not html:
        return ""
    range_str = (range_str or "").strip().lower()
    if range_str and any(tag in range_str for tag in ("<p", "<div", "<table")):
        range_str = "all"
    blocks = _top_level_blocks(html)
    if not blocks:
        return html.strip()
    if range_str in ("", "all"):
        extracted = extract_quoted_html_robust(html, log_callback)
        return extracted if extracted is not None else html.strip()
    indices = _parse_requested_indices(range_str)
    pairs = [(i - 1, blocks[i - 1]) for i in indices if 1 <= i <= len(blocks)]
    if not pairs:
        return ""
    selected = [copy(b) for _, b in pairs]
    _strip_selected_boundaries(selected)
    result = "\n".join(str(b) for b in selected if str(b).strip()).strip()
    if log_callback:
        log_callback(f"  [QUOTE EXTRACT] robust: запрошены исходные блоки {','.join(str(i+1) for i, _ in pairs)}, результат {len(result)} симв.", "source")
    return result
