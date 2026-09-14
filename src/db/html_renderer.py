"""HTML renderer for NPA documents - generates static HTML at import time."""
from __future__ import annotations

import re
import html
from typing import Dict, List, Optional, Tuple, Any
from datetime import date, datetime

from npazs.db.connection import DBConnection


class NpaHtmlRenderer:
    """Renders NPA documents to HTML for a specific date."""

    def __init__(self, db: DBConnection):
        self.db = db

    def render_npa_html(self, npa_id: int, as_of_date: str) -> str:
        """Generate full HTML for an NPA document on a specific date."""
        npa_data = self.db.fetch_one(
            "SELECT * FROM npa_base WHERE npa_id = %s", (npa_id,)
        )
        if not npa_data:
            return f"<!-- NPA {npa_id} not found -->"

        head_rev = self.db.fetch_one(
            "SELECT npa_title FROM npa_head_revision "
            "WHERE npa_id = %s AND (valid_from <= %s OR valid_from IS NULL) "
            "AND (valid_to IS NULL OR valid_to >= %s) "
            "ORDER BY valid_from DESC LIMIT 1",
            (npa_id, as_of_date, as_of_date)
        )
        doc_title = head_rev['npa_title'] if head_rev else npa_data.get('npa_number', '')

        items = self._load_items_tree(npa_id, as_of_date)

        html_parts = []
        html_parts.append(
            f'<div class="npa-document" data-npa-id="{npa_id}" '
            f'data-view-date="{as_of_date}">'
        )
        html_parts.append(f'  <h1 class="npa-title">{html.escape(doc_title)}</h1>')

        rendered_ids = set()
        for item in items:
            if not item.get('parent_id') and item.get('id') not in rendered_ids:
                html_parts.append(
                    self._render_item(item, items, as_of_date, rendered_ids)
                )

        html_parts.append('</div>')
        return '\n'.join(html_parts)
    def _load_items_tree(self, npa_id: int, as_of_date: str) -> List[Dict]:
        """Load all items with their active revisions for the date."""
        items = self.db.fetch_all(
            "SELECT * FROM npa_item WHERE npa_id = %s ORDER BY sort_order, id",
            (npa_id,)
        )

        result = []
        for item in items:
            rev = self.db.fetch_one(
                "SELECT * FROM npa_item_revision "
                "WHERE item_internal_id = %s "
                "AND (valid_from <= %s OR valid_from IS NULL) "
                "AND (valid_to IS NULL OR valid_to >= %s) "
                "ORDER BY valid_from DESC LIMIT 1",
                (item['id'], as_of_date, as_of_date)
            )
            if not rev:
                continue

            head = self.db.fetch_one(
                "SELECT head_text FROM npa_item_head_revision "
                "WHERE item_internal_id = %s "
                "AND (valid_from <= %s OR valid_from IS NULL) "
                "AND (valid_to IS NULL OR valid_to >= %s) "
                "ORDER BY valid_from DESC LIMIT 1",
                (item['id'], as_of_date, as_of_date)
            )

            paragraphs = self.db.fetch_all(
                "SELECT * FROM npa_paragraph WHERE rev_id = %s ORDER BY sort_order",
                (rev['id'],)
            )

            item_data = {
                'id': item['id'],
                'item_id': item['item_id'],
                'item_type': item['item_type'],
                'item_number': item.get('item_number', ''),
                'parent_id': item.get('parent_id'),
                'sort_order': item.get('sort_order', 0),
                'head_text': head['head_text'] if head else '',
                'paragraphs': paragraphs,
                'valid_from': rev['valid_from'],
                'valid_to': rev['valid_to'],
                'is_expired': rev['valid_to'] and rev['valid_to'] < as_of_date,
            }
            result.append(item_data)

        return result
    def _render_item(self, item: Dict, all_items: List[Dict],
                     as_of_date: str, rendered_ids: set) -> str:
        """Render a single item and its children to HTML."""
        if item['id'] in rendered_ids:
            return ''
        rendered_ids.add(item['id'])

        item_type = item['item_type']
        item_number = item.get('item_number', '')
        head_text = item.get('head_text', '')
        paragraphs = item.get('paragraphs', [])

        type_labels = {
            'chapter': 'Глава',
            'section': 'Раздел',
            'article': 'Статья',
            'part': 'Часть',
            'point': 'Пункт',
            'subpoint': 'Подпункт',
            'appendix': 'Приложение',
            'preamble': 'Преамбула',
        }
        label = type_labels.get(item_type, '')

        html_parts = []
        html_parts.append(
            f'<div class="npa-item-block" data-item-type="{item_type}" '
            f'data-npa-item-id="{item["item_id"]}">'
        )

        if head_text and item_type in ('chapter', 'section', 'article', 'appendix'):
            display = f"{label} {item_number}. {head_text}" if item_number else f"{label}. {head_text}"
            html_parts.append(
                f'  <div class="npa-item-head-block"><p class="npa-doc-title">'
                f'<b>{html.escape(display)}</b></p></div>'
            )
        elif head_text:
            html_parts.append(
                f'  <div class="npa-item-head-block"><p class="npa-doc-title">'
                f'<b>{html.escape(head_text)}</b></p></div>'
            )

        for para in paragraphs:
            block_type = para.get('block_type', 'paragraph')
            if block_type == 'child_ref':
                ref_id = para.get('ref_item_internal_id')
                if ref_id:
                    child = next((i for i in all_items if i['id'] == ref_id), None)
                    if child and child['id'] not in rendered_ids:
                        html_parts.append(
                            self._render_item(child, all_items, as_of_date, rendered_ids)
                        )
            elif block_type == 'paragraph' and para.get('html_text'):
                html_parts.append(f'  {para["html_text"]}')
            elif block_type == 'table' and para.get('html_text'):
                html_parts.append(f'  <div class="npa-table">{para["html_text"]}</div>')

        children = [i for i in all_items
                    if i.get('parent_id') == item['id'] and i['id'] not in rendered_ids]
        children.sort(key=lambda x: x.get('sort_order', 0))
        for child in children:
            html_parts.append(
                self._render_item(child, all_items, as_of_date, rendered_ids)
            )

        html_parts.append('</div>')
        return '\n'.join(html_parts)
    def save_to_cache(self, npa_id: int, as_of_date: str, html_content: str) -> None:
        """Save rendered HTML to npa_rendered_cache table."""
        self.db.exec(
            "INSERT INTO npa_rendered_cache (npa_id, as_of_date, html_full, generated_at) "
            "VALUES (%s, %s, %s, NOW()) "
            "ON DUPLICATE KEY UPDATE html_full = VALUES(html_full), generated_at = NOW()",
            (npa_id, as_of_date, html_content)
        )

    def render_and_cache_all_dates(self, npa_id: int) -> int:
        """Render HTML for all unique valid_from dates of an NPA."""
        rows = self.db.fetch_all(
            "SELECT DISTINCT r.valid_from "
            "FROM npa_item_revision r "
            "JOIN npa_item i ON r.item_internal_id = i.id "
            "WHERE i.npa_id = %s ORDER BY r.valid_from",
            (npa_id,)
        )

        count = 0
        for row in rows:
            valid_from = row['valid_from']
            if isinstance(valid_from, date):
                date_str = valid_from.strftime('%Y-%m-%d')
            else:
                date_str = str(valid_from)

            html_content = self.render_npa_html(npa_id, date_str)
            self.save_to_cache(npa_id, date_str, html_content)
            count += 1

        return count