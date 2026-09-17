"""Регрессионные тесты: впервые созданное поддерево должно получать привязку
к изменяющему НПА.

Воспроизводится кейс 269-ЗС <- 380-ЗС: 380-ЗС изложил статью 4 в новой
редакции, из-за чего в статье 4 появились части 1-2, а бывшие прямые пункты
1)-5) оказались внутри части 1 с новыми ``item_id``. Парсер создаёт ревизии
новых элементов с голым ``body`` (без ``valid_from``, ``mod_type`` и
``modified_by_id``); до исправления эти атрибуты у нового поддерева просто
снимались (``pop``), и элемент оставался без привязки к 380-ЗС:

* импортёр молча подставлял дату корневой редакции (08.08.2016) — пункты
  «существовали» с 2016 года и не были связаны с изменяющим НПА;
* режим «выбранная редакция» на сайте ищет ревизию по ``modified_by_id``
  (``getRevisionForSelectedEdition``) и не находил её — часть 1 статьи 4
  отображалась **без пунктов**;
* ни верификация, ни change tracker, ни пост-анализ, ни ``validate`` этого
  не видели, потому что проверялось только тело целевого элемента.

Тесты фиксируют три независимых барьера: штамп при слиянии дерева,
правило валидатора и контроль привязки в пайплайне.
"""
import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "npazs_bootstrap", _ROOT / "src" / "bootstrap.py"
)
assert _spec is not None and _spec.loader is not None
_bootstrap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bootstrap)
_bootstrap.bootstrap()


_CHANGE_DATE = "15.12.2017"
_PREV_DAY = "14.12.2017"
_MODIFIER = "33699_article_1_point_5"  # пункт 5 ст. 1 закона 380-ЗС
_ARTICLE_ID = "16012_article_4"
_PART_1 = f"{_ARTICLE_ID}_part_1"
_PART_2 = f"{_ARTICLE_ID}_part_2"


def _old_point(num):
    """Пункт статьи 4 в исходной редакции (прямой ребёнок статьи)."""
    return {
        "item_id": f"{_ARTICLE_ID}_point_{num}",
        "item_type": "point",
        "item_number": f"{num})",
        "item_level": 2,
        "revisions": [
            {
                "body": [
                    {
                        "type": "paragraph",
                        "html_text": f"<p>исходный пункт {num}) редакции 08.08.2016;</p>",
                        "order": 1,
                    }
                ]
            }
        ],
    }


def _old_article4():
    """Статья 4 до 380-ЗС: прямые пункты 1)-3), у ревизий нет метаданных."""
    children = [_old_point(n) for n in (1, 2, 3)]
    body = [
        {"type": "paragraph", "html_text": "<p>Статья 4. Основания предоставления;</p>", "order": 1}
    ]
    for idx, child in enumerate(children, start=2):
        body.append({"type": "child_ref", "item_id": child["item_id"], "order": idx})
    return {
        "item_id": _ARTICLE_ID,
        "item_type": "article",
        "item_number": "4",
        "item_level": 1,
        "head_revisions": [{"head_text": "Статья 4. Основания предоставления"}],
        "revisions": [{"body": body}],
        "item_children": children,
    }


def _new_point(num):
    """Пункт внутри вновь созданной части 1 (как его отдаёт парсер)."""
    return {
        "item_id": f"{_PART_1}_point_{num}",
        "item_type": "point",
        "item_number": f"{num})",
        "item_level": 3,
        "revisions": [
            {
                "body": [
                    {
                        "type": "paragraph",
                        "html_text": f"<p>пункт {num}) в редакции 380-ЗС;</p>",
                        "order": 1,
                    }
                ]
            }
        ],
    }


def _new_article4():
    """Статья 4 после 380-ЗС («в новой редакции»): части 1-2, пункты внутри части 1."""
    points = [_new_point(n) for n in (1, 2, 3)]
    part_body = [
        {
            "type": "paragraph",
            "html_text": "<p>Основанием для предоставления участков являются условия:</p>",
            "order": 1,
        }
    ]
    for idx, point in enumerate(points, start=2):
        part_body.append({"type": "child_ref", "item_id": point["item_id"], "order": idx})
    part_1 = {
        "item_id": _PART_1,
        "item_type": "part",
        "item_number": "1",
        "item_level": 2,
        "revisions": [{"body": part_body}],
        "item_children": points,
    }
    part_2 = {
        "item_id": _PART_2,
        "item_type": "part",
        "item_number": "2",
        "item_level": 2,
        "revisions": [
            {
                "body": [
                    {"type": "paragraph", "html_text": "<p>Часть 2 статьи 4 в редакции 380-ЗС;</p>", "order": 1}
                ]
            }
        ],
    }
    return {
        "item_id": _ARTICLE_ID,
        "item_type": "article",
        "item_number": "4",
        "item_level": 1,
        "head_revisions": [{"head_text": "Статья 4. Основания предоставления"}],
        "revisions": [
            {
                "body": [
                    {"type": "paragraph", "html_text": "<p>Статья 4 в редакции 380-ЗС;</p>", "order": 1},
                    {"type": "child_ref", "item_id": _PART_1, "order": 2},
                    {"type": "child_ref", "item_id": _PART_2, "order": 3},
                ]
            }
        ],
        "item_children": [part_1, part_2],
    }


def _sync_article4():
    """Выполнить слияние статьи 4 (как это делает этап перестройки дерева)."""
    from npazs.revision.ui_utils import sync_structural_element_recursive

    old_article = _old_article4()
    sync_structural_element_recursive(
        old_element=old_article,
        new_element=_new_article4(),
        change_date=_CHANGE_DATE,
        modified_by_id=_MODIFIER,
        data_context=None,
        log_callback=lambda *_a, **_k: None,
        is_top_level=True,
        override_mod_type="new_redaction",
        highlights=None,
    )
    return old_article


def _by_id(root, item_id):
    if root.get("item_id") == item_id:
        return root
    for child in root.get("item_children", []):
        found = _by_id(child, item_id)
        if found is not None:
            return found
    return None


def _document(article, amended=True):
    doc = {"npa_id": 16012, "npa_items_revision": [article]}
    if amended:
        doc["revision_info"] = [{"revision_id": "33699", "revision_date_valid": _PREV_DAY}]
    return doc


def _strip_provenance(article, item_id):
    """Имитировать прежнее (сломанное) поведение: метаданные ревизии сняты."""
    item = _by_id(article, item_id)
    for rev in item["revisions"]:
        rev.pop("valid_from", None)
        rev.pop("mod_type", None)
        rev.pop("modified_by_id", None)
    return article


# --------------------------------------------------------------- штамп ревизий
def test_new_part_and_points_get_provenance_after_sync():
    """Каждый новый элемент поддерева привязан к 380-ЗС и дате 15.12.2017.

    Без этого импортёр подставляет дату корневой редакции (08.08.2016),
    а сайт в режиме «выбранная редакция» не находит ревизию по
    modified_by_id — часть 1 отображается без пунктов.
    """
    article = _sync_article4()

    for item_id in (
        _PART_1,
        _PART_2,
        f"{_PART_1}_point_1",
        f"{_PART_1}_point_2",
        f"{_PART_1}_point_3",
    ):
        item = _by_id(article, item_id)
        assert item is not None, f"{item_id} потерян при слиянии"
        revs = item["revisions"]
        assert len(revs) == 1, f"{item_id}: ожидалась одна активная ревизия, {revs}"
        rev = revs[0]
        assert rev.get("valid_from") == _CHANGE_DATE, f"{item_id}: valid_from={rev.get('valid_from')}"
        assert rev.get("mod_type"), f"{item_id}: не проставлен mod_type"
        assert rev.get("modified_by_id") == _MODIFIER, (
            f"{item_id}: modified_by_id={rev.get('modified_by_id')}"
        )
        assert rev.get("valid_to") in (None, ""), f"{item_id}: активная ревизия закрыта"


def test_part_with_points_is_kept_whole():
    """Часть 1 не «теряет» пункты: дети на месте и на них есть child_ref."""
    article = _sync_article4()
    part_1 = _by_id(article, _PART_1)
    numbers = [c.get("item_number") for c in part_1.get("item_children", [])]
    assert numbers == ["1)", "2)", "3)"]

    refs = {
        block.get("item_id")
        for block in part_1["revisions"][0]["body"]
        if block.get("type") == "child_ref"
    }
    assert refs == {f"{_PART_1}_point_{n}" for n in (1, 2, 3)}


def test_moved_old_points_are_closed_with_not_valid():
    """Прямые пункты статьи 4 (бывшие до 380-ЗС) закрыты и помечены not_valid."""
    article = _sync_article4()
    for num in (1, 2, 3):
        old_point = _by_id(article, f"{_ARTICLE_ID}_point_{num}")
        if old_point is None:
            continue  # элемент удалён из дерева — допустимо
        rev = old_point["revisions"][-1]
        assert rev.get("valid_to") == _PREV_DAY
        assert rev.get("not_valid") == _MODIFIER


# ------------------------------------------------------- контроль пайплайна
def test_find_new_items_without_provenance_detects_bug_shape():
    """Проверка пайплайна ловит «голые» ревизии новых элементов."""
    from npazs.utils.validation import find_new_items_without_provenance

    old_article = _old_article4()
    result = _sync_article4()
    broken = _strip_provenance(_sync_article4(), _PART_1)

    assert find_new_items_without_provenance(
        _document(old_article), _document(broken)
    ), "сломанное поддерево должно обнаруживаться"
    assert find_new_items_without_provenance(
        _document(old_article), _document(result)
    ) == [], "исправленное поддерево не должно давать замечаний"


def test_validator_warns_on_nested_revision_without_provenance():
    """Валидатор предупреждает о вложенной ревизии без привязки к редакции."""
    from npazs.utils.validation import validate_document

    result = _sync_article4()
    clean = validate_document(_document(result))
    assert "revision_without_provenance" not in {i.code for i in clean.warnings}

    broken = _strip_provenance(_sync_article4(), _PART_1)
    dirty = validate_document(_document(broken))
    flagged = {i.item_id for i in dirty.warnings if i.code == "revision_without_provenance"}
    assert _PART_1 in flagged, f"часть 1 не помечена: {dirty.warnings}"

