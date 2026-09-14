"""Tests for the static HTML renderer (npa_rendered_cache generation).

Uses a fake DB connection so no MySQL is required.
"""
import importlib.util
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "npazs_bootstrap", _ROOT / "src" / "bootstrap.py"
)
assert _spec is not None and _spec.loader is not None
_bootstrap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bootstrap)
_bootstrap.bootstrap()

from npazs.db.html_renderer import NpaHtmlRenderer


class FakeDB:
    """Minimal stand-in for DBConnection: returns canned data."""

    def __init__(self, base=None, head=None, items=None, revisions=None,
                 paragraphs=None, heads=None, item_heads=None):
        self._base = base
        self._head = head
        self._items = items or []
        self._revisions = revisions or {}
        self._paragraphs = paragraphs or {}
        self._heads = heads or {}
        self.saved = []

    def fetch_one(self, sql, params=()):
        if "npa_base" in sql:
            return self._base
        if "npa_head_revision" in sql:
            return self._head
        if "npa_item_head_revision" in sql:
            # params (item_id, as_of, as_of) -> look up by item id
            return self._heads.get(params[0])
        if "npa_item_revision" in sql:
            return self._revisions.get(params[0])
        if "npa_item" in sql:
            return self._items[0] if self._items else None
        return None

    def fetch_all(self, sql, params=()):
        if sql.startswith("SELECT * FROM npa_item WHERE"):
            return self._items
        if "npa_paragraph" in sql:
            return self._paragraphs.get(params[0], [])
        if "DISTINCT r.valid_from" in sql:
            return [{'valid_from': date(2026, 1, 1)}]
        return []

    def exec(self, sql, params=()):
        self.saved.append((sql, params))


def _make_renderer():
    db = FakeDB(
        base={'npa_id': 1, 'npa_number': '896-ЗС'},
        head={'npa_title': 'О примере'},
        items=[
            {'id': 10, 'item_id': '1_article_1', 'item_type': 'article',
             'item_number': '1', 'parent_id': None, 'sort_order': 1},
            {'id': 20, 'item_id': '1_article_1_part_1', 'item_type': 'part',
             'item_number': '1.', 'parent_id': 10, 'sort_order': 1},
        ],
        revisions={
            10: {'id': 100, 'valid_from': '2026-01-01', 'valid_to': None},
            20: {'id': 200, 'valid_from': '2026-01-01', 'valid_to': None},
        },
        heads={
            10: {'head_text': 'Предмет регулирования'},
            20: None,
        },
        paragraphs={
            100: [
                {'block_type': 'paragraph', 'html_text': '<p>Текст абзаца.</p>',
                 'sort_order': 1},
                {'block_type': 'child_ref', 'ref_item_internal_id': 20,
                 'sort_order': 2},
            ],
            200: [],
        },
    )
    return db, NpaHtmlRenderer(db)


def test_render_npa_html_basic():
    db, renderer = _make_renderer()
    html = renderer.render_npa_html(1, '2026-01-01')
    assert 'npa-document' in html
    assert 'data-npa-id="1"' in html
    assert 'data-view-date="2026-01-01"' in html
    assert 'О примере' in html
    assert 'Текст абзаца.' in html
    assert 'data-item-type="article"' in html
    assert 'data-npa-item-id="1_article_1"' in html
    # child part rendered recursively
    assert 'data-npa-item-id="1_article_1_part_1"' in html


def test_render_missing_npa():
    db, renderer = _make_renderer()
    db._base = None
    html = renderer.render_npa_html(999, '2026-01-01')
    assert 'not found' in html


def test_render_and_cache_all_dates_saves():
    db, renderer = _make_renderer()
    count = renderer.render_and_cache_all_dates(1)
    assert count == 1
    assert len(db.saved) == 1
    sql, params = db.saved[0]
    assert 'npa_rendered_cache' in sql
    assert params[0] == 1
    assert params[1] == '2026-01-01'
    assert 'npa-document' in params[2]