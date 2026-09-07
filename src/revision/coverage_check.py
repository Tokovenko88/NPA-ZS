"""Детерминированная проверка покрытия норм изменяющего НПА.

Пост-анализ строит список ``<changes>`` из фактических ревизий результата,
отфильтрованных по авторству изменяющего закона. Если правка не была
применена (ревизия от изменяющего закона не создана, а трекер ошибочно
закрыл её чужой ревизией), запись в списке отсутствует и LLM-агент такую
проблему не видит. Модуль закрывает дыру: сверяет нормы из снимка трекера
с фактическими ревизиями JSON-результата и возвращает «непокрытые» нормы.

Выявляемые причины (reason):
- ``not_applied_status``        — норма не доведена до статуса APPLIED/VERIFIED;
- ``no_revision_id``            — норма применена, но без ссылки на ревизию;
- ``revision_missing_in_result``— указанной ревизии нет в дереве результата;
- ``foreign_revision``          — ревизия существует, но создана НЕ изменяющим НПА;
- ``wrong_target``              — ревизия найдена, но на другом элементе.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

#: Статусы, которыми трекер закрывает успешно применённые правки.
#: Учитываем, что трекер может хранить статусы как строку в верхнем регистре,
#: так и как элемент enum ``ChangeStatus`` (str, Enum) со значением в нижнем регистре.
_APPLIED_STATUSES = {"applied", "verified", "APPLIED", "VERIFIED"}

#: Типы правок, для которых применима строгая проверка по ревизии.
#: Для ``delete``/аннулирований отсутствие новой ревизии в результате — норма.
_STRICT_TYPES = {"change", "new_redaction", "add"}

#: Описание пробела покрытия одной нормы (словарь с ключами reason, change_id, …).
CoverageGap = dict


def _iter_elements(items: list[dict] | None) -> Iterable[dict]:
    """Итерация по всем элементам дерева (включая вложенных детей)."""
    stack = list(items or [])
    while stack:
        element = stack.pop()
        yield element
        stack.extend(element.get("item_children") or [])


def collect_result_revisions(result: dict) -> dict[str, tuple[str | None, Any]]:
    """Карта ``revision_id -> (item_id, modified_by_id)`` по всему дереву результата."""
    revisions: dict[str, tuple[str | None, Any]] = {}
    for element in _iter_elements(result.get("npa_items_revision")):
        for rev in element.get("revisions") or []:
            rev_id = rev.get("revision_id")
            if rev_id:
                revisions[str(rev_id)] = (element.get("item_id"), rev.get("modified_by_id"))
    return revisions


def _is_own_revision(modified_by_id: Any, change_npa_id: Any) -> bool:
    """True, если ревизия создана изменяющим НПА (сравнение по префиксу item_id).

    ``change_npa_id`` — id изменяющего НПА (например ``59121``) либо коллекция
    допустимых авторов (ids норм изменяющего закона).
    """
    modified = str(modified_by_id or "")
    if not modified:
        return False
    if isinstance(change_npa_id, (list, tuple, set, frozenset)):
        candidates: list[Any] = list(change_npa_id)
    else:
        candidates = [change_npa_id]
    for own in candidates:
        own_id = str(own or "")
        if own_id and (modified == own_id or modified.startswith(own_id + "_")):
            return True
    return False


def check_tracker_coverage(
    result: dict,
    changes: Iterable[dict],
    change_npa_id: Any,
) -> list[dict]:
    """Сверяет нормы трекера с ревизиями результата.

    Args:
        result: разобранный JSON результата ревизии (ключ ``npa_items_revision``).
        changes: снимок списка изменений трекера (словари с ключами
            ``change_id``, ``revision_number``, ``structural_element``, ``type``,
            ``status``, ``revision_id``, ``target_item_id``).
        change_npa_id: id изменяющего НПА или коллекция ids его норм.

    Returns:
        Список «пробелов покрытия» — норм, помеченных как применённые, но не
        породивших в результате ревизию от изменяющего НПА (или не доведённых
        до применения вовсе).
    """
    result_revisions = collect_result_revisions(result)
    gaps: list[dict] = []
    seen: set = set()
    for change in changes or []:
        change_id = str(change.get("change_id") or "")
        # Нормализуем статус: трекер может хранить строку или enum (str, Enum)
        status_raw = change.get("status")
        status = str(status_raw).lower().strip() if status_raw is not None else ""
        change_type = str(change.get("type") or "").lower()
        reason: str | None = None
        # Проверяем только правки, которые трекер считает применёнными (APPLIED/VERIFIED).
        # Статусы вроде EXTRACTED означают "ещё не применено" — это не пробел, это просто не сделано.
        if status not in {"applied", "verified"}:
            continue
        if change_type in _STRICT_TYPES:
            rev_id = change.get("revision_id")
            if not rev_id:
                reason = "no_revision_id"
            elif str(rev_id) not in result_revisions:
                reason = "revision_missing_in_result"
            else:
                item_id, modified_by = result_revisions[str(rev_id)]
                if not _is_own_revision(modified_by, change_npa_id):
                    reason = "foreign_revision"
                elif item_id and change.get("target_item_id") and item_id != change.get("target_item_id"):
                    reason = "wrong_target"
        if reason:
            key = (change_id, reason)
            if key in seen:
                continue
            seen.add(key)
            gaps.append(
                {
                    "change_id": change_id,
                    "revision_number": change.get("revision_number"),
                    "structural_element": change.get("structural_element"),
                    "type": change.get("type"),
                    "status": status,
                    "reason": reason,
                    "revision_id": change.get("revision_id"),
                    "target_item_id": change.get("target_item_id"),
                }
            )
    return gaps


def format_coverage_gaps(gaps: list[dict]) -> str:
    """Текст секции ``<coverage_gaps>`` для промпта пост-анализа (пусто, если нет пробелов)."""
    if not gaps:
        return ""
    lines = [
        "<coverage_gaps>",
        "ДЕТЕРМИНИРОВАННАЯ ПРОВЕРКА ПОКРЫТИЯ выявила нормы изменяющего закона,",
        "которые НЕ породили ревизию в результате (правка не применена):",
    ]
    for gap in gaps:
        lines.append(
            f"- change_id={gap.get('change_id')} | пункт/подпункт: {gap.get('revision_number')} | "
            f"элемент: {gap.get('structural_element')} | тип: {gap.get('type')} | "
            f"статус: {gap.get('status')} | причина: {gap.get('reason')}"
        )
    lines.append("</coverage_gaps>")
    return "\n".join(lines)


def serialize_tracker_changes(tracker: Any) -> list[dict]:
    """Снимок списка изменений трекера в виде простых словарей.

    Принимает объект ChangeTracker (атрибут ``_changes`` — словарь записей
    по change_id), готовый список записей или ``None``. Записи могут быть
    как dict, так и объектами с одноимёнными атрибутами.
    """
    if tracker is None:
        return []
    raw = getattr(tracker, "_changes", None)
    if raw is None:
        raw = getattr(tracker, "changes", tracker)
    if isinstance(raw, dict):
        values = list(raw.values())
    elif isinstance(raw, (list, tuple)):
        values = list(raw)
    else:
        return []
    keys = (
        "change_id",
        "revision_number",
        "structural_element",
        "type",
        "mod_type",
        "status",
        "revision_id",
        "target_item_id",
    )
    snapshot: list[dict] = []
    for item in values:
        if isinstance(item, dict):
            snapshot.append({key: item.get(key) for key in keys})
        else:
            snapshot.append({key: getattr(item, key, None) for key in keys})
    return snapshot


def check_coverage(tracker: Any, result: dict, change_npa_id: Any) -> list[dict]:
    """Обёртка: снять снимок изменений трекера и сверить с результатом."""
    return check_tracker_coverage(result, serialize_tracker_changes(tracker), change_npa_id)


def append_coverage_section(report_path: Any, gaps: list[dict]) -> bool:
    """Дописать в Markdown-отчёт раздел о непокрытых нормах.

    Возвращает True, если раздел был дописан (есть пробелы покрытия).
    """
    if not gaps:
        return False
    with open(str(report_path), "a", encoding="utf-8") as handle:
        handle.write("\n\n## Проверка покрытия норм (coverage_check)\n\n")
        handle.write(
            "Следующие нормы изменяющего НПА помечены применёнными в трекере, "
            "но не породили ревизию от изменяющего НПА в результате:\n\n"
        )
        handle.writelines(f"- **{gap.get('revision_number')}** {gap.get('structural_element')} — "
                f"тип: {gap.get('type')}, статус: {gap.get('status')}, "
                f"причина: `{gap.get('reason')}` (change_id: {gap.get('change_id')})\n" for gap in gaps)
    return True

