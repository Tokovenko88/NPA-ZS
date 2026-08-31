"""Этап 5 — пересборка элементов, синхронизация родителей и верификация.

Назначение
----------
После применения всех изменений (этапы 1-4) дерево целевого НПА содержит
элементы с «отложенным» состоянием: новый HTML, новые дочерние узлы, изменённые
номера. Этап 5 приводит дерево в консистентное состояние:

1. пересобирает каждый затронутый элемент в новую ревизию;
2. синхронизирует тела родителей с фактическим составом ``item_children``;
3. удаляет пустые узлы-заготовки;
4. корректирует пунктуацию соседних элементов после вставки/удаления;
5. запускает верификацию: все ли изменения из этапа 3 действительно применены.

Реализация: ``AiPipelineMixin._stage5_rebuild`` (:mod:`npazs.pipeline.orchestrator`),
опирается на ``rebuild_element_with_history`` из :mod:`npazs.revision.engine`.

Режимы пересборки
-----------------
Изменение содержимого и структурная операция — принципиально разные вещи, и
:mod:`npazs.revision.engine` различает их явно:

``CONTENT_REBUILD``
    Пересобирается только тот элемент, чей собственный текст изменился
    (``_pending_mod_type`` = ``change`` или ``new_redaction``). Родитель НЕ
    пересобирается лишь потому, что изменился потомок.

``STRUCTURE_REBUILD``
    Пересобирается элемент, который был структурно добавлен
    (``_pending_mod_type`` = ``add``). Тела родителей обновляются самой
    структурной операцией через ``child_ref``, но неизменённый родитель не
    превращается в новую ревизию.

Элемент с отложенным HTML, но без типа операции — **не** корректный запрос на
пересборку. Такое состояние является артефактом логики продвижения к родителю и
отклоняется: ``rebuild_element_with_history`` возвращает
``"SKIPPED_PARENT_REBUILD:<id>"``. Этап 5 трактует непустой результат как
успешный no-op, поэтому синтетический родитель не попадает в отчёт как ошибка и,
что важнее, не создаёт ревизию и не меняет структуру.

Верификация
-----------
``run_verification_stage`` (:mod:`npazs.revision.change_pipeline`) сверяет
журнал ``ChangeTracker`` с фактическим состоянием JSON по каждому типу:

* ``_verify_delete``       — активная ревизия закрыта и помечена ``not_valid``;
* ``_verify_add``          — узел существует, у родителя есть ``child_ref``;
* ``_verify_modification`` — создана новая ревизия с ожидаемым ``revision_id``.

Изменения, не прошедшие проверку, попадают в отчёт со статусом из
:class:`npazs.revision.change_tracker.ChangeStatus`.
"""

from __future__ import annotations

from typing import Any, Optional

STAGE_NUMBER = 5
STAGE_NAME = 'Пересборка и верификация'

#: У этапа нет промпта — он полностью детерминирован.
PROMPT_STAGE = None
MIXIN_METHOD = '_stage5_rebuild'

#: Режимы пересборки (реэкспорт значений из npazs.revision.engine).
CONTENT_REBUILD = 'CONTENT_REBUILD'
STRUCTURE_REBUILD = 'STRUCTURE_REBUILD'

#: Префикс маркера пропущенной родительской пересборки.
SKIPPED_PARENT_PREFIX = 'SKIPPED_PARENT_REBUILD:'


def run(
    app: Any,
    result_data: Any,
    rebuild_ids: Any,
    general_valid_from: str,
    change_data: Any,
    tracker: Optional[Any] = None,
):
    """Выполнить этап 5 для приложения ``app``."""
    return getattr(app, MIXIN_METHOD)(
        result_data,
        rebuild_ids,
        general_valid_from,
        change_data,
        tracker,
    )


def get_rebuild_mode(item: Any):
    """Вернуть режим пересборки элемента (``CONTENT_REBUILD``/``STRUCTURE_REBUILD``/``None``)."""
    from npazs.revision.engine import get_rebuild_mode as _get_rebuild_mode

    return _get_rebuild_mode(item)


def is_skipped_parent(result: Any) -> bool:
    """True, если пересборка была намеренно пропущена как родительская."""
    return isinstance(result, str) and result.startswith(SKIPPED_PARENT_PREFIX)


def verify(
    tracker: Any,
    data: Any,
    log_callback: Any = None,
    **kwargs: Any,
):
    """Запустить стадию верификации применённых изменений."""
    from npazs.revision.change_pipeline import run_verification_stage

    return run_verification_stage(tracker, data, log_callback, **kwargs)


__all__ = [
    'STAGE_NUMBER',
    'STAGE_NAME',
    'PROMPT_STAGE',
    'MIXIN_METHOD',
    'CONTENT_REBUILD',
    'STRUCTURE_REBUILD',
    'SKIPPED_PARENT_PREFIX',
    'run',
    'get_rebuild_mode',
    'is_skipped_parent',
    'verify',
]
