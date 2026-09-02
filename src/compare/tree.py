"""Построение структурных элементов НПА по тексту документа.

Из потока блоков (см. :mod:`npazs.compare.converters`) выделяем структурные
заголовки (раздел/глава/статья/часть/приложение) и группируем под ними
блоки в :class:`Element`. Элементы затем используются для попарного
посимвольного сравнения документов.

Нумерованные пункты («1) …») внутри статьи сознательно НЕ выносятся в
отдельные элементы — это стилистический приём, и сопоставление по статье/
части остаётся устойчивым между разными форматами.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .converters import Block

__all__ = ['Element', 'build_elements', 'path_key', 'path_text']

#: Регулярки структурных заголовков.
_STRUCT_WORD_RE = re.compile(
    r'^(раздел|глава|статья|часть|приложение|преамбула)\b', re.IGNORECASE
)
_STRUCT_NUM_RE = re.compile(r'([\dIVXLC]+(?:[.\-][\dIVXLC]+)*)')

#: Канонические (латинские) токены для сопоставления путей.
_RU_TOKEN = {
    'раздел': 'section',
    'глава': 'chapter',
    'статья': 'article',
    'часть': 'part',
    'приложение': 'appendix',
    'преамбула': 'preamble',
}

#: Типы, у которых может быть номер.
_NUMBERED_TYPES = ('статья', 'глава', 'раздел', 'приложение', 'часть')


@dataclass
class Element:
    """Структурный элемент: путь + блоки + заголовок."""

    path: List[Tuple[str, str]]  # [(тип_ru, номер), ...]
    blocks: List[Block] = field(default_factory=list)
    title: str = ''
    order: int = 0

    @property
    def path_text(self) -> str:
        return path_text(self.path)

    @property
    def key(self) -> tuple:
        return path_key(self.path)

    @property
    def text(self) -> str:
        return '\n'.join(b.text for b in self.blocks)


def _norm_number(number: str) -> str:
    return number.strip().lower()


def path_key(path: List[Tuple[str, str]]) -> tuple:
    """Канонический ключ пути: tuple из (тип, номер)."""
    keys = []
    for token, number in path:
        token_norm = _RU_TOKEN.get(token.lower().strip(), token.lower().strip())
        keys.append((token_norm, _norm_number(number)))
    return tuple(keys)


def path_text(path: List[Tuple[str, str]]) -> str:
    """Человекочитаемый путь вида «статья 2 -> часть 1.4»."""
    parts = []
    for token, number in path:
        label = token
        if number:
            label = f'{token} {number}'
        parts.append(label)
    return ' -> '.join(parts)


def _match_structural(text: str) -> Optional[Tuple[str, str, str]]:
    """Проверить, начинается ли блок с структурного заголовка.

    Возвращает ``(тип_ru, номер, остаток_заголовка)`` или ``None``.
    """
    m = _STRUCT_WORD_RE.match(text)
    if not m:
        return None
    token = m.group(1).lower()
    rest = text[m.end():]
    number = ''
    if token in _NUMBERED_TYPES:
        nm = _STRUCT_NUM_RE.match(rest.strip())
        if nm:
            number = nm.group(1).strip('.').strip()
            rest = rest[nm.end():].strip()
    return token, number, rest.strip()


def build_elements(blocks: List[Block]) -> List[Element]:
    """Собрать список :class:`Element` из блоков документа.

    Блоки до первого структурного заголовка образуют элемент «преамбула».
    """
    elements: List[Element] = []
    current: Optional[Element] = None
    order = 0

    def _new(path: List[Tuple[str, str]], title: str = '') -> None:
        nonlocal current, order
        current = Element(path=path, title=title, order=order)
        order += 1
        elements.append(current)

    for blk in blocks:
        parsed = _match_structural(blk.text)
        if parsed is not None:
            token, number, rest = parsed
            # Преамбула не может поглощать структурные заголовки: первая
            # «Статья/Глава/…» всегда начинает новый элемент.
            in_preamble = (
                current is not None and current.path == [('преамбула', '')]
            )
            if current is None or in_preamble:
                _new([(token, number)], title=rest or '')
                continue
            depth = [t for t, _ in current.path]
            if token not in depth:
                current.path.append((token, number))
                if rest:
                    current.title = rest
            else:
                idx = depth.index(token)
                _new(current.path[:idx] + [(token, number)], title=rest or '')
            continue

        if current is None:
            _new([('преамбула', '')])
        current.blocks.append(blk)

    return elements