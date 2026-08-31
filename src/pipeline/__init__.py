"""AI-пайплайн NPA-ZS: пять детерминированных этапов обработки изменений.

Пакет — «сборочный цех» проекта. На вход поступают два JSON-документа
(изменяющий и целевой НПА), на выходе получается новая ревизия целевого НПА
с полной историей изменений.

Состав
------

:mod:`npazs.pipeline.orchestrator`
    ``AiPipelineMixin`` — реальная реализация всех этапов и метод ``run_all``.

:mod:`npazs.pipeline.prompts`
    Загрузка и подстановка значений в промпты ``data/prompts/prompt_{1..4}.md``.

:mod:`npazs.pipeline.stage1_revocation`
    Этап 1 — анализ утраты силы.

:mod:`npazs.pipeline.stage2_dates`
    Этап 2 — специальные даты вступления в силу и ретроактивные оговорки.

:mod:`npazs.pipeline.stage3_extraction`
    Этап 3 — извлечение перечня изменений.

:mod:`npazs.pipeline.stage4_html`
    Этап 4 — применение текстовых правок к HTML элементов.

:mod:`npazs.pipeline.stage5_rebuild`
    Этап 5 — пересборка элементов и родительских тел, верификация.

Инварианты пайплайна
--------------------
1. **Детерминированность.** ``temperature=0.0``, ``top_p=0.1``; один и тот же
   вход обязан давать один и тот же выход.
2. **Идемпотентность.** Повторный прогон на уже обработанном документе не
   должен создавать дублирующие ревизии.
3. **Хронология ревизий.** У элемента может быть только одна активная ревизия
   (``valid_to is None``); закрываемая ревизия получает
   ``valid_to = valid_from - 1 день``.
4. **Верификация извлечения.** HTML, предложенный моделью, сверяется с
   детерминированным извлечением программы; расхождение выносится оператору
   (см. :mod:`npazs.revision.extraction_verifier`).

Импорты ленивые: ``orchestrator`` тянет ``tkinter`` и весь слой ``revision``,
поэтому ``import npazs.pipeline`` сам по себе остаётся дешёвым.
"""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    'orchestrator',
    'prompts',
    'stage1_revocation',
    'stage2_dates',
    'stage3_extraction',
    'stage4_html',
    'stage5_rebuild',
    'AiPipelineMixin',
    'STAGES',
]

#: Порядок этапов и модули-обёртки. Используется CLI (`npazs revise`) и отчётами.
STAGES = (
    (1, 'stage1_revocation', 'Анализ утраты силы'),
    (2, 'stage2_dates', 'Даты вступления в силу и ретроактивность'),
    (3, 'stage3_extraction', 'Извлечение изменений'),
    (4, 'stage4_html', 'Применение правок к HTML'),
    (5, 'stage5_rebuild', 'Пересборка и верификация'),
)


def __getattr__(name: str) -> Any:
    """Ленивая загрузка подмодулей и ``AiPipelineMixin``."""
    if name == 'AiPipelineMixin':
        module = importlib.import_module('npazs.pipeline.orchestrator')
        return module.AiPipelineMixin
    if name in __all__:
        return importlib.import_module(f'npazs.pipeline.{name}')
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
