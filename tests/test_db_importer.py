"""Test DB importer."""
import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "npazs_bootstrap", _ROOT / "src" / "bootstrap.py"
)
assert _spec is not None and _spec.loader is not None
_bootstrap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bootstrap)
_bootstrap.bootstrap()

def test_connection_config():
    from npazs.db.connection import DB_DEFAULTS, DB_CONFIG
    assert "host" in DB_CONFIG
    assert "port" in DB_CONFIG

def test_parse_date():
    from npazs.db.connection import parse_date
    d = parse_date("30.12.2022")
    assert d is not None
    assert d.year == 2022


# ---------------------------------------------------------------------------
# Регрессия 269-ЗС <- 380-ЗС: часть 1 статьи 4 «внесена без пунктов».
#
# Импортёр собирал ревизии только для верхнего уровня и прямых детей, поэтому
# пункты 3-го уровня (внутри вновь созданной части) получали строку в
# npa_item, но НЕ получали ревизий — сайт пропускал их (getItemTree
# отбрасывает элементы без ревизии), и часть 1 отображалась без пунктов.
# ---------------------------------------------------------------------------
_CHANGE_DATE = "15.12.2017"
_MODIFIER = "33699_article_1_point_5"


class _FakeDB:
    """Минимальная заглушка DBConnection: фиксирует вставленные строки."""

    def __init__(self):
        self.revisions = []
        self.paragraphs = []
        self.executed = []

    def fetch_all(self, sql, params=()):
        return []

    def fetch_revision_ids(self, npa_id):
        return {(row[0], row[2]): 1000 + idx for idx, row in enumerate(self.revisions)}

    def bulk_insert(self, table, columns, rows, chunk_size=1000):
        if table == "npa_item_revision":
            self.revisions.extend(rows)
        elif table == "npa_paragraph":
            self.paragraphs.extend(rows)

    def exec_many(self, sql, data, attempts=3, delay=1.0):
        self.executed.append((sql, data))
        return len(data)

    def exec(self, sql, params=(), attempts=3, delay=1.0):
        self.executed.append((sql, params))
        return 1


def _make_importer():
    from npazs.db.importer import NpaImporter

    db = _FakeDB()
    importer = NpaImporter.__new__(NpaImporter)
    importer.db = db
    importer.messages = []
    importer.log = lambda level, msg: importer.messages.append((level, msg))
    importer._tables_cache = {
        "npa_item_revision": True,
        "npa_paragraph": True,
        "npa_item_head_revision": True,
        "npa_item_prefix_revision": True,
    }
    importer._item_id_cache = {}
    importer._person_cache = {}
    importer._post_cache = {}
    importer._conv_cache = {}
    importer._committee_cache = {}
    importer._revision_exists_cache = {}
    return importer, db


def _paragraph(text):
    return {"type": "paragraph", "html_text": text, "order": 1}


def _article4_tree(grandchild_revision):
    """Статья 4 -> часть 1 -> пункт 1) (три уровня вложенности)."""
    point = {
        "item_id": "16012_article_4_part_1_point_1",
        "item_type": "point",
        "item_number": "1)",
        "item_level": 3,
        "revisions": [grandchild_revision],
    }
    part = {
        "item_id": "16012_article_4_part_1",
        "item_type": "part",
        "item_number": "1",
        "item_level": 2,
        "revisions": [
            {
                "body": [
                    _paragraph("<p class=\"justifyfull\">Основанием являются условия:</p>"),
                    {"type": "child_ref", "item_id": point["item_id"], "order": 2},
                ],
                "valid_from": _CHANGE_DATE,
                "mod_type": "new_redaction",
                "modified_by_id": _MODIFIER,
            }
        ],
        "item_children": [point],
    }
    article = {
        "item_id": "16012_article_4",
        "item_type": "article",
        "item_number": "4",
        "item_level": 1,
        "head_revisions": [
            {
                "head_text": "Статья 4. Основания предоставления",
                "valid_from": _CHANGE_DATE,
                "mod_type": "new_redaction",
                "modified_by_id": _MODIFIER,
            }
        ],
        "revisions": [
            {
                "body": [
                    _paragraph("<p>Статья 4 в редакции 380-ЗС;</p>"),
                    {"type": "child_ref", "item_id": part["item_id"], "order": 2},
                ],
                "valid_from": _CHANGE_DATE,
                "mod_type": "new_redaction",
                "modified_by_id": _MODIFIER,
            }
        ],
        "item_children": [part],
    }
    mapping = {article["item_id"]: 1, part["item_id"]: 2, point["item_id"]: 3}
    return article, mapping


def _run_import(grandchild_revision):
    from datetime import date

    importer, db = _make_importer()
    article, mapping = _article4_tree(grandchild_revision)
    importer._insert_items_revisions(
        [article], npa_id=33699, root_valid_from=date(2017, 12, 15),
        mapping=mapping, is_amended=True,
    )
    return importer, db


def test_importer_walks_whole_tree_and_inserts_grandchild_revision():
    """Ревизия пункта 3-го уровня (под частью 1) попадает в npa_item_revision."""
    from datetime import date

    revision = {
        "body": [_paragraph("<p>гражданин принят на учет в порядке, установленном Законом;</p>")],
        "valid_from": _CHANGE_DATE,
        "mod_type": "add",
        "modified_by_id": _MODIFIER,
    }
    _importer, db = _run_import(revision)

    internal_ids = [row[0] for row in db.revisions]
    assert 3 in internal_ids, (
        "ревизия пункта 3-го уровня не вставлена — часть 1 останется без пунктов"
    )
    grandchild = next(row for row in db.revisions if row[0] == 3)
    assert grandchild[2] == date(2017, 12, 15)  # valid_from — дата 380-ЗС
    assert grandchild[4] == "add"               # mod_type

    grandchild_paras = [row for row in db.paragraphs if row[1] == 3]
    assert grandchild_paras, "параграфы пункта 3-го уровня не вставлены"
    assert all(row[0] is not None for row in grandchild_paras)


def test_importer_warns_when_nested_revision_has_no_provenance():
    """Ревизия внука без valid_from/mod_type: WARN + дата корневой редакции."""
    revision = {"body": [_paragraph("<p>пункт без привязки к редакции;</p>")]}
    importer, db = _run_import(revision)

    warnings = [msg for level, msg in importer.messages if level == "WARN"]
    assert any("16012_article_4_part_1_point_1" in w for w in warnings), (
        f"нет WARN про потерю привязки: {importer.messages}"
    )
    assert any("2017-12-15" in w for w in warnings), (
        f"WARN не сообщает подставленную дату: {warnings}"
    )

    grandchild = next(row for row in db.revisions if row[0] == 3)
    assert grandchild[4] is None   # mod_type отсутствует
    assert grandchild[3] is None   # valid_to отсутствует (активная ревизия)


