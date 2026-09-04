"""Пост-анализ внесения изменений: автоматический ИИ-контроль результата прогона.

Модуль запускается автоматически в конце пайплайна внесения изменений
(см. ``process()`` в ``npazs.pipeline.orchestrator``). Логика работы:

1. Собирает все изменения, внесённые изменяющим НПА в целевой JSON —
   по ``modified_by_id`` (правки текста/заголовков/номеров), ``not_valid``
   (утрата силы), ``source_item_id`` (примечания), ``revision_info``
   (информация об изменяющем документе).
2. Формирует промпт из ``data/prompts/prompt_post_analysis.md``: описание
   структуры JSON (``docs/json_schema.md``), полный текст инструкций
   изменяющего закона и список «до/после» по каждому изменению.
3. Отправляет промпт ИИ-агенту (тот же бэкенд/модель, что и основной прогон).
4. Вердикт агента:
   - ``correct``   — пишется отчёт-подтверждение ``<результат>_post_analysis.md``;
   - ``incorrect`` — применяются точечные исправления и создаётся
     ``<результат>_corrected.json`` + отчёт ``.md`` в той же папке.

Журнал работы дублируется в ``data/logs/post_analysis.log``.
Отключается переменной окружения ``NPAZS_POST_ANALYSIS=0``.
"""

import copy
import json
import os
import re
from datetime import datetime

from npazs.constants import (
    LOGS_DIR,
    PROJECT_ROOT,
    TYPE_TO_RUSSIAN,
    load_prompt_from_file,
)
from npazs.revision.ai_utils import _repair_json_answer, ask_ollama
from npazs.revision.html_utils import extract_text_from_element, split_html_to_paragraphs
from npazs.revision.text_utils import get_active_revision, safe_re_sub
from npazs.revision.tree_utils import find_item_by_id

PROMPT_POST_ANALYSIS_FILE = 'prompt_post_analysis.md'
POST_ANALYSIS_ENV_FLAG = 'NPAZS_POST_ANALYSIS'
LOG_BASENAME = 'post_analysis.log'

MAX_SCHEMA_CHARS = 60000
MAX_INSTRUCTIONS_CHARS = 150000
MAX_FIELD_CHARS = 8000
MAX_HIGHLIGHT_TEXT_CHARS = 300

_SHORT_SCHEMA = (
    'NPA JSON: корень — паспорт НПА (npa_id, npa_number, история наименований в '
    'head_revision, npa_notes, revision_info, not_valid/not_valid_npa). Дерево '
    'элементов — npa_items_revision; каждый элемент: item_id, item_type, '
    'item_number, item_children, head_revisions (head_text/valid_to/'
    'modified_by_id), number_revisions, item_notes, item_prefix_revisions и '
    'revisions — список редакций: valid_from/valid_to, modified_by_id, '
    'not_valid, body (блоки paragraph/table/child_ref с html_text и order), '
    'highlights (previous_edition/current_edition: deletion/addition/'
    'difference: text, positions "M-N"). Активная редакция — последняя с '
    'пустым valid_to.'
)

_FALLBACK_TEMPLATE = (
    '# SYSTEM DIRECTIVE\n'
    'You verify that the changes described in the amending law were applied '
    'correctly to the target law JSON. Compare each <changes> entry (before/after) '
    'against <instructions>. Output ONLY a JSON object: '
    '{"status": "correct", "summary": "..."} or {"status": "incorrect", '
    '"summary": "...", "issues": [{"index": 0, "path": "...", "issue": "...", '
    '"expected": "...", "actual": "...", "fix": "...", "corrections": '
    '[{"item_id": "...", "field": "element_html|element_head|item_number|'
    'note_add|npa_head|not_valid", "value": "..."}]}]}. '
    'corrections.value must contain the COMPLETE corrected text (whole element). '
    'Only report real semantic errors; ignore cosmetic HTML markup differences.'
)


def post_analysis_enabled():
    """Пост-анализ включён по умолчанию; отключается ``NPAZS_POST_ANALYSIS=0``."""
    return os.environ.get(POST_ANALYSIS_ENV_FLAG, '1') != '0'


def _log_to_file(lines):
    """Дописать журнал прогона в ``data/logs/post_analysis.log`` (ошибки глушатся)."""
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        with open(os.path.join(LOGS_DIR, LOG_BASENAME), 'a', encoding='utf-8') as f:
            f.write('\n'.join(str(x) for x in lines) + '\n')
    except Exception:  # noqa: BLE001, S110 — журнал не должен ломать основной прогон
        pass


def _cap(text, limit=MAX_FIELD_CHARS):
    text = text or ''
    if len(text) <= limit:
        return text
    return text[:limit] + ' …[обрезано]'


def _strip_html(html):
    if not html:
        return ''
    text = safe_re_sub(r'<[^>]+>', ' ', str(html))
    text = text.replace('&nbsp;', ' ')
    return ' '.join(text.split())


def _norm_for_match(text):
    """Нормализация текста для проверки «фраза ещё присутствует в элементе»."""
    text = _strip_html(text).lower().replace('ё', 'е')
    return safe_re_sub(r'[^\w]+', '', text)


def _ids_match(modified_by_id, change_npa_id):
    """Совпадает ли ссылка на изменяющий НПА (id или список id через запятую).

    ``modified_by_id`` хранит item_id элементов изменяющего закона вида
    ``516_law_1_art_3`` или просто ``516``; сравнение по префиксу с разделителем
    исключает ложные совпадения (516 vs 5162).
    """
    if not modified_by_id:
        return False
    prefix = str(change_npa_id)
    for part in str(modified_by_id).split(','):
        part = part.strip()
        if part == prefix or part.startswith(prefix + '_'):
            return True
    return False


def _revision_body_html(rev):
    """Собственный HTML ревизии: блоки paragraph/table в порядке order."""
    if not rev:
        return ''
    blocks = sorted(rev.get('body', []) or [], key=lambda b: b.get('order', 0))
    parts = []
    for block in blocks:
        if block.get('type') in ('paragraph', 'table', 'table_header', 'table_fragment'):
            html = block.get('html_text', '')
            if html:
                parts.append(html)
    return '\n'.join(parts)


def _type_ru(item_type):
    return TYPE_TO_RUSSIAN.get(item_type, item_type or '')


def _build_path(chain):
    """Читаемое расположение элемента: «Раздел II > Статья 12 > Часть 2»."""
    parts = []
    for item in chain:
        label = _type_ru(item.get('item_type'))
        number = str(item.get('item_number') or '').strip()
        parts.append(f"{label} {number}".strip() if number else label)
    return ' > '.join(p for p in parts if p) or '—'


def _highlights_summary(highlights):
    """Компактная текстовая сводка объекта highlights для промпта."""
    if not isinstance(highlights, dict):
        return ''
    parts = []
    for side in ('previous_edition', 'current_edition'):
        side_data = highlights.get(side)
        if not isinstance(side_data, dict):
            continue
        for key in ('deletion', 'addition', 'difference'):
            for item in side_data.get(key) or []:
                if not isinstance(item, dict):
                    continue
                text = _cap(str(item.get('text', '')), MAX_HIGHLIGHT_TEXT_CHARS)
                pos = str(item.get('positions', ''))
                parts.append(f"{side}.{key}: '{text}' @ {pos}")
    return ' | '.join(parts)


def _highlights_empty(highlights):
    if not isinstance(highlights, dict):
        return True
    for side in ('previous_edition', 'current_edition'):
        side_data = highlights.get(side)
        if not isinstance(side_data, dict):
            continue
        for key in ('deletion', 'addition', 'difference'):
            if side_data.get(key):
                return False
    return True


def _change_entry(kind, item_id, path, before, after, highlights_summary='', item_number=''):
    return {
        'kind': kind,
        'item_id': item_id,
        'path': path,
        'item_number': item_number or '',
        'before': before or '',
        'after': after or '',
        'highlights': highlights_summary or '',
    }


def _collect_element_changes(element, change_npa_id, chain, out):
    """Собрать изменения одного элемента, внесённые изменяющим НПА."""
    path = _build_path(chain + [element])
    item_id = element.get('item_id', '')
    item_number = str(element.get('item_number') or '')
    revisions = element.get('revisions', []) or []
    for idx, rev in enumerate(revisions):
        if rev.get('not_valid'):
            if _ids_match(rev.get('not_valid'), change_npa_id):
                out.append(_change_entry(
                    'repel_law', item_id, path,
                    _cap(_revision_body_html(rev)),
                    f"Элемент помечен утратившим силу (not_valid по изменяющему НПА {change_npa_id})",
                    _highlights_summary(rev.get('highlights')), item_number,
                ))
            continue
        if not _ids_match(rev.get('modified_by_id'), change_npa_id):
            continue
        if idx == 0:
            kind, before = 'add', ''
        else:
            kind, before = 'change', _revision_body_html(revisions[idx - 1])
        out.append(_change_entry(
            kind, item_id, path, _cap(before), _cap(_revision_body_html(rev)),
            _highlights_summary(rev.get('highlights')), item_number,
        ))
    head_revs = element.get('head_revisions', []) or []
    for idx, entry in enumerate(head_revs):
        if not _ids_match(entry.get('modified_by_id'), change_npa_id):
            continue
        before = head_revs[idx - 1].get('head_text', '') if idx else ''
        out.append(_change_entry(
            'head', item_id, path, _cap(before), _cap(entry.get('head_text', '')),
            _highlights_summary(entry.get('highlights')), item_number,
        ))
    number_revs = element.get('number_revisions', []) or []
    for idx, entry in enumerate(number_revs):
        if not _ids_match(entry.get('modified_by_id'), change_npa_id):
            continue
        before = number_revs[idx - 1].get('number_text', '') if idx else ''
        out.append(_change_entry(
            'number', item_id, path, _cap(before), _cap(entry.get('number_text', '')),
            '', item_number,
        ))
    for entry in element.get('item_prefix_revisions', []) or []:
        if _ids_match(entry.get('modified_by_id'), change_npa_id):
            out.append(_change_entry(
                'prefix', item_id, path, '',
                _cap(entry.get('prefix_text', '')),
                _highlights_summary(entry.get('highlights')), item_number,
            ))
    for entry in element.get('item_notes', []) or []:
        if _ids_match(entry.get('source_item_id'), change_npa_id):
            out.append(_change_entry(
                'note', item_id, path, '', _cap(entry.get('text', '')), '', item_number,
            ))


def _walk_items(items, change_npa_id, chain, out):
    for item in items or []:
        _collect_element_changes(item, change_npa_id, chain, out)
        _walk_items(item.get('item_children'), change_npa_id, chain + [item], out)


def collect_changes(result, change_data):
    """Все изменения в ``result``, внесённые изменяющим НПА ``change_data``.

    Идентификация: ``modified_by_id``/``source_item_id``/``not_valid`` хранят
    item_id элементов изменяющего закона с префиксом его ``npa_id`` (сравнение
    по префиксу). Для ``revision_info`` дополнительно сверяется номер закона.

    Возвращает список записей вида ``{kind, item_id, path, item_number,
    before, after, highlights}`` с ключом ``index``.
    """
    change_npa_id = change_data.get('npa_id')
    change_number = str(change_data.get('npa_number', '') or '')
    out = []
    _walk_items(result.get('npa_items_revision'), change_npa_id, [], out)

    head_revision = result.get('head_revision')
    if isinstance(head_revision, list):
        for idx, entry in enumerate(head_revision):
            if _ids_match(entry.get('modified_by_id'), change_npa_id):
                before = head_revision[idx - 1].get('npa_head', '') if idx else ''
                out.append(_change_entry(
                    'npa_head', '__npa__', 'Наименование НПА',
                    _cap(before), _cap(entry.get('npa_head', '')),
                    _highlights_summary(entry.get('highlights')),
                ))

    for entry in result.get('npa_notes', []) or []:
        if _ids_match(entry.get('source_item_id'), change_npa_id):
            out.append(_change_entry(
                'note', '__npa__', 'Примечания НПА (npa_notes)',
                '', _cap(entry.get('text', '')), '',
            ))

    if result.get('not_valid') and _ids_match(result.get('not_valid_npa'), change_npa_id):
        out.append(_change_entry(
            'repel_law', '__npa__', 'НПА целиком',
            '', f"НПА помечен утратившим силу с {result.get('not_valid')}", '',
        ))

    for entry in result.get('revision_info', []) or []:
        rid = str(entry.get('revision_id', ''))
        rnum = str(entry.get('revision_number', ''))
        if (str(change_npa_id) and rid == str(change_npa_id)) or \
                (change_number and rnum == change_number):
            out.append(_change_entry(
                'revision', '__npa__', 'revision_info',
                '', json.dumps(entry, ensure_ascii=False), '',
            ))
            break

    for i, entry in enumerate(out):
        entry['index'] = i
    return out


def extract_instructions_text(change_data):
    """Полный текст изменяющего закона (источник инструкций) из его JSON."""
    parts = []
    for item in change_data.get('npa_items_revision', []) or []:
        text = extract_text_from_element(item)
        if text:
            parts.append(text)
    return '\n\n'.join(parts)


def build_prompt(result, change_data, changes, extracted_instructions=None):
    """Собрать промпт пост-анализа: шаблон + схема JSON + инструкции + изменения."""
    template = load_prompt_from_file(PROMPT_POST_ANALYSIS_FILE) or _FALLBACK_TEMPLATE
    schema = ''
    schema_path = os.path.join(PROJECT_ROOT, 'docs', 'json_schema.md')
    try:
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema = f.read()
    except Exception:  # noqa: BLE001 — краткая схема как запасной вариант
        schema = _SHORT_SCHEMA
    instructions = extract_instructions_text(change_data)
    if extracted_instructions:
        extra = '\n'.join(f"- {_cap(str(t), 2000)}" for t in extracted_instructions if t)
        if extra:
            instructions = (
                (instructions + '\n\n' if instructions else '')
                + '=== КРАТКИЕ ИНСТРУКЦИИ, ИЗВЛЕЧЁННЫЕ НА ЭТАПЕ 3 ===\n' + extra
            )
    changes_json = json.dumps(changes, ensure_ascii=False, indent=1)
    prompt = (
        template
        + '\n\n<json_schema>\n' + _cap(schema, MAX_SCHEMA_CHARS) + '\n</json_schema>'
        + '\n\n<change_npa_number>' + str(change_data.get('npa_number', '')) + '</change_npa_number>'
        + '\n\n<target_npa_number>' + str(result.get('npa_number', '')) + '</target_npa_number>'
        + '\n\n<instructions>\n' + _cap(instructions, MAX_INSTRUCTIONS_CHARS) + '\n</instructions>'
        + '\n\n<changes>\n' + changes_json + '\n</changes>'
    )
    return prompt


def _find_rev_created_by(element, change_npa_id):
    """Ревизия элемента, созданная изменяющим НПА (для точечной правки)."""
    for rev in reversed(element.get('revisions', []) or []):
        if _ids_match(rev.get('modified_by_id'), change_npa_id) and not rev.get('not_valid'):
            return rev
    return None


def _build_body_preserving_structure(old_rev, new_html):
    """Собрать body из исправленного HTML: paragraph/table + перенос child_ref."""
    paragraphs = split_html_to_paragraphs(new_html or '')
    if not paragraphs and (new_html or '').strip():
        paragraphs = [new_html.strip()]
    new_body = []
    for para in paragraphs:
        btype = 'table' if re.search(r'<table[\s>]', para, re.IGNORECASE) else 'paragraph'
        new_body.append({'type': btype, 'html_text': para, 'order': len(new_body) + 1})
    if old_rev:
        for ref in old_rev.get('body', []) or []:
            if ref.get('type') == 'child_ref':
                new_ref = dict(ref)
                new_ref['order'] = len(new_body) + 1
                new_body.append(new_ref)
    for i, block in enumerate(new_body, 1):
        block['order'] = i
    return new_body


def _sanitize_highlights(highlights, old_html, new_html, log_callback=None):
    """Убрать подсветку, которая перестала соответствовать исправленному тексту.

    Тексты ``current_edition`` (addition/difference) обязаны присутствовать в
    исправленном HTML, ``previous_edition`` (deletion/difference) — в прежнем.
    Табличные записи (text == "table") не трогаются.
    """
    if not isinstance(highlights, dict):
        return None
    old_norm = _norm_for_match(old_html)
    new_norm = _norm_for_match(new_html)
    dropped = []
    cleaned = copy.deepcopy(highlights)
    for side, ref_norm in (('previous_edition', old_norm), ('current_edition', new_norm)):
        side_data = cleaned.get(side)
        if not isinstance(side_data, dict):
            continue
        for key in ('deletion', 'addition', 'difference'):
            items = side_data.get(key)
            if not isinstance(items, list):
                continue
            kept = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                text = str(item.get('text', ''))
                if text == 'table' or not text.strip():
                    kept.append(item)
                    continue
                norm = _norm_for_match(text)
                if norm and norm in ref_norm:
                    kept.append(item)
                else:
                    dropped.append(_cap(text, 80))
            side_data[key] = kept
    if dropped and log_callback:
        log_callback(
            "  Пост-анализ: удалена устаревшая подсветка изменений "
            f"(текст больше не соответствует): {dropped}", 'warning',
        )
    return cleaned


def _apply_correction(result, corr, change_npa_id, change_valid_from, log_callback=None):
    """Применить одну коррекцию из вердикта ИИ. Возвращает (успех, ошибка)."""
    field = str(corr.get('field', ''))
    value = corr.get('value', '')
    value = '' if value is None else str(value)
    item_id = str(corr.get('item_id', ''))

    if field == 'element_html':
        element = find_item_by_id(result, item_id)
        if not element:
            return False, f"элемент {item_id} не найден"
        rev = _find_rev_created_by(element, change_npa_id) or get_active_revision(element)
        if rev is None:
            return False, f"у элемента {item_id} нет ревизий"
        old_html = _revision_body_html(rev)
        new_body = _build_body_preserving_structure(rev, value)
        if not new_body:
            return False, 'пустой исправленный HTML'
        rev['body'] = new_body
        cleaned = _sanitize_highlights(rev.get('highlights'), old_html, value, log_callback)
        if cleaned is not None and not _highlights_empty(cleaned):
            rev['highlights'] = cleaned
        else:
            rev.pop('highlights', None)
        if element.get('item_children'):
            from npazs.revision.revision_builder import sync_parent_body_with_children
            sync_parent_body_with_children(element, log_callback)
        return True, ''

    if field == 'element_head':
        element = find_item_by_id(result, item_id)
        if not element:
            return False, f"элемент {item_id} не найден"
        entries = element.get('head_revisions', []) or []
        target = None
        for entry in reversed(entries):
            if _ids_match(entry.get('modified_by_id'), change_npa_id):
                target = entry
                break
        if target is None:
            for entry in reversed(entries):
                if entry.get('valid_to') in (None, ''):
                    target = entry
                    break
        if target is not None:
            target['head_text'] = value
        else:
            element['head_revisions'] = entries + [{
                'head_text': value, 'modified_by_id': str(change_npa_id), 'valid_to': '',
            }]
        return True, ''

    if field == 'item_number':
        element = find_item_by_id(result, item_id)
        if not element:
            return False, f"элемент {item_id} не найден"
        element['item_number'] = value
        number_revs = element.get('number_revisions', []) or []
        updated = False
        for entry in reversed(number_revs):
            if _ids_match(entry.get('modified_by_id'), change_npa_id):
                entry['number_text'] = value
                updated = True
                break
        if not updated and number_revs:
            number_revs[-1]['number_text'] = value
        return True, ''

    if field == 'note_add':
        note = {'text': value, 'valid_from': change_valid_from or '', 'valid_to': ''}
        if item_id == '__npa__':
            result.setdefault('npa_notes', []).append(note)
            return True, ''
        element = find_item_by_id(result, item_id)
        if not element:
            return False, f"элемент {item_id} не найден"
        element.setdefault('item_notes', []).append(note)
        return True, ''

    if field == 'npa_head':
        entries = result.get('head_revision')
        if not isinstance(entries, list):
            entries = []
        target = None
        for entry in reversed(entries):
            if _ids_match(entry.get('modified_by_id'), change_npa_id):
                target = entry
                break
        if target is None:
            for entry in reversed(entries):
                if entry.get('valid_to') in (None, ''):
                    target = entry
                    break
        if target is not None:
            target['npa_head'] = value
        else:
            entries.append({'npa_head': value, 'modified_by_id': str(change_npa_id), 'valid_to': ''})
            result['head_revision'] = entries
        return True, ''

    if field == 'not_valid':
        result['not_valid'] = value
        result['not_valid_npa'] = str(change_npa_id)
        return True, ''

    return False, f"неизвестное поле коррекции: {field}"


def apply_corrections(result, verdict, change_npa_id, change_valid_from, log_callback=None):
    """Применить все ``corrections`` из вердикта ИИ. Возвращает список статусов."""
    applied = []
    for issue in (verdict.get('issues') or []):
        for corr in (issue.get('corrections') or []):
            ok, err = _apply_correction(result, corr, change_npa_id, change_valid_from, log_callback)
            applied.append({
                'item_id': corr.get('item_id', ''),
                'field': corr.get('field', ''),
                'path': issue.get('path', ''),
                'ok': ok,
                'error': err,
            })
            if log_callback:
                if ok:
                    log_callback(
                        f"  Пост-анализ: исправление применено "
                        f"({corr.get('field')} → {corr.get('item_id')})", 'info',
                    )
                else:
                    log_callback(
                        f"  Пост-анализ: исправление НЕ применено "
                        f"({corr.get('field')} → {corr.get('item_id')}): {err}", 'warning',
                    )
    return applied


def _result_path(orig_file, result_data, change_data):
    """Путь к сохранённому файлу результата (схема имён из ``_save_result``)."""
    from npazs.revision.ui_utils import clean_number_for_filename, get_date_for_filename
    orig_doc_type = result_data.get('doc_type', result_data.get('npa_type', 'law'))
    change_doc_type = change_data.get('doc_type', change_data.get('npa_type', 'law'))
    filename = (
        f"{clean_number_for_filename(result_data.get('npa_number', ''))}_"
        f"{get_date_for_filename(result_data, orig_doc_type)}_izm_"
        f"{clean_number_for_filename(change_data.get('npa_number', ''))}_"
        f"{get_date_for_filename(change_data, change_doc_type)}.json"
    )
    return os.path.join(os.path.dirname(orig_file) or '.', filename)


def _write_report(report_path, meta, verdict=None, raw_answer='', changes=None,
                  applied=None, corrected_path=None, result_path=None, note=''):
    """Записать отчёт пост-анализа в формате Markdown."""
    changes = changes or []
    applied = applied or []
    status = verdict.get('status') if isinstance(verdict, dict) else None
    if status == 'correct':
        headline = '✅ ИЗМЕНЕНИЯ ВНЕСЕНЫ КОРРЕКТНО'
    elif status == 'incorrect':
        headline = '❌ ВЫЯВЛЕНЫ ОШИБКИ ВНЕСЕНИЯ'
    else:
        headline = '⚠️ ПОСТ-АНАЛИЗ НЕ ЗАВЕРШИЛСЯ ШТАТНО'

    lines = [
        f"# Пост-анализ внесения изменений — {headline}",
        '',
        f"- Дата проверки: {meta.get('started', '')}",
        f"- Целевой НПА: {meta.get('target_npa', '')}",
        f"- Изменяющий НПА: {meta.get('change_npa', '')}",
        f"- Проверено изменений: {len(changes)}",
    ]
    if result_path:
        lines.append(f"- Проверенный файл результата: `{result_path}`")
    if corrected_path:
        lines.append(f"- **Исправленный файл: `{corrected_path}`**")
    if note:
        lines += ['', f"> {note}"]
    if isinstance(verdict, dict) and verdict.get('summary'):
        lines += ['', '## Резюме ИИ-агента', '', str(verdict['summary'])]
    if changes:
        lines += [
            '', '## Проверенные изменения', '',
            '| # | Тип | Расположение | item_id |',
            '|---|-----|--------------|---------|',
        ]
        for c in changes:
            lines.append(
                f"| {c.get('index', '')} | {c.get('kind', '')} | "
                f"{c.get('path', '')} | `{c.get('item_id', '')}` |"
            )
    if applied:
        lines += ['', '## Применённые исправления', '']
        for a in applied:
            mark = '✅' if a.get('ok') else '❌'
            line = f"- {mark} `{a.get('field')}` → `{a.get('item_id')}`"
            if a.get('path'):
                line += f" ({a['path']})"
            if a.get('error'):
                line += f" — ошибка: {a['error']}"
            lines.append(line)
    issues = verdict.get('issues') if isinstance(verdict, dict) else None
    if issues:
        lines += ['', '## Выявленные проблемы', '']
        for i, issue in enumerate(issues, 1):
            lines.append(f"### Проблема {i}: {issue.get('path', '')}")
            lines.append('')
            if issue.get('issue'):
                lines.append(f"- **Суть:** {issue['issue']}")
            if issue.get('expected'):
                lines.append(f"- **Ожидалось:** {_cap(str(issue['expected']), 4000)}")
            if issue.get('actual'):
                lines.append(f"- **Фактически:** {_cap(str(issue['actual']), 4000)}")
            if issue.get('fix'):
                lines.append(f"- **Исправление:** {issue['fix']}")
            lines.append('')
    if raw_answer and status != 'correct':
        fenced = raw_answer.replace('```', '```\\n')
        lines += ['', '## Исходный ответ ИИ-агента', '', '```', _cap(fenced, 20000), '```']
    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
        return True
    except Exception:  # noqa: BLE001 — отчёт не должен ломать основной прогон
        return False


def _finish_run(orig_file, started, result_data, change_data, final, verdict,
                raw_answer, changes, applied, corrected_path, result_path, log_lines):
    """Записать отчёт и журнал, вернуть итоговый результат пост-анализа."""
    report_path = os.path.join(
        os.path.dirname(orig_file) or '.',
        os.path.splitext(os.path.basename(result_path or 'result.json'))[0] + '_post_analysis.md',
    )
    meta = {
        'started': started.strftime('%d.%m.%Y %H:%M:%S'),
        'target_npa': f"{result_data.get('npa_number', '')} (id {result_data.get('npa_id', '')})",
        'change_npa': f"{change_data.get('npa_number', '')} (id {change_data.get('npa_id', '')})",
    }
    _write_report(report_path, meta, verdict=verdict, raw_answer=raw_answer,
                  changes=changes, applied=applied, corrected_path=corrected_path,
                  result_path=result_path)
    final['report_path'] = report_path
    log_lines.append(f"REPORT: {report_path}")
    log_lines.append(f"RESULT: {json.dumps(final, ensure_ascii=False)}")
    _log_to_file(log_lines)
    return final


def run_post_analysis(orig_file, result_data, change_data, model=None, extra_options=None,
                      stop_event=None, log_callback=None, backend=None,
                      extracted_instructions=None):
    """Пост-анализ внесённых изменений (автоматический ИИ-контроль).

    Args:
        orig_file: путь к файлу целевого НПА (результат лежит рядом).
        result_data: результат прогона (изменённый целевой НПА, dict).
        change_data: JSON изменяющего НПА (источник инструкций).
        model: модель ИИ (по умолчанию — из настроек для выбранного бэкенда).
        extra_options: параметры генерации (temperature/top_p).
        stop_event: threading.Event для отмены.
        log_callback: функция ``log(message, level)``.
        backend: ``kilo_gateway`` | ``ollama`` (по умолчанию — из настроек).
        extracted_instructions: краткие инструкции изменений из трекера (этап 3).

    Returns:
        dict: ``{status, checked, issues, report_path, corrected_path}``,
        где ``status`` — ``correct`` | ``incorrect`` | ``skipped`` | ``error``.
    """
    started = datetime.now()  # noqa: DTZ005 — локальное время прогона, как в остальном коде
    log_lines = [f"=== POST ANALYSIS {started:%Y-%m-%d %H:%M:%S} ==="]

    def _log(msg, level='info'):
        if log_callback:
            try:
                log_callback(str(msg), level)
            except Exception:  # noqa: BLE001, S110 — сбой UI-лога не критичен
                pass
        log_lines.append(f"[{level}] {msg}")

    change_npa_id = change_data.get('npa_id')
    if not change_npa_id:
        _log('Пост-анализ пропущен: у изменяющего НПА нет npa_id', 'warning')
        return _finish_run(orig_file, started, result_data, change_data,
                           {'status': 'skipped', 'checked': 0, 'issues': 0,
                            'corrected_path': None},
                           None, '', [], None, None, '', log_lines)

    result_path = _result_path(orig_file, result_data, change_data)
    work = None
    if os.path.exists(result_path):
        try:
            with open(result_path, 'r', encoding='utf-8') as f:
                work = json.load(f)
            _log(f"Проверяется сохранённый результат: {result_path}", 'info')
        except Exception as exc:  # noqa: BLE001 — запасной путь, ошибка логируется
            _log(f"Не удалось прочитать {result_path}, используется результат из памяти: {exc}", 'warning')
            work = None
    if work is None:
        work = copy.deepcopy(result_data)

    changes = collect_changes(work, change_data)
    if not changes:
        _log('Пост-анализ пропущен: изменения изменяющего НПА в результате не найдены', 'warning')
        return _finish_run(orig_file, started, result_data, change_data,
                           {'status': 'skipped', 'checked': 0, 'issues': 0,
                            'corrected_path': None},
                           None, '', [], None, None, result_path, log_lines)

    _log(f"Пост-анализ: найдено изменений, внесённых изменяющим НПА: {len(changes)}", 'info')
    prompt = build_prompt(work, change_data, changes, extracted_instructions)

    from npazs.config.settings import get_settings
    settings = get_settings()
    backend = backend or getattr(settings, 'llm_backend', None) or 'kilo_gateway'
    if not model:
        model = (settings.kilo_gateway_default_model if backend == 'kilo_gateway'
                 else settings.default_ollama_model)
    if extra_options is None:
        extra_options = {'temperature': 0.0, 'top_p': 0.1}

    _log(f"Запрос к ИИ-агенту пост-анализа (бэкенд: {backend}, модель: {model})", 'info')

    try:
        answer = ask_ollama(prompt, model, _log, extra_options=extra_options,
                            stop_event=stop_event, backend=backend)
    except Exception as exc:  # noqa: BLE001 — сбой пост-анализа не должен ломать прогон
        _log(f"Ошибка запроса к ИИ-агенту пост-анализа: {exc}", 'error')
        return _finish_run(orig_file, started, result_data, change_data,
                           {'status': 'error', 'checked': len(changes), 'issues': 0,
                            'corrected_path': None},
                           None, '', changes, None, None, result_path, log_lines)

    verdict = None
    raw_answer = answer or ''
    if answer:
        repaired = _repair_json_answer(answer, _log)
        if repaired:
            try:
                verdict = json.loads(repaired)
            except Exception as exc:  # noqa: BLE001 — вердикт остаётся None → status=error
                _log(f"Вердикт пост-анализа не разобран: {exc}", 'error')
    if isinstance(verdict, dict) and verdict.get('status'):
        status = str(verdict['status'])
    else:
        status = 'error'
        _log('Пост-анализ: ИИ не вернул валидный вердикт (status отсутствует)', 'error')
    issues = (verdict.get('issues') or []) if isinstance(verdict, dict) else []

    corrected_path = None
    applied = []
    if status == 'incorrect':
        _log(f"Пост-анализ: выявлены проблемы ({len(issues)}). Применяются исправления…", 'warning')
        change_valid_from = (change_data.get('valid_from')
                             or change_data.get('date_signed') or '')
        applied = apply_corrections(work, verdict, change_npa_id, change_valid_from, _log)
        if any(a.get('ok') for a in applied):
            corrected_path = os.path.join(
                os.path.dirname(result_path) or '.',
                os.path.splitext(os.path.basename(result_path))[0] + '_corrected.json',
            )
            try:
                with open(corrected_path, 'w', encoding='utf-8') as f:
                    json.dump(work, f, ensure_ascii=False, indent=2)
                _log(f"Сохранён исправленный JSON: {corrected_path}", 'result')
            except Exception as exc:  # noqa: BLE001 — corrected_path сбрасывается в None
                _log(f"Не удалось сохранить исправленный JSON: {exc}", 'error')
                corrected_path = None
        else:
            _log('Исправления применить не удалось — файл _corrected не создан', 'warning')

    return _finish_run(orig_file, started, result_data, change_data,
                       {'status': status, 'checked': len(changes), 'issues': len(issues),
                        'corrected_path': corrected_path},
                       verdict if isinstance(verdict, dict) else None,
                       raw_answer, changes, applied, corrected_path, result_path, log_lines)