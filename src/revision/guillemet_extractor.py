"""Stack-based guillemet quote extractor for nested HTML."""

from __future__ import annotations

import re
from copy import copy
from bs4 import BeautifulSoup

_BLOCK_TAGS = ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "table", "tr")


def _top_level_blocks(html: str):
    soup = BeautifulSoup(html, "html.parser")
    blocks = [c for c in soup.children if getattr(c, "name", None) in _BLOCK_TAGS]
    if not blocks:
        body = soup.find("body")
        root = body if body is not None else soup
        blocks = [c for c in root.children if getattr(c, "name", None) in _BLOCK_TAGS]
    if not blocks:
        blocks = soup.find_all(list(_BLOCK_TAGS))
    return blocks


def _iter_text_nodes(blocks):
    for block in blocks:
        for node in block.find_all(string=True):
            yield block, node


class GuillemetExtractor:
    """Extract HTML blocks enclosed in exterior guillemet quotes «...>.

    Combines heuristic bounds detection with stack-based quote removal.
    """

    @staticmethod
    def _find_exterior_bounds(blocks):
        """Find (start_block, end_block) of exterior quoted region.

        Uses heuristics:
        - Start: first block whose text (after lstrip) starts with «
        - End: last block whose text ends with » (after stripping trailing punctuation)
        """
        start_block = None
        for block in blocks:
            text = block.get_text(strip=True)
            if text.startswith("«"):
                start_block = block
                break

        if start_block is None:
            return None, None

        end_block = None
        for block in reversed(blocks):
            text = block.get_text(strip=True)
            tail = re.sub(r"[\s;,.!?…]+$", "", text.rstrip())
            if tail.endswith("»"):
                end_block = block
                break

        return start_block, end_block

    @staticmethod
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
        for node in reversed(list(selected[-1].find_all(string=True))):
            value = str(node)
            pos = value.rfind("»")
            if pos >= 0:
                final_node, final_pos = node, pos
                break
        if final_node is None:
            return None

        nodes = []
        for block in selected:
            nodes.extend(block.find_all(string=True))
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

    @staticmethod
    def _remove_exterior_quotes(selected):
        """Remove exterior opening « and closing » with surrounding punctuation."""
        if not selected:
            return selected

        start_block = selected[0]
        end_block = selected[-1]

        # Remove first exterior « (must be first non-whitespace char in start_block)
        for block, node in _iter_text_nodes([start_block]):
            text = str(node)
            pos = next((i for i, ch in enumerate(text) if not ch.isspace()), None)
            if pos is not None and text[pos] == "«":
                node.replace_with(text[:pos] + text[pos + 1 :])
                break

        # Remove last exterior » ONLY if it is actually the outer closing quote
        candidate = GuillemetExtractor._find_final_outer_quote(selected)
        if candidate is not None:
            node, quote_pos = candidate
            value = str(node)
            before = value[:quote_pos]
            after = value[quote_pos + 1 :]
            after = re.sub(r"^[\s;,.!?…]+", "", after)
            node.replace_with(before + after)

        return selected

    @classmethod
    def extract(cls, html, log_callback=None):
        """Extract exterior quoted HTML block."""
        if not html or not html.strip():
            return None

        if "«" not in html or "»" not in html:
            return None

        blocks = _top_level_blocks(html)
        if not blocks:
            return None

        start_block, end_block = cls._find_exterior_bounds(blocks)

        if start_block is None:
            return html.strip()

        # Determine which blocks to extract
        if end_block is None:
            end_block = blocks[-1]

        start_idx = blocks.index(start_block)
        end_idx = blocks.index(end_block)
        selected = [copy(b) for b in blocks[start_idx : end_idx + 1]]

        cls._remove_exterior_quotes(selected)

        result = "\n".join(str(b) for b in selected if str(b).strip()).strip()
        result = re.sub(r";{2,}", ";", result)

        if log_callback:
            log_callback(
                f"  [QUOTE EXTRACT] stack: {len(result)} chars from {len(html)}",
                "source",
            )
        return result


def _parse_requested_indices(range_str):
    result = set()
    for part in (range_str or "").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            try:
                a, b = (int(x.strip()) for x in part.split("-", 1))
                if b < a:
                    a, b = b, a
                result.update(range(a, b + 1))
            except ValueError:
                continue
        elif part.isdigit():
            result.add(int(part))
    return sorted(result)


def extract_paragraphs_by_indices_robust(html, range_str, log_callback=None):
    """Extract specific paragraphs from within the exterior quoted region."""
    if not html:
        return ""

    range_str = (range_str or "").strip().lower()
    if range_str and any(tag in range_str for tag in ("<p", "<div", "<table")):
        range_str = "all"

    blocks = _top_level_blocks(html)
    if not blocks:
        return html.strip()

    start_block, end_block = GuillemetExtractor._find_exterior_bounds(blocks)

    if start_block is None:
        if range_str in ("", "all"):
            return html.strip()
        indices = _parse_requested_indices(range_str)
        pairs = [(i - 1, blocks[i - 1]) for i in indices if 1 <= i <= len(blocks)]
        if not pairs:
            return ""
        selected = [copy(b) for _, b in pairs]
        result = "\n".join(str(b) for b in selected if str(b).strip()).strip()
        return result

    if end_block is None:
        end_block = blocks[-1]

    start_idx = blocks.index(start_block)
    end_idx = blocks.index(end_block)
    quoted_blocks = blocks[start_idx : end_idx + 1]

    if range_str in ("", "all"):
        selected = [copy(b) for b in quoted_blocks]
        GuillemetExtractor._remove_exterior_quotes(selected)
        result = "\n".join(str(b) for b in selected if str(b).strip()).strip()
        if log_callback:
            log_callback(
                f"  [QUOTE EXTRACT] robust: все исходные блоки, результат {len(result)} симв. из {len(html)}",
                "source",
            )
        return result

    # Extract specific paragraphs from within the quoted region
    indices = _parse_requested_indices(range_str)
    pairs = [
        (i - 1, quoted_blocks[i - 1])
        for i in indices
        if 1 <= i <= len(quoted_blocks)
    ]
    if not pairs:
        return ""

    selected = [copy(b) for _, b in pairs]
    GuillemetExtractor._remove_exterior_quotes(selected)
    result = "\n".join(str(b) for b in selected if str(b).strip()).strip()
    if log_callback:
        log_callback(
            f"  [QUOTE EXTRACT] robust: запрошены исходные блоки {','.join(str(i+1) for i, _ in pairs)}, результат {len(result)} симв.",
            "source",
        )
    return result


def extract_quoted_html_robust(html, log_callback=None):
    """Public API: extract exterior quoted HTML using stack-based parser."""
    return GuillemetExtractor.extract(html, log_callback=log_callback)
