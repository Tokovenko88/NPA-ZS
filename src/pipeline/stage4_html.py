"""Этап 4 — применение текстовых правок к HTML элемента.

Назначение
----------
Для каждого изменения типа ``change`` (см. :mod:`npazs.pipeline.stage3_extraction`)
взять текущий HTML целевого элемента, применить к нему описание правки и
получить новый HTML вместе с подсветками изменённых фрагментов
(``highlights``).

Промпт: ``data/prompts/prompt_4.md``.

Особенность реализации
----------------------
В отличие от этапов 1-3, у этапа 4 нет отдельного метода ``_stage4_*``.
Исторически он встроен в применение изменений: промпт вызывается внутри
``apply_grouped_changes`` (:mod:`npazs.revision.change_applier`), которому
``PROMPT_4`` передаётся аргументом ``prompt4``. Ответ модели разбирается
функцией ``parse_ai_response_for_prompt4``
(:mod:`npazs.revision.html_utils`).

Такое устройство сохранено намеренно: правка текста и создание ревизии должны
происходить в одной транзакции, иначе при отказе модели элемент останется с
закрытой старой ревизией и без новой.

Подставляемые значения промпта
------------------------------
``{element_html}``
    Текущий HTML активной ревизии элемента.
``{description}``
    Описание изменения из этапа 3.

Формат ответа модели
--------------------
Ожидается HTML либо JSON-объект с полями ``html``/``text`` и ``highlights``.
Нормализация «сырых» ответов (обрамляющие ``` ```-блоки, JSON-обёртки,
``<thinking>``-теги) выполняется ``normalize_ai_html_response``.

``highlights`` — список фрагментов для визуальной подсветки правок на сайте;
позиции нормализуются ``_normalize_highlights_positions``
(:mod:`npazs.revision.ui_utils`), а для таблиц дополнительно корректируются
``_correct_table_highlights`` (:mod:`npazs.revision.html_utils`).

Инвариант
---------
Этап 4 **не создаёт** ревизий и **не меняет** структуру дерева. Он возвращает
только новый HTML и highlights; всё остальное делает
:mod:`npazs.revision.change_applier`.
"""

from __future__ import annotations

from typing import Any, Optional

STAGE_NUMBER = 4
STAGE_NAME = 'Применение правок к HTML'
PROMPT_STAGE = 4

#: Этап встроен в применение изменений; отдельного метода-миксина нет.
MIXIN_METHOD = None

#: Функции, реально выполняющие работу этапа.
IMPLEMENTED_BY = (
    'npazs.revision.change_applier.apply_grouped_changes',
    'npazs.revision.html_utils.parse_ai_response_for_prompt4',
)

#: Типы изменений, для которых этап 4 обязателен.
APPLIES_TO_TYPES = ('change',)


def get_prompt() -> str:
    """Вернуть текст промпта этапа 4."""
    from npazs.pipeline.prompts import get_prompt as _get_prompt

    return _get_prompt(PROMPT_STAGE)


def render_prompt(element_html: str, description: str) -> str:
    """Собрать готовый промпт этапа 4 для одного элемента."""
    from npazs.pipeline.prompts import render

    return render(
        get_prompt(),
        {'element_html': element_html, 'description': description},
    )


def parse_response(response_text: str, change_description: str = '', log_callback=None):
    """Разобрать ответ модели: вернуть ``(html, highlights)``.

    Тонкая обёртка над ``npazs.revision.html_utils.parse_ai_response_for_prompt4``.
    """
    from npazs.revision.html_utils import parse_ai_response_for_prompt4

    return parse_ai_response_for_prompt4(response_text, change_description, log_callback)


def apply(
    element: Any,
    changes: Any,
    valid_from: str,
    change_data: Any,
    data: Any,
    model: str,
    prompt4: Optional[str] = None,
    **kwargs: Any,
):
    """Применить сгруппированные изменения к элементу (включая этап 4).

    Делегирует в ``npazs.revision.change_applier.apply_grouped_changes``.
    Если ``prompt4`` не передан, берётся промпт из ``data/prompts/prompt_4.md``.
    """
    from npazs.revision.change_applier import apply_grouped_changes

    return apply_grouped_changes(
        element,
        changes,
        valid_from,
        change_data,
        data,
        model,
        prompt4 if prompt4 is not None else get_prompt(),
        **kwargs,
    )


__all__ = [
    'STAGE_NUMBER',
    'STAGE_NAME',
    'PROMPT_STAGE',
    'MIXIN_METHOD',
    'IMPLEMENTED_BY',
    'APPLIES_TO_TYPES',
    'get_prompt',
    'render_prompt',
    'parse_response',
    'apply',
]
