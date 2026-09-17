"""Regression tests for extraction verification fixes (run 380-ЗС → 269-ЗС)."""
import importlib.util
from pathlib import Path

import pytest

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


def _statya_8_variants():
    """Реальный случай: ИИ потерял точку в конце второго абзаца статьи 8."""
    program = (
        '<p class="justifyfull">Статья 8. Максимальные и минимальные размеры '
        'земельных участков, предоставляемых гражданам в собственность бесплатно</p>\n'
        '<p class="justifyfull">Для земельных участков, предоставляемых в '
        'соответствии с настоящим Законом для индивидуального жилищного строительства '
        'в собственность бесплатно, устанавливаются следующие предельные (минимальные '
        'и максимальные) размеры – от 0,04 до 0,10 гектара.</p>'
    )
    return program, program.replace("гектара.</p>", "гектара</p>")


def test_diff_fragments_expand_single_char_difference_to_paragraph():
    """Различие в один символ должно подсвечивать абзац, а не теряться в тексте."""
    from npazs.ui.dialogs.extraction_conflict import _diff_fragments

    program, ai = _statya_8_variants()
    fragments = _diff_fragments(program, ai)
    assert len(fragments) == 1

    fragment = fragments[0]
    assert fragment["op"] == "delete"
    assert program[fragment["prog"][0]:fragment["prog"][1]] == "."

    # Фоном закрывается весь абзац с различием, а не один символ.
    block_start, block_end = fragment["prog_vis"]
    assert program[block_start:block_end].startswith('<p class="justifyfull">Для земельных')
    assert program[block_start:block_end].endswith("гектара.</p>")

    # У варианта ИИ самого символа нет: точного диапазона нет, но тот же абзац
    # тоже закрашивается — чтобы различие было видно в обеих панелях.
    assert fragment["ai"][0] == fragment["ai"][1]
    ai_block_start, ai_block_end = fragment["ai_vis"]
    assert ai[ai_block_start:ai_block_end].startswith('<p class="justifyfull">Для земельных')
    assert ai[ai_block_start:ai_block_end].endswith("гектара</p>")
    assert fragment["position"] == fragment["ai"][0]


def test_diff_fragments_detect_insert_and_replace():
    from npazs.ui.dialogs.extraction_conflict import _diff_fragments

    # Лишние символы у ИИ — вставки, у программы в этих местах ничего не подсвечивается.
    program = "<p>учет граждан</p>"
    ai = "<p>снятие с учета граждан!</p>"
    fragments = _diff_fragments(program, ai)
    assert fragments, "различия должны находиться"
    assert any(ai[f["ai"][0]:f["ai"][1]].endswith("!") for f in fragments), (
        "лишний символ «!» в варианте ИИ должен быть найден"
    )
    assert all(f["op"] == "insert" for f in fragments)
    assert all(f["prog_vis"] is not None for f in fragments), (
        "в панели программы тоже должен закрашиваться абзац с различием"
    )

    # Вставка в самый конец текста не должна выходить за его границы.
    tail_program, tail_ai = "<p>учет</p>", "<p>учет</p>!"
    tail = _diff_fragments(tail_program, tail_ai)
    assert tail and all(f["prog_vis"][1] <= len(tail_program) for f in tail)
    assert all(f["ai_vis"][1] <= len(tail_ai) for f in tail)

    # Замена символа той же длины отмечается с обеих сторон.
    program_yo, ai_yo = "<p>учет</p>", "<p>учёт</p>"
    replaced = _diff_fragments(program_yo, ai_yo)
    assert [f["op"] for f in replaced] == ["replace"]
    assert program_yo[replaced[0]["prog"][0]:replaced[0]["prog"][1]] == "е"
    assert ai_yo[replaced[0]["ai"][0]:replaced[0]["ai"][1]] == "ё"

    assert _diff_fragments(program, program) == []


def test_diff_summary_names_the_missing_symbol():
    from npazs.ui.dialogs.extraction_conflict import _diff_fragments, _diff_summary_lines

    program, ai = _statya_8_variants()
    summary = _diff_summary_lines(program, ai, _diff_fragments(program, ai))
    assert summary[0].startswith("Различий: 1")
    assert "в программе лишнее «.»" in summary[1]
    assert "в варианте ИИ на этом месте символа нет" in summary[1]


def test_expand_range_falls_back_to_sentence():
    from npazs.ui.dialogs.extraction_conflict import _expand_range

    text = "Первое предложение. Второе предложение с различием. Третье предложение."
    start = text.index("различием")
    expanded = _expand_range(text, start, start + len("различием"))
    assert expanded is not None
    assert text[expanded[0]:expanded[1]].strip() == "Второе предложение с различием."


def test_expand_range_falls_back_to_window_for_huge_paragraph():
    from npazs.ui.dialogs.extraction_conflict import (
        _DIFF_SENTENCE_WINDOW,
        _expand_range,
    )

    text = ("слово " * 200) + "конец.</p>"
    start = text.index("конец")
    end = start + len("конец")
    expanded = _expand_range(text, start, end, block_limit=50)
    assert expanded is not None
    # Абзац больше лимита — блоком становится предложение вместе с точкой.
    assert expanded == (start - _DIFF_SENTENCE_WINDOW, end + 1)
    text_small = "без разделителей " * 20
    middle = len(text_small) // 2
    assert _expand_range(text_small, middle, middle + 1) == (
        middle - _DIFF_SENTENCE_WINDOW,
        middle + 1 + _DIFF_SENTENCE_WINDOW,
    )


def test_highlight_index_survives_newlines():
    """Регресс: индексы вида ``1.N`` обнулялись после первого перевода строки."""
    import tkinter as tk

    from npazs.ui.dialogs.extraction_conflict import ExtractionConflictDialog, _diff_fragments

    try:
        root = tk.Tk()
    except tk.TclError:  # pragma: no cover - среда без графического дисплея
        pytest.skip("нет графического дисплея для Tk")
    root.withdraw()
    try:
        program = '<p>Статья 8</p>\n<p>гектара.</p>'
        ai = '<p>Статья 8</p>\n<p>гектара</p>'
        widget = tk.Text(root)
        widget.insert("1.0", program)
        start, end = _diff_fragments(program, ai)[0]["prog"]
        widget.tag_add(
            "diff_exact_program",
            ExtractionConflictDialog._index(start),
            ExtractionConflictDialog._index(end),
        )
        ranges = widget.tag_ranges("diff_exact_program")
        assert ranges, "подсветка после перевода строки не должна теряться"
        assert widget.get(ranges[0], ranges[1]) == "."
    finally:
        root.destroy()

