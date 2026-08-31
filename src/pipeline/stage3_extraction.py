"""Этап 3 — извлечение перечня изменений.

Назначение
----------
Разобрать текст изменяющего НПА и получить плоский список операций, которые
нужно применить к целевому НПА.

Промпт: ``data/prompts/prompt_3.md`` (самый большой промпт проекта).
Реализация: ``AiPipelineMixin._stage3_changes_extraction`` и вспомогательный
``AiPipelineMixin._process_element_for_changes``
(:mod:`npazs.pipeline.orchestrator`).

Промпт выполняется **по одной статье** изменяющего НПА.

Формат ответа модели
--------------------
::

    [
      {
        "revision_number": "1) а)",
        "structural_element": "Статья 3 часть 2 пункт 1",
        "type": "new_redaction",
        "description": "<p>1) новый текст пункта;</p>",
        "new": null
      }
    ]

``revision_number``
    Иерархия подпунктов **изменяющего** НПА («адрес» изменения в его тексте).
    Используется для разрешения ``modified_by_id`` и для отчётов.
``structural_element``
    Целевой элемент в **целевом** НПА.
``type``
    Одно из :data:`CHANGE_TYPES`.
``description``
    Описание изменения либо готовый HTML (для ``add`` / ``new_redaction``).
``new``
    Только для ``add``: тип и номер нового элемента (например ``"пункт 4"``).

Типы изменений
--------------
``add``
    Добавить новый структурный элемент. Родитель получает ``child_ref`` в теле,
    у нового элемента создаётся ревизия с ``mod_type = "add"``.
``delete``
    Признать элемент недействующим: закрыть активную ревизию, пометить
    ``not_valid``. Физического удаления узла не происходит — история сохраняется.
``change``
    Частичная правка текста. Требует этапа 4 (см.
    :mod:`npazs.pipeline.stage4_html`).
``new_redaction``
    Полная замена текста элемента новой редакцией.

Диапазоны
---------
Изменения вида «пункты 1-3 изложить в новой редакции» разворачиваются в
отдельные операции функцией ``split_range_changes``
(:mod:`npazs.revision.ui_utils`) до применения.

Верификация извлечённого HTML
-----------------------------
Для ``add`` и ``new_redaction`` HTML, предложенный моделью, сверяется с
детерминированным извлечением из исходного текста
(:mod:`npazs.revision.quote_extraction`,
:mod:`npazs.revision.guillemet_extractor`). При расхождении вызывается диалог
:mod:`npazs.ui.dialogs.extraction_conflict`, и оператор выбирает верный вариант.
Молча принять вариант модели нельзя — это ключевая гарантия качества.
"""

from __future__ import annotations

from typing import Any, Optional

STAGE_NUMBER = 3
STAGE_NAME = 'Извлечение изменений'
PROMPT_STAGE = 3
MIXIN_METHOD = '_stage3_changes_extraction'
HELPER_METHOD = '_process_element_for_changes'

#: Допустимые значения поля ``type``.
CHANGE_TYPES = ('add', 'delete', 'change', 'new_redaction')

#: Типы, для которых обязателен этап 4 (обработка HTML моделью).
TYPES_REQUIRING_STAGE4 = ('change',)

#: Типы, для которых выполняется сверка извлечённого HTML с программным.
TYPES_REQUIRING_EXTRACTION_CHECK = ('add', 'new_redaction')

#: Обязательные ключи каждого объекта изменения.
RESULT_KEYS = ('revision_number', 'structural_element', 'type')


def run(
    app: Any,
    target_element: Any,
    model: str,
    extra_options: Optional[dict] = None,
    change_data: Any = None,
    manual_resolver: Any = None,
    stop_event: Any = None,
):
    """Выполнить этап 3 для приложения ``app``."""
    return getattr(app, MIXIN_METHOD)(
        target_element,
        model,
        extra_options,
        change_data,
        manual_resolver,
        stop_event,
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
            if not item.get(key):
                problems.append(f'[{index}] отсутствует обязательное поле "{key}"')
        change_type = item.get('type')
        if change_type and change_type not in CHANGE_TYPES:
            problems.append(
                f'[{index}] недопустимый type={change_type!r}; ожидается одно из {CHANGE_TYPES}'
            )
        if change_type == 'add' and not item.get('new'):
            problems.append(f'[{index}] для type="add" требуется поле "new"')
    return problems


def summarize(result: Any) -> dict:
    """Свести ответ этапа к счётчикам по типам изменений (для отчётов)."""
    counts = {change_type: 0 for change_type in CHANGE_TYPES}
    counts['unknown'] = 0
    if not isinstance(result, list):
        return counts
    for item in result:
        if not isinstance(item, dict):
            continue
        change_type = item.get('type')
        if change_type in counts:
            counts[change_type] += 1
        else:
            counts['unknown'] += 1
    return counts


__all__ = [
    'STAGE_NUMBER',
    'STAGE_NAME',
    'PROMPT_STAGE',
    'MIXIN_METHOD',
    'HELPER_METHOD',
    'CHANGE_TYPES',
    'TYPES_REQUIRING_STAGE4',
    'TYPES_REQUIRING_EXTRACTION_CHECK',
    'RESULT_KEYS',
    'run',
    'validate_result',
    'summarize',
]
