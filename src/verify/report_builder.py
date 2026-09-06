"""Генерация Markdown-отчёта AI-пост-анализа."""

from __future__ import annotations

from datetime import datetime, timezone

from .models import PostAnalysisResult

__all__ = ['build_post_analysis_report']


def build_post_analysis_report(result: PostAnalysisResult, raw: dict | None = None) -> str:
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    status = str(result.status or 'unknown').lower()
    if status == 'correct':
        headline = '✅ ИЗМЕНЕНИЯ ВНЕСЕНЫ КОРРЕКТНО'
    elif status == 'incorrect':
        headline = '❌ ВЫЯВЛЕНЫ ОШИБКИ ВНЕСЕНИЯ'
    elif status == 'skipped':
        headline = '⚠️ ПОСТ-АНАЛИЗ ПРОПУЩЕН'
    else:
        headline = '⚠️ ПОСТ-АНАЛИЗ НЕ ЗАВЕРШИЛСЯ ШТАТНО'

    lines = [
        '# Отчёт AI-пост-анализа внесения изменений',
        '',
        f'Сформирован: {now}',
        '',
        f'## {headline}',
        '',
        f'- Проверено изменений: {result.checked}',
        f'- Выявлено проблем: {result.issues}',
    ]
    if result.report_path:
        lines.append(f'- Подробный отчёт: `{result.report_path}`')
    if result.corrected_path:
        lines.append(f'- **Исправленный файл: `{result.corrected_path}`**')

    if result.errors:
        lines.extend(['', '## Ошибки', ''])
        for err in result.errors:
            lines.append(f'- {err}')

    if isinstance(raw, dict) and raw.get('summary'):
        lines.extend(['', '## Резюме ИИ-агента', '', str(raw.get('summary'))])

    lines.append('')
    return '\n'.join(lines)
