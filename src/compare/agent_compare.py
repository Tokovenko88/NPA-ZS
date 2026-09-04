"""Агент-классификация расхождений между редакциями НПА.

Задача агента — для каждого найденного посимвольного расхождения определить
причину и, если расхождение связано с внесением изменений, указать изменяющий
НПА. Скрипт (:mod:`npazs.compare.npa_resolver`) подтягивает текст конкретного
изменения из базы JSON, а если определить элемент не удалось — полный текст
изменяющего НПА.

Причины (``reason``):

* ``original_edition``     — различие было в исходной редакции НПА;
* ``amendment``            — внесение изменений другим НПА;
* ``implementation_gap``   — одна и та же правка по-разному реализована
  проектом и правовой системой;
* ``technical_correction`` — правовая система исправила техническую ошибку
  законодателя (наш проект этого не делает);
* ``formatting``           — только оформление, без изменения смысла;
* ``unclear``              — не удалось определить.

Если агент недоступен (модель не ответила), используется механический фолбэк:
по примечаниям к элементу определяется связанный НПА и подтягивается текст
изменения из базы; если примечаний нет — различие помечается «unclear».
"""

from __future__ import annotations

import json
import re
from typing import Callable, Dict, List, Optional

from json_repair import repair_json
from npazs.config.ollama import get_active_llm_config, get_llm_backend
from npazs.revision.ai_utils import ask_ollama

from .differ import DiffRecord
from .npa_resolver import extract_change_text

__all__ = [
    'DEFAULT_PROMPT',
    'REASON_LABELS',
    'build_classify_prompt',
    'classify_diffs',
    'mechanical_resolve',
]

REASON_LABELS = {
    'original_edition': 'Исходная редакция',
    'amendment': 'Внесение изменений',
    'implementation_gap': 'Разная реализация правки',
    'technical_correction': 'Техническая правка законодателя',
    'formatting': 'Только оформление',
    'unclear': 'Не определено',
}

DEFAULT_PROMPT = """Вы — эксперт-аналитик нормативных правовых актов (НПА).

Даны две версии одного НПА:
* «документ проекта» — сформирован нашей системой;
* «документ правовой системы» — сформирован сторонней правовой системой.

target_number: {target_number}

Направление всегда однозначно: поле old — текст ДОКУМЕНТА ПРОЕКТА,
поле new — текст ДОКУМЕНТА ПРАВОВОЙ СИСТЕМЫ. kind означает:
* change — фрагмент есть в ОБОИХ документах, но различается (old ≠ new);
* add — фрагмент ЕСТЬ ТОЛЬКО в документе проекта; в правовой системе
  отсутствует (new пуст);
* remove — фрагмент есть ТОЛЬКО в документе правовой системы; в документе
  проекта отсутствует (old пуст).

Различия (json-массив с полем id):
{diff_json}

Примечания к документу (текст и связанные НПА):
{notes_json}

Для каждого id верните СТРОГО JSON-массив без пояснений:
[
  {"id": 0, "reason": "amendment", "source_npa": "930-ЗС", "explanation": "краткое обоснование"}
]

reason — одно из: original_edition, amendment, implementation_gap,
technical_correction, formatting, unclear.
Если источник изменения неизвестен, укажите source_npa пустой строкой.

Правила:
1. Объяснение НЕ должно противоречить направлению. Для kind = add нельзя
   писать «в проекте отсутствует»/«проект не включил» — напротив, фрагмент
   ЕСТЬ только в проекте. Для kind = remove нельзя писать «в правовой системе
   отсутствует» — фрагмент есть только в правовой системе.
2. reason = formatting применяется ТОЛЬКО к косметическим различиям (регистр,
   пробелы, пунктуация, е/ё). Эти различия уже отнесены к содержательным,
   поэтому formatting здесь, как правило, ошибочен — выбирайте содержательную
   причину.
3. source_npa — ИЗМЕНЯЮЩИЙ НПА (например, «516-ЗС»), а НЕ сам целевой НПА
   ({target_number}) и не номер, совпадающий с ним. Если источник не
   определён — пустая строка.
"""


#: Маркеры, противоречащие направлению: если модель объясняет add словами
#: «в проекте … отсутствует» или remove словами «в правовой системе …
#: отсутствует», объяснение инвертировано и должно быть заменено нейтральным.
#: Regex допускает слова между субъектом и отрицанием («в проекте эта норма
#: отсутствует»).
_NEG_PROJECT_RE = re.compile(
    r'в проекте[^.]*?отсутств'
    r'|в проекте[^.]*?\bнет\b'
    r'|проект(?:ная версия)?[^.]*?\bне\s+(?:включ|содерж|учитыва|отража|использ|предостав)'
    r'|проектной версией[^.]*?\bне\b'
    r'|проектом[^.]*?\bне\b',
    re.IGNORECASE,
)
_NEG_THEIRS_RE = re.compile(
    r'в правовой системе[^.]*?отсутств'
    r'|в правовой системе[^.]*?\bнет\b'
    r'|в правовой версии[^.]*?отсутств'
    r'|правовая система[^.]*?\bне\s+(?:включ|содерж|учитыва|отража|предостав)'
    r'|в консультант(?:е)?\s+[^.]*?отсутств',
    re.IGNORECASE,
)


def _direction_neutral_explanation(diff: DiffRecord) -> str:
    """Читаемое нейтральное объяснение, согласованное с направлением."""
    if diff.kind == 'add':
        return ('Фрагмент содержится только в документе проекта и отсутствует '
                'в документе правовой системы.')
    if diff.kind == 'remove':
        return ('Фрагмент содержится только в документе правовой системы и '
                'отсутствует в документе проекта.')
    return ''


def _sanitize_direction(diff: DiffRecord, log=None) -> bool:
    """Заменить объяснение, противоречащее направлению, нейтральным.

    Модель иногда инвертирует направление («в проекте отсутствует» при
    add) — из-за этого отчёт противоречит сам себе. Возвращает True, если
    объяснение было заменено.
    """
    expl = diff.explanation or ''
    if not expl.strip():
        return False
    if diff.kind == 'add':
        bad = bool(_NEG_PROJECT_RE.search(expl))
    elif diff.kind == 'remove':
        bad = bool(_NEG_THEIRS_RE.search(expl))
    else:
        bad = False
    if bad:
        if log:
            log(
                f'Объяснение модели противоречит направлению ({diff.kind}, '
                f'{diff.path}) — заменено на нейтральное',
                'warning',
            )
        diff.explanation = _direction_neutral_explanation(diff)
        return True
    return False


def _is_same_npa(a: str, b: str) -> bool:
    """Совпадают ли номера НПА (по цифрам): «127-ЗС» == «№ 127-ЗС»."""
    return _only_digits(a or '') == _only_digits(b or '')


def _only_digits(s: str) -> str:
    return re.sub(r'\D', '', s or '')


def _apply_guards(diff: DiffRecord, target_number: str = '', log=None) -> None:
    """Детерминированные правки ошибочной классификации модели.

    1) reason=formatting невозможен для расхождений основного списка: косметика
       (регистр, пунктуация, пробелы, е/ё) отсеивается в differ ещё до агента,
       поэтому «только оформление» — всегда ошибка модели. Сбрасываем на unclear.
    2) Объяснение не должно противоречить направлению (add/remove).
    3) source_npa == целевой НПА — это не изменяющий акт, а сам закон.
    """
    if diff.reason == 'formatting':
        if log:
            log(
                f'Модель отнесла содержательное различие к «оформлению» '
                f'({diff.path}) — причина сброшена на unclear',
                'warning',
            )
        diff.reason = 'unclear'
        diff.explanation = (
            'Расхождение относится к содержанию текста (не только к '
            'оформлению); причина не установлена однозначно.'
        )
    _sanitize_direction(diff, log)
    if diff.source_npa and target_number and _is_same_npa(diff.source_npa, target_number):
        if log:
            log(
                f'Модель указала source_npa = целевой НПА ({target_number}) '
                f'— источник сброшен',
                'warning',
            )
        diff.source_npa = ''


def build_classify_prompt(
    template: str,
    diffs: List[DiffRecord],
    notes_ctx: str,
    target_number: str = '',
) -> str:
    """Собрать промпт для модели по списку различий."""
    payload = []
    for idx, diff in enumerate(diffs):
        payload.append(
            {
                'id': idx,
                'path': diff.path,
                # точное место (элемент, абзац, часть/пункт) — помогает
                # модели привязать объяснение к конкретному месту текста
                'location': diff.location,
                'kind': diff.kind,
                'old': diff.old,
                'new': diff.new,
            }
        )
    text = template
    text = text.replace('{diff_json}', json.dumps(payload, ensure_ascii=False))
    text = text.replace('{notes_json}', notes_ctx or '[]')
    text = text.replace('{target_number}', target_number or '')
    return text


def mechanical_resolve(
    diff: DiffRecord,
    notes_by_path: Dict[str, List[dict]],
    target_number: str,
    get_original_text: Callable[[str, tuple], str],
) -> None:
    """Механический фолбэк (без ИИ): подтянуть изменение по примечаниям."""
    notes = notes_by_path.get(diff.path, [])
    source_numbers = []
    for note in notes:
        numbers = note.get('npa_numbers', []) if isinstance(note, dict) else []
        source_numbers.extend(numbers)
    if source_numbers:
        diff.reason = 'amendment'
        diff.source_npa = source_numbers[0]
        resolved = extract_change_text(source_numbers[0], path_key=diff.path_key)
        diff.source_item_id = resolved.get('item_id', '')
        diff.change_text = resolved.get('text', '')
    else:
        diff.reason = 'unclear'
        if target_number:
            diff.original_text = get_original_text(target_number, diff.path_key)

    if diff.kind in ('add', 'remove') and not diff.explanation:
        diff.explanation = _direction_neutral_explanation(diff)


def classify_diffs(
    diffs: List[DiffRecord],
    *,
    notes_by_path: Dict[str, List[dict]],
    target_number: str = '',
    get_original_text: Optional[Callable[[str, tuple], str]] = None,
    log=None,
    stop_event=None,
    prompt_template: Optional[str] = None,
    backend: Optional[str] = None,
    model: Optional[str] = None,
    batch_size: int = 1,
    max_queries: int = 200,
    kilo_gateway_url: Optional[str] = None,
    kilo_gateway_api_key: Optional[str] = None,
) -> None:
    """Классифицировать все различия (мутирует ``diffs``).

    При недоступности модели выполняется механический фолбэк для каждого
    необработанного различия.
    """
    if not diffs:
        return
    if log is None:
        log = lambda msg, level='info': None

    template = prompt_template or DEFAULT_PROMPT
    active_backend = backend or get_llm_backend()
    active_config = get_active_llm_config()
    current_model = model or active_config.get('model', '')

    if get_original_text is None:
        from .npa_resolver import get_original_element_text

        def _get_orig(tn, key):
            return get_original_element_text(tn, key) if tn else ''

        get_original_text = _get_orig

    index = 0
    while index < len(diffs):
        if stop_event is not None and stop_event.is_set():
            if log:
                log('Сравнение остановлено пользователем', 'warning')
            return

        batch = diffs[index:index + batch_size]
        notes_ctx = json.dumps(notes_by_path, ensure_ascii=False, indent=1)
        prompt = build_classify_prompt(template, batch, notes_ctx, target_number)
        log(f'Запрос к модели (пакет {index + 1}..{index + len(batch)} из {len(diffs)})', 'info')
        answer = ask_ollama(
            prompt,
            current_model,
            log,
            extra_options=None,
            stop_event=stop_event,
            max_retries=5,
            retry_delay=15,
            backoff_factor=2,
            change_info=f'Сравнение НПА: пакет {index}',
            backend=active_backend,
            kilo_gateway_url=kilo_gateway_url or active_config.get('base_url'),
            api_key=kilo_gateway_api_key or active_config.get('api_key'),
        )
        parsed = _parse_classification(answer)
        result_map = {}
        for item in parsed:
            try:
                result_map[int(item.get('id', -1))] = item
            except (TypeError, ValueError):
                continue

        for offset, diff in enumerate(batch):
            item = result_map.get(offset)
            if item is None:
                log(f'Нет ответа модели для {diff.path} — механический фолбэк', 'warning')
                mechanical_resolve(diff, notes_by_path, target_number, get_original_text)
                continue
            diff.reason = str(item.get('reason', 'unclear'))
            diff.explanation = str(item.get('explanation', ''))
            diff.source_npa = str(item.get('source_npa', '') or '')

            # Детерминированные гварды против ошибочной классификации модели
            # (formatting на содержательном различии, инверсия направления,
            # source_npa == целевой НПА).
            _apply_guards(diff, target_number, log)

            if diff.reason in ('amendment', 'implementation_gap'):
                source = diff.source_npa
                if not source:
                    notes = notes_by_path.get(diff.path, [])
                    for note in notes:
                        numbers = note.get('npa_numbers', []) if isinstance(note, dict) else []
                        if numbers:
                            source = numbers[0]
                            break
                if source:
                    resolved = extract_change_text(source, path_key=diff.path_key)
                    diff.source_npa = source
                    diff.source_item_id = resolved.get('item_id', '')
                    diff.change_text = resolved.get('text', '')
            elif diff.reason in ('technical_correction', 'original_edition', 'unclear', 'formatting'):
                if target_number:
                    diff.original_text = get_original_text(target_number, diff.path_key)

        index += len(batch)


def _parse_classification(answer: str) -> List[dict]:
    """Разобрать ответ модели в список словарей классификации.

    Ожидается JSON-массив вида::

        [{"id": 0, "reason": "amendment", "source_npa": "930-ЗС",
          "explanation": "..."}]

    Допускается markdown-обёртка ```` ```json ... ``` ```` и словари с
    массивом в ключе ``items``/``results``/``data``. При любом сбое разбора
    возвращается пустой список (вызывающий код применит механический фолбэк).
    """
    if not answer:
        return []
    text = answer.strip()
    if text.startswith('```'):
        text = re.sub(r'^```[A-Za-z]*\s*', '', text)
        text = re.sub(r'\s*```$', '', text).strip()
    data = None
    try:
        data = json.loads(text)
    except ValueError:
        try:
            data = json.loads(repair_json(text))
        except (ValueError, TypeError):
            return []
    if isinstance(data, dict):
        data = data.get('items') or data.get('results') or data.get('data') or []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]