"""Этап 1 — анализ утраты силы (revocation analysis).

Назначение
----------
Найти в изменяющем НПА указания об утрате силы, относящиеся к целевому НПА,
и определить дату, с которой сила утрачивается.

Промпт: ``data/prompts/prompt_1.md``.
Реализация: ``AiPipelineMixin._stage1_deletion_analysis``
(:mod:`npazs.pipeline.orchestrator`).

Подставляемые значения промпта
------------------------------
``{date_pub}``
    Дата публикации изменяющего НПА.
``{law_number}``
    Номер изменяющего НПА.
``{doc_text}``
    Полный HTML-текст изменяющего НПА.

Формат ответа модели
--------------------
JSON-массив объектов (или ``null``, если указаний нет)::

    [
      {
        "structural_element": "Статья 2",
        "structural_element_for_delete": "law",
        "valid_from": "01.01.2026"
      }
    ]

``structural_element``
    Где в **изменяющем** НПА находится указание об утрате силы.
``structural_element_for_delete``
    Что именно утрачивает силу в **целевом** НПА. Значение ``"law"`` означает
    утрату силы всего документа.
``valid_from``
    Дата, с которой элемент/документ утрачивает силу, формат ``DD.MM.YYYY``.

Применение результата
---------------------
Для каждой записи активная ревизия целевого элемента закрывается
(``valid_to = valid_from - 1 день``) и помечается ``not_valid``. Новая ревизия
при утрате силы НЕ создаётся — элемент просто перестаёт действовать.

Пустой ответ (``null``/``[]``) — нормальная ситуация: большинство изменяющих
НПА ничего не отменяют. Этап тихо пропускается.
"""

from __future__ import annotations

from typing import Any, Optional

STAGE_NUMBER = 1
STAGE_NAME = 'Анализ утраты силы'
PROMPT_STAGE = 1
MIXIN_METHOD = '_stage1_deletion_analysis'

#: Ключи, ожидаемые в каждом объекте ответа этапа.
RESULT_KEYS = ('structural_element', 'structural_element_for_delete', 'valid_from')


def run(
    app: Any,
    final_text: str,
    model: str,
    extra_options: Optional[dict] = None,
    pub_date_str: str = '',
    original_law_number: str = '',
):
    """Выполнить этап 1 для приложения ``app``.

    ``app`` — экземпляр класса, в который подмешан
    :class:`npazs.pipeline.orchestrator.AiPipelineMixin` (обычно
    :class:`npazs.ui.revision_app.App`). Обёртка не дублирует логику, а лишь
    даёт стабильную точку входа с говорящим именем.
    """
    return getattr(app, MIXIN_METHOD)(
        final_text,
        model,
        extra_options,
        pub_date_str,
        original_law_number,
    )


def validate_result(result: Any) -> list[str]:
    """Проверить структуру ответа этапа. Вернуть список замечаний."""
    problems: list[str] = []
    if result in (None, '', [], {}):
        return problems
    if not isinstance(result, list):
        return [f'Ожидался список, получено {type(result).__name__}']
    for index, item in enumerate(result):
        if not isinstance(item, dict):
            problems.append(f'[{index}] ожидался объект, получено {type(item).__name__}')
            continue
        for key in RESULT_KEYS:
            if key not in item:
                problems.append(f'[{index}] отсутствует обязательное поле "{key}"')
    return problems


__all__ = [
    'STAGE_NUMBER',
    'STAGE_NAME',
    'PROMPT_STAGE',
    'MIXIN_METHOD',
    'RESULT_KEYS',
    'run',
    'validate_result',
]
