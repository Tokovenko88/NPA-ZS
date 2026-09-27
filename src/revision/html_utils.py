"""HTML-утилиты для извлечения и очистки HTML."""

import copy
import difflib
import json
import re

from bs4 import BeautifulSoup
from npazs.revision.ai_utils import TYPE_TO_RUSSIAN
from npazs.revision.text_utils import clean_number, safe_re_sub, strip_thinking_tags


def clean_and_unwrap_html(html_text, is_table_child=False):
    if not html_text:
        return ""
    html_text = safe_re_sub(r'^(?:\s*<p[^>]*>\s*(?:&nbsp;|\s|<br/>|<br>)*</p>\s*)+', '', html_text, flags=re.IGNORECASE)
    html_text = safe_re_sub(r'(?:\s*<p[^>]*>\s*(?:&nbsp;|\s|<br/>|<br>)*</p>\s*)+$', '', html_text, flags=re.IGNORECASE)
    if is_table_child:
        soup = BeautifulSoup(html_text, 'html.parser')
        table_tag = soup.find('table')
        if table_tag:
            rows = table_tag.find_all('tr')
            if rows:
                html_text = "\n".join(str(row) for row in rows)
            else:
                html_text = table_tag.decode_contents()
    return html_text.strip()

_STRUCTURAL_TAGS = ['p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'table', 'tr']


def _top_level_blocks(html):
    """Возвращает список верхнеуровневых блочных тегов из HTML-фрагмента."""
    soup = BeautifulSoup(html, 'html.parser')
    blocks = [c for c in soup.children if hasattr(c, 'name') and c.name in _STRUCTURAL_TAGS]
    if not blocks:
        body = soup.find('body')
        candidate = body if body is not None else soup
        blocks = [c for c in candidate.children if hasattr(c, 'name') and c.name in _STRUCTURAL_TAGS]
    if not blocks:
        blocks = soup.find_all(_STRUCTURAL_TAGS)
    return blocks


def _find_external_quote_bounds(blocks):
    """Находит индексы (start, end) внешней цитаты «...» среди блоков.

    Начало — первый блок, чей текст (после lstrip) начинается с «.
    Конец — последний блок, чей текст заканчивается на » (после удаления
    trailing-пунктуации).

    ВАЖНО: НЕ используется балансировка кавычек. Количество « и » в тексте
    может не совпадать (вложенные кавычки внутри внешней пары).

    Возвращает (start_idx, end_idx) или (-1, -1), если внешняя цитата
    не найдена (ни один блок не начинается с «).
    """
    start_idx = -1
    for i, block in enumerate(blocks):
        if block.get_text(strip=True).startswith('«'):
            start_idx = i
            break
    if start_idx == -1:
        return -1, -1

    end_idx = -1
    for i in range(len(blocks) - 1, start_idx - 1, -1):
        text = blocks[i].get_text(strip=True)
        tail = re.sub(r'[\s;,.!?…]+$', '', text.rstrip())
        if tail.endswith('»'):
            end_idx = i
            break
    if end_idx == -1:
        for i in range(len(blocks) - 1, start_idx - 1, -1):
            if '»' in blocks[i].get_text():
                end_idx = i
                break
        if end_idx == -1:
            end_idx = len(blocks) - 1
    return start_idx, end_idx


def _strip_first_quote_mark(block, quote_char):
    """Удаляет первое вхождение ``quote_char`` в первом текстовом узле блока."""
    for text_node in list(block.find_all(string=True)):
        node_text = str(text_node)
        idx = node_text.find(quote_char)
        if idx != -1:
            text_node.replace_with(node_text[:idx] + node_text[idx + 1:])
            return True
    return False


def _strip_last_quote_mark(block, quote_char):
    """Удаляет последнее вхождение ``quote_char`` в последнем текстовом узле блока,
    а также trailing-пунктуацию, стоящую сразу после неё."""
    nodes = list(block.find_all(string=True))
    for text_node in reversed(nodes):
        node_text = str(text_node)
        idx = node_text.rfind(quote_char)
        if idx != -1:
            after = node_text[idx + 1:]
            after = re.sub(r'^[\s;,.!?…]+', '', after)
            text_node.replace_with(node_text[:idx] + after)
            return True
    return False


def _extract_quoted_html(html, log_callback=None):
    """Извлекает блок HTML, окружённый внешними кавычками «...».

    Надёжный extractor внешнего блока:
      * начало определяется первым блоком, чей текст (после удаления пробелов)
        начинается с «;
      * конец — последним блоком, чей текст заканчивается на » (после удаления
        trailing-пунктуации);
      * НЕ используется балансировка кавычек — количество « и » может не совпадать;
      * удаляются ТОЛЬКО первая внешняя « и последняя внешняя »;
      * вложенные пары кавычек («Закон ...», «О ставках ...») не трогаются;
      * функция идемпотентна: повторный вызов на уже разобранном HTML
        возвращает его без изменений.
    """
    if not html or not html.strip():
        return None
    if '«' not in html or '»' not in html:
        if log_callback:
            log_callback("  Не найдены кавычки « » в HTML", 'warning')
        return None

    blocks = _top_level_blocks(html)
    if not blocks:
        if log_callback:
            log_callback("  _extract_quoted_html: блочные теги не найдены", 'warning')
        return None

    start_idx, end_idx = _find_external_quote_bounds(blocks)
    if start_idx == -1:
        if log_callback:
            log_callback(
                "  _extract_quoted_html: внешняя цитата не найдена "
                "(нет блока, начинающегося с «). HTML возвращён без изменений.",
                'info'
            )
        return html

    selected_blocks = blocks[start_idx:end_idx + 1]

    _strip_first_quote_mark(selected_blocks[0], '«')
    _strip_last_quote_mark(selected_blocks[-1], '»')

    result = '\n'.join(str(b) for b in selected_blocks if str(b).strip())
    result = safe_re_sub(r';{2,}', ';', result)
    if log_callback:
        log_callback(f"  _extract_quoted_html: извлечено {len(result)} симв. (из {len(html)})", 'source')
    return result


def unwrap_outer_legal_quotes(text):
    """Удаляет внешнюю пару юридических кавычек «...» из текста.

    Контракт:
      * удаляет только действительно внешнюю пару;
      * не удаляет внутренние кавычки;
      * не требует глобального баланса кавычек;
      * корректно работает, если внешняя закрывающая кавычка находится
        в конце другого HTML-блока;
      * не изменяет содержимое текста без необходимости;
      * если невозможно доказать, что кавычки являются enclosing quotes,
        функция не удаляет их молча.

    Правило определения внешней пары:
      1. Первый блок должен начинаться с « (после lstrip).
      2. Последний блок должен заканчиваться на » (после удаления trailing-пунктуации).
      3. Если оба условия выполнены — удаляем первую « и последнюю ».
    """
    if not text or not text.strip():
        return text

    blocks = _top_level_blocks(text)
    if not blocks:
        stripped = text.strip()
        first_open = stripped.find('«')
        last_close = stripped.rfind('»')

        if first_open == -1 or last_close == -1 or first_open >= last_close:
            return text

        after_close = stripped[last_close + 1:]
        trailing_match = re.match(r'^[\s;,.!?…]+$', after_close)

        if trailing_match:
            return stripped[:first_open] + stripped[first_open + 1:last_close]
        else:
            return stripped[:first_open] + stripped[first_open + 1:last_close] + after_close

    first_text = blocks[0].get_text(strip=True)
    if not first_text.startswith('«'):
        stripped = text.strip()
        first_open = stripped.find('«')
        last_close = stripped.rfind('»')

        if first_open == -1 or last_close == -1 or first_open >= last_close:
            return text

        after_close = stripped[last_close + 1:]
        trailing_match = re.match(r'^[\s;,.!?…]+$', after_close)

        if trailing_match:
            return stripped[:first_open] + stripped[first_open + 1:last_close]
        else:
            return stripped[:first_open] + stripped[first_open + 1:last_close] + after_close

    last_text = blocks[-1].get_text(strip=True)
    last_tail = re.sub(r'[\s;,.!?…]+$', '', last_text.rstrip())
    if not last_tail.endswith('»'):
        return text

    _strip_first_quote_mark(blocks[0], '«')
    _strip_last_quote_mark(blocks[-1], '»')

    result = '\n'.join(str(b) for b in blocks if str(b).strip())
    result = safe_re_sub(r';{2,}', ';', result)
    return result


def validate_quote_extraction(html, item_type, item_number, log_callback=None):
    """Диагностика целостности извлечённого HTML перед передачей парсеру.

    Выводит диагностический лог ``[QUOTE EXTRACT VALIDATION]`` и проверяет,
    что HTML содержит ожидаемые структурные маркеры.

    Проверяет баланс кавычек «...». После удаления внешней пары «...»
    количество « и » может не совпадать из-за вложенных кавычек, но
    если в последнем блоке есть незакрытая кавычка — это признак повреждения.

    Возвращает ``False``, если HTML пустой или повреждён.
    """
    if not html:
        if log_callback:
            log_callback("[QUOTE EXTRACT VALIDATION] empty html — cannot validate", 'error')
        return False

    text = safe_re_sub(r'<[^>]+>', ' ', html)
    text = safe_re_sub(r'&nbsp;', ' ', text)
    text = ' '.join(text.split())

    contains_1 = bool(re.search(r'(?<![.\d])1\s*[.\)]', text))
    contains_2 = bool(re.search(r'(?<![.\d])2\s*[.\)]', text))
    contains_subpoints = bool(re.search(r'\b[а-яё]\s*[.\)]', text, re.IGNORECASE))
    contains_3 = bool(re.search(r'(?<![.\d])3\s*[.\)]', text))

    open_quotes = text.count('«')
    close_quotes = text.count('»')
    quote_diff = abs(open_quotes - close_quotes)

    soup = BeautifulSoup(html, 'html.parser')
    blocks = [c for c in soup.children if hasattr(c, 'name') and c.name] or soup.find_all(_STRUCTURAL_TAGS)

    last_block_has_unclosed_quote = False
    if blocks:
        last_block_text = blocks[-1].get_text()
        last_open = last_block_text.count('«')
        last_close = last_block_text.count('»')
        if last_open > last_close:
            last_block_has_unclosed_quote = True

    quotes_balanced = not last_block_has_unclosed_quote

    if log_callback:
        log_callback("[QUOTE EXTRACT VALIDATION]", 'info')
        log_callback(f"  item_type={item_type}", 'info')
        log_callback(f"  item_number={item_number}", 'info')
        log_callback(f"  source_len={len(html)}", 'info')
        log_callback(f"  contains_1={contains_1}", 'info')
        log_callback(f"  contains_2={contains_2}", 'info')
        log_callback(f"  contains_subpoints={contains_subpoints}", 'info')
        log_callback(f"  contains_3={contains_3}", 'info')
        log_callback(f"  open_quotes=«{open_quotes}", 'info')
        log_callback(f"  close_quotes=»{close_quotes}", 'info')
        log_callback(f"  quote_diff={quote_diff}", 'info')
        log_callback(f"  last_block_has_unclosed_quote={last_block_has_unclosed_quote}", 'info')

        log_callback("[QUOTE EXTRACT VALIDATION] structural markers:", 'info')
        for b in blocks:
            m = _classify_structural_marker(str(b))
            if m:
                log_callback(f"  {m[1]}", 'info')

    if not quotes_balanced:
        if log_callback:
            log_callback(
                f"[QUOTE EXTRACT ERROR] extracted structural block {item_type} {item_number} "
                f"has unbalanced quotes («={open_quotes}, »={close_quotes}) — possible loss of closing quote",
                'error'
            )
        return False

    return True


def extract_paragraphs_by_indices(html: str, range_str: str, log_callback=None) -> str:
    if not html:
        return ''
    range_str = range_str.strip().lower() if range_str else ''
    if range_str and ('<p' in range_str or '<div' in range_str or '<table' in range_str):
        if log_callback:
            log_callback("  WARNING: range_str выглядит как HTML, используем 'all'", 'warning')
        range_str = 'all'
    soup = BeautifulSoup(html, 'html.parser')
    all_blocks = [c for c in soup.children if hasattr(c, 'name') and c.name]
    if not all_blocks:
        all_blocks = soup.find_all(['p', 'div', 'table', 'tr'])
    if not all_blocks:
        return html.strip()
    selected_blocks = []
    if range_str == 'all' or not range_str:
        first_q = html.find('«')
        last_q = html.rfind('»')
        if first_q != -1 and last_q != -1 and last_q > first_q:
            start_idx = -1
            # Начало цитаты-блока — первый блок, который НАЧИНАЕТСЯ с «.
            # (не любой блок, содержащий «: в вводном абзаце «...изложить в
            #  следующей редакции» может встречаться вложенная цитата с названием
            #  закона «О предоставлении...», которая НЕ является началом блока)
            for i, block in enumerate(all_blocks):
                if block.get_text(strip=True).lstrip().startswith('«'):
                    start_idx = i
                    break
            if start_idx == -1:
                # fallback: ни один блок не начинается с « — берём первый,
                # содержащий открывающую кавычку (возможно « внутри предложения)
                for i, block in enumerate(all_blocks):
                    if '«' in block.get_text():
                        start_idx = i
                        break
            end_idx = -1
            for i in range(len(all_blocks)-1, -1, -1):
                if '»' in all_blocks[i].get_text():
                    end_idx = i
                    break
            if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
                selected_blocks = all_blocks[start_idx:end_idx+1]
            else:
                selected_blocks = all_blocks
        else:
            selected_blocks = all_blocks
    else:
        indices = set()
        parts = range_str.split(',')
        for part in parts:
            part = part.strip()
            if '-' in part:
                try:
                    s, e = map(int, part.split('-'))
                    for i in range(s, e + 1):
                        indices.add(i)
                except (ValueError, TypeError):
                    pass
            elif part.isdigit():
                indices.add(int(part))
        for idx in sorted(indices):
            if 1 <= idx <= len(all_blocks):
                selected_blocks.append(all_blocks[idx - 1])
            else:
                if log_callback:
                    log_callback(f"  Абзац {idx} выходит за пределы элемента (всего {len(all_blocks)})", 'warning')
        if not selected_blocks:
            if log_callback:
                log_callback(f"  Абсолютные индексы не найдены для '{range_str}'. Попытка извлечь N-ю цитату...", 'warning')
            quotes = []
            current_quote = []
            in_quote = False
            for block in all_blocks:
                text = block.get_text(strip=True)
                starts_with_quote = text.lstrip().startswith('«')
                ends_with_quote = '»' in text
                if starts_with_quote:
                    if in_quote and current_quote:
                        quotes.append(current_quote)
                    current_quote = [block]
                    in_quote = True
                    if ends_with_quote:
                        quotes.append(current_quote)
                        current_quote = []
                        in_quote = False
                elif in_quote:
                    current_quote.append(block)
                    if ends_with_quote:
                        quotes.append(current_quote)
                        current_quote = []
                        in_quote = False
            if in_quote and current_quote:
                quotes.append(current_quote)
            if quotes:
                if '-' in range_str:
                    try:
                        s, e = map(int, range_str.split('-'))
                        for i in range(s, e + 1):
                            if 1 <= i <= len(quotes):
                                selected_blocks.extend(quotes[i-1])
                    except (ValueError, TypeError):
                        pass
                elif range_str.isdigit():
                    idx = int(range_str)
                    if 1 <= idx <= len(quotes):
                        selected_blocks = quotes[idx-1]
                    else:
                        if len(quotes) == 1:
                            quote_html = '\n'.join(str(b) for b in quotes[0])
                            clean_quote = safe_re_sub(r'^\s*«', '', quote_html)
                            parts = split_html_by_leading_number(clean_quote, [str(idx) + ')', str(idx) + '.'])
                            for key, val in parts.items():
                                if key.rstrip('.)') == str(idx):
                                    selected_blocks = [BeautifulSoup(val, 'html.parser')]
                                    break
                        if not selected_blocks:
                            selected_blocks = [b for q in quotes for b in q]
                else:
                    if len(quotes) == 1:
                        quote_html = '\n'.join(str(b) for b in quotes[0])
                        clean_quote = safe_re_sub(r'^\s*«', '', quote_html)
                        markers = [range_str, range_str + ')', range_str + '.']
                        parts = split_html_by_leading_number(clean_quote, markers)
                        for key, val in parts.items():
                            if key.rstrip('.)') == range_str.rstrip('.)'):
                                selected_blocks = [BeautifulSoup(val, 'html.parser')]
                                break
                    if not selected_blocks:
                        selected_blocks = [b for q in quotes for b in q]
    if not selected_blocks:
        if log_callback:
            log_callback("  Не найдены блоки для извлечения. Возвращаем HTML как есть.", 'warning')
        return '\n'.join(str(b) for b in all_blocks if str(b).strip())

    # ========== ИСПРАВЛЕННЫЙ БЛОК УДАЛЕНИЯ ВНЕШНИХ КАВЫЧЕК ==========
    if selected_blocks:
        # Удаляем внешние кавычки ТОЛЬКО в пределах выбранных блоков
        # 1. Найти первый блок среди выбранных, который начинается с «
        first_open_idx = None
        for i, block in enumerate(selected_blocks):
            text = block.get_text(strip=True)
            if text.lstrip().startswith('«'):
                first_open_idx = i
                break
        if first_open_idx is not None:
            first_block = selected_blocks[first_open_idx]
            # Ищем первый текстовый узел с «
            first_node = first_block.find(string=True)
            if first_node and '«' in str(first_node):
                original = str(first_node)
                pos = original.find('«')
                if pos != -1:
                    # Удаляем только эту кавычку, остальное оставляем
                    first_node.replace_with(original[:pos] + original[pos+1:])

        # 2. Найти последний блок среди выбранных, который содержит » и заканчивается на неё
        last_close_idx = None
        for i in range(len(selected_blocks)-1, -1, -1):
            block = selected_blocks[i]
            text = block.get_text(strip=True)
            # Проверяем, заканчивается ли текст на » (после удаления завершающей пунктуации)
            tail = re.sub(r'[\s;,.!?…]+$', '', text.rstrip())
            if tail.endswith('»'):
                last_close_idx = i
                break
        if last_close_idx is not None:
            last_block = selected_blocks[last_close_idx]
            # Находим последний текстовый узел, содержащий »
            last_nodes = list(last_block.find_all(string=True))
            last_quote_node = None
            last_quote_pos = -1
            for node in reversed(last_nodes):
                text = str(node)
                pos = text.rfind('»')
                if pos != -1:
                    last_quote_node = node
                    last_quote_pos = pos
                    break
            if last_quote_node is not None:
                original = str(last_quote_node)
                before_quote = original[:last_quote_pos]
                after_quote = original[last_quote_pos+1:]
                # Удаляем пунктуацию сразу после кавычки (пробелы, ; , . ! ? …)
                after_quote = re.sub(r'^[\s;,.!?…]+', '', after_quote)
                new_text = before_quote + after_quote
                last_quote_node.replace_with(new_text)
                # Если блок после этого стал пустым, удаляем его
                if not last_block.get_text(strip=True):
                    last_block.decompose()
    # ========== КОНЕЦ ИСПРАВЛЕННОГО БЛОКА ==========

    result_html = '\n'.join(str(b) for b in selected_blocks if b and str(b).strip())
    result_html = safe_re_sub(r';{2,}', ';', result_html)
    if log_callback:
        log_callback(f"  Извлечён HTML по индексу '{range_str}' (длина {len(result_html)})", 'source')
    return result_html.strip()

def extract_leading_number(html):
    """Извлекает ведущий номер первого абзаца HTML-фрагмента.

    Возвращает строку с номером (без скобки/точки) или None,
    если первый абзац не начинается с маркера (цифра или буква + скобка/точка).
    """
    if not html:
        return None
    soup = BeautifulSoup(html, 'html.parser')
    first_para = soup.find(['p', 'div'])
    if first_para is None:
        first_para = soup
    text = first_para.get_text(strip=True)
    text = safe_re_sub(r'^[«»"\'“”‘’\s]+', '', text)
    m = re.match(r'^(\d+(?:\.\d+)?|[а-яё])(?:[\.\)])\s*', text)
    if m:
        return m.group(1).rstrip('.)')
    return None


def _classify_structural_marker(text):
    """Классифицирует ведущий структурный маркер в тексте.

    Возвращает (level, number) или None.
    level: 0=article/chapter/section, 1=part, 2=point, 3=subpoint
    """
    if not text:
        return None
    clean = safe_re_sub(r'<[^>]+>', '', text)
    clean = safe_re_sub(r'&nbsp;', ' ', clean)
    clean = safe_re_sub(r'[\s\u00a0]+', ' ', clean)
    clean = safe_re_sub(r'^[«»"\'‘’“”\s]+', '', clean).strip()
    if not clean:
        return None

    # Article/chapter/section - level 0 (номер может быть дробным: 5.1, 5.2)
    m = re.match(r'^(Статья|Глава|Раздел)\s+(\d+(?:\.\d+)?)', clean, re.IGNORECASE)
    if m:
        return (0, m.group(2))

    # Subpoint - level 3
    m = re.match(r'^([а-яё])\)\s', clean, re.IGNORECASE)
    if m:
        return (3, m.group(1).lower())

    # Point - level 2
    m = re.match(r'^(\d+)\)\s', clean)
    if m:
        return (2, m.group(1))

    # Part - level 1 (dotted or plain number with dot/paren)
    m = re.match(r'^(\d+(?:\.\d+)?)[\.\)]?\s*', clean)
    if m:
        return (1, m.group(1))

    return None


def extract_structural_block(html, structural_type, structural_number, log_callback=None):
    """Извлекает полный структурный блок из HTML.

    Например, для части 1.4 извлекает все абзацы от '1.4.'
    до следующего элемента того же или более высокого уровня.
    """
    if not html or not structural_type or not structural_number:
        return ''

    type_level_map = {
        'article': 0, 'chapter': 0, 'section': 0, 'appendix': 0,
        'part': 1, 'point': 2, 'subpoint': 3, 'paragraph': 4,
    }
    target_level = type_level_map.get(structural_type, 4)
    target_number = str(structural_number).strip().rstrip('.)')

    soup = BeautifulSoup(html, 'html.parser')
    all_blocks = [c for c in soup.children if hasattr(c, 'name') and c.name]
    if not all_blocks:
        all_blocks = soup.find_all(['p', 'div', 'table', 'tr'])
    if not all_blocks:
        return ''

    start_idx = -1
    for i, block in enumerate(all_blocks):
        marker = _classify_structural_marker(str(block))
        if marker and marker[0] == target_level and marker[1] == target_number:
            start_idx = i
            break

    if start_idx == -1:
        if log_callback:
            log_callback(f"  [ADD EXTRACT DEBUG] structural marker '{target_number}' not found", 'warning')
        return ''

    if log_callback:
        log_callback(f"  [ADD EXTRACT DEBUG] structural marker '{target_number}' found at block {start_idx + 1}", 'info')

    end_idx = len(all_blocks)
    for i in range(start_idx + 1, len(all_blocks)):
        marker = _classify_structural_marker(str(all_blocks[i]))
        if marker and marker[0] < target_level:
            end_idx = i
            if log_callback:
                log_callback(f"  [ADD EXTRACT DEBUG] boundary at block {i + 1} (higher level {marker[0]}: {marker[1]})", 'info')
            break
        if marker and marker[0] == target_level:
            end_idx = i
            if log_callback:
                log_callback(f"  [ADD EXTRACT DEBUG] boundary at block {i + 1} (same level: {marker[1]})", 'info')
            break

    selected_blocks = all_blocks[start_idx:end_idx]
    result_html = '\n'.join(str(b) for b in selected_blocks if b and str(b).strip())
    result_html = safe_re_sub(r';{2,}', ';', result_html)

    if log_callback:
        log_callback(f"  [ADD EXTRACT DEBUG] extracted {len(selected_blocks)} blocks, length={len(result_html)}", 'info')

    return result_html.strip()


def extract_html_for_added_element(source_html, range_str, child_number, log_callback=None):
    """Извлекает HTML для добавляемого элемента с защитой от неверного description.

    Проблема: модель на этапе 3 может указать в description неверные абсолютные
    номера абзацев, из-за чего по индексам извлекается фрагмент, начинающийся
    НЕ с номера добавляемого элемента (например, для «пункт 7» попадает и «пункт 6»).
    Это приводит к ложному диалогу «неоднозначности» на этапе перестройки.

    Функция проверяет, что первый абзац извлечённого HTML начинается с номера
    добавляемого элемента (child_number), и если нет — ищет корректный фрагмент
    по ведущему маркеру в исходном HTML.
    """
    if not source_html:
        return ''
    extracted = extract_paragraphs_by_indices(source_html, range_str, log_callback)
    if not extracted:
        return ''
    expected_num = str(child_number).strip().rstrip('.)')
    if not expected_num:
        return extracted
    first_num = extract_leading_number(extracted)
    if first_num is not None and first_num == expected_num:
        return extracted
    # Ведущий маркер не совпадает с номером добавляемого элемента.
    # Пытаемся найти фрагмент, начинающийся с ожидаемого маркера.
    if log_callback:
        log_callback(
            f"  add: первый абзац извлечённого HTML начинается с '{first_num}', "
            f"ожидался '{expected_num}'. Ищем фрагмент по маркеру...", 'warning'
        )
    clean_source = safe_re_sub(r'[«»]', '', source_html)
    markers = [expected_num + ')', expected_num + '.', expected_num]
    parts = split_html_by_leading_number(clean_source, markers)
    found_fragment = None
    for key, val in parts.items():
        if key.rstrip('.)') == expected_num:
            found_fragment = val
            break
    if found_fragment:
        if log_callback:
            log_callback(f"  add: найден фрагмент по маркеру '{expected_num}' (длина {len(found_fragment)})", 'info')
        return clean_description_html(found_fragment)
    # Не удалось найти по маркеру — возвращаем извлечённое по description.
    if log_callback:
        log_callback(
            f"  add: не удалось найти фрагмент по маркеру '{expected_num}', "
            f"используем извлечённый по description", 'warning'
        )
    return extracted


def remove_leading_number_from_html(html, item_number):
    if not html or not item_number:
        return html
    item_number = str(item_number)
    base = re.escape(item_number.rstrip('.)'))
    pattern_tag = r'^\s*(<[^>]+>)\s*' + base + r'[\.\)]?\s*'
    result = safe_re_sub(pattern_tag, r'\1', html, count=1, flags=re.DOTALL)
    if result != html:
        return result
    pattern_plain = r'^\s*' + base + r'[\.\)]?\s*'
    return safe_re_sub(pattern_plain, '', html, count=1)

def clean_description_html(html: str) -> str:
    if not html or not html.strip():
        return html
    html = html.strip()
    soup = BeautifulSoup(html, "html.parser")
    firsttext = soup.find(string=True)
    if firsttext and firsttext.strip():
        firsttext.replace_with(safe_re_sub(r'^\s+', '', firsttext, count=1))
    result = str(soup).strip()
    return result

def split_html_to_paragraphs(html_text):
    html_text = html_text.strip()
    if not html_text:
        return []
    result = []
    cursor = 0
    for m in re.finditer(r'<p[^>]*>.*?</p>', html_text, re.DOTALL | re.IGNORECASE):
        gap = html_text[cursor:m.start()].strip()
        if gap:
            result.append(gap)
        result.append(m.group(0).strip())
        cursor = m.end()
    tail = html_text[cursor:].strip()
    if tail:
        result.append(tail)
    if not result:
        return [html_text] if html_text.strip() else []
    return [r for r in result if r.strip()]

def split_html_by_leading_number(html_str, numbers):
    if not html_str or not numbers:
        return {}
    paragraphs = re.findall(r'<p[^>]*>.*?</p>', html_str, re.DOTALL | re.IGNORECASE)
    if not paragraphs:
        blocks = re.split(r'\n\s*\n', html_str.strip())
        if blocks:
            paragraphs = [f'<p>{b.strip()}</p>' for b in blocks if b.strip()]
        else:
            paragraphs = [f'<p>{html_str.strip()}</p>'] if html_str.strip() else []
    if not paragraphs:
        return {}
    all_markers = []
    for idx, para in enumerate(paragraphs):
        text = safe_re_sub(r'<[^>]+>', '', para)
        text = safe_re_sub(r'&nbsp;', ' ', text)
        text = safe_re_sub(r'^[«»"\'‘’“”\s]+', '', text).strip()
        m = re.match(r'^(\d+(?:\.\d+)?[\.\)]|[а-яё][\.\)])\s', text)
        if m:
            marker_norm = re.sub(r'[\.\)]$', '', m.group(1))
            all_markers.append((marker_norm, idx))
    if not all_markers:
        return {numbers[0]: html_str}
    all_markers.sort(key=lambda x: x[1])
    result = {}
    requested = {n.rstrip('.)') for n in numbers}
    for i, (marker, idx) in enumerate(all_markers):
        start = idx
        end = all_markers[i + 1][1] if i + 1 < len(all_markers) else len(paragraphs)
        fragment = '\n'.join(paragraphs[start:end]).strip()
        if marker in requested:
            result[marker] = fragment
    return result

def build_search_pattern(original_data):
    doc_type = original_data.get('doc_type', original_data.get('npa_type', 'law'))
    npa_number = original_data.get('npa_number', '')
    clean_number = safe_re_sub(r'[^0-9]', '', npa_number)
    if doc_type == 'law':
        return rf'(?i)(закон[а-я]*)?\s*№\s*{clean_number}', clean_number
    date_str = original_data.get('date_passed', '') or original_data.get('date_reg', '')
    if not date_str:
        return rf'(?i)постановление[а-я]*\s+Законодательного\ Собрания\ города\ Севастополя\s+№\s*{clean_number}', clean_number
    try:
        day, month, year = date_str.split('.')
        months = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
                  'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
        month_name = months[int(month) - 1]
        date_pattern = rf'от\s+{int(day)}\s+{month_name}\s+{year}\s+года'
    except (ValueError, IndexError):
        date_pattern = ''
    if date_pattern:
        pattern = rf'(?i)(постановление[а-я]*)\s+Законодательного\ Собрания\ города\ Севастополя\s+{date_pattern}\s+№\s*{clean_number}'
    else:
        pattern = rf'(?i)(постановление[а-я]*)\s+Законодательного\ Собрания\ города\ Севастополя\s+№\s*{clean_number}'
    return pattern, clean_number

def get_clean_text_from_block(block):
    raw = block.get('html_text', block.get('text', ''))
    if not raw:
        return ''
    clean = safe_re_sub(r'<[^>]+>', '', raw)
    clean = ' '.join(clean.split())
    return clean

def strip_number_from_element_html(html: str, item_number: str, item_type: str) -> str:
    if not html or not item_number or item_type not in ('part', 'point', 'subpoint'):
        return html
    item_number = str(item_number)
    item_num_clean = item_number.strip().rstrip('.)')
    pattern = r'^\s*(<p[^>]*>)\s*' + re.escape(item_num_clean) + r'[\.\)]?\s*'
    cleaned = safe_re_sub(pattern, r'\1', html, count=1, flags=re.DOTALL)
    return cleaned

def strip_leading_number_from_html_if_needed(html, element_type, item_number):
    if element_type in ('part', 'point', 'subpoint') and html and item_number:
        item_number = str(item_number)
        return remove_leading_number_from_html(html, item_number)
    return html

def _correct_table_highlights(old_html, new_html, highlights, log_callback=None):
    if not highlights or not isinstance(highlights, dict):
        return highlights

    try:
        old_soup = BeautifulSoup(old_html, 'html.parser')
        new_soup = BeautifulSoup(new_html, 'html.parser')

        old_rows = old_soup.find_all('tr')
        new_rows = new_soup.find_all('tr')

        if not old_rows or not new_rows:
            return highlights

        # Сравниваем именно HTML-код строк, чтобы заметить даже изменение тегов
        old_strs = [str(r).strip() for r in old_rows]
        new_strs = [str(r).strip() for r in new_rows]

        # SequenceMatcher умно находит изменившиеся блоки, не путая их со сдвигом
        sm = difflib.SequenceMatcher(None, old_strs, new_strs)

        diff_prev = []
        diff_curr = []
        additions = []
        deletions = []

        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == 'equal':
                continue
            elif tag == 'replace':
                # Произошла замена строк (старые i1..i2 на новые j1..j2)
                old_range = list(range(i1, i2))
                new_range = list(range(j1, j2))
                # Сохраняем попарную сортировку
                for k in range(max(len(old_range), len(new_range))):
                    o_idx = old_range[k] if k < len(old_range) else None
                    n_idx = new_range[k] if k < len(new_range) else None
                    if o_idx is not None and n_idx is not None:
                        diff_prev.append(["table", str(o_idx + 1)])
                        diff_curr.append(["table", str(n_idx + 1)])
                    elif o_idx is not None:
                        deletions.append(["table", str(o_idx + 1)])
                    elif n_idx is not None:
                        additions.append(["table", str(n_idx + 1)])
            elif tag == 'delete':
                # Строки были удалены
                for k in range(i1, i2):
                    deletions.append(["table", str(k + 1)])
            elif tag == 'insert':
                # Строки были добавлены
                for k in range(j1, j2):
                    additions.append(["table", str(k + 1)])

        # Если программа вообще не нашла изменений, оставляем ответ ИИ (он может быть прав)
        if not diff_prev and not diff_curr and not additions and not deletions:
            if log_callback:
                log_callback("  Корректировка: изменений в HTML строк не найдено, оставлен ответ ИИ.", 'info')
            return highlights

        if log_callback:
            log_callback(f"  Корректировка подсветки: замен={len(diff_prev)}, доб={len(additions)}, уд={len(deletions)}", 'info')

        return {
            "previous_edition": {
                "deletion": deletions,
                "addition": [],
                "difference": diff_prev
            },
            "current_edition": {
                "deletion": [],
                "addition": additions,
                "difference": diff_curr
            }
        }
    except Exception as e:
        # Если в программе произошла ошибка, безопасно возвращаем ответ ИИ
        if log_callback:
            log_callback(f"  Ошибка при программной корректировке подсветки: {e}. Оставлен ответ ИИ.", 'warning')
        return highlights

def _looks_like_json_response(text):
    if not isinstance(text, str):
        return False

    stripped = text.strip()
    if not stripped:
        return False

    lower = stripped.lower()

    if lower.startswith('json'):
        return True

    if stripped.startswith(('{', '[')):
        return True

    if '"html"' in stripped[:500] or "'html'" in stripped[:500]:
        return True

    return '"highlights"' in stripped[:1000]


def _is_valid_ai_html(html):
    if not isinstance(html, str):
        return False

    html = html.strip()

    if not html:
        return False

    if html.startswith(('{', '[')):
        return False

    if re.search(r'^\s*\{?\s*"html"\s*:', html, re.IGNORECASE):
        return False

    if re.search(r'^\s*\{?\s*["\']html["\']\s*:', html, re.IGNORECASE):
        return False

    return re.search(r'<(?:p|div|table|tbody|thead|tr|td|th|br|ol|ul|li)\b', html, re.IGNORECASE)


def _extract_html_from_parsed_data(data, log_callback=None):
    if isinstance(data, dict):
        html = data.get('html', '')
        if not html:
            body = data.get('body', [])
            if body and isinstance(body, list) and len(body) > 0:
                first = body[0]
                if isinstance(first, dict):
                    html = first.get('html_text', first.get('html', ''))
        return html
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return _extract_html_from_parsed_data(data[0], log_callback)
    if log_callback:
        log_callback(f"Ответ ИИ — не dict/list: {type(data).__name__}", 'warning')
    return ""


def normalize_ai_html_response(response, log_callback=None):
    if not response:
        return ""

    if isinstance(response, str):
        text = strip_thinking_tags(response)
        text = text.strip()
        if text.startswith('```json') and text.endswith('```'):
            text = text[7:-3].strip()
        elif text.startswith('```') and text.endswith('```'):
            text = text[3:-3].strip()

        try:
            data = json.loads(text)
            return _extract_html_from_parsed_data(data, log_callback)
        except json.JSONDecodeError:
            pass

        lower = text.lower()
        if lower.startswith('json'):
            rest = text[4:].strip()
            try:
                data = json.loads(rest)
                return _extract_html_from_parsed_data(data, log_callback)
            except json.JSONDecodeError:
                if log_callback:
                    log_callback(
                        "[AI HTML NORMALIZATION ERROR] Не удалось распарсить ответ ИИ как JSON.",
                        'error'
                    )
                return ""

        if log_callback:
            log_callback(
                "[AI HTML NORMALIZATION ERROR] Не удалось распарсить ответ ИИ как JSON.",
                'error'
            )
        return ""

    if isinstance(response, dict):
        return _extract_html_from_parsed_data(response, log_callback)

    if isinstance(response, list):
        return _extract_html_from_parsed_data(response, log_callback)

    if log_callback:
        log_callback(f"Ответ ИИ имеет неподдерживаемый тип: {type(response).__name__}", 'warning')
    return ""


def parse_ai_response_for_prompt4(response_text, change_description="", log_callback=None):
    from npazs.revision.ui_utils import _normalize_highlights_positions
    if not response_text:
        return "", None
    response_text = strip_thinking_tags(response_text)
    response_text = response_text.strip()
    highlights = None
    data = None

    if response_text.startswith('```json') and response_text.endswith('```'):
        json_text = response_text[7:-3].strip()
    elif response_text.startswith('```') and response_text.endswith('```'):
        json_text = response_text[3:-3].strip()
    else:
        json_text = response_text

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        lower = json_text.lower()
        if lower.startswith('json'):
            rest = json_text[4:].strip()
            try:
                data = json.loads(rest)
            except json.JSONDecodeError:
                if _looks_like_json_response(json_text):
                    if log_callback:
                        log_callback(
                            "[PROMPT4 VALIDATION ERROR] Ответ ИИ не является валидным JSON/HTML. "
                            "Изменение не будет применено.",
                            'error'
                        )
                    return "", None
                html = json_text
                if not _is_valid_ai_html(html):
                    if log_callback:
                        log_callback(
                            "[PROMPT4 VALIDATION ERROR] Ответ ИИ не содержит валидный HTML. "
                            "Изменение не будет применено.",
                            'error'
                        )
                    return "", None
                html = normalize_space_boundaries(html)
                html = safe_re_sub(r';{2,}', ';', html)
                highlights = _normalize_highlights_positions(highlights)
                return html, highlights
        elif _looks_like_json_response(json_text):
            if log_callback:
                log_callback(
                    "[PROMPT4 VALIDATION ERROR] Ответ ИИ не является валидным JSON/HTML. "
                    "Изменение не будет применено.",
                    'error'
                )
            return "", None
        else:
            html = json_text
            if not _is_valid_ai_html(html):
                if log_callback:
                    log_callback(
                        "[PROMPT4 VALIDATION ERROR] Ответ ИИ не содержит валидный HTML. "
                        "Изменение не будет применено.",
                        'error'
                    )
                return "", None
            html = normalize_space_boundaries(html)
            html = safe_re_sub(r';{2,}', ';', html)
            highlights = _normalize_highlights_positions(highlights)
            return html, highlights

    if data is not None:
        if isinstance(data, dict):
            highlights = data.get('highlights', None)
        html = normalize_ai_html_response(data, log_callback)
        if not _is_valid_ai_html(html):
            if log_callback:
                log_callback(
                    "[PROMPT4 VALIDATION ERROR] Ответ ИИ не содержит валидный HTML. "
                    "Изменение не будет применено.",
                    'error'
                )
            return "", None
        html = normalize_space_boundaries(html)
        html = safe_re_sub(r';{2,}', ';', html)
        highlights = _normalize_highlights_positions(highlights)
        return html, highlights

    return "", None

def add_number_to_paragraph_html(html_text, item_number, item_type):
    if not html_text or not item_number or item_type not in ('part', 'point', 'subpoint'):
        return html_text
    item_number = str(item_number)
    if item_type in ('part', 'point'):
        formatted_num = f"{item_number}."
    else:
        formatted_num = item_number.rstrip('.') + ')'
    soup = BeautifulSoup(html_text, 'html.parser')
    first_para = soup.find(['p', 'div'])
    if not first_para:
        return f"{formatted_num} {html_text}"
    para_text = first_para.get_text(strip=True)
    if re.match(r'^' + re.escape(formatted_num) + r'[\s\.\)]', para_text):
        return html_text
    original_content = first_para.decode_contents()
    first_para.clear()
    first_para.append(f"{formatted_num} {original_content}")
    return str(soup)

def parse_structural_tokens(structural):
    if not structural:
        return []
    structural = safe_re_sub(r'[\s\xa0\u2000-\u200F\u2028\u202F\u3000]+', ' ', structural)
    tokens = []
    structural_lower = structural.lower()
    parts = structural_lower.split()
    i = 0
    while i < len(parts):
        word = parts[i]
        found_type = None
        for eng, rus in TYPE_TO_RUSSIAN.items():
            if rus.lower() == word:
                found_type = eng
                break
        if not found_type:
            if 'стат' in word:
                found_type = 'article'
            elif 'част' in word:
                found_type = 'part'
            elif 'подпункт' in word:
                found_type = 'subpoint'
            elif 'пункт' in word:
                found_type = 'point'
            elif 'абзац' in word:
                found_type = 'paragraph'
            elif 'глав' in word:
                found_type = 'chapter'
            elif 'раздел' in word:
                found_type = 'section'
            elif 'приложен' in word:
                found_type = 'appendix'
            elif 'преамбул' in word:
                found_type = 'preamble'
            elif 'таблиц' in word:
                found_type = 'structured_table'
        if not found_type:
            i += 1
            continue
        num = None
        _ROMAN_RE = re.compile(r'^[IVXLCDM]+[⁰¹²³⁴⁵⁶⁷⁸⁹]*$', re.IGNORECASE)
        if i + 1 < len(parts):
            cand = parts[i+1]
            cand_clean = cand.rstrip('.,;:)')
            cand_clean = cand_clean.strip('«»\u201c\u201d\u2018\u2019"\'')
            cand_clean = cand_clean.rstrip('.,;:)')
            if (cand_clean.isdigit()
                    or ('.' in cand_clean and cand_clean.replace('.', '').isdigit())
                    or re.match(r'^[а-я]$', cand_clean)
                    or _ROMAN_RE.match(cand_clean)):
                if _ROMAN_RE.match(cand_clean):
                    roman_letters = re.sub(r'[⁰¹²³⁴⁵⁶⁷⁸⁹]', '', cand_clean).upper()
                    indices = re.sub(r'[^⁰¹²³⁴⁵⁶⁷⁸⁹]', '', cand_clean)
                    num = roman_letters + indices
                else:
                    num = cand_clean
                i += 1
        tokens.append((found_type, num))
        i += 1
    return tokens

def format_structural_number(number, is_header=False, has_title=False):
    if not number:
        return ""
    clean_num = str(number).strip()
    if is_header:
        if has_title:
            return f"{clean_num}." if not clean_num.endswith('.') else clean_num
        else:
            return clean_num.rstrip('.')
    else:
        if clean_num.endswith(')'):
            return clean_num
        return f"{clean_num}." if not clean_num.endswith('.') else clean_num

def get_item_html_recursive(item, all_items_map, include_header=True, include_children=True):
    item_type = item.get('item_type', '')
    number = item.get('item_number', '')
    item.get('item_id', '')
    html_out = ""
    if include_header and item_type in ('article', 'chapter', 'section', 'appendix'):
        type_rus = TYPE_TO_RUSSIAN.get(item_type, item_type).capitalize()
        head_text = ""
        if item.get('head_revisions'):
            for hr in reversed(item['head_revisions']):
                if hr.get('valid_to') is None:
                    head_text = hr.get('head_text', '').strip()
                    break
        if item_type == 'appendix':
            prefix_text = get_active_prefix_text(item)
            if prefix_text:
                html_out += f"{prefix_text}\n"
            else:
                formatted_num = format_structural_number(number, is_header=True, has_title=bool(head_text))
                header_content = f"{type_rus} {formatted_num}"
                if head_text:
                    header_content += f" {head_text}"
                html_out += f"<p><b>{header_content}</b></p>\n"
        else:
            formatted_num = format_structural_number(number, is_header=True, has_title=bool(head_text))
            header_content = f"{type_rus} {formatted_num}"
            if head_text:
                header_content += f" {head_text}"
            html_out += f"<p><b>{header_content}</b></p>\n"
    active_body = []
    if item.get('revisions'):
        for rev in reversed(item['revisions']):
            if rev.get('valid_to') is None:
                active_body = copy.deepcopy(rev.get('body', []))
                break
    if item_type in ('part', 'point', 'subpoint'):
        formatted_num = format_structural_number(number, is_header=False)
        found_paragraph = False
        for block in active_body:
            if block.get('type') == 'paragraph':
                orig_text = block.get('html_text', '')
                match = re.match(r'(<p[^>]*>)(.*)', orig_text, re.IGNORECASE | re.DOTALL)
                if match:
                    block['html_text'] = f"{match.group(1)}{formatted_num} {match.group(2)}"
                else:
                    block['html_text'] = f"{formatted_num} {orig_text}"
                found_paragraph = True
                break
        if not found_paragraph:
            active_body.insert(0, {'type': 'paragraph', 'html_text': f"{formatted_num} ", 'order': 1})
    for block in active_body:
        b_type = block.get('type')
        if b_type == 'paragraph' or b_type == 'table_fragment' or b_type == 'table_header':
            html_out += block.get('html_text', '') + "\n"
        elif b_type == 'child_ref':
            if not include_children:
                continue
            child_id = block.get('item_id')
            child_item = None
            if item.get('item_children'):
                child_item = next((c for c in item['item_children'] if c['item_id'] == child_id), None)
            if child_item:
                html_out += get_item_html_recursive(child_item, all_items_map)
    return html_out

def extract_html_from_element(element, include_number=True):
    return get_item_html_recursive(element, {})

def get_full_element_html(element, use_original_structure=False, include_number=True, include_header=True):
    if not element:
        return ""
    return get_item_html_recursive(element, {}, include_header=include_header)

def get_own_text_html(element, include_header=True):
    """HTML только собственного текста элемента — без разворота дочерних элементов.

    Блоки ``child_ref`` пропускаются: тексты дочерних пунктов/частей хранятся
    в отдельных элементах и попадают в тело родителя только как ``child_ref``.
    Для элемента без детей результат совпадает с ``get_full_element_html``.

    Используется при подготовке HTML для ИИ и pending-HTML, когда меняется
    собственный текст элемента, у которого есть дети. Полный разворот детей
    приводил к тому, что их тексты дублировались при перестройке родителя
    как неструктурированные абзацы (прогон 516-ЗС -> 127-ЗС, часть 5 статьи 6).
    """
    if not element:
        return ""
    return get_item_html_recursive(
        element, {}, include_header=include_header, include_children=False
    )

def extract_text_from_revision(rev):
    text = ''
    for block in rev.get('body', []):
        if block.get('type') == 'paragraph':
            html = block.get('html_text', '')
            clean = safe_re_sub(r'<[^>]+>', '', html)
            text += clean + ' '
    return text.strip()

def extract_text_from_element(element):
    from npazs.revision.text_utils import get_active_revision
    rev = get_active_revision(element)
    text = extract_text_from_revision(rev) if rev else ''
    for child in element.get('item_children', []):
        text += ' ' + extract_text_from_element(child)
    return text

def get_active_prefix_text(element):
    if element.get('item_type') != 'appendix':
        return None
    prefix_revs = element.get('item_prefix_revisions', [])
    for rev in reversed(prefix_revs):
        if rev.get('valid_to') is None:
            return rev.get('prefix_text', '')
    if prefix_revs:
        return prefix_revs[-1].get('prefix_text', '')
    return None

def get_current_head(element):
    head_revisions = element.get('head_revisions', [])
    for rev in reversed(head_revisions):
        if rev.get('valid_to') in (None, ''):
            return rev.get('head_text', '')
    if head_revisions:
        return head_revisions[-1].get('head_text', '')
    revisions = element.get('revisions', [])
    if not revisions:
        return ''
    for rev in reversed(revisions):
        if rev.get('valid_to') in (None, ''):
            return rev.get('item_head', '')
    return revisions[-1].get('item_head', '')

def create_element_skeleton(item_type, item_number, html_text, parent_id, existing_ids, id_counter, item_level,
                           valid_from=None, modified_by_id=None, mod_type=None, doc_id=None):
    clean_num = str(clean_number(str(item_number))).replace('.', '_')
    clean_parent_id = parent_id.rstrip('_') if parent_id else ''
    if clean_parent_id:
        base_id = f"{clean_parent_id}_{item_type}_{clean_num}"
    else:
        if doc_id:
            base_id = f"{doc_id}_{item_type}_{clean_num}"
        else:
            base_id = f"toc_{item_type}_{clean_num}"
    base_id = safe_re_sub(r'_+', '_', base_id).rstrip('_')
    candidate_id = base_id
    suffix = 2
    while candidate_id in existing_ids:
        candidate_id = f"{base_id}_{suffix}"
        suffix += 1
    existing_ids.add(candidate_id)
    id_counter[0] += 1
    element = {
        'item_id': candidate_id,
        'item_type': item_type,
        'item_number': str(item_number),
        'item_level': item_level,
        'item_children': []
    }
    if item_type in ('article', 'chapter', 'section', 'appendix'):
        element['head_revisions'] = []
    if item_type == 'appendix':
        element['item_prefix_revisions'] = []
    if valid_from is not None:
        body = []
        if html_text:
            if isinstance(html_text, list):
                for idx, t in enumerate(html_text, 1):
                    body.append({'type': 'paragraph', 'html_text': t, 'order': idx})
            else:
                body.append({'type': 'paragraph', 'html_text': html_text, 'order': 1})
        rev = {'body': body}
        if mod_type:
            rev['mod_type'] = mod_type
        if valid_from:
            rev['valid_from'] = valid_from
        if modified_by_id:
            rev['modified_by_id'] = modified_by_id
        element['revisions'] = [rev]
    else:
        body = []
        if html_text:
            if isinstance(html_text, list):
                for idx, t in enumerate(html_text, 1):
                    body.append({'type': 'paragraph', 'html_text': t, 'order': idx})
            else:
                body.append({'type': 'paragraph', 'html_text': html_text, 'order': 1})
        element['revisions'] = [{'body': body}]
    return element


# --------------------------------------------------------------------------- #
# Детерминированная замена слов «слова «X» заменить словами «Y»
# (fallback, если ИИ не применил замену — кейс 444-ЗС → 269-ЗС: замена
# «К отдельным категориям граждан» → «1. К отдельным категориям граждан»
# не попала в ответ ИИ, из-за чего абзац не стал частью 1).
# --------------------------------------------------------------------------- #

def parse_word_replacements(description):
    """Все пары «слово(а) «X» заменить слово(м/ами) «Y»» из инструкции.

    Работает по чистому тексту описания (HTML-теги удаляются). Поддерживаются
    и множественное число («слова … заменить словами …»), и единственное
    («слово «ребенка» заменить словом «детей»» — кейс 516-ЗС → 127-ЗС: такие
    инструкции раньше guard-ом не распознавались). Возвращает список пар
    ``(old_phrase, new_phrase)`` — в описании может быть несколько замен.
    """
    text = re.sub(r'<[^>]+>', ' ', str(description or ''))
    pairs = []
    for m in re.finditer(
            r'слов(?:о|а)\s*«\s*(.+?)\s*»\s*заменить\s*слов(?:ом|ами)\s*«\s*(.+?)\s*»',
            text):
        old_phrase = m.group(1).strip()
        new_phrase = m.group(2).strip()
        if old_phrase and new_phrase:
            pairs.append((old_phrase, new_phrase))
    return pairs


def parse_word_replacement(description):
    """Разобрать ПЕРВУЮ инструкцию «слова «X» заменить словами «Y»».

    Работает по чистому тексту описания (HTML-теги удаляются). Возвращает
    пару строк ``(old_phrase, new_phrase)`` или ``None``, если шаблон не найден.
    Обёртка над :func:`parse_word_replacements` (обратная совместимость).
    """
    pairs = parse_word_replacements(description)
    return pairs[0] if pairs else None


def norm_for_phrase_match(text):
    """Нормализовать фразу для поиска: нижний регистр, схлопнутые пробелы."""
    return re.sub(r'\s+', ' ', str(text or '')).strip().lower()


def _norm_char_map(html_text):
    """Отображение символов нормализованного текста на индексы исходного HTML.

    Возвращает ``(norm_string, raw_indices)``: символы вне HTML-тегов в нижнем
    регистре; последовательности пробелов схлопываются в один пробел, который
    отображается на индекс первого символа пробельного прогона.
    """
    chars = []
    raw = []
    in_tag = False
    prev_space = False
    for i, ch in enumerate(html_text):
        if ch == '<':
            in_tag = True
            continue
        if ch == '>':
            in_tag = False
            continue
        if in_tag:
            continue
        if ch.isspace():
            if not prev_space:
                chars.append(' ')
                raw.append(i)
                prev_space = True
            continue
        prev_space = False
        chars.append(ch.lower())
        raw.append(i)
    return ''.join(chars), raw


_PHRASE_WINDOW_DELTA = 3  # допуск длины окна при нечётком поиске фразы


def find_phrase_raw_range_fuzzy(html_text, phrase, min_ratio=0.8):
    """Найти диапазон ``(raw_start, raw_end)`` фразы в HTML-тексте.

    Сначала точный поиск по нормализованному тексту (регистр/пробелы не важны);
    если не нашлось — нечёткий поиск скользящим окном с допуском на опечатки
    OCR в описании правки (difflib, порог ``min_ratio``).

    Длина окна перебирается вокруг длины фразы (± ``_PHRASE_WINDOW_DELTA``):
    иначе фрагмент, отличающийся от фразы на несколько символов, обрезался бы
    (кейс 444-ЗС → 269-ЗС: описание «К отельным категориям граждан» на один
    символ короче реального «К отдельным категориям граждан» — конец диапазона
    попадал на предпоследний символ, и в тексте появлялось «гражданн»).
    Возвращает ``None``, если фраза не найдена.
    """
    norm_html, raw_idx = _norm_char_map(html_text)
    norm_phrase = norm_for_phrase_match(phrase)
    if not norm_html or not norm_phrase:
        return None
    plen = len(norm_phrase)
    idx = norm_html.find(norm_phrase)
    if idx >= 0:
        return raw_idx[idx], raw_idx[idx + plen - 1] + 1
    if plen < 6 or len(norm_html) < plen - _PHRASE_WINDOW_DELTA:
        return None
    best = None
    low = max(1, plen - _PHRASE_WINDOW_DELTA)
    for length in range(low, plen + _PHRASE_WINDOW_DELTA + 1):
        if length > len(norm_html):
            continue
        for start in range(len(norm_html) - length + 1):
            window = norm_html[start:start + length]
            matcher = difflib.SequenceMatcher(None, norm_phrase, window)
            if matcher.quick_ratio() < min_ratio:
                continue
            ratio = matcher.ratio()
            if ratio >= min_ratio and (best is None or ratio > best[0]):
                best = (ratio, start, length)
    if best is None:
        return None
    _, start, length = best
    return raw_idx[start], raw_idx[start + length - 1] + 1


def _phrase_index_map(phrase, found):
    """Вернуть ``(map_start, map_end)`` — перевод индексов ``phrase`` в ``found``.

    Совпавшие блоки ``difflib`` задают соответствие; на границе двух блоков
    начало относится к следующему блоку, а конец — к предыдущему (иначе при
    вставке символа в середину фразы он попадал бы и в «совпадающую» часть).
    Позиции вне блоков притягиваются к концу ближайшего предыдущего блока.
    """
    blocks = [(a, b, size) for a, b, size in
              difflib.SequenceMatcher(None, phrase, found).get_matching_blocks()
              if size]

    def _prev_end(idx):
        best = 0
        for a, b, size in blocks:
            if a + size <= idx:
                best = b + size
            else:
                break
        return best

    def map_start(idx):
        for a, b, _size in blocks:          # начало блока — высший приоритет
            if idx == a:
                return b
        for a, b, size in blocks:           # внутри блока — со сдвигом
            if a < idx < a + size:
                return b + (idx - a)
        for a, b, size in blocks:           # конец блока
            if idx == a + size:
                return b + size
        return _prev_end(idx)

    def map_end(idx):
        for a, b, size in blocks:           # конец блока — высший приоритет
            if idx == a + size:
                return b + size
        for a, b, size in blocks:
            if a < idx < a + size:
                return b + (idx - a)
        for a, b, _size in blocks:
            if idx == a:
                return b
        return _prev_end(idx)

    return map_start, map_end


def _splice_minimal_edit(found, old_phrase, new_phrase):
    """Собрать результат замены как минимальное редактирование фрагмента.

    Неизменённые части берутся из ``found`` (написание целевого документа —
    источник истины), новые/изменённые — из ``new_phrase``. Так опечатки в
    описании правки (ИИ переписывает инструкцию своими словами: «отельным»
    вместо «отдельным») не попадают в текст НПА.
    """
    map_start, map_end = _phrase_index_map(old_phrase, found)
    out = []
    matcher = difflib.SequenceMatcher(None, old_phrase, new_phrase)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            out.append(found[map_start(i1):map_end(i2)])
        elif tag in ('replace', 'insert'):
            out.append(new_phrase[j1:j2])
    return ''.join(out)



def refine_word_replacement(old_phrase, new_phrase, source_html):
    """Уточнить фразы замены по написанию исходного текста документа.

    ИИ на этапе разбора инструкций иногда переписывает её своими словами и
    допускает опечатки (кейс 444-ЗС → 269-ЗС: «К отельным категориям граждан»
    вместо «К отдельным категориям граждан»). Написание нормы — в документе,
    поэтому фразы приводим к нему: ``old_clean`` — реально найденный фрагмент,
    ``new_clean`` — ``new_phrase`` с неизменёнными частями из этого фрагмента.
    Если фраза в документе не найдена или совпадает — возвращаем исходные.
    """
    rng = find_phrase_raw_range_fuzzy(source_html or '', old_phrase)
    if rng is None:
        return old_phrase, new_phrase
    found = (source_html or '')[rng[0]:rng[1]]
    if not found or found == old_phrase:
        return old_phrase, new_phrase
    return found, _splice_minimal_edit(found, old_phrase, new_phrase)


def apply_word_replacement_fuzzy(html_text, old_phrase, new_phrase, min_ratio=0.8):
    """Заменить в HTML-тексте фразу ``old_phrase`` на ``new_phrase`` (чистый текст).

    Поиск нечувствителен к регистру/пробелам и допускает опечатки OCR. Замена
    выполняется минимальным редактированием: совпадающие части сохраняют
    написание целевого текста, подставляются только новые фрагменты.
    Возвращает исправленный HTML или ``None``, если фраза не найдена.
    """
    rng = find_phrase_raw_range_fuzzy(html_text, old_phrase, min_ratio)
    if rng is None:
        return None
    start, end = rng
    found = html_text[start:end]
    if not found:
        return None
    replacement = _splice_minimal_edit(found, old_phrase, new_phrase)
    # Границы замены нормализуются: если фраза начиналась/заканчивалась
    # пунктуацией с пробелом и вставляемый текст зеркала не даёт, пробел
    # восстанавливается (кейс 516-ЗС → 127-ЗС: «обращенияграждан»).
    return join_edit_span(html_text[:start], found, html_text[end:], replacement)


# --------------------------------------------------------------------------- #
# Детерминированное исключение фразы «слова «X» исключить»
#
# Fallback, если ИИ правку не применил. Кейс 516-ЗС → 127-ЗС (часть 3 статьи 6):
# в инструкции ссылка записана абсолютным URL (http://sevzakon.ru/view/laws/…),
# а в целевом документе — относительным (view/laws/…). Точного совпадения фразы
# нет, а prompt_4 (WHOLE PHRASE MATCHING / VERBATIM SUBSTITUTION) предписывает в
# этом случае оставить текст без изменений — ИИ так и сделал, правка потерялась.
# Поиск ниже идёт по нормализованному тексту (без тегов, регистра и пробелов),
# поэтому расхождение в href ему не мешает.
# --------------------------------------------------------------------------- #

def html_to_plain_text(html_text):
    """Текст HTML без тегов со схлопнутыми пробелами (для сравнения фраз)."""
    without_tags = re.sub(r'<[^>]+>', ' ', str(html_text or ''))
    return re.sub(r'\s+', ' ', without_tags).strip()


def parse_word_exclusion(description):
    """Разобрать инструкцию «слова «X» исключить» и вернуть фразу ``X``.

    Работает по чистому тексту описания (HTML-теги удаляются). Возвращает
    ``None``, если шаблон инструкции не найден.

    Учитываются вложенные кавычки: внешняя и внутренняя цитата могут
    разделять одну закрывающую „»“ (кейс 516-ЗС → 127-ЗС: «слова «, указанными
    … № 185-ЗС «О правовых актах города Севастополя» исключить»). В этом
    случае общая „»“ входит в фразу — иначе при вырезании в тексте остаётся
    «висячая» кавычка («…законодательной инициативы».”).
    """
    text = re.sub(r'<[^>]+>', ' ', str(description or ''))
    for match in re.finditer(r'слова\s*', text):
        start = text.find('«', match.end())
        if start == -1:
            continue
        depth = 0
        last_close = -1
        close = -1
        for i in range(start, len(text)):
            ch = text[i]
            if ch == '«':
                depth += 1
            elif ch == '»':
                depth -= 1
                last_close = i
                if depth == 0:
                    close = i
                    break
        if close == -1:
            # Несбалансированные кавычки: общая закрывающая „»“ входит в фразу
            if last_close <= start:
                continue
            phrase = text[start + 1:last_close + 1]
            tail = text[last_close + 1:]
        else:
            phrase = text[start + 1:close]
            tail = text[close + 1:]
        if not re.match(r'\s*исключить', tail):
            continue  # это не инструкция «исключить» (например, «заменить»)
        phrase = phrase.strip()
        if phrase:
            return phrase
    return None


def _extract_quoted_phrase_at(text, search_from):
    """Фраза в «...», начинающаяся не раньше ``search_from``.

    Возвращает ``(фраза, хвост)`` или ``None``. Учитываются вложенные цитаты:
    внешняя и внутренняя «...» могут разделять одну закрывающую „»“.
    """
    start = text.find('«', search_from)
    if start == -1:
        return None
    depth = 0
    last_close = -1
    close = -1
    for index in range(start, len(text)):
        char = text[index]
        if char == '«':
            depth += 1
        elif char == '»':
            depth -= 1
            last_close = index
            if depth == 0:
                close = index
                break
    if close == -1:
        if last_close <= start:
            return None
        return text[start + 1:last_close + 1], text[last_close + 1:]
    return text[start + 1:close], text[close + 1:]


def parse_word_addition(description):
    """Разобрать инструкцию «дополнить словами «X»» и вернуть фразу ``X``.

    Работает по чистому тексту описания (HTML-теги удаляются). Возвращает
    ``None``, если шаблон инструкции не найден или после фразы идёт что-то
    кроме терминальной пунктуации (тогда это составная инструкция и
    программный контроль к ней неприменим).
    """
    text = re.sub(r'<[^>]+>', ' ', str(description or ''))
    for match in re.finditer(r'дополнить\s+словами\s*', text, re.IGNORECASE):
        found = _extract_quoted_phrase_at(text, match.end())
        if found is None:
            continue
        phrase, tail = found
        if not re.match(r'^\s*[;,)\s]*$', tail or ''):
            continue
        phrase = phrase.strip()
        if phrase:
            return phrase
    return None


def parse_addition_anchor(description):
    """Опорная фраза инструкции «после слов «X» дополнить …» (или ``None``)."""
    text = re.sub(r'<[^>]+>', ' ', str(description or ''))
    match = re.search(r'после\s+слов\s*', text, re.IGNORECASE)
    if not match:
        return None
    found = _extract_quoted_phrase_at(text, match.end())
    if found is None:
        return None
    anchor = found[0].strip()
    return anchor or None


def refine_phrase_from_document(phrase, source_html):
    """Привести фразу инструкции к написанию целевого документа.

    Инструкция приходит от ИИ и может отличаться от документа оформлением
    ссылок (абсолютный URL вместо относительного) и опечатками, поэтому
    возвращаем реально найденный в документе фрагмент. Если фраза в документе
    не найдена — возвращаем её без изменений.
    """
    rng = find_phrase_raw_range_fuzzy(source_html or '', phrase)
    if rng is None:
        return phrase
    found = (source_html or '')[rng[0]:rng[1]]
    return found or phrase


def _prune_empty_inline_tags(html_text):
    """Убрать пустые inline-теги, оставшиеся от вырезанного фрагмента."""
    pattern = re.compile(
        r'<(a|em|strong|b|i|span|u|sub|sup)\b[^>]*>\s*</\1>', re.IGNORECASE)
    result = html_text
    while True:
        pruned = pattern.sub('', result)
        if pruned == result:
            return result
        result = pruned


def _collapse_html_text_spaces(html_text):
    """Схлопнуть двойные пробелы в текстовых узлах (вне HTML-тегов)."""
    out = []
    in_tag = False
    prev_space = False
    for char in html_text:
        if char == '<':
            in_tag = True
            prev_space = False
            out.append(char)
            continue
        if char == '>':
            in_tag = False
            out.append(char)
            continue
        if not in_tag and char in ' \t':
            if prev_space:
                continue
            prev_space = True
            out.append(char)
            continue
        if not in_tag:
            prev_space = False
        out.append(char)
    return ''.join(out)


def _ends_inside_tag(fragment):
    """True, если фрагмент обрывается внутри HTML-тега (между ``<`` и ``>``)."""
    text = str(fragment or '')
    last_open = text.rfind('<')
    if last_open < 0:
        return False
    return text.rfind('>') < last_open


# символ слова (буква/цифра) — для определения склейки «слово+слово»
_WORD_CHAR_RE = re.compile(r'[0-9A-Za-zА-Яа-яЁё]')
# «жёсткая» пунктуация: пробел перед ней в русском тексте недопустим
_HARD_PUNCT_BEFORE = ';,.:!?'
# хвостовые пробели/табуляции (перенос строки в HTML — обычный пробел)
_TAIL_SPACE_RE = re.compile(r'[ \t]+$')
_LEAD_SPACE_RE = re.compile(r'^[ \t]+')


def _join_two_fragments(head, tail, broken_word_boundary=False):
    """Соединить два куска HTML, выровняв пробелы на границе.

    ``broken_word_boundary`` — True, если вырезанный/заменённый фрагмент
    начинался (или заканчивался) с не-буквенного символа, то есть граница
    слова была разрушена и её нужно восстановить пробелом.

    Контрольные кейсы прогона 516-ЗС → 127-ЗС от 23.09.2026:

    * ``обращения`` + ``граждан`` → ``обращения граждан`` (замена
      «, касающиеся» → «граждан, …»: запятая и пробел целиком ушли
      в вырезаемую фразу, слова склеились);
    * ``Федерации `` + ``;`` → ``Федерации;`` (исключение закончилось ровно
      перед точкой с запятой, пробел остался слева).

    Стык внутри HTML-тега (например, внутри ``href="…"``) не трогается.
    """
    if not tail:
        return head
    if not head:
        return tail
    if _ends_inside_tag(head) or head[-1] == '<' or tail[0] == '>':
        return head + tail
    head_space = _TAIL_SPACE_RE.search(head)
    tail_space = _LEAD_SPACE_RE.search(tail)
    had_space = bool(head_space or tail_space)
    if head_space:
        head = head[:head_space.start()]
    if tail_space:
        tail = tail[tail_space.end():]
    if not tail:
        return head
    if not head:
        return tail
    first, last = tail[0], head[-1]
    if first in _HARD_PUNCT_BEFORE:
        # пробел перед «;,.:!?» не нужен ни при каких условиях
        return head + tail
    if broken_word_boundary and _WORD_CHAR_RE.match(last) and _WORD_CHAR_RE.match(first):
        return head + ' ' + tail
    if had_space:
        return head + ' ' + tail
    return head + tail


def join_edit_span(left, removed, right, replacement=''):
    """Собрать HTML после правки: ``left + replacement + right``.

    ``removed`` — вырезанный/заменённый фрагмент исходного HTML (по нему
    определяется, была ли граница слова разрушена), ``replacement`` — что
    вставляется вместо него (пустая строка при чистом исключении).
    Обе границы нормализуются через :func:`_join_two_fragments`.
    """
    left_boundary_broken = bool(removed) and not _WORD_CHAR_RE.match(removed[0])
    right_boundary_broken = bool(removed) and not _WORD_CHAR_RE.match(removed[-1])
    head = _join_two_fragments(left, replacement, left_boundary_broken)
    return _join_two_fragments(head, right, right_boundary_broken)


def normalize_space_boundaries(html_text):
    """Убрать пробелы перед «жёсткой» пунктуацией в текстовых узлах HTML.

    Ответ ИИ на промпт 4 часто содержит «Российской Федерации ;»: модель
    вырезает фразу и не схлопывает пробел перед точкой с запятой (кейс
    516-ЗС → 127-ЗС, ст.6 ч.5 п.2). Применяется только к элементам, которые
    реально редактируются, — нетронутые нормы через эту функцию не проходят.
    """
    text = str(html_text or '')
    if not text:
        return text
    parts = re.split(r'(<[^>]*>)', text)
    for index, part in enumerate(parts):
        if not part or part[0] == '<':
            continue
        part = re.sub(r'[ \t]+([' + _HARD_PUNCT_BEFORE + '])', r'\1', part)
        part = re.sub(r'  +', ' ', part)
        parts[index] = part
    return ''.join(parts)


def _quote_counters(text):
    """Считает ««» и „»“ вне HTML-тегов → ``(открыто, закрыто)``."""
    opens = closes = 0
    in_tag = False
    for char in str(text or ''):
        if char == '<':
            in_tag = True
            continue
        if char == '>':
            in_tag = False
            continue
        if in_tag:
            continue
        if char == '«':
            opens += 1
        elif char == '»':
            closes += 1
    return opens, closes


def _first_orphan_close_pos(text):
    """Индекс первой „»“ без парной „«“ (или -1), теги пропускаются."""
    depth = 0
    in_tag = False
    for index, char in enumerate(str(text or '')):
        if char == '<':
            in_tag = True
            continue
        if char == '>':
            in_tag = False
            continue
        if in_tag:
            continue
        if char == '«':
            depth += 1
        elif char == '»':
            if depth <= 0:
                return index
            depth -= 1
    return -1


def drop_orphan_close_quote(new_html, source_html):
    """Убрать „»“, появившуюся в результате вырезания фразы.

    Вырезание фразы с вложенной цитатой (внешняя и внутренняя «...» делят
    одну закрывающую „»“) оставляет в тексте одиночную «» без парной ««
    (кейс 516-ЗС → 127-ЗС, ст.6 ч.3: «…законодательной инициативы».”).
    Удаляется только та кавычка, дисбаланс которой появился ИМЕННО из-за
    этой правки, — чужие/исходные цитаты не трогаются.
    """
    fixed = str(new_html or '')
    source = str(source_html or '')
    if not fixed:
        return fixed
    fixed_open, fixed_close = _quote_counters(fixed)
    source_open, source_close = _quote_counters(source)
    if fixed_close - fixed_open <= source_close - source_open:
        return fixed
    index = _first_orphan_close_pos(fixed)
    if index < 0:
        return fixed
    return fixed[:index] + fixed[index + 1:]


def find_text_boundary_defects(old_html, new_html):
    """Список дефектов границ, появившихся именно в новом тексте.

    Страховочная сеть для трёх классов дефектов прогона 516-ЗС → 127-ЗС
    (23.09.2026), которые пост-анализ находил уже постфактум:

    * склейка двух слов (``обращенияграждан``);
    * пробел перед «жёсткой» пунктуацией (``Федерации ;``);
    * «висячая» „»“ после вырезания вложенной цитаты.

    Сравнение идёт с исходным HTML: дефект, который был в документе и до
    правки, новым не считается. Возвращает список человекочитаемых описаний.
    """
    defects = []
    old = str(old_html or '')
    new = str(new_html or '')
    if not new or new == old:
        return defects

    # 1) Пробел перед «жёсткой» пунктуацией в текстовых узлах.
    def _hard_punct_spaces(html):
        total = 0
        for part in re.split(r'(<[^>]*>)', html):
            if part[:1] == '<':
                continue
            total += len(re.findall(r'[ \t]+[' + _HARD_PUNCT_BEFORE + ']', part))
        return total

    extra_punct = _hard_punct_spaces(new) - _hard_punct_spaces(old)
    if extra_punct > 0:
        defects.append(
            f'лишний пробел перед «;,.:!?» (+{extra_punct}) — например '
            f'«Федерации ;»')

    # 2) «Висячая» „»“.
    old_open, old_close = _quote_counters(old)
    new_open, new_close = _quote_counters(new)
    if new_close - new_open > old_close - old_open:
        defects.append('несбалансированная закрывающая „»“ после правки')

    # 3) Склейка двух слов: токен, которого не было в исходнике, но который
    #    разбивается на два слова, знакомых документу (одно — из исходника,
    #    второе — из старого или нового текста: «граждан» могло быть добавлено
    #    самой инструкцией).
    old_token_list = re.findall(r'[0-9A-Za-zА-Яа-яЁё]+',
                                html_to_plain_text(old).lower())
    new_token_list = re.findall(r'[0-9A-Za-zА-Яа-яЁё]+',
                                html_to_plain_text(new).lower())
    old_tokens = set(old_token_list)
    known_tokens = old_tokens | set(new_token_list)
    for token in new_token_list:
        if len(token) < 6 or token in old_tokens:
            continue
        for cut in range(3, len(token) - 2):
            left, right = token[:cut], token[cut:]
            glued = ((left in old_tokens and right in known_tokens)
                     or (right in old_tokens and left in known_tokens))
            if glued:
                defects.append(f'возможная склейка слов «{left}»+«{right}» '
                               f'→ «{token}»')
                break
    return defects


def apply_word_exclusion_fuzzy(html_text, phrase, min_ratio=0.8):
    """Удалить фразу из HTML-текста (поиск по нормализованному тексту).

    Поиск нечувствителен к тегам, регистру и пробелам и допускает опечатки OCR
    в описании правки. Теги в самой ``phrase`` вычищаются перед поиском:
    ``find_phrase_raw_range_fuzzy`` сравнивает фразу с текстом без тегов, и
    фраза-описание, содержащая ссылку (кейс 516-ЗС → 127-ЗС: вокруг «№ 185-ЗС»
    стоит <a href>), иначе не находится никогда. Возвращаемая пара —
    ``(исправленный HTML, удалённый фрагмент исходного HTML)``: удалённый
    фрагмент сохраняет теги документа (нужны для highlights). ``None`` — если
    фраза не найдена или удаление не изменило текст.
    """
    source = str(html_text or '')
    if not source or not phrase:
        return None
    rng = find_phrase_raw_range_fuzzy(source, html_to_plain_text(phrase), min_ratio)
    if rng is None:
        return None
    start, end = rng
    if start >= end:
        return None
    removed = source[start:end]
    # Границы выреза нормализуются: пробел перед «;,.:!?» убирается, склеившиеся
    # слова разъединяются (кейсы 516-ЗС → 127-ЗС: «Федерации ;», «обращенияграждан»).
    joined = join_edit_span(source[:start], removed, source[end:])
    corrected = _collapse_html_text_spaces(_prune_empty_inline_tags(joined))
    # Пустая пара кавычек на границе выреза: документ обрамлял исключаемую
    # фразу в «...» — после удаления внутреннего текста остаётся «»
    # (в нормальном тексте пустых кавычек не бывает).
    corrected = safe_re_sub(r'«\s*»', '', corrected)
    # «Висячая» „»“: внешняя и внутренняя цитаты разделяли одну закрывающую.
    corrected = drop_orphan_close_quote(corrected, source)
    before = norm_for_phrase_match(html_to_plain_text(source))
    after = norm_for_phrase_match(html_to_plain_text(corrected))
    if not removed or after == before:
        return None
    return corrected, removed
