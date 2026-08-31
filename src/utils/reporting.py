"""Сборка отчёта о прогоне конвейера NPA-ZS в формате Markdown.

Формат отчёта унаследован от ``06_work_tools/report.md`` исходного проекта и
описан в ``AGENTS.md`` (раздел «Отчёт»). Отчёт сохраняется в
``data/work_tools/report.md``.

Использование::

    from npazs.utils.reporting import RunReport

    report = RunReport(source='768-ЗС', target='110-ЗС')
    report.stage(1, found=2, applied=2)
    report.stage(3, found=17, applied=16, errors=['Статья 5 часть 2: элемент не найден'])
    report.set_change_counts({'add': 3, 'delete': 1, 'change': 10, 'new_redaction': 2})
    report.save()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

__all__ = ['StageResult', 'RunReport', 'render_validation_report']

#: Человекочитаемые названия этапов.
STAGE_TITLES = {
    1: 'Утрата силы',
    2: 'Даты и ретроактивность',
    3: 'Изменения',
    4: 'HTML-обработка',
    5: 'Пересборка и верификация',
}


@dataclass
class StageResult:
    """Итог одного этапа конвейера."""

    number: int
    found: int = 0
    applied: int = 0
    skipped: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def title(self) -> str:
        return STAGE_TITLES.get(self.number, f'Этап {self.number}')

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass
class RunReport:
    """Отчёт о прогоне: этапы, счётчики изменений, итоговый статус."""

    source: str = ''
    target: str = ''
    started_at: datetime = field(default_factory=datetime.now)
    stages: Dict[int, StageResult] = field(default_factory=dict)
    change_counts: Dict[str, int] = field(default_factory=dict)
    output_path: str = ''
    notes: List[str] = field(default_factory=list)

    # ------------------------------------------------------------------ ввод
    def stage(
        self,
        number: int,
        *,
        found: int = 0,
        applied: int = 0,
        skipped: int = 0,
        errors: Optional[Sequence[str]] = None,
    ) -> StageResult:
        """Записать (или обновить) итог этапа."""
        result = StageResult(
            number=number,
            found=found,
            applied=applied,
            skipped=skipped,
            errors=list(errors or []),
        )
        self.stages[number] = result
        return result

    def set_change_counts(self, counts: Dict[str, int]) -> None:
        """Задать счётчики изменений по типам (``add``/``delete``/...)."""
        self.change_counts = dict(counts)

    def note(self, text: str) -> None:
        """Добавить произвольное замечание в отчёт."""
        self.notes.append(text)

    # --------------------------------------------------------------- свойства
    @property
    def total_errors(self) -> int:
        return sum(len(stage.errors) for stage in self.stages.values())

    @property
    def ok(self) -> bool:
        return self.total_errors == 0

    @property
    def status(self) -> str:
        return 'Успешно' if self.ok else 'С ошибками'

    # ---------------------------------------------------------------- вывод
    def render(self) -> str:
        """Собрать Markdown-текст отчёта."""
        lines: List[str] = [
            '# Отчёт об обработке НПА',
            '',
            '## Исходные данные',
            '',
            f'- Изменяющий НПА: {self.source or "—"}',
            f'- Целевой НПА: {self.target or "—"}',
            f'- Начало прогона: {self.started_at.strftime("%d.%m.%Y %H:%M:%S")}',
            '',
        ]

        for number in sorted(self.stages):
            stage = self.stages[number]
            lines.append(f'## Этап {number}: {stage.title}')
            lines.append('')
            lines.append(f'- Найдено: {stage.found}')
            lines.append(f'- Применено: {stage.applied}')
            if stage.skipped:
                lines.append(f'- Пропущено: {stage.skipped}')
            if number == 3 and self.change_counts:
                for change_type in ('add', 'delete', 'change', 'new_redaction'):
                    if change_type in self.change_counts:
                        lines.append(f'  - {change_type}: {self.change_counts[change_type]}')
            if stage.errors:
                lines.append('- Ошибки:')
                lines.extend(f'  - {error}' for error in stage.errors)
            else:
                lines.append('- Ошибки: нет')
            lines.append('')

        if self.notes:
            lines.append('## Замечания')
            lines.append('')
            lines.extend(f'- {note}' for note in self.notes)
            lines.append('')

        lines.append('## Итог')
        lines.append('')
        lines.append(f'- Статус: {self.status}')
        lines.append(f'- Всего ошибок: {self.total_errors}')
        lines.append(f'- Итоговый файл: {self.output_path or "data/output/result_npa.json"}')
        lines.append('')

        return '\n'.join(lines)

    def save(self, path: Optional[str] = None) -> Path:
        """Сохранить отчёт (по умолчанию в ``data/work_tools/report.md``)."""
        from npazs.utils.file_ops import write_text_atomic

        if path is None:
            from npazs.constants import WORK_TOOLS_DIR

            path = str(Path(WORK_TOOLS_DIR) / 'report.md')
        return write_text_atomic(path, self.render())


def render_validation_report(report: Any, *, title: str = 'Отчёт валидации') -> str:
    """Отрендерить :class:`npazs.utils.validation.ValidationReport` в Markdown."""
    lines = [f'# {title}', '', f'- {report.summary()}', '']

    if report.errors:
        lines.append('## Ошибки')
        lines.append('')
        lines.extend(f'- {issue}' for issue in report.errors)
        lines.append('')

    if report.warnings:
        lines.append('## Предупреждения')
        lines.append('')
        lines.extend(f'- {issue}' for issue in report.warnings)
        lines.append('')

    if not report.issues:
        lines.append('Замечаний нет.')
        lines.append('')

    return '\n'.join(lines)
