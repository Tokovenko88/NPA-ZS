"""Валидация каноничной JSON-структуры НПА.

Проверки соответствуют разделу «Верификация» в ``AGENTS.md`` и
``instructions/09_qa_verification.md``. Модуль сознательно не зависит от Tk,
БД и сети, поэтому его можно запускать в CI и из хуков.

Основная точка входа — :func:`validate_document`, возвращающая
:class:`ValidationReport`.

Проверяемые инварианты
----------------------
Структура
    * ``item_id`` уникальны в пределах документа;
    * ``item_type`` входит в допустимый перечень;
    * ``item_level`` начинается с 1 и растёт на 1 при спуске;
    * дети ``structured_table`` имеют тип ``section``/``point``/``subpoint``.

Ссылки
    * каждый ``child_ref`` в теле ревизии указывает на существующий ``item_id``;
    * каждый ребёнок из ``item_children`` упомянут в теле активной ревизии
      родителя (предупреждение, а не ошибка: у скрытых узлов бывает иначе).

Ревизии и даты
    * у элемента максимум одна активная ревизия (``valid_to`` пусто);
    * даты в формате ``ДД.ММ.ГГГГ``;
    * ``valid_to`` не раньше ``valid_from``;
    * периоды ревизий не пересекаются и идут хронологически;
    * активная ревизия вложенного элемента исправленного документа должна
      иметь ``valid_from`` и ``mod_type`` (привязка к редакции).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

__all__ = [
    'DATE_FORMAT',
    'ITEM_TYPES',
    'MOD_TYPES',
    'Issue',
    'ValidationReport',
    'find_new_items_without_provenance',
    'iter_items',
    'parse_date',
    'validate_dates',
    'validate_document',
    'validate_ids',
    'validate_refs',
    'validate_revisions',
]

DATE_FORMAT = '%d.%m.%Y'
_DATE_RE = re.compile(r'^\d{2}\.\d{2}\.\d{4}$')

#: Допустимые типы структурных элементов (соответствует ENUM в БД).
ITEM_TYPES = (
    'preamble',
    'chapter',
    'section',
    'article',
    'part',
    'point',
    'subpoint',
    'appendix',
    'nested_appendix',
    'structured_table',
)

#: Допустимые значения ``mod_type`` в ревизиях контента.
MOD_TYPES = ('add', 'change', 'delete', 'new_redaction')

#: Типы, допустимые как дети ``structured_table``.
STRUCTURED_TABLE_CHILD_TYPES = ('section', 'point', 'subpoint')

SEVERITY_ERROR = 'error'
SEVERITY_WARNING = 'warning'


@dataclass(frozen=True)
class Issue:
    """Одно замечание валидации."""

    severity: str
    code: str
    message: str
    item_id: str | None = None

    def __str__(self) -> str:
        where = f' [{self.item_id}]' if self.item_id else ''
        return f'{self.severity.upper()}: {self.code}{where}: {self.message}'


@dataclass
class ValidationReport:
    """Результат валидации документа."""

    issues: list[Issue] = field(default_factory=list)
    items_checked: int = 0
    revisions_checked: int = 0

    def add(
        self,
        severity: str,
        code: str,
        message: str,
        item_id: str | None = None,
    ) -> None:
        self.issues.append(Issue(severity, code, message, item_id))

    def error(self, code: str, message: str, item_id: str | None = None) -> None:
        self.add(SEVERITY_ERROR, code, message, item_id)

    def warning(self, code: str, message: str, item_id: str | None = None) -> None:
        self.add(SEVERITY_WARNING, code, message, item_id)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == SEVERITY_ERROR]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == SEVERITY_WARNING]

    @property
    def ok(self) -> bool:
        """True, если ошибок нет (предупреждения допустимы)."""
        return not self.errors

    def extend(self, other: ValidationReport) -> ValidationReport:
        self.issues.extend(other.issues)
        self.items_checked += other.items_checked
        self.revisions_checked += other.revisions_checked
        return self

    def summary(self) -> str:
        status = 'OK' if self.ok else 'ОШИБКИ'
        return (
            f'{status}: элементов {self.items_checked}, ревизий {self.revisions_checked}, '
            f'ошибок {len(self.errors)}, предупреждений {len(self.warnings)}'
        )


# ------------------------------------------------------------------ помощники
def parse_date(value: Any):
    """Разобрать дату ``ДД.ММ.ГГГГ``. Вернуть ``date`` или ``None``."""
    text = str(value or '').strip()
    if not _DATE_RE.match(text):
        return None
    try:
        return datetime.strptime(text, DATE_FORMAT).date()
    except ValueError:
        return None


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def iter_items(document: dict[str, Any]) -> Iterable[tuple[dict[str, Any], dict[str, Any] | None]]:
    """Рекурсивно перебрать элементы документа: ``(элемент, родитель)``.

    Поддерживает обе формы хранения дерева: ``item_children`` (плоское
    дерево-обёртка) и ``npa_items_revision`` (корневой список реального файла
    НПА). Ранее поддерживалась только первая форма, из-за чего валидация
    реальных файлов молча проверяла 0 элементов.
    """
    roots = document.get('item_children') or document.get('npa_items_revision') or []
    stack: list[tuple[dict[str, Any], dict[str, Any] | None]] = [
        (child, None) for child in reversed(roots)
    ]
    while stack:
        item, parent = stack.pop()
        if not isinstance(item, dict):
            continue
        yield item, parent
        for child in reversed(item.get('item_children') or []):
            if isinstance(child, dict):
                stack.append((child, item))


def _revisions(item: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in (item.get('revisions') or []) if isinstance(r, dict)]


def _child_refs(revision: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for block in revision.get('body') or []:
        if isinstance(block, dict):
            ref = block.get('child_ref')
            if ref:
                refs.append(str(ref))
    return refs


# ------------------------------------------------------------------- проверки
def validate_ids(document: dict[str, Any]) -> ValidationReport:
    """Уникальность ``item_id``, допустимость типов и корректность уровней."""
    report = ValidationReport()
    seen: dict[str, int] = {}

    for item, parent in iter_items(document):
        report.items_checked += 1
        item_id = item.get('item_id')

        if _is_empty(item_id):
            report.error('missing_item_id', 'У элемента отсутствует item_id')
        else:
            item_id = str(item_id)
            seen[item_id] = seen.get(item_id, 0) + 1
            if seen[item_id] == 2:
                report.error(
                    'duplicate_item_id',
                    'item_id встречается более одного раза; '
                    'при дублировании номеров используйте суффикс _double_N',
                    item_id,
                )

        item_type = item.get('item_type')
        if item_type not in ITEM_TYPES:
            report.error(
                'bad_item_type',
                f'недопустимый item_type={item_type!r}; ожидается одно из {ITEM_TYPES}',
                str(item_id) if item_id else None,
            )

        level = item.get('item_level')
        if not isinstance(level, int):
            report.error('bad_item_level', f'item_level должен быть int, получено {level!r}',
                         str(item_id) if item_id else None)
        elif parent is None:
            if level != 1:
                report.warning(
                    'unexpected_root_level',
                    f'элемент верхнего уровня имеет item_level={level}, ожидался 1',
                    str(item_id) if item_id else None,
                )
        else:
            parent_level = parent.get('item_level')
            if isinstance(parent_level, int) and level != parent_level + 1:
                report.warning(
                    'level_gap',
                    f'item_level={level} у родителя с item_level={parent_level} '
                    '(ожидался parent+1)',
                    str(item_id) if item_id else None,
                )

        if parent is not None and parent.get('item_type') == 'structured_table':
            if item_type not in STRUCTURED_TABLE_CHILD_TYPES:
                report.error(
                    'bad_structured_table_child',
                    f'дочерний элемент structured_table имеет тип {item_type!r}; '
                    f'допустимы {STRUCTURED_TABLE_CHILD_TYPES}',
                    str(item_id) if item_id else None,
                )

    return report


def validate_refs(document: dict[str, Any]) -> ValidationReport:
    """Целостность ``child_ref`` и полнота упоминания детей в теле родителя."""
    report = ValidationReport()

    known_ids = {
        str(item.get('item_id'))
        for item, _ in iter_items(document)
        if not _is_empty(item.get('item_id'))
    }

    for item, _ in iter_items(document):
        item_id = str(item.get('item_id') or '')
        for revision in _revisions(item):
            for ref in _child_refs(revision):
                if ref not in known_ids:
                    report.error(
                        'dangling_child_ref',
                        f'child_ref="{ref}" не соответствует ни одному item_id',
                        item_id,
                    )

        children = [
            str(child.get('item_id'))
            for child in (item.get('item_children') or [])
            if isinstance(child, dict) and not _is_empty(child.get('item_id'))
        ]
        if not children:
            continue

        active = [r for r in _revisions(item) if _is_empty(r.get('valid_to'))]
        if not active:
            continue
        referenced = set(_child_refs(active[0]))
        for child_id in children:
            if child_id not in referenced:
                report.warning(
                    'child_not_referenced',
                    f'дочерний элемент "{child_id}" отсутствует в body активной ревизии родителя',
                    item_id,
                )

    return report


def validate_revisions(document: dict[str, Any]) -> ValidationReport:
    """Одна активная ревизия, корректный ``mod_type``, непересекающиеся периоды."""
    report = ValidationReport()
    is_amended = bool(document.get('revision_info'))

    for item, parent in iter_items(document):
        item_id = str(item.get('item_id') or '')
        revisions = _revisions(item)
        report.revisions_checked += len(revisions)

        if not revisions:
            report.warning('no_revisions', 'у элемента нет ни одной ревизии', item_id)
            continue

        active = [r for r in revisions if _is_empty(r.get('valid_to'))]
        if len(active) > 1:
            report.error(
                'multiple_active_revisions',
                f'активных ревизий {len(active)}; допускается ровно одна '
                '(valid_to пусто)',
                item_id,
            )

        for revision in revisions:
            mod_type = revision.get('mod_type')
            if mod_type is not None and mod_type not in MOD_TYPES:
                report.error(
                    'bad_mod_type',
                    f'недопустимый mod_type={mod_type!r}; ожидается одно из {MOD_TYPES}',
                    item_id,
                )

        # Ревизия вложенного элемента без valid_from и без mod_type не
        # привязана ни к одной редакции: импортёр молча подставит дату
        # корневой редакции, а режим «выбранная редакция» на сайте не найдёт
        # такую ревизию по modified_by_id (кейс 269-ЗС <- 380-ЗС: часть 1
        # статьи 4 отображалась без внесённых пунктов).
        #
        # У нетронутых элементов базовой редакции отсутствие дат — принятая
        # конвенция, поэтому сигнал подаётся только когда выполнены оба
        # условия: документ исправленный (есть revision_info), элемент
        # вложенный, а его родитель уже привязан к редакции (непустой
        # valid_from). В дереве базовой редакции привязки нет ни у кого, так
        # что ложных срабатываний не возникает.
        if is_amended and parent is not None:
            parent_active = [
                r for r in _revisions(parent) if _is_empty(r.get('valid_to'))
            ]
            parent_has_provenance = any(
                not _is_empty(r.get('valid_from')) for r in parent_active
            )
            if parent_has_provenance:
                for revision in active:
                    if (
                        _is_empty(revision.get('valid_from'))
                        and _is_empty(revision.get('mod_type'))
                        and _is_empty(revision.get('not_valid'))
                        and revision.get('body')
                    ):
                        report.warning(
                            'revision_without_provenance',
                            'активная ревизия вложенного элемента без valid_from и '
                            'mod_type: элемент не привязан к изменяющему НПА '
                            '(риск потери содержимого в выбранной редакции)',
                            item_id,
                        )

        periods = []
        for revision in revisions:
            start = parse_date(revision.get('valid_from'))
            end = parse_date(revision.get('valid_to'))
            if start is not None:
                periods.append((start, end))
        periods.sort(key=lambda pair: pair[0])
        for (start, end), (next_start, _) in zip(periods, periods[1:]):
            if end is None:
                report.error(
                    'open_revision_before_next',
                    f'ревизия с valid_from={start.strftime(DATE_FORMAT)} не закрыта, '
                    f'хотя существует более поздняя (с {next_start.strftime(DATE_FORMAT)})',
                    item_id,
                )
            elif end >= next_start:
                report.error(
                    'overlapping_revisions',
                    f'период ревизии ({start.strftime(DATE_FORMAT)}-'
                    f'{end.strftime(DATE_FORMAT)}) пересекается со следующей '
                    f'(с {next_start.strftime(DATE_FORMAT)}); ожидалось '
                    'valid_to = следующая valid_from - 1 день',
                    item_id,
                )

    return report


def validate_dates(document: dict[str, Any]) -> ValidationReport:
    """Формат дат в ревизиях, примечаниях и паспорте документа."""
    report = ValidationReport()

    for field_name in ('date_reg', 'date_passed', 'date_pub', 'valid_from', 'not_valid'):
        value = document.get(field_name)
        if not _is_empty(value) and parse_date(value) is None:
            report.error(
                'bad_date_format',
                f'{field_name}="{value}" не в формате ДД.ММ.ГГГГ',
            )

    def _check_notes(notes: Any, owner: str | None) -> None:
        for note in notes or []:
            if not isinstance(note, dict):
                continue
            for key in ('valid_from', 'valid_to'):
                value = note.get(key)
                if not _is_empty(value) and parse_date(value) is None:
                    report.error(
                        'bad_note_date',
                        f'примечание: {key}="{value}" не в формате ДД.ММ.ГГГГ',
                        owner,
                    )
            start = parse_date(note.get('valid_from'))
            end = parse_date(note.get('valid_to'))
            if start and end and end < start:
                report.error(
                    'note_period_inverted',
                    f'примечание: valid_to ({note.get("valid_to")}) раньше '
                    f'valid_from ({note.get("valid_from")})',
                    owner,
                )

    _check_notes(document.get('npa_notes'), None)

    for item, _ in iter_items(document):
        item_id = str(item.get('item_id') or '')
        _check_notes(item.get('item_notes'), item_id)
        for revision in _revisions(item):
            for key in ('valid_from', 'valid_to'):
                value = revision.get(key)
                if not _is_empty(value) and parse_date(value) is None:
                    report.error(
                        'bad_revision_date',
                        f'ревизия: {key}="{value}" не в формате ДД.ММ.ГГГГ',
                        item_id,
                    )
            start = parse_date(revision.get('valid_from'))
            end = parse_date(revision.get('valid_to'))
            if start and end and end < start:
                report.error(
                    'revision_period_inverted',
                    f'ревизия: valid_to ({revision.get("valid_to")}) раньше '
                    f'valid_from ({revision.get("valid_from")})',
                    item_id,
                )

    return report


def validate_document(document: dict[str, Any]) -> ValidationReport:
    """Полная валидация документа НПА."""
    report = ValidationReport()
    if not isinstance(document, dict):
        report.error('not_an_object', f'Ожидался JSON-объект, получено {type(document).__name__}')
        return report

    ids_report = validate_ids(document)
    report.items_checked = ids_report.items_checked
    report.issues.extend(ids_report.issues)

    refs_report = validate_refs(document)
    report.issues.extend(refs_report.issues)

    revisions_report = validate_revisions(document)
    report.revisions_checked = revisions_report.revisions_checked
    report.issues.extend(revisions_report.issues)

    dates_report = validate_dates(document)
    report.issues.extend(dates_report.issues)

    return report


def find_new_items_without_provenance(
    original: dict[str, Any],
    result: dict[str, Any],
) -> list[dict[str, str]]:
    """Найти элементы, впервые созданные при внесении изменений, чьи активные
    ревизии не привязаны к изменяющему НПА.

    Сравнивает наборы ``item_id`` исходного и результирующего документа; для
    каждого нового элемента проверяет активную ревизию (``valid_to`` пусто).
    Ревизия без ``valid_from`` и без ``mod_type`` не привязана к изменяющему
    НПА: импортёр подставит дату корневой редакции, а режим «выбранная
    редакция» на сайте не найдёт такую ревизию по ``modified_by_id`` —
    содержимое элемента потеряется в редакции (кейс 269-ЗС <- 380-ЗС:
    часть 1 статьи 4 «внесена без пунктов»).

    Возвращает список ``{'item_id': ..., 'reason': ...}``.
    """
    original_ids = {
        str(item.get('item_id') or '')
        for item, _ in iter_items(original)
        if not _is_empty(item.get('item_id'))
    }
    problems: list[dict[str, str]] = []
    for item, _parent in iter_items(result):
        item_id = str(item.get('item_id') or '')
        if _is_empty(item_id) or item_id in original_ids:
            continue
        for revision in _revisions(item):
            if not _is_empty(revision.get('valid_to')):
                continue
            if _is_empty(revision.get('valid_from')) and _is_empty(revision.get('mod_type')):
                problems.append({
                    'item_id': item_id,
                    'reason': 'активная ревизия нового элемента без valid_from и mod_type',
                })
    return problems
