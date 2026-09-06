"""Модуль AI-пост-анализа внесённых изменений.

Обёртка над :mod:`npazs.revision.post_analysis` для запуска
автоматического ИИ-контроля уже готового результата внесения изменений.
"""

from .report_builder import build_post_analysis_report
from .runner import PostAnalysisOptions, PostAnalysisResult, run_post_analysis_standalone

__all__ = [
    'PostAnalysisOptions',
    'PostAnalysisResult',
    'build_post_analysis_report',
    'run_post_analysis_standalone',
]
