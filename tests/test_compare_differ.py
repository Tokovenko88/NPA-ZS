"""Тесты построения структурных элементов и посимвольного сравнения."""
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

from npazs.compare.converters import Block  # noqa: E402
from npazs.compare.differ import compare_elements  # noqa: E402
from npazs.compare.tree import build_elements, path_key  # noqa: E402


def _blocks(*texts):
    return [Block(kind='paragraph', text=t, order=i) for i, t in enumerate(texts)]


# --------------------------------------------------------------------- tree
def test_build_elements_paths():
    elements = build_elements(
        _blocks(
            'Статья 1. Общие положения',
            'Текст статьи 1.',
            'Статья 2. Полномочия',
            'Орган осуществляет полномочия.',
        )
    )
    assert len(elements) == 2
    first, second = elements
    assert first.path_text == 'статья 1'
    assert first.text == 'Текст статьи 1.'
    assert second.text == 'Орган осуществляет полномочия.'
    assert first.key == (('article', '1'),)
    assert second.key == (('article', '2'),)


def test_build_elements_nested_chapter():
    elements = build_elements(
        _blocks(
            'Раздел II. Полномочия',
            'Глава 3. Финансы',
            'Статья 11. Бюджет',
            'Бюджет формируется на год.',
        )
    )
    assert len(elements) == 1
    el = elements[0]
    # римские цифры сохраняются целиком (раньше 'II' усекалась до 'I'),
    # в каноническом ключе — нижний регистр (как в _norm_json_number базы)
    assert el.key == (('section', 'ii'), ('chapter', '3'), ('article', '11'))
    assert 'глава 3' in el.path_text and 'статья 11' in el.path_text
    assert 'II' in el.path_text


# ------------------------------------------------------------------- differ
def test_compare_identical_documents():
    blocks = _blocks('Статья 1. Общие положения', 'Текст.', 'Статья 2. Итог', 'Текст 2.')
    ours = build_elements(blocks)
    theirs = build_elements(blocks)
    diffs, stats, cosmetics = compare_elements(ours, theirs)
    assert diffs == []
    assert cosmetics == []
    assert sum(stats.values()) == 0


def test_compare_char_level_change():
    ours = build_elements(_blocks('Статья 1. Положения', 'Срок равен 10 дням.'))
    theirs = build_elements(_blocks('Статья 1. Положения', 'Срок равен 15 дням.'))
    diffs, stats, cosmetics = compare_elements(ours, theirs)
    assert stats.get('change') == 1
    assert cosmetics == []
    diff = diffs[0]
    assert diff.kind == 'change'
    assert diff.old and diff.new
    assert '0' in diff.old and '5' in diff.new
    # фрагмент снабжён контекстом (читабельность отчёта)
    assert 'Срок равен' in diff.old and 'Срок равен' in diff.new
    assert diff.count >= 1


def test_compare_punctuation_diff_is_cosmetic():
    # Различие только в пунктуации — не содержательное: попадает в
    # косметический список, основной список расхождений остаётся чистым.
    ours = build_elements(_blocks('Статья 1. Положения', 'Полномочия органа: контроль.'))
    theirs = build_elements(_blocks('Статья 1. Положения', 'Полномочия органа; контроль.'))
    diffs, stats, cosmetics = compare_elements(ours, theirs)
    assert diffs == []
    assert stats.get('cosmetic') == 1
    assert len(cosmetics) == 1
    assert ':' in cosmetics[0].old and ';' in cosmetics[0].new


def test_compare_case_diff_is_cosmetic():
    # Различие в регистре («интересов» vs «Интересов») — оформление.
    ours = build_elements(_blocks('Статья 1. Положения', 'защита интересов детей'))
    theirs = build_elements(_blocks('Статья 1. Положения', 'защита Интересов детей'))
    diffs, stats, cosmetics = compare_elements(ours, theirs)
    assert diffs == []
    assert stats.get('cosmetic') == 1


def test_compare_single_comma_not_split_into_huge_fragments():
    # Регрессия autojunk: одно различие (запятая) не должно дробиться
    # на несколько крупных ложных фрагментов.
    ours = build_elements(_blocks('Статья 1. Положения', 'рассматривает обращения, граждан'))
    theirs = build_elements(_blocks('Статья 1. Положения', 'рассматривает обращения граждан'))
    diffs, stats, cosmetics = compare_elements(ours, theirs)
    assert diffs == []
    assert stats.get('cosmetic') == 1


def test_compare_add_and_remove():
    ours = build_elements(_blocks('Статья 1. Положения', 'Текст проекта.'))
    theirs = build_elements(
        _blocks('Статья 1. Положения', 'Текст проекта.', 'Статья 2. Новая')
    )
    # элемент есть только в правовой системе -> remove
    diffs, stats, cosmetics = compare_elements(ours, theirs)
    assert stats.get('remove') == 1
    assert diffs[0].kind == 'remove'
    assert 'Новая' in (diffs[0].new or diffs[0].old)

    # элемент есть только в документе проекта -> add
    diffs, stats, cosmetics = compare_elements(theirs, ours)
    assert stats.get('add') == 1
    assert diffs[0].kind == 'add'
    assert 'Новая' in (diffs[0].old or diffs[0].new)
