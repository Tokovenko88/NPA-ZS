"""Модели данных модуля AI-пост-анализа."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PostAnalysisOptions:
    """Параметры запуска пост-анализа."""

    result_path: str = ''
    original_path: str = ''
    change_path: str = ''
    work_json_path: str = ''
    output_path: str = ''
    model: str = ''
    backend: str = ''
    extra_options: str = ''


@dataclass
class PostAnalysisResult:
    """Итог выполнения пост-анализа."""

    status: str = ''
    checked: int = 0
    issues: int = 0
    report_path: str = ''
    corrected_path: str = ''
    output_path: str = ''
    errors: list[str] = field(default_factory=list)
