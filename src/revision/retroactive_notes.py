"""Применение ретроактивных правил (retroactive_note) после Stage 3.

Разделение обязанностей:
- Stage 2 находит ретро-клаузулы и возвращает их как «правила».
- Stage 3 извлекает конкретные изменения целевого НПА.
- Этот модуль применяет rules к фактическим изменениям.

Ключевые инварианты:
- ``amending_law`` + ``retroactive_note`` никогда не добавляет запись в
  ``npa_notes`` целевого НПА.
- ``npa_notes`` допустим ТОЛЬКО для ``target_law`` + ``structural_element == "law"``.
- ``note_valid_from`` берётся из правила (если задано), иначе из общей даты вступления.
- Итоговый note для amending-law формулируется относительно ИЗМЕНЕНИЯ
  и включает реквизиты изменяющего НПА, например: «Изменения Закона № X от Y
  распространяются...».
"""

import re

from npazs.revision.ui_utils import _find_existing_element_flexible


def normalize_note_text(text):
    """Нормализация текста note для сравнения на дубликаты."""
    if not text:
        return ""
    s = re.sub(r"\s+", " ", str(text))
    s = s.strip().strip(".,;:").strip()
    return s.lower()


def _note_already_exists(element, text, valid_from, source_item_id=None):
    """Есть ли уже такой note (по нормализованному тексту) у item элемента."""
    norm = normalize_note_text(text)
    if not norm:
        return True
    for note in element.get("item_notes", []):
        old_norm = normalize_note_text(note.get("text", ""))
        if old_norm and old_norm == norm:
            if not valid_from or not note.get("valid_from") or note.get("valid_from") == valid_from:
                old_source = note.get("source_item_id")
                if not source_item_id or not old_source or source_item_id == old_source:
                    return True
    return False


def _append_item_note(element, text, valid_from, log_callback=None, element_label="", source_item_id=None):
    """Добавляет note в item_notes с защитой от дубликатов. Возвращает True, если добавлено."""
    if not text or not text.strip():
        return False
    norm = normalize_note_text(text)
    if not norm:
        return False
    for note in element.get("item_notes", []):
        old_norm = normalize_note_text(note.get("text", ""))
        if old_norm and old_norm == norm:
            if not valid_from or not note.get("valid_from") or note.get("valid_from") == valid_from:
                old_source = note.get("source_item_id")
                if not source_item_id or not old_source or source_item_id == old_source:
                    if source_item_id and not old_source:
                        note["source_item_id"] = source_item_id
                        if log_callback:
                            log_callback(f"Обновлен source_item_id для примечания: {text[:50]}...", 'result')
                    return False
    if "item_notes" not in element:
        element["item_notes"] = []
    note = {
        "text": text,
        "valid_from": valid_from,
        "valid_to": "",
    }
    if source_item_id:
        note["source_item_id"] = source_item_id
    element["item_notes"].append(note)
    if log_callback:
        label = element_label or str(element.get("item_id", ""))
        log_callback(f"Добавлено примечание к элементу (item_notes): {text[:50]}...", 'result')
    return True


def _npa_note_already(original_data, text, valid_from, source_item_id=None):
    """Есть ли уже такой note в npa_notes целевого НПА."""
    norm = normalize_note_text(text)
    if not norm:
        return True
    for note in original_data.get("npa_notes", []):
        old_norm = normalize_note_text(note.get("text", ""))
        if old_norm and old_norm == norm:
            if not valid_from or not note.get("valid_from") or note.get("valid_from") == valid_from:
                old_source = note.get("source_item_id")
                if not source_item_id or not old_source or source_item_id == old_source:
                    return True
    return False


def _add_npa_note(original_data, text, valid_from, log_callback=None, source_item_id=None):
    """Добавляет note в npa_notes целевого НПА (ТОЛЬКО для целевого закона целиком)."""
    if not text or not text.strip():
        return False
    norm = normalize_note_text(text)
    if not norm:
        return False
    for note in original_data.get("npa_notes", []):
        old_norm = normalize_note_text(note.get("text", ""))
        if old_norm and old_norm == norm:
            if not valid_from or not note.get("valid_from") or note.get("valid_from") == valid_from:
                old_source = note.get("source_item_id")
                if not source_item_id or not old_source or source_item_id == old_source:
                    if source_item_id and not old_source:
                        note["source_item_id"] = source_item_id
                        if log_callback:
                            log_callback(f"Обновлен source_item_id для примечания к НПА: {text[:50]}...", 'result')
                    return False
    if "npa_notes" not in original_data:
        original_data["npa_notes"] = []
    note = {
        "text": text,
        "valid_from": valid_from,
        "valid_to": "",
    }
    if source_item_id:
        note["source_item_id"] = source_item_id
    original_data["npa_notes"].append(note)
    if log_callback:
        log_callback(f"Добавлено примечание к НПА (npa_notes): {text[:50]}...", 'result')
    return True
def normalize_amending_note_text(note_text, log_callback=None, amending_law_number=None, amending_law_date=None):
    """Нормализует note для amending-правила, чтобы он был относительно изменения
    и содержал реквизиты изменяющего НПА.

    «Действие настоящего Закона распространяется ...» -> «Изменения распространяются ...»
    «Действие настоящего Закона № X от Y распространяется ...» -> «Изменения Закона № X от Y распространяются ...»
    """
    if not note_text:
        return note_text
    s = note_text.strip()
    # «действие [любые слова] настоящего Закона [реквизиты] распространяется»
    pat = re.compile(
        r"действие\s+[^.]*?настоящего\s+закона\s+(.*?)\s*распространяется",
        flags=re.IGNORECASE,
    )
    if pat.search(s):
        def _repl(m):
            details = m.group(1).strip()
            if details:
                return f"Изменения Закона {details} распространяются"
            return "Изменения распространяются"
        new = _cap_start(pat.sub(_repl, s, count=1))
        if log_callback:
            log_callback(f"Нормализован текст ретро-примечания для amending: {new[:60]}...", 'info')
        return _ensure_amending_details(new, amending_law_number, amending_law_date, log_callback)
    # «изменения, вносимые настоящим Законом»
    pat3 = re.compile(r"изменения\s*,\s*вносимые\s+настоящим\s+законом", flags=re.IGNORECASE)
    if pat3.search(s):
        new = _cap_start(pat3.sub("Изменения", s, count=1))
        return _ensure_amending_details(new, amending_law_number, amending_law_date, log_callback)
    # Страховка: «действие настоящего Закона ... распространяется»
    pat2 = re.compile(r"действие\s+настоящего\s+закона\s+распространяется", flags=re.IGNORECASE)
    if pat2.search(s):
        new = _cap_start(pat2.sub("Изменения распространяются", s, count=1))
        return _ensure_amending_details(new, amending_law_number, amending_law_date, log_callback)
    # Уже нормализованный текст — проверяем, есть ли реквизиты
    return _ensure_amending_details(s, amending_law_number, amending_law_date, log_callback)


def _ensure_amending_details(text, number, date, log_callback=None):
    """Гарантирует, что в тексте есть реквизиты изменяющего НПА."""
    if not text:
        return text
    if not number and not date:
        return text
    # Проверяем, есть ли уже номер закона/постановления в тексте
    if re.search(r"(закона|постановления)\s+№\s*\S+", text, re.IGNORECASE):
        return text
    # Определяем тип НПА по умолчанию
    law_type = "Закона"
    details = ""
    if number:
        details += f"№ {number}"
    if date:
        if details:
            details += f" от {date}"
        else:
            details += f"от {date}"
    if not details:
        return text
    # Вставляем после "Изменения "
    new = re.sub(r"^(изменения\s+)(.+)$", f"\\1{law_type} {details} \\2", text, flags=re.IGNORECASE)
    if new != text:
        if log_callback:
            log_callback(f"Добавлены реквизиты изменяющего НПА: {new[:60]}...", 'info')
        return _cap_start(new)
    # Если не подошло — пробуем вставить после "Изменения"
    if text.lower().startswith("изменения "):
        new = f"Изменения {law_type} {details} {text[10:]}"
        if log_callback:
            log_callback(f"Добавлены реквизиты изменяющего НПА: {new[:60]}...", 'info')
        return new
    return text


def _cap_start(s):
    if not s:
        return s
    return s[0].upper() + s[1:]


def _norm_path(s):
    if not s:
        return ""
    s = str(s).lower().strip()
    s = s.replace(" -> ", "->")
    s = re.sub(r"\s+", "", s)
    return s.strip(" >-")


def _match_selected_change(rule_structural, change):
    """Сопоставляет элемент изменяющего НПА из правила с конкретным изменением Stage 3."""
    rnorm = _norm_path(rule_structural)
    if not rnorm:
        return False
    candidates = [
        change.get("revision_number"),
        change.get("_source_path"),
        change.get("source_structural_element"),
        change.get("revision_path"),
    ]
    for cand in candidates:
        if cand is None:
            continue
        cnorm = _norm_path(cand)
        if not cnorm:
            continue
        if cnorm == rnorm or rnorm in cnorm:
            return True
    return False


def _target_element_for_change(original_data, change, log_callback=None):
    structural = change.get("structural_element", "")
    if not structural or not structural.strip():
        return None
    try:
        return _find_existing_element_flexible(original_data, structural, log_callback)
    except ValueError:
        if log_callback:
            log_callback(f"⚠️ Неоднозначный путь '{structural}' при назначении примечания.", 'warning')
        return None


def _structural_path_tokens(structural):
    """Parse a structural path string into normalized (type, number) tokens.

    Handles different separators (->, /, ,, space), case, and Russian
    case forms (статья/статьи/статью → article, etc.).
    """
    from npazs.revision.html_utils import parse_structural_tokens
    return parse_structural_tokens(structural) if structural else []


# Порядок иерархии сверху вниз. Используется, чтобы приводить пути вида
# «часть 1.4 статьи 2» к каноническому «статья 2 -> часть 1.4».
_HIERARCHY_ORDER = {
    'preamble': 0,
    'chapter': 0, 'section': 0, 'appendix': 0, 'structured_table': 0,
    'article': 1,
    'part': 2,
    'point': 3,
    'subpoint': 4,
    'paragraph': 5,
}

_RU_TYPE_NAME = {
    'preamble': 'преамбула',
    'chapter': 'глава',
    'section': 'раздел',
    'appendix': 'приложение',
    'structured_table': 'таблица',
    'article': 'статья',
    'part': 'часть',
    'point': 'пункт',
    'subpoint': 'подпункт',
    'paragraph': 'абзац',
}

# Обратный словарь: русская (каноническая) форма → английский тип токена,
# чтобы сравнивать с результатом ``parse_structural_tokens``.
_RU_TO_ENG = {v: k for k, v in _RU_TYPE_NAME.items()}


def _canonical_structural_tokens(structural):
    """Токены пути, отсортированные по иерархии сверху вниз.

    Порядок слов в исходной строке не важен — «часть 1.4 статьи 2» и
    «статья 2 -> часть 1.4» дают одинаковый канонический набор.
    """
    tokens = _structural_path_tokens(structural)
    return sorted(tokens, key=lambda t: (_HIERARCHY_ORDER.get(t[0], 10), str(t[1] or '')))


def _canonical_structural_path(structural):
    """Каноническая строка пути сверху вниз, например «статья 2 -> часть 1.4»."""
    if not structural:
        return ""
    parts = []
    for etype, num in _canonical_structural_tokens(structural):
        ru = _RU_TYPE_NAME.get(etype, etype)
        parts.append(f"{ru} {num}".strip() if num is not None else ru)
    return " -> ".join(parts)


def _structural_path_key(tokens):
    """Create a hashable comparable key from structural path tokens.

    Ключ сортируется, поэтому сравнение не зависит от порядка следования
    токенов: «часть 1.4 статьи 2» эквивалентно «статья 2 -> часть 1.4».
    """
    return tuple(sorted(
        (t, str(n)) if n is not None else (t, '')
        for t, n in tokens
    ))


def _change_created_path_tokens(change):
    """Compute the full structural path tokens of an ``add`` change's created element.

    For ``add`` changes that carry a ``new`` field, the full path is
    ``parse_structural_tokens(structural_element) + [token_from_new]``.

    For ``add`` changes without a ``new`` field, the ``structural_element``
    itself IS the full path of the created element.
    """
    from npazs.revision.html_utils import parse_structural_tokens
    from npazs.revision.ui_utils import parse_add_new_field

    new_str = change.get('new', '')
    structural = change.get('structural_element', '')

    if new_str:
        parent_tokens = parse_structural_tokens(structural)
        ru_type, child_num = parse_add_new_field(new_str)
        if ru_type:
            # ``parse_add_new_field`` возвращает русскую форму («часть»),
            # а ``parse_structural_tokens`` — английскую («part»).
            # Приводим к английской, чтобы ключи сравнимы были.
            eng_type = _RU_TO_ENG.get(ru_type, ru_type)
            parent_tokens.append((eng_type, str(child_num) if child_num is not None else None))
        return parent_tokens
    return parse_structural_tokens(structural)


def resolve_rule_target(rule, target_data, changes=None, log_callback=None):
    """Resolve a rule's ``structural_element`` to an element in ``target_data``.

    Resolution order (never creates elements):

    Scenario A -- element already exists in the final tree:
        Search by structural path via ``_find_existing_element_flexible``.

    Scenario B -- element was created by a current ``add`` change:
        Compute each ``add`` change's full path and compare against the
        rule's path. If a match is found, resolve via ``_created_item_id``.

    Scenario C -- element created by a chain of changes:
        Same as B; the full path computation handles arbitrary depth.

    Returns the element dict if found, ``None`` otherwise.
    """
    structural = (rule.get("structural_element") or "").strip()
    if not structural or structural.lower() == "law":
        return None

    # Scenario A: element already exists in the final tree.
    # Пробуем оба варианта пути: как есть и в каноническом порядке сверху вниз
    # («статья 2 -> часть 1.4»), т.к. ИИ может вернуть «часть 1.4 статьи 2».
    candidates_paths = [structural]
    canonical = _canonical_structural_path(structural)
    if canonical and canonical != structural:
        candidates_paths.append(canonical)
    for candidate in candidates_paths:
        try:
            elem = _find_existing_element_flexible(target_data, candidate, log_callback)
            if elem:
                if log_callback:
                    log_callback(
                        f"🔗 Resolved retroactive_note target: "
                        f"'{structural}' -> {elem.get('item_id')} (existing)"
                        f"{'' if candidate == structural else f' via {candidate!r}'}", 'info')
                return elem
        except ValueError:
            if log_callback:
                log_callback(
                    f"⚠️ Неоднозначность при разрешении target: '{candidate}'", 'warning')

    # Scenario B/C: element created by an add change
    rule_tokens = _structural_path_tokens(structural)
    rule_key = _structural_path_key(rule_tokens)
    if not rule_key:
        return None

    if changes:
        for ch in changes:
            if ch.get("type") != "add":
                continue
            created_id = ch.get("_created_item_id")
            if not created_id:
                continue
            change_tokens = _change_created_path_tokens(ch)
            change_key = _structural_path_key(change_tokens)
            # Полное совпадение (порядок токенов не важен) или правило,
            # покрывающее нижнюю часть пути созданного элемента
            # (например, правило «часть 1.4» при изменении «статья 2 / new=часть 1.4»).
            matched = change_key == rule_key
            if not matched and len(rule_key) < len(change_key):
                # rule — суффикс change-пути: первые (менее глубокие) токены
                # правила должны совпадать с хвостом пути изменения.
                change_sorted = list(change_key)
                for split_idx in range(1, len(change_sorted) - len(rule_key) + 1):
                    if tuple(change_sorted[split_idx:split_idx + len(rule_key)]) == rule_key:
                        matched = True
                        break
            if not matched:
                continue
            from npazs.revision.tree_utils import find_item_by_id
            elem = find_item_by_id(target_data, created_id)
            if elem:
                if log_callback:
                    log_callback(
                        f"🔗 Resolved retroactive_note target: "
                        f"'{structural}' -> {elem.get('item_id')} "
                        f"(created by change: {ch.get('structural_element')} / {ch.get('new')})",
                        'info')
                return elem

    if log_callback:
        log_callback(
            f"⚠️ Не удалось разрешить target retroactive_note: '{structural}'", 'warning')
    return None


def apply_retroactive_rules(rules, stage3_changes, original_data, general_valid_from,
                            log_callback=None, fallback_scope=None, change_data=None):
    """Применяет retroactive rules (обычно amending_law) к фактическим изменениям.

    Возвращает кортеж (applied, matched_total).
    """
    if not rules:
        return 0, 0
    general_str = general_valid_from.strftime('%d.%m.%Y') if general_valid_from else ""
    applied = 0

    for rule in rules:
        rule = dict(rule)
        if rule.get("action_type") != "retroactive_note":
            continue
        if rule.get("applies_to") != "amending_law":
            if log_callback:
                log_callback(
                    f"Правило retroactive с applies_to={rule.get('applies_to')} ошибочно передано сюда, "
                    "пропускается", 'warning')
            continue

        structural = (rule.get("structural_element") or "").strip()
        scope = rule.get("scope")
        if not scope:
            scope = fallback_scope
        if not scope:
            scope = "all_changes" if structural.lower() == "law" or not structural else "selected_changes"

        note_raw = rule.get("note_text", "")
        note_valid_from = rule.get("note_valid_from") or general_str or None
        if not note_valid_from:
            note_valid_from = general_str
        note_text = normalize_amending_note_text(note_raw, log_callback) if note_raw else \
            "Изменения изменяющего НПА распространяются на правоотношения, возникшие ранее"

        matched = list(stage3_changes) if scope != "selected_changes" else [
            ch for ch in stage3_changes if _match_selected_change(structural, ch)
        ]
        skipped = 0
        for ch in matched:
            source_item_id = None
            if change_data:
                rev_num = ch.get("revision_number")
                if rev_num and not (isinstance(rev_num, str) and rev_num.lower() == "null") and not (isinstance(rev_num, list) and not rev_num):
                    try:
                        from npazs.revision.element_finder import find_item_by_revision_number
                        source_item_id = find_item_by_revision_number(change_data, rev_num)
                    except Exception:
                        pass
            elem = _target_element_for_change(original_data, ch, log_callback=log_callback)
            if elem is None:
                skipped += 1
                if log_callback:
                    log_callback(
                        f"⚠️ Целевой элемент '{ch.get('structural_element', '')}' не найден для ретро-note",
                        'warning')
                continue
            if _append_item_note(elem, note_text, note_valid_from, log_callback=log_callback,
                                 element_label=str(ch.get("structural_element", "")),
                                 source_item_id=source_item_id):
                applied += 1

        if log_callback:
            if scope == "all_changes":
                log_callback(
                    f"Applied amending-law retroactive rule to {len(matched)} changes", 'info')
            else:
                log_callback(
                    f"Applied retroactive rule for amending element \"{structural}\" "
                    f"to {len(matched) - skipped} changes", 'info')
        if not matched:
            if log_callback:
                log_callback(
                    f"WARNING: No Stage 3 changes matched amending-law retroactive rule: "
                    f"scope={scope} {structural}", 'warning')

    return applied, len(stage3_changes)


def _infer_scope(structural):
    """Определяет scope по старой схеме Stage 2 без поля scope (backward compatibility)."""
    if not structural or structural.lower() == "law":
        return "all_changes"
    return "selected_changes"


def apply_retroactive_rules_to_groups(rules, groups_by_target_id, target_data,
                                      general_valid_from, log_callback=None, change_data=None):
    """Применяет amending-law и target_law retroactive rules к ФАКТИЧЕСКИМ
    изменениям target law.

    Отличие от ``apply_retroactive_rules``: здесь используется АВТОРИТЕТНЫЙ
    механизм разрешения из ``_group_changes`` и ``_apply_changes``:

    - ``_resolved_item_id`` — id целевого элемента, вычисленный группировкой
      (учитывает granularность: для «статья 2 часть 1.1 абзац 1» владельцем
      считается «статья 2 часть 1.1»);
    - ``_created_item_id`` — id элемента, СОЗДАННОГО в Stage 4 (add), которого
      ещё не было в исходном target JSON.

    Правила применяются к ``target_data`` (итоговому JSON ПОСЛЕ Stage 4/5),
    поэтому примечания попадают и в элементы, созданные в ходе обработки, и
    сохраняются в финальном результате.

    ``amending_law`` + ``all_changes`` НИКОГДА не создаёт ``npa_notes``.

    Для ``target_law`` правил target разрешается структурным путём в итоговом
    дереве (см. ``resolve_rule_target``): сначала ищет существующий элемент,
    затем — элемент, созданный ``add``-изменением. Текст примечания
    сохраняется без нормализации (в отличие от amending-law). Правила
    ``target_law`` с ``structural_element == "law"`` обрабатываются на
    этапе Stage 2 (npa_notes) и здесь пропускаются.
    """
    if not rules:
        return 0
    general_str = general_valid_from.strftime('%d.%m.%Y') if general_valid_from else ""
    applied = 0

    all_changes = []
    for _target_id, ch_list in groups_by_target_id.items():
        for ch in ch_list:
            all_changes.append(ch)

    for rule in rules:
        rule = dict(rule)
        if rule.get("action_type") != "retroactive_note":
            continue
        applies_to = rule.get("applies_to")

        if applies_to == "amending_law":
            structural = (rule.get("structural_element") or "").strip()
            scope = rule.get("scope") or _infer_scope(structural)

            note_raw = rule.get("note_text", "")
            note_valid_from = rule.get("note_valid_from") or general_str or None
            if not note_valid_from:
                note_valid_from = general_str
            note_text = normalize_amending_note_text(note_raw, log_callback) if note_raw else \
                "Изменения изменяющего НПА распространяются на правоотношения, возникшие ранее"

            if log_callback:
                log_callback(
                    f"[RETRO DEBUG] применение amending-law правила: scope={scope} "
                    f"structural_element={structural!r} note_valid_from={note_valid_from}", 'info')

            if scope == "selected_changes":
                matched = [ch for ch in all_changes if _match_selected_change(structural, ch)]
            else:
                matched = list(all_changes)

            if not matched:
                if log_callback:
                    log_callback(
                        f"WARNING: no target changes matched retroactive rule "
                        f"(scope={scope}, {structural})", 'warning')
                continue

            per_rule_applied = 0
            for ch in matched:
                source_item_id = None
                if change_data:
                    rev_num = ch.get("revision_number")
                    if rev_num and not (isinstance(rev_num, str) and rev_num.lower() == "null") and not (isinstance(rev_num, list) and not rev_num):
                        try:
                            from npazs.revision.element_finder import find_item_by_revision_number
                            source_item_id = find_item_by_revision_number(change_data, rev_num)
                        except Exception:
                            pass
                elem = None
                created = ch.get("_created_item_id")
                if created:
                    from npazs.revision.tree_utils import find_item_by_id
                    elem = find_item_by_id(target_data, created)
                else:
                    rid = ch.get("_resolved_item_id")
                    if isinstance(rid, str) and not rid.startswith("__"):
                        from npazs.revision.tree_utils import find_item_by_id
                        elem = find_item_by_id(target_data, rid)
                if elem is None:
                    if log_callback:
                        log_callback(
                            f"⚠️ Целевой элемент не найден в итоговом JSON для ретро-note "
                            f"(change: {ch.get('structural_element', '')}, "
                            f"resolved={ch.get('_resolved_item_id')})", 'warning')
                    continue
                if not source_item_id:
                    for rev in reversed(elem.get('revisions', [])):
                        if rev.get('modified_by_id'):
                            source_item_id = rev.get('modified_by_id')
                            if log_callback:
                                log_callback(
                                    f"  source_item_id получен из modified_by_id элемента "
                                    f"{elem.get('item_id')}: {source_item_id}", 'info')
                            break
                if _append_item_note(elem, note_text, note_valid_from, log_callback=log_callback,
                                    element_label=str(ch.get("structural_element", "")),
                                    source_item_id=source_item_id):
                    applied += 1
                    per_rule_applied += 1

            if log_callback:
                log_callback(
                    f"[RETRO DEBUG] retroactive note applied to {per_rule_applied} target items "
                    f"(scope={scope})", 'info')

        elif applies_to == "target_law":
            structural = (rule.get("structural_element") or "").strip()
            if structural.lower() == "law":
                if log_callback:
                    log_callback(
                        "[RETRO DEBUG] target_law 'law' note handled in Stage 2 (npa_notes)", 'info')
                continue
            note_raw = rule.get("note_text", "")
            if not note_raw:
                continue
            note_valid_from = rule.get("note_valid_from") or general_str or None
            if not note_valid_from:
                note_valid_from = general_str
            note_text = note_raw

            if log_callback:
                log_callback(
                    f"⏳ Resolving target_law retroactive_note for '{structural}'", 'info')

            elem = resolve_rule_target(rule, target_data, all_changes, log_callback)
            if elem is None:
                continue

            source_item_id = None
            if change_data:
                parts = re.split(r'\s*->\s*', structural)
                for i in range(len(parts), 0, -1):
                    partial = " -> ".join(parts[:i])
                    try:
                        source_elem = _find_existing_element_flexible(change_data, partial, log_callback)
                        if source_elem:
                            source_item_id = source_elem.get("item_id")
                            if log_callback:
                                log_callback(
                                    f"  source_item_id from amending NPA '{partial}': {source_item_id}",
                                    'info')
                            break
                    except Exception:
                        pass
            if not source_item_id:
                for rev in reversed(elem.get('revisions', [])):
                    if rev.get('modified_by_id'):
                        source_item_id = rev.get('modified_by_id')
                        if log_callback:
                            log_callback(
                                f"  source_item_id получен из modified_by_id элемента "
                                f"{elem.get('item_id')}: {source_item_id}", 'info')
                        break

            if _append_item_note(elem, note_text, note_valid_from, log_callback=log_callback,
                                 element_label=structural,
                                 source_item_id=source_item_id):
                applied += 1

        else:
            if log_callback:
                log_callback(
                    f"[RETRO DEBUG] skipped rule applies_to={applies_to} "
                    "(not amending_law or target_law)", 'warning')
            continue

    return applied