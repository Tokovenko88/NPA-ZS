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

У нас есть две версии одного НПА: «документ проекта» (сформирован нашей
системой) и «документ правовой системы». Для каждого различия укажите, чем оно
вызвано.

target_number: {target_number}

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
"""


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