"""Regression tests for extraction verification fixes (run 380-ЗС → 269-ЗС)."""
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


def test_default_extraction_choice_is_program():
    from npazs.ui.dialogs.extraction_conflict import DEFAULT_EXTRACTION_CHOICE

    assert DEFAULT_EXTRACTION_CHOICE == "program"


def test_normalize_ignores_nbsp_and_inner_block_whitespace():
    from npazs.revision.quote_extraction import extraction_results_equal

    program = (
        '<p class="justifyfull">Статья 5.1. Основания для отказа в постановке '
        'граждан на учет\u00a0</p>'
    )
    ai = (
        "<p>Статья 5.1. Основания для отказа в постановке граждан на учет</p>"
    )
    assert extraction_results_equal(program, ai) is True

    # Переносы строк и атрибуты тоже не должны влиять на сравнение.
    multiline = '<p class="x">Статья 5.1.\n Основания</p>'
    assert extraction_results_equal(multiline, ai) is False  # текст другой
    same_multiline = "<p>Статья 5.1. Основания</p>"
    assert extraction_results_equal(same_multiline, same_multiline) is True


def test_normalize_still_detects_real_difference():
    from npazs.revision.quote_extraction import extraction_results_equal

    assert extraction_results_equal("<p>учет</p>", "<p>снятие с учета</p>") is False


def test_classify_structural_marker_fractional_article():
    from npazs.revision.html_utils import _classify_structural_marker

    assert _classify_structural_marker(
        '<p class="justifyfull">«Статья 5.1. Основания для отказа</p>'
    ) == (0, "5.1")
    assert _classify_structural_marker("<p>Статья 5.2. Основания</p>") == (0, "5.2")
    assert _classify_structural_marker("<p>Статья 12. Общие положения</p>") == (0, "12")
    # Регресс: раньше «Статья 5.1» классифицировалась как (0, "5")
    assert _classify_structural_marker("<p>Статья 5.1. Основания</p>") != (0, "5")


def test_extract_structural_block_finds_quoted_article_5_1():
    from npazs.revision.html_utils import extract_structural_block

    source_html = (
        '<p class="justifyfull">«Статья 5.1. Основания для отказа в постановке '
        'граждан на учет </p>'
        '<p class="justifyfull">Основанием для отказа является:</p>'
        '<p class="justifyfull">1) отсутствие права;</p>'
        '<p class="justifyfull">2) недостоверные сведения.»;</p>'
        '<p class="justifyfull">«Статья 5.2. Основания для снятия граждан с учета</p>'
        '<p class="justifyfull">Основанием для снятия является:</p>'
        '<p class="justifyfull">1) подача заявления.»;</p>'
    )
    extracted = extract_structural_block(source_html, "article", "5.1")
    assert extracted, "маркер 'Статья 5.1' должен находиться в цитируемом блоке"
    assert "Статья 5.1" in extracted
    assert "Статья 5.2" not in extracted, "в блок 5.1 не должна попадать статья 5.2"

    extracted_52 = extract_structural_block(source_html, "article", "5.2")
    assert extracted_52, "маркер 'Статья 5.2' должен находиться в цитируемом блоке"
    assert "Статья 5.2" in extracted_52
    assert "Статья 5.1" not in extracted_52


def test_verify_one_trusts_already_verified_candidate(monkeypatch):
    import npazs.revision.extraction_verifier as ev

    def _fail_ask(*args, **kwargs):
        raise AssertionError("диалог не должен открываться для уже верифицированного изменения")

    monkeypatch.setattr(ev, "_ask_user", _fail_ask)
    change = {
        "type": "add",
        "structural_element": "НПА",
        "content": "<p>вариант ИИ</p>",
        "_quoted_html": "<p>весь диапазон 5.1-5.2 из полного исходника</p>",
        "description": "all",
        "new": "статья 5.1",
        "_verified_extracted_html": "<p>подтверждённая статья 5.1</p>",
    }
    assert ev._verify_one(change, None, None, None) is True
    assert change["_verified_extracted_html"] == "<p>подтверждённая статья 5.1</p>"


def test_verify_add_finds_element_by_pending_change_id():
    from npazs.revision.change_pipeline import _find_element_by_pending_change_id, _verify_add

    data = {
        "npa_items_revision": [
            {
                "item_id": "16012_article_1",
                "item_type": "article",
                "item_number": "1",
                "item_children": [
                    {
                        "item_id": "16012_article_5_1",
                        "item_type": "article",
                        "item_number": "5.1",
                        "_pending_change_id": "db7ad259-c8d",
                        "revisions": [
                            {"revision_id": "rev-add-1", "mod_type": "add"}
                        ],
                    }
                ],
            }
        ]
    }
    found = _find_element_by_pending_change_id(data, "db7ad259-c8d")
    assert found is not None and found["item_id"] == "16012_article_5_1"

    change = {
        "type": "add",
        "structural_element": "НПА",
        "change_id": "db7ad259-c8d",
    }
    assert _verify_add(change, data, None, "rev-add-1") is True


def test_verify_add_finds_element_by_created_item_id():
    from npazs.revision.change_pipeline import _verify_add

    data = {
        "npa_items_revision": [
            {
                "item_id": "16012_article_5_2",
                "item_type": "article",
                "item_number": "5.2",
                "revisions": [{"revision_id": "rev-add-2", "mod_type": "add"}],
            }
        ]
    }
    change = {
        "type": "add",
        "structural_element": "НПА",
        "_created_item_id": "16012_article_5_2",
    }
    assert _verify_add(change, data, None, "rev-add-2") is True


def test_first_difference_hint_points_to_single_word_typo():
    """Реальный случай из лога (Статья 5): ИИ потерял «ин» в «гражданина»."""
    from npazs.revision.extraction_verifier import _first_difference_hint

    program = (
        '<p class="justifyfull">Статья 5. Порядок постановки граждан на учет </p>'
        '<p class="justifyfull">5. В случае смерти … постановке на учет с '
        "сохранением очередности такого гражданина подлежит второй родитель.</p>"
    )
    ai = (
        '<p class="justifyfull">Статья 5. Порядок постановки граждан на учет </p>'
        '<p class="justifyfull">5. В случае смерти … постановке на учет с '
        "сохранением очередности такого граждана подлежит второй родитель.</p>"
    )
    hint = _first_difference_hint(program, ai)
    assert hint.startswith("блок 2")
    prog_part = hint.split("программа «", 1)[1].split("»", 1)[0]
    ai_part = hint.split("ИИ «", 1)[1].split("»", 1)[0]
    assert "гражданина" in prog_part
    assert "гражданина" not in ai_part and "граждана" in ai_part


def test_first_difference_hint_extra_block_and_equal():
    from npazs.revision.extraction_verifier import _first_difference_hint

    two = "<p>один</p><p>два</p>"
    one = "<p>один</p>"
    hint_prog_extra = _first_difference_hint(two, one)
    assert "лишний блок 2" in hint_prog_extra and "у программы" in hint_prog_extra
    hint_ai_extra = _first_difference_hint(one, two)
    assert "у ИИ" in hint_ai_extra
    # Атрибуты/пробелы не считаются различием — подсказки нет.
    assert _first_difference_hint('<p class="x">учет </p>', "<p>учет</p>") == ""
    # Разные теги при равном тексте — подсказка показывает оба HTML-варианта.
    hint_tags = _first_difference_hint("<div>текст</div>", "<p>текст</p>")
    assert "<div>текст</div>" in hint_tags and "<p>текст</p>" in hint_tags

