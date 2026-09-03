"""Тесты отбора free-моделей Kilo Gateway для GUI сравнения."""

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "npazs_bootstrap", _ROOT / "src" / "bootstrap.py"
)
assert _spec is not None and _spec.loader is not None
_bootstrap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bootstrap)
_bootstrap.bootstrap()

from npazs.compare.gui import _filter_free_models


def test_keeps_only_free_marked_ids():
    payload = {
        'data': [
            {'id': 'provider:paid-fast', 'name': 'Paid Fast'},
            {'id': 'provider:free-turbo', 'name': 'Free Turbo'},
            {'id': 'google/gemini-2.5-flash:free', 'name': 'Gemini 2.5 Flash'},
        ]
    }
    assert _filter_free_models(payload) == [
        'google/gemini-2.5-flash:free',
        'provider:free-turbo',
    ]


def test_recognizes_free_in_name_only():
    payload = {'data': [{'id': 'meituan:longcat', 'name': 'LongCat 2.0 (free)'}]}
    assert _filter_free_models(payload) == ['meituan:longcat']


def test_keeps_auto_free():
    payload = {'data': [{'id': 'openrouter/auto:free', 'name': 'Auto Free'}]}
    assert _filter_free_models(payload) == ['openrouter/auto:free']


def test_deduplicates_and_sorts():
    payload = {
        'data': [
            {'id': 'provider:b', 'name': 'B (free)'},
            {'id': 'provider:a', 'name': 'A (free)'},
            {'id': 'provider:b', 'name': 'B (free)'},
        ]
    }
    assert _filter_free_models(payload) == ['provider:a', 'provider:b']


def test_falls_back_to_known_ids_without_free_marker():
    # Если API не помечает free в id/названии, используются известные id.
    known = ['Tencent: Hy3 (free)', 'Auto Free']
    payload = {'data': [{'id': 'Tencent: Hy3 (free)', 'name': 'Hy3'}]}
    assert _filter_free_models(payload, known=known) == ['Tencent: Hy3 (free)']


def test_known_ids_match_case_insensitively():
    known = ['Tencent: Hy3 (free)', 'Auto Free']
    payload = {'data': [{'id': 'tencent: hy3 (free)', 'name': 'Hy3'}]}
    assert _filter_free_models(payload, known=known) == ['tencent: hy3 (free)']


def test_skips_non_dict_entries():
    payload = {'data': [None, 'oops', {'id': 'poolside:laguna:free', 'name': 'Laguna'}]}
    assert _filter_free_models(payload) == ['poolside:laguna:free']


def test_empty_payload_returns_empty_list():
    assert _filter_free_models({'data': []}) == []
    assert _filter_free_models({}) == []
    assert _filter_free_models([]) == []
    assert _filter_free_models(None) == []