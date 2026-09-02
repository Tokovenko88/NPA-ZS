"""Сравнение редакций НПА: документ проекта против документа правовой системы.

Модуль решает задачу контроля качества результата ревизионного пайплайна:

* читает RTF/DOCX/DOC/HTML и представляет их в виде «структурных блоков»;
* выделяет структурные элементы, примечания и даты вступления в силу;
* посимвольно сравнивает тексты (посимвольный diff по каждому элементу);
* в режиме ``agent`` классифицирует причины расхождений через LLM
  (исходная редакция / внесение изменений / разная имплементация / техническая
  правка) и подтягивает из JSON-базы тексты изменяющих НПА;
* формирует отчёт в формате Markdown.

Публичный API:

.. code-block:: python

    from npazs.compare import run_compare, CompareOptions, CompareResult

Запуск графического интерфейса — :mod:`npazs.compare.gui`:

.. code-block:: python

    from npazs.compare.gui import main

Для чтения файлов используются только библиотеки, уже подтверждённые в
``requirements.txt``: ``lxml``/``bs4`` для DOCX и HTML; RTF и DOC разбираются
собственными парсерами (без внешних зависимостей). LLM-часть переиспользует
:mod:`npazs.revision.ai_utils`.
"""

from __future__ import annotations

from .converters import (
    Block,
    Document,
    detect_format,
    parse_doc_bytes,
    parse_docx_bytes,
    parse_rtf_bytes,
    read_document,
)
from .differ import DiffRecord, compare_elements
from .normalizer import (
    Note,
    extract_notes,
    normalize_block,
    normalize_text,
    parse_note,
)
from .npa_resolver import (
    clean_number,
    extract_change_text,
    find_npa_document,
    find_npa_files,
    get_full_document_text,
    get_original_element_text,
)
from .report_builder import build_diffs_report, build_notes_report, build_report
from .runner import CompareOptions, CompareResult, run_compare
from .tree import Element, build_elements, path_key, path_text

__all__ = [
    'Block',
    'CompareOptions',
    'CompareResult',
    'DiffRecord',
    'Document',
    'Element',
    'Note',
    'build_diffs_report',
    'build_elements',
    'build_notes_report',
    'build_report',
    'clean_number',
    'compare_elements',
    'detect_format',
    'extract_change_text',
    'extract_notes',
    'find_npa_document',
    'find_npa_files',
    'get_full_document_text',
    'get_original_element_text',
    'normalize_block',
    'normalize_text',
    'parse_doc_bytes',
    'parse_docx_bytes',
    'parse_note',
    'parse_rtf_bytes',
    'path_key',
    'path_text',
    'read_document',
    'run_compare',
]