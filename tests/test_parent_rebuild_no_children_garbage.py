"""Regression: перестройка родителя не должна «выносить» тексты дочерних пунктов
в тело родителя неструктурированными абзацами.

Воспроизводит баг прогона 516-ЗС -> 127-ЗС (правка 6)->г)): в части 5 статьи 6
после пункта 9) в новой ревизии «вылезали» тексты пунктов 1-9 (в новых редакциях)
и добавленных 10-11 как неструктурированные абзацы, и только потом шли child_ref
новых пунктов. Причина была двойной:

1. ``apply_grouped_changes`` отправлял ИИ и клал в ``_pending_new_redaction_html``
   ПОЛНЫЙ HTML элемента с развёрнутыми текстами детей (``get_full_element_html``);
2. оркестратор на этапе перестройки дописывал HTML перестроенных детей (без
   нумераторов) в этот pending — парсер распознавал только «эхо» ИИ, а
   безномерные копии падали в collected_content родителя обычными абзацами.

Фикс: собственный текст родителя готовится через ``get_own_text_html`` (без
детей), а ``update_parent_pending_html`` больше не дописывает тексты детей в
собственный pending родителя — дети сохраняются в теле как ``child_ref``.
"""
import importlib.util
import re
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "npazs_bootstrap", _ROOT / "src" / "bootstrap.py"
)
_bootstrap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bootstrap)
_bootstrap.bootstrap()

_CHANGE_DATE = "19.07.2019"
_MODIFIED_BY = "59121_article_1_point_6_subpoint_г"
_GOVERNOR = "в Законодательное Собрание города Севастополя"

_INTRO_OLD = (
    "К предложению о внесении кандидатуры на должность Уполномоченного "
    "должны быть приложены следующие документы:"
)
_INTRO_NEW = _INTRO_OLD.replace("должны быть приложены", "прилагаются")

_POINT_OLD = {
    1: "письменное заявление кандата о согласии на внесение его кандидатуры для назначения на должность Уполномоченного, в котором указываются: фамилия, имя, отчество;",
    2: "копия паспорта гражданина Российской Федерации или копия основного документа, содержащего указание на гражданство кандидата;",
    3: "анкета, содержащая биографические сведения о кандидате;",
    4: "автобиография кандидата;",
    5: "копия трудовой книжки кандидата;",
    6: "копия документа о высшем профессиональном образовании кандидата;",
    7: "сведения о доходах кандидата;",
    8: "справка о наличии (отсутствии) судимости;",
    9: "справка об отсутствии заболевания;",
}
_POINT_NEW = {
    1: (
        "письменное заявление кандидата о согласии на внесение его кандидатуры "
        f"{_GOVERNOR} для назначения на должность Уполномоченного, в котором "
        "указываются: фамилия, имя, отчество;"
    ),
    2: "копия паспорта гражданина Российской Федерации;",
    3: "анкета, содержащая биографические сведения о кандидате, по форме, установленной федеральным законодательством;",
    4: "копия документа о высшем образовании кандидата;",
    7: "сведения о доходах, расходах, об имуществе и обязательствах имущественного характера кандидата;",
    9: "заключение медицинского учреждения об отсутствии у кандидата заболевания;",
}
_POINT_10 = "согласие кандидата на обработку его персональных данных;"
_POINT_11 = (
    "иные документы и материалы, подтверждающие наличие у кандидата опыта "
    "работы по реализации и защите прав и законных интересов детей."
)
_CHANGED_POINTS = (1, 2, 3, 4, 7, 9)
_PART5_ID = "60050_article_6_part_5"

def _norm(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


def _log_collector():
    lines = []

    def log(msg, level="info"):
        lines.append(f"[{level}] {msg}")

    return log, lines


def _make_point(n):
    point = {
        "item_id": f"{_PART5_ID}_point_{n}",
        "item_type": "point",
        "item_number": f"{n})",
        "item_level": 3,
        "item_children": [],
        "revisions": [
            {
                "revision_id": f"rev-old-{n}",
                "body": [
                    {
                        "type": "paragraph",
                        "html_text": f'<p class="justifyfull">{_POINT_OLD[n]}</p>',
                        "order": 1,
                    }
                ],
            }
        ],
    }
    if n in _CHANGED_POINTS:
        # Пункт уже перестроен сам (как это делает оркестратор перед родителем)
        point["revisions"][0]["valid_to"] = "18.07.2019"
        point["revisions"].append(
            {
                "revision_id": f"rev-new-{n}",
                "body": [
                    {
                        "type": "paragraph",
                        "html_text": f"<p>{_POINT_NEW[n]}</p>",
                        "order": 1,
                    }
                ],
                "mod_type": "change",
                "modified_by_id": _MODIFIED_BY,
                "valid_from": _CHANGE_DATE,
            }
        )
    return point


def _make_doc():
    """Мини-документ 60050: статья 6 -> часть 5 -> пункты 1-11.

    Состояние имитирует момент перед перестройкой части 5 в реальном прогоне:
    пункты 1,2,3,4,7,9 уже перестроены сами (активная ревизия датирована датой
    изменения), пункты 10 и 11 добавлены (pending add), у части 5 есть
    собственный pending (изменение первого абзаца).
    """
    points = [_make_point(n) for n in range(1, 10)]
    for n, text in ((10, _POINT_10), (11, _POINT_11)):
        points.append(
            {
                "item_id": f"{_PART5_ID}_point_{n}",
                "item_type": "point",
                "item_number": f"{n})",
                "item_level": 3,
                "item_children": [],
                "revisions": [],
                "_pending_new_redaction_html": f"<p>{text}</p>",
                "_pending_mod_type": "add",
                "_pending_modified_by_id": _MODIFIED_BY,
                "_pending_valid_from": _CHANGE_DATE,
            }
        )

    part_5 = {
        "item_id": _PART5_ID,
        "item_type": "part",
        "item_number": "5",
        "item_level": 2,
        "item_children": points,
        "revisions": [
            {
                "revision_id": "rev-part5-old",
                "body": [
                    {
                        "type": "paragraph",
                        "html_text": f'<p class="justifyfull">{_INTRO_OLD}</p>',
                        "order": 1,
                    }
                ]
                + [
                    {
                        "type": "child_ref",
                        "item_id": f"{_PART5_ID}_point_{n}",
                        "order": n + 1,
                    }
                    for n in range(1, 10)
                ],
            }
        ],
        "_pending_new_redaction_html": f'<p class="justifyfull">{_INTRO_NEW}</p>',
        "_pending_mod_type": "change",
        "_pending_modified_by_id": _MODIFIED_BY,
        "_pending_valid_from": _CHANGE_DATE,
    }
    article_6 = {
        "item_id": "60050_article_6",
        "item_type": "article",
        "item_number": "6",
        "item_level": 1,
        "item_children": [part_5],
        "head_revisions": [{"head_text": "Полномочия Уполномоченного"}],
        "revisions": [
            {
                "body": [
                    {"type": "child_ref", "item_id": _PART5_ID, "order": 1},
                ]
            }
        ],
    }
    return {"npa_id": "60050", "npa_items_revision": [article_6]}


def _changed_point_ids():
    return {f"{_PART5_ID}_point_{n}" for n in _CHANGED_POINTS} | {
        f"{_PART5_ID}_point_10",
        f"{_PART5_ID}_point_11",
    }


def _active_revision(item):
    for rev in reversed(item.get("revisions", [])):
        if rev.get("valid_to") is None:
            return rev
    return None


def test_update_parent_pending_html_keeps_own_pending_intact():
    """При собственном pending родителя тексты детей НЕ дописываются."""
    from npazs.pipeline.orchestrator import update_parent_pending_html

    data = _make_doc()
    part_5 = data["npa_items_revision"][0]["item_children"][0]
    log, lines = _log_collector()
    pending_before = part_5["_pending_new_redaction_html"]

    update_parent_pending_html(part_5, part_5["item_id"], _changed_point_ids(), data, log)

    assert part_5["_pending_new_redaction_html"] == pending_before, (
        "собственный pending родителя не должен дополняться текстами детей"
    )
    assert _POINT_10 not in part_5["_pending_new_redaction_html"]
    assert _POINT_11 not in part_5["_pending_new_redaction_html"]
    assert any("не дописываются" in line for line in lines)


def test_update_parent_pending_html_falls_back_to_full_flatten():
    """Без собственного pending родитель получает полный HTML (как раньше)."""
    from npazs.pipeline.orchestrator import update_parent_pending_html

    data = _make_doc()
    part_5 = data["npa_items_revision"][0]["item_children"][0]
    for attr in (
        "_pending_new_redaction_html",
        "_pending_mod_type",
        "_pending_modified_by_id",
        "_pending_valid_from",
    ):
        part_5.pop(attr, None)

    log, _ = _log_collector()
    update_parent_pending_html(part_5, part_5["item_id"], _changed_point_ids(), data, log)

    pending = part_5.get("_pending_new_redaction_html", "")
    assert pending, "полный HTML должен быть собран"
    assert _INTRO_OLD in _norm(pending)
    # Дети разворачиваются с нумераторами — парсер сможет построить структуру
    assert "1) " in pending


def test_rebuild_parent_produces_refs_without_garbage_paragraphs():
    """Полный сценарий: перестройка детей, затем части 5.

    В активной ревизии части 5 должны быть: новый вводный абзац + child_ref на
    все 11 пунктов по порядку и НИ ОДНОГО абзаца с текстом пункта.
    """
    from npazs.pipeline.orchestrator import update_parent_pending_html
    from npazs.revision.ui_utils import rebuild_element_with_history

    data = _make_doc()
    part_5 = data["npa_items_revision"][0]["item_children"][0]
    part_5_id = part_5["item_id"]
    log, _ = _log_collector()
    valid_from = date(2019, 7, 19)
    raw_ids = _changed_point_ids()

    # Оркестратор: сначала дети (по глубине), затем родитель
    update_parent_pending_html(part_5, part_5_id, raw_ids, data, log)
    for n in (10, 11):
        assert rebuild_element_with_history(
            data,
            f"{part_5_id}_point_{n}",
            valid_from=valid_from,
            modified_by_id_str=_MODIFIED_BY,
            doc_type="law",
            log_callback=log,
        ), f"перестройка пункта {n} должна завершиться успешно"

    assert rebuild_element_with_history(
        data,
        part_5_id,
        valid_from=valid_from,
        modified_by_id_str=_MODIFIED_BY,
        doc_type="law",
        log_callback=log,
    ), "перестройка части 5 должна завершиться успешно"

    # --- проверки результата ---
    active = _active_revision(part_5)
    assert active is not None and active.get("valid_from") == _CHANGE_DATE
    body = active["body"]

    # 1) первый блок — вводный абзац в новой редакции
    assert body[0]["type"] == "paragraph"
    assert "прилагаются" in _norm(body[0]["html_text"])

    # 2) все остальные блоки — child_ref на пункты 1-11 строго по порядку
    refs = [b for b in body[1:] if b["type"] == "child_ref"]
    paragraphs_after_intro = [b for b in body[1:] if b["type"] == "paragraph"]
    expected_ids = [f"{part_5_id}_point_{n}" for n in range(1, 12)]
    assert [r["item_id"] for r in refs] == expected_ids, (
        f"ожидались child_ref 1-11 по порядку, получено: {[r['item_id'] for r in refs]}"
    )
    assert len(body) == 1 + len(refs), (
        "в теле части 5 есть лишние блоки: "
        f"{[(b['type'], _norm(b.get('html_text', ''))[:80]) for b in body]}"
    )

    # 3) главный признак бага: никакой абзац в теле родителя не дублирует текст пункта
    point_texts = []
    for n in range(1, 12):
        point = next(
            c for c in part_5["item_children"] if c["item_id"] == f"{part_5_id}_point_{n}"
        )
        for rev in point["revisions"]:
            point_texts.extend(
                _norm(b.get("html_text", ""))
                for b in rev.get("body", [])
                if b.get("type") == "paragraph"
            )
    for block in paragraphs_after_intro:
        text = _norm(block.get("html_text", ""))
        for pt in point_texts:
            assert not (pt and (pt in text or text in pt)), (
                f"текст пункта продублирован абзацем в теле части 5: {text[:120]}"
            )

    # 4) собственные ревизии пунктов не тронуты: правка пункта 1 жива
    point_1 = next(
        c for c in part_5["item_children"] if c["item_id"] == f"{part_5_id}_point_1"
    )
    p1_active = _active_revision(point_1)
    assert p1_active.get("valid_from") == _CHANGE_DATE
    assert _GOVERNOR in _norm(p1_active["body"][0]["html_text"])

    # 5) новые пункты 10 и 11 получили свои add-ревизии
    for n, text in ((10, _POINT_10), (11, _POINT_11)):
        point = next(
            c for c in part_5["item_children"] if c["item_id"] == f"{part_5_id}_point_{n}"
        )
        active_point = _active_revision(point)
        assert active_point is not None, f"у пункта {n} должна появиться активная ревизия"
        assert active_point.get("valid_from") == _CHANGE_DATE
        assert text in _norm(active_point["body"][0]["html_text"])


