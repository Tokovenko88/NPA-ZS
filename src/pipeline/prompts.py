"""Работа с промптами AI-пайплайна NPA-ZS.

Промпты — файлы Markdown в ``data/prompts/``:

===========  ====================================  =====================================
Файл         Этап                                  Исходное имя в NPA-JSON-Processor
===========  ====================================  =====================================
prompt_1.md  Анализ утраты силы                    prompt_1_revocation_analysis.md
prompt_2.md  Даты и ретроактивные оговорки         prompt_2_dates_analysis.md
prompt_3.md  Извлечение изменений                  prompt_3_changes_extraction.md
prompt_4.md  Обработка текста/HTML                 prompt_4_text_processing.md
===========  ====================================  =====================================

Промпты содержат плейсхолдеры в фигурных скобках, например ``{date_pub}``,
``{law_number}``, ``{article_number}``, ``{doc_text}``, ``{element_html}``,
``{description}``.

Подстановка выполняется :func:`render` — она намеренно НЕ использует
``str.format``: тексты промптов содержат примеры JSON с фигурными скобками,
которые ``format`` попытался бы интерпретировать как поля и упал бы с
``KeyError``/``IndexError``. Вместо этого делается точная строковая замена
только известных плейсхолдеров.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Mapping

from npazs.constants import (
    PROMPT_1,
    PROMPT_2,
    PROMPT_3,
    PROMPT_4,
    PROMPT_FILES,
    PROMPTS_DIR,
    load_prompt,
    load_prompt_from_file,
)

#: Промпты, загруженные при импорте (совместимо с историческим API).
PROMPTS: Dict[int, str] = {
    1: PROMPT_1,
    2: PROMPT_2,
    3: PROMPT_3,
    4: PROMPT_4,
}

#: Плейсхолдеры, встречающиеся в промптах проекта.
KNOWN_PLACEHOLDERS = (
    'date_pub',
    'law_number',
    'article_number',
    'doc_text',
    'element_html',
    'description',
    'base_law_date_pub',
    'original_law_number',
    'structural_element',
)

_PLACEHOLDER_RE = re.compile(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}')


def get_prompt(stage: int, *, reload: bool = False) -> str:
    """Вернуть текст промпта для этапа ``stage`` (1..4)."""
    if stage not in PROMPT_FILES:
        raise ValueError(f'Неизвестный этап промпта: {stage!r} (ожидается 1..4)')
    if reload or not PROMPTS.get(stage):
        PROMPTS[stage] = load_prompt(stage)
    return PROMPTS[stage]


def render(template: str, values: Mapping[str, Any]) -> str:
    """Подставить значения плейсхолдеров в текст промпта.

    Выполняется буквальная замена ``{name}`` -> ``str(value)`` только для тех
    ключей, что переданы в ``values``. Любые другие фигурные скобки (примеры
    JSON внутри промпта) остаются нетронутыми.
    """
    result = template
    for key, value in values.items():
        result = result.replace('{' + key + '}', '' if value is None else str(value))
    return result


def render_stage(stage: int, values: Mapping[str, Any], *, strict: bool = False) -> str:
    """Загрузить промпт этапа и подставить значения.

    При ``strict=True`` бросает :class:`ValueError`, если после подстановки в
    тексте остались известные проекту плейсхолдеры — это надёжно отлавливает
    опечатки в именах ключей.
    """
    text = render(get_prompt(stage), values)
    if strict:
        leftover = sorted(set(find_placeholders(text)) & set(KNOWN_PLACEHOLDERS))
        if leftover:
            raise ValueError(
                f'В промпте этапа {stage} не заполнены плейсхолдеры: {", ".join(leftover)}'
            )
    return text


def find_placeholders(text: str) -> Iterable[str]:
    """Вернуть имена всех ``{...}``-плейсхолдеров, найденных в тексте."""
    return _PLACEHOLDER_RE.findall(text or '')


def reload_all() -> Dict[int, str]:
    """Перечитать все промпты с диска (после правки файлов в ``data/prompts``)."""
    for stage in PROMPT_FILES:
        PROMPTS[stage] = load_prompt(stage)
    return dict(PROMPTS)


def prompt_status() -> Dict[int, bool]:
    """Карта «этап -> промпт непустой». Используется командой ``validate``."""
    return {stage: bool(get_prompt(stage)) for stage in sorted(PROMPT_FILES)}


__all__ = [
    'PROMPTS',
    'PROMPTS_DIR',
    'PROMPT_FILES',
    'KNOWN_PLACEHOLDERS',
    'PROMPT_1',
    'PROMPT_2',
    'PROMPT_3',
    'PROMPT_4',
    'get_prompt',
    'render',
    'render_stage',
    'find_placeholders',
    'reload_all',
    'prompt_status',
    'load_prompt',
    'load_prompt_from_file',
]
