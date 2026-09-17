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
- ``wrong_target``              — ревизия найдена, но на другом элементе;
- ``not_marked_invalid``        — правка «признать утратившим силу» (delete), но
  ревизия элемента не помечена ``not_valid`` изменяющим НПА.

Особый случай ``orphan_child_not_closed``: ребёнок родителя, пересозданного
изменяющим НПА через ``new_redaction``, должен либо иметь активную ревизию от
изменяющего НПА, либо быть помечен ``not_valid``. Исключение — ребёнок,
«перенесённый» новой редакцией без изменений: текст нормы в новой редакции
не менялся, поэтому пайплайн сознательно не создаёт новую ревизию (кейс
380-ЗС → 269-ЗС: часть 7 статьи 7) — родительская ревизия от изменяющего
НПА продолжает ссылаться на него через ``child_ref``, а старая ревизия
остаётся открытой. Такой ребёнок сиротой НЕ считается.

Важно про ``delete``: признание элемента утратившим силу НЕ создаёт новую
ревизию от изменяющего НПА — корректное применение означает, что существующая
ревизия элемента помечена ``not_valid`` нормой изменяющего закона (см. ветку
``delete`` в ``change_applier.apply_change``). Вариант «слова … исключить»
наоборот создаёт собственную ревизию изменяющего НПА на элементе. Поэтому
``delete`` исключён из строгой проверки по автору ревизии: трекер ссылается на
существующую ревизию (обычно чужого закона), и сверка ``modified_by_id``
давала ложные ``foreign_revision`` на корректно утративших силу элементах.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

#: Статусы, которыми трекер закрывает успешно применённые правки.
#: Учитываем, что трекер может хранить статусы как строку в верхнем регистре,
#: так и как элемент enum ``ChangeStatus`` (str, Enum) со значением в нижнем регистре.
_APPLIED_STATUSES = {"applied", "verified", "APPLIED", "VERIFIED"}

#: Типы правок, для которых применима строгая проверка по ревизии.
#: Для ``delete`` проверка отдельная: «признать утратившим силу» не создаёт
#: ревизию от изменяющего НПА, а помечает существующую ревизию элемента
#: полем ``not_valid`` (см. change_applier.apply_change, ветка delete).
_STRICT_TYPES = {"change", "new_redaction", "add"}

#: Списки ревизий элемента, которые могут нести ``revision_id`` и учитываются
#: при резолвинге. head-ревизии создаются с собственным ``revision_id``
#: (см. change_applier, ветка наименования), поэтому head-правки, которые
#: трекер хранит как обычные изменения, обязаны резолвиться через
#: ``head_revisions`` — иначе ложный ``revision_missing_in_result``.
_REVISION_LIST_KEYS = ("revisions", "head_revisions", "number_revisions", "item_prefix_revisions")

#: Описание пробела покрытия одной нормы (словарь с ключами reason, change_id, …).
CoverageGap = dict


def _iter_elements(items: list[dict] | None) -> Iterable[dict]:
    """Итерация по всем элементам дерева (включая вложенных детей)."""
    stack = list(items or [])
    while stack:
        element = stack.pop()
        yield element
        stack.extend(element.get("item_children") or [])


#: Sentinel-идентификаторы корневых объектов, которые хранятся вне
#: ``npa_items_revision``. Ревизии из этих списков не индексируются в
#: ``_REVISION_LIST_KEYS`` (там работает обход ``_iter_elements``), поэтому
#: их обрабатываем отдельно в ``collect_result_revisions``.
_CORE_HEAD_LIST_KEYS = (
    ("head_revision", "__наименование__"),
    ("preamble_revision", "__преамбула__"),
)

def collect_result_revisions(result: dict) -> dict[str, tuple[str | None, Any]]:
    """Карта ``revision_id -> (item_id, modified_by_id)`` по всему дереву результата.

    Индексируются:
    - ревизии элементов (``revisions``, ``head_revisions``,
      ``number_revisions``, ``item_prefix_revisions``) — созданные изменяющим НПА
      записи этих списков несут собственный ``revision_id``, по которому трекер
      закрывает соответствующие правки (например head-правки наименований
      конкретных статей/разделов);
    - корневые списки документа: ``head_revision`` (наименование НПА) и
      ``preamble_revision`` (преамбула) — они хранятся вне ``npa_items_revision``
      в корне результата, но тем не менее несут ``revision_id`` и могут закрывать
      правки трекера с ``target_item_id`` ``__наименование__`` / ``__преамбула__``.
    """
    revisions: dict[str, tuple[str | None, Any]] = {}
    for element in _iter_elements(result.get("npa_items_revision")):
        for key in _REVISION_LIST_KEYS:
            for rev in element.get(key) or []:
                if not isinstance(rev, dict):
                    continue
                rev_id = rev.get("revision_id")
                if rev_id:
                    revisions[str(rev_id)] = (element.get("item_id"), rev.get("modified_by_id"))

    # Корневые ревизии документа (наименование НПА, преамбула), которые живут
    # вне дерева элементов.
    for list_key, item_id in _CORE_HEAD_LIST_KEYS:
        for rev in result.get(list_key) or []:
            if not isinstance(rev, dict):
                continue
            rev_id = rev.get("revision_id")
            if rev_id:
                revisions[str(rev_id)] = (item_id, rev.get("modified_by_id"))

    return revisions


def _is_own_mark(mark_value: Any, change_npa_id: Any) -> bool:
    """True, если метка (``not_valid`` ревизии) проставлена изменяющим НПА.

    ``not_valid`` ревизии хранит item_id нормы изменяющего закона (возможно,
    несколько id через запятую) — сравнение по префиксу с разделителем,
    как ``_ids_match`` в ``post_analysis`` (исключает 516 vs 5162).
    """
    own_id = str(change_npa_id or "")
    if not own_id:
        return False
    for part in str(mark_value or "").split(","):
        part = part.strip()
        if part and (part == own_id or part.startswith(own_id + "_")):
            return True
    return False


def _find_element(result: dict, item_id: Any) -> dict | None:
    """Найти элемент дерева по ``item_id``."""
    if not item_id:
        return None
    wanted = str(item_id)
    for element in _iter_elements(result.get("npa_items_revision")):
        if element.get("item_id") == wanted:
            return element
    return None


def _active_rev_is_own(element: dict, change_npa_id: Any) -> bool:
    """True, если активная ревизия элемента создана изменяющим НПА
    (``modified_by_id`` совпадает с ``change_npa_id`` по префиксу)."""
    for rev in reversed(element.get("revisions") or []):
        if rev.get("not_valid"):
            continue
        if rev.get("valid_to") in (None, ""):
            return _is_own_revision(rev.get("modified_by_id"), change_npa_id)
    return False


def _has_own_not_valid(element: dict, change_npa_id: Any) -> bool:
    """True, если какая-либо ревизия элемента помечена ``not_valid``
    нормой изменяющего закона."""
    for rev in element.get("revisions") or []:
        if not isinstance(rev, dict):
            continue
        if _is_own_mark(rev.get("not_valid"), change_npa_id):
            return True
    return False


def _collect_child_refs(element: dict) -> set[str]:
    """Все ``item_id``, на которые ревизии элемента ссылаются через ``child_ref``."""
    refs: set[str] = set()
    for rev in element.get("revisions") or []:
        if not isinstance(rev, dict):
            continue
        for block in rev.get("body") or []:
            if (isinstance(block, dict) and block.get("type") == "child_ref"
                    and block.get("item_id")):
                refs.add(str(block["item_id"]))
    return refs


def check_orphan_children(result: dict, change_npa_id: Any) -> list[dict]:
    """Детерминированная проверка: дети родителя, пересозданного через
    ``new_redaction`` (модифицированного изменяющим НПА), должны либо
    иметь активную ревизию от изменяющего НПА, либо быть помеченными
    ``not_valid``. Иначе ребёнок остался «висеть» — его ревизия не
    закрылась, а пост-анализ (собирающий изменения по ``modified_by_id``)
    такую проблему не видит (кейс 380-ЗС -> 269-ЗС: части 8-11 статьи 5
    исчезли из новой редакции, но остались активными).

    Исключение: ребёнок, «перенесённый» новой редакцией без изменений —
    родительская ревизия от изменяющего НПА по-прежнему ссылается на него
    через ``child_ref``, а его старая ревизия осталась открытой, потому что
    текст нормы в новой редакции не поменялся и новая ревизия не нужна
    (кейс 380-ЗС -> 269-ЗС: часть 7 статьи 7). Такой ребёнок сиротой не
    считается — иначе ложный пробел и вредная автоправка ``not_valid``,
    удаляющая действующую норму.
    """
    gaps: list[dict] = []
    for element in _iter_elements(result.get("npa_items_revision")):
        # Родитель должен быть пересоздан изменяющим НПА (new_redaction/change).
        if not _active_rev_is_own(element, change_npa_id):
            continue
        parent_refs = None
        for child in element.get("item_children") or []:
            if not isinstance(child, dict):
                continue
            if _active_rev_is_own(child, change_npa_id):
                continue
            if _has_own_not_valid(child, change_npa_id):
                continue
            # Ребёнок добавлен в этом же прогона (add) — его ревизия
            # создана изменяющим НПА, просто без modified_by_id на активной
            # ревизии (см. _stamp_new_subtree_provenance). Проверим, что
            # активная ревизия датирована change_date — тогда это норма.
            active_rev = None
            for rev in reversed(child.get("revisions") or []):
                if rev.get("not_valid"):
                    continue
                if rev.get("valid_to") in (None, ""):
                    active_rev = rev
                    break
            if active_rev and active_rev.get("valid_from"):
                continue
            # Ребёнок «перенесён» новой редакцией без изменений: родительская
            # ревизия от изменяющего НПА по-прежнему ссылается на него через
            # child_ref, а его старая ревизия осталась открытой — текст нормы
            # в новой редакции не менялся, новая ревизия не нужна. Не сирота
            # (кейс 380-ЗС -> 269-ЗС: часть 7 статьи 7).
            if active_rev is not None:
                if parent_refs is None:
                    parent_refs = _collect_child_refs(element)
                if str(child.get("item_id") or "") in parent_refs:
                    continue
            gaps.append({
                "change_id": None,
                "revision_number": child.get("item_number"),
                "structural_element": f"{child.get('item_type')} {child.get('item_number')}",
                "type": "new_redaction",
                "status": "applied",
                "reason": "orphan_child_not_closed",
                "revision_id": None,
                "target_item_id": child.get("item_id"),
                "description": (
                    f"Родитель {element.get('item_id')} пересоздан изменяющим "
                    f"НПА, но ребёнок {child.get('item_id')} "
                    f"({child.get('item_type')} {child.get('item_number')}) "
                    f"не имеет активной ревизии от изменяющего НПА и не "
                    f"помечен not_valid — ревизия не закрылась."
                ),
            })
    return gaps


def _delete_applied(result: dict, change: dict, change_npa_id: Any,
                     result_revisions: dict) -> bool:
    """Проверка корректного применения правки типа ``delete``.

    Корректные исходы:
    - правка целикового НПА: ``result['not_valid']`` + ``not_valid_npa`` от
      изменяющего НПА;
    - repel элемента: какая-либо ревизия элемента помечена ``not_valid``
      нормой изменяющего закона;
    - «слова … исключить»: на элементе есть ревизия, созданная изменяющим НПА.
    """
    target = str(change.get("target_item_id") or "")
    if target == "__npa__":
        return bool(result.get("not_valid")) and _is_own_mark(
            result.get("not_valid_npa"), change_npa_id
        )
    element = _find_element(result, target)
    if element is None:
        mapped = result_revisions.get(str(change.get("revision_id") or ""))
        if mapped and mapped[0]:
            element = _find_element(result, mapped[0])
    if element is None:
        return False
    for rev in element.get("revisions") or []:
        if not isinstance(rev, dict):
            continue
        if _is_own_mark(rev.get("not_valid"), change_npa_id):
            return True
        if _is_own_revision(rev.get("modified_by_id"), change_npa_id):
            return True
    return False


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
        # Нормализуем статус и тип: трекер может хранить строку или enum (str, Enum).
        status = _normalize_status(change.get("status"))
        change_type_raw = change.get("type")
        if hasattr(change_type_raw, "value"):
            change_type = str(change_type_raw.value).lower().strip()
        else:
            change_type = str(change_type_raw or "").lower()
        reason: str | None = None
        # Проверяем только правки, которые трекер считает применёнными (APPLIED/VERIFIED).
        # Статусы вроде EXTRACTED означают "ещё не применено" — это не пробел, это просто не сделано.
        # Примечание: в Python 3.11+ str(EnumMember) возвращает "Class.MEMBER", поэтому
        # используем .value для получения строкового значения enum.
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
        elif change_type == "delete":
            # «Признать утратившим силу» не порождает новой ревизии от
            # изменяющего НПА: корректное применение — существующая ревизия
            # элемента помечена not_valid нормой изменяющего закона (либо
            # создана собственная ревизия — вариант «слова … исключить»).
            if not _delete_applied(result, change, change_npa_id, result_revisions):
                reason = "not_marked_invalid"
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
                    "description": change.get("description"),
                }
            )
    # Детерминированная проверка «сирот»: дети родителя, пересозданного
    # изменяющим НПА (new_redaction), должны либо иметь активную ревизию
    # от изменяющего НПА, либо быть помеченными not_valid. Иначе их
    # ревизия не закрылась, а пост-анализ (собирающий изменения по
    # modified_by_id) такую проблему не видит (кейс 380-ЗС -> 269-ЗС:
    # части 8-11 статьи 5 остались активными).
    gaps.extend(check_orphan_children(result, change_npa_id))
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
            record = {key: item.get(key) for key in keys}
            source = item.get("source_change")
            description = source.get("description") if isinstance(source, dict) else None
            if description is None:
                description = item.get("description")
        else:
            record = {key: getattr(item, key, None) for key in keys}
            source = getattr(item, "source_change", None)
            description = getattr(source, "description", None) if source is not None else None
            if description is None:
                description = getattr(item, "description", None)
        # Нормализуем status: enum -> строковое значение
        record["status"] = _normalize_status(record.get("status"))
        # Текст инструкции (description из stage 3) — нужен пост-анализу,
        # чтобы детерминированно применить правку (например «слова ... исключить»).
        record["description"] = description
        snapshot.append(record)
    return snapshot


def _normalize_status(status: Any) -> str:
    """Преобразовать статус трекера в строку (enum -> .value, str -> lower)."""
    if status is None:
        return ""
    if hasattr(status, "value"):
        return str(status.value).lower().strip()
    return str(status).lower().strip()


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

