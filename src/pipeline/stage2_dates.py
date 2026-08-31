"""Этап 2 — специальные даты вступления в силу и ретроактивные оговорки.

Назначение
----------
Найти в изменяющем НПА:

* **специальные даты** вступления в силу отдельных положений
  (``action_type = "special_valid_from"``);
* **ретроактивные оговорки** — «действие положений распространяется на
  правоотношения, возникшие с ...» (``action_type = "retroactive_note"``).

Промпт: ``data/prompts/prompt_2.md``.
Реализация: ``AiPipelineMixin._stage2_dates_analysis``
(:mod:`npazs.pipeline.orchestrator`).

Промпт выполняется **по одной статье** изменяющего НПА за раз — так модель не
теряет контекст на длинных документах.

Формат ответа модели
--------------------
::

    [
      {
        "applies_to": "target_law",
        "action_type": "retroactive_note",
        "structural_element": "Статья 5 часть 1",
        "note_text": "Действие положений ... распространяется на правоотношения, возникшие с 01.01.2025",
        "note_valid_from": "01.01.2026"
      }
    ]

``applies_to``
    ``"amending_law"`` — положение относится к самому изменяющему НПА;
    ``"target_law"`` — к целевому НПА.
``action_type``
    ``"special_valid_from"`` или ``"retroactive_note"``.
``structural_element``
    Путь к элементу, к которому применяется правило.
``date`` / ``note_text`` / ``note_valid_from``
    Дата для ``special_valid_from``; текст и дата начала для примечания.

Временная семантика примечаний
------------------------------
Ретроактивное примечание — **временная запись**, а не безусловный тег. Когда
появляется новое примечание того же смыслового вида на том же элементе, ранее
активное примечание закрывается: ``valid_to = новая valid_from - 1 день``.

Это поведение реализовано хуком ``_append_item_note_with_validity`` в
:mod:`npazs.revision` (``__init__.py``), а не в самом этапе. Хук намеренно
узкий: он оборачивает ``retroactive_notes._append_item_note`` и не меняет
публичный API примечаний.

Согласование этапа 2 с этапом 3 описано в
``docs/prompt_2_coordination_summary.md``.
"""

from __future__ import annotations

from typing import Any, Optional

STAGE_NUMBER = 2
STAGE_NAME = 'Даты вступления в силу и ретроактивность'
PROMPT_STAGE = 2
MIXIN_METHOD = '_stage2_dates_analysis'

#: Допустимые значения поля ``applies_to``.
APPLIES_TO = ('amending_law', 'target_law')

#: Допустимые значения поля ``action_type``.
ACTION_TYPES = ('special_valid_from', 'retroactive_note')


def run(
    app: Any,
    final_text: str,
    target_element: Any,
    model: str,
    extra_options: Optional[dict] = None,
    pub_date_str: str = '',
    original_law_number: str = '',
    change_data: Any = None,
    base_law_date_pub: str = '',
):
    """Выполнить этап 2 для приложения ``app``.

    Тонкая обёртка над ``AiPipelineMixin._stage2_dates_analysis``; порядок
    аргументов повторяет исходный метод.
    """
    return getattr(app, MIXIN_METHOD)(
        final_text,
        target_element,
        model,
        extra_options,
        pub_date_str,
        original_law_number,
        change_data,
        base_law_date_pub,
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
        applies_to = item.get('applies_to')
        if applies_to not in APPLIES_TO:
            problems.append(
                f'[{index}] недопустимое applies_to={applies_to!r}; '
                f'ожидается одно из {APPLIES_TO}'
            )
        action_type = item.get('action_type')
        if action_type not in ACTION_TYPES:
            problems.append(
                f'[{index}] недопустимое action_type={action_type!r}; '
                f'ожидается одно из {ACTION_TYPES}'
            )
        if action_type == 'special_valid_from' and not item.get('date'):
            problems.append(f'[{index}] для special_valid_from требуется поле "date"')
        if action_type == 'retroactive_note' and not item.get('note_text'):
            problems.append(f'[{index}] для retroactive_note требуется поле "note_text"')
    return problems


__all__ = [
    'STAGE_NUMBER',
    'STAGE_NAME',
    'PROMPT_STAGE',
    'MIXIN_METHOD',
    'APPLIES_TO',
    'ACTION_TYPES',
    'run',
    'validate_result',
]
