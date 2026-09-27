"""Утилиты для взаимодействия с Ollama API."""

import json
import re
import time

import npazs.constants as _constants
import requests
from json_repair import repair_json
from npazs.constants import (  # noqa: F401  (TYPE_TO_RUSSIAN/PLURAL_TO_SINGULAR — ре-экспорт)
    DEFAULT_KILO_GATEWAY_MODEL,
    DEFAULT_KILO_GATEWAY_URL,
    DEFAULT_OLLAMA_MODEL,
    HTTP_BACKEND_DEFS,
    HTTP_BACKENDS,
    PLURAL_TO_SINGULAR,
    TYPE_TO_RUSSIAN,
    _ollama_base_url,
)
from npazs.llm_models import OLLAMA_SIGNIN_HINT
from npazs.revision.text_utils import strip_thinking_tags


class _OllamaAuthError(Exception):
    """Авторизация Ollama cloud отсутствует (HTTP 403): повторы бесполезны.

    До выполнения ``ollama signin`` повторный запрос вернёт тот же 403,
    поэтому ask_ollama логирует подсказку и сразу возвращает None.
    """


class InvalidJsonAnswerError(Exception):
    """Модель вернула ответ без валидного JSON (``repair_json=True``).

    Такой ответ не принимается и не «пропускается» с продолжением
    программно: исключение поднимается внутри цикла ``ask_kilo_gateway`` /
    ``ask_ollama``, чтобы запрос повторился так же, как при HTTP-сбое, а после
    исчерпания ``max_retries`` пользователю задавался обычный вопрос
    о повторе/смене бэкенда (см. ``_user_retry_callback``).
    """


#: Флаг «в этой сессии уже предлагали вход в Ollama» — чтобы при dozens of
#: elementwise-запросах не показывать диалог после каждого HTTP 403.
_ollama_signin_notified = False


def _offer_ollama_signin_once() -> None:
    """Сообщить GUI о HTTP 403 от Ollama Cloud (не чаще одного раза за запуск).

    Вызывается из ``ask_ollama`` (рабочий поток).  Сам диалог показывает GUI:
    колбэк обязан перенести вызов в главный поток Tkinter.  Сброс флага —
    функцией :func:`reset_ollama_signin_notice` (успешный запрос / обновление
    списка моделей), чтобы после ``ollama signin`` предложение появилось снова.
    """
    global _ollama_signin_notified
    if _ollama_signin_notified:
        return
    callback = _constants._ollama_signin_callback
    if callback is None:
        return
    _ollama_signin_notified = True
    try:
        callback()
    except Exception:  # noqa: BLE001 — диалог не должен ломать пайплайн
        pass


def reset_ollama_signin_notice() -> None:
    """Разрешить повторное предложение ``ollama signin`` в следующий раз."""
    global _ollama_signin_notified
    _ollama_signin_notified = False



def tls_interception_hint(backend_name, error):
    """Подсказка при сбое локального прокси ``qwen2api`` из-за перехвата TLS.

    Прокси Qwen2API отвечает ``HTTP 500`` с текстом вроде
    «无法创建或续接 Qwen 会话», когда не может открыть сессию на
    ``chat.qwen.ai``. Частая причина — антивирус или корпоративный прокси с
    проверкой защищённых соединений (Kaspersky, Dr.Web, ESET): Node.js/bun не
    читают хранилище корней Windows и отвергают подменённый сертификат.
    Возвращает строку-подсказку (с ведущими пробелами) или пустую строку.
    """
    if (backend_name or '').strip().lower() != 'qwen2api':
        return ''
    text = str(error)
    if 'HTTP 500' not in text and '无法创建或续接' not in text:
        return ''
    return (
        '  Подсказка: прокси Qwen2API не смог создать сессию чата — частая причина '
        'перехват TLS антивирусом/корпоративным прокси. Перезапустите прокси через '
        'scripts\\qwen-proxy.bat (или make run-qwen2api): launcher подставит '
        'NODE_EXTRA_CA_CERTS с корнями Windows. Диагностика — docs/qwen2api.md.'
    )


#: Aliyun WAF на chat.qwen.ai отдаёт капчу-челлендж, когда JSON-тело запроса
#: приближается к 128 KiB (конфиг прокси Qwen2API: комментарий
#: ``AGENT_CONTEXT_FILE_THRESHOLD_BYTES`` = 90 KiB, замерено 2026-09-10).
#: ``requests.post(json=payload)`` сериализует с ``ensure_ascii=True``: кириллица
#: превращается в ``\u0420`` (6 байт вместо 2 в UTF-8) и тело раздувается втрое —
#: промпт stage 3 (87.7 KB текста) уходил как 124.3 KiB, т.е. вплотную к капче.
#: Поэтому тело отправляется как UTF-8-байты (``ensure_ascii=False``).
WAF_BODY_LIMIT_BYTES = 128 * 1024

#: Предупреждаем заранее — при таком размере тела до капчи остаётся мало запаса.
WAF_BODY_WARN_BYTES = 112 * 1024

#: Ошибка ``HTTP 502`` от Qwen2API: Aliyun WAF на chat.qwen.ai прислал капчу-
#: челлендж (``FAIL_SYS_USER_VALIDATE`` / ``RGV587`` — часто из-за слишком частых
#: или тяжёлых запросов). Прокси ставит аккаунт на паузу 5 минут
#: (``AccountRotator.cooldownPeriod``), поэтому обычный бэк-офф 15/30/60/120 с
#: укладывается в охлаждение и все попытки сгорают впустую: ждём дольше.
WAF_CHALLENGE_WAIT_SECONDS = 330

#: Маркеры WAF-челленджа в тексте ошибки (тело ответа прокси/апстрима).
_WAF_CHALLENGE_MARKERS = (
    'upstream_waf_challenge',
    'FAIL_SYS_USER_VALIDATE',
    'RGV587',
    'WAF/captcha',
    '/punish?',
)


def is_waf_challenge_error(backend_name, error):
    """True: ``error`` — капча Aliyun WAF от локального прокси ``qwen2api``."""
    if (backend_name or '').strip().lower() != 'qwen2api':
        return False
    text = str(error)
    return any(marker in text for marker in _WAF_CHALLENGE_MARKERS)


def waf_challenge_hint(backend_name, error):
    """Подсказка при ``HTTP 502 ... upstream_waf_challenge`` (капча WAF).

    WAF chat.qwen.ai срабатывает на частоту/объём запросов или тяжёлый
    контекст — это не поломка прокси и не неверный ключ. Прокси сам ставит
    сработавший аккаунт на паузу ~5 минут и исключает его из ротации;
    NPA-ZS в этом случае спрашивает у прокси статус аккаунтов
    (``GET /api/accountStats``) и повторяет запрос сразу через следующий
    свободный аккаунт (см. :func:`retry_wait_seconds`). Возвращает
    строку-подсказку или пустую строку.
    """
    if not is_waf_challenge_error(backend_name, error):
        return ''
    return (
        '  Подсказка: WAF chat.qwen.ai (Aliyun) прислал капчу-челлендж — прокси '
        'поставил аккаунт на паузу ~5 минут. NPA-ZS спросит у прокси, на каком '
        'именно аккаунте проблема (GET /api/accountStats), и повторит запрос сразу '
        'через следующий свободный аккаунт; пауза перед повтором нужна только если '
        'в cooldown оказались ВСЕ аккаунты. Если ошибка повторяется: подождите '
        '5–15 минут; откройте chat.qwen.ai в браузере под аккаунтом прокси и '
        'пройдите капчу; добавьте второй аккаунт в веб-панель прокси (ротация '
        'снизит нагрузку). Диагностика — docs/qwen2api.md.'
    )


def waf_body_size_hint(body_bytes, backend_name='qwen2api'):
    """Подсказка, если тело запроса близко к порогу капчи WAF (~128 KiB).

    Размер тела — единственная причина WAF-челленджа, которую NPA-ZS видит
    заранее: при ``ensure_ascii=True`` (поведение ``requests.post(json=...)``)
    кириллица раздувает тело втрое, и ``prompt_3.md`` подходил к капче на
    считаные килобайты. Возвращает строку-подсказку или пустую строку.
    """
    if (backend_name or '').strip().lower() != 'qwen2api':
        return ''
    if body_bytes < WAF_BODY_WARN_BYTES:
        return ''
    return (
        f"  Подсказка: тело запроса {body_bytes / 1024:.0f} KiB — вплотную к порогу "
        f"капчи WAF chat.qwen.ai (~{WAF_BODY_LIMIT_BYTES / 1024:.0f} KiB). "
        'Уменьшите промпт (data/prompts/prompt_3.md) или выберите другой бэкенд: '
        'повторы будут упираться в капчу. Диагностика — docs/qwen2api.md.'
    )


#: Маркеры дневной квоты модели на chat.qwen.ai от локального прокси ``qwen2api``.
#: Прокси Qwen2API (см. ``tools/Qwen2API/src/utils/upstream-error.js``) объявляет квоту
#: кодом ``RateLimited`` / ``quota_limit`` и текстом «You've reached the upper limit for
#: today's usage» (EN) / «已达上限» / «次数已达上限» (CN). OpenAI-совместимый путь
#: ``/v1/chat/completions`` доставляет это как ``HTTP 429 insufficient_quota``.
#: WAF-маркеры (выше) — отдельная категория; квота и капча не пересекаются.
#: Тексты квоты прокси: регекс (CN/EN, регистронезависимо).
_QUOTA_RE = re.compile(
    r'upper limit for today|reached the upper limit|已达上限|次数已达上限|配额已用尽|'
    r'daily\s*(limit|quota)',
    re.IGNORECASE,
)
#: Коды ошибок квоты (в нижнем регистре — сравнение по ``text.lower()``).
_QUOTA_CODE_MARKERS = (
    'ratelimited',
    'quota_limit',
    'insufficient_quota',
    'quota_exhausted',
)


class QuotaExhaustedError(Exception):
    """Дневной лимит модели на chat.qwen.ai исчерпан (qwen2api).

    Поднимается, чтобы отличить «квота кончилась — повторы бессмысленны» от
    временных сбоев (WAF/HTTP 5xx). Верхний слой (``ask_kilo_gateway``) ловит
    этот тип и сразу уведомляет пользователя о необходимости переключить бэкенд,
    не запуская ``max_retries`` и не спрашивая «повторить?».
    """

    def __init__(self, message, backend=None, model=None):
        super().__init__(message)
        # backend/model хранятся для диалога пользователю.
        self.backend = backend
        self.model = model


def is_quota_exhausted_error(backend_name, error):
    """True: ``error`` — дневная квота модели на chat.qwen.ai (qwen2api).

    Только для бэкенда ``qwen2api`` (``free_deepseek``/``kilo_gateway`` и т.п.
    имеют свои тарифы — к ним не применяется). WAF-ошибки считаются НЕ квотой:
    ``is_waf_challenge_error`` здесь проверяется первой (капча и квота
    в ответах прокси не пересекаются).
    """
    if (backend_name or '').strip().lower() != 'qwen2api':
        return False
    if is_waf_challenge_error(backend_name, error):
        return False
    text = str(error)
    if _QUOTA_RE.search(text):
        return True
    low = text.lower()
    for marker in _QUOTA_CODE_MARKERS:
        if marker in low:
            return True
    return False


def quota_exhausted_hint(backend_name, error, model=None):
    """Подсказка при исчерпании дневной квоты модели (``qwen2api``).

    Возвращает строку с пояснением, что лимит — на сегодня, повторы бесполезны
    (они будут сгорать впустую, как и WAF, но без таймаута), и нужно
    переключиться на другой бэкенд/модель или добавить аккаунт в прокси.
    Пустая строка — если это не квота.
    """
    if not is_quota_exhausted_error(backend_name, error):
        return ''
    model_name = model or ''
    extra = f" (модель: {model_name})" if model_name else ""
    return (
        f"  Подсказка: дневной лимит модели{extra} на chat.qwen.ai через "
        f"прокси qwen2api исчерпан — повторы бессмысленны (лимит обновляется "
        f"утром). Лимит в qwen2api МОДЕЛЬНЫЙ, поэтому достаточно выбрать "
        f"другую модель того же бэкенда. Если подходящей модели нет — "
        f"Переключитесь на другой бэкенд (free_deepseek / kilo_gateway / "
        f"openrouter / openai-compatible) или добавьте аккаунт в веб-панель "
        f"прокси (data/logs/qwen2api-proxy.log). Диагностика — docs/qwen2api.md."
    )


#: Таймаут запроса статуса аккаунтов локального прокси ``qwen2api``
#: (``GET /api/accountStats`` — адрес локальный, секунд).
QWEN2API_STATS_TIMEOUT = 5


def qwen2api_account_stats(base_url, api_key=None, timeout=QWEN2API_STATS_TIMEOUT):
    """Статус аккаунтов прокси ``qwen2api`` (``GET /api/accountStats``).

    Прокси сам ротирует аккаунты (``AccountRotator``): после капчи WAF
    сработавший аккаунт уходит в cooldown ~5 минут и исключается из выбора,
    поэтому следующий запрос уходит на другой аккаунт. Чтобы решить, ждать
    ли перед повтором, NPA-ZS запрашивает у прокси, какие аккаунты сейчас
    в cooldown и есть ли свободные.

    Возвращает ``(records, error)``:

    * ``records`` — список ``{email, kind, cooldown_ends_at, last_error_code}``
      или ``None``, если статус получить не удалось;
    * ``error`` — причина (``'HTTP 403'``, текст исключения и т.п.)
      либо ``None``.

    ``base_url`` — ``QWEN2API_BASE_URL`` вида ``http://127.0.0.1:3000/v1``;
    эндпоинт админки живёт под ``/api`` на том же хосте и требует admin-ключ
    (первый ключ ``API_KEY`` в ``.env`` прокси) — при совпадении
    ``QWEN2API_API_KEY`` с ним всё работает без дополнительной настройки.
    """
    if not base_url:
        return None, 'base_url не задан'
    origin = str(base_url).strip().rstrip('/')
    if origin.endswith('/v1'):
        origin = origin[:-3].rstrip('/')
    headers = {}
    key = (api_key or '').strip()
    if key:
        headers['Authorization'] = f'Bearer {key}'
    try:
        resp = requests.get(
            f'{origin}/api/accountStats', headers=headers, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 — прокси может быть не запущен
        return None, str(exc)
    if resp.status_code != 200:
        return None, f'HTTP {resp.status_code}'
    try:
        data = resp.json()
    except Exception as exc:  # noqa: BLE001 — не-JSON тело админки
        return None, f'не удалось разобрать ответ: {exc}'
    records = []
    for item in data.get('accounts') or []:
        status = item.get('status') or {}
        cooldown = status.get('cooldownEndsAt')
        records.append({
            'email': str(item.get('email') or ''),
            'kind': str(status.get('kind') or ''),
            'cooldown_ends_at': cooldown if isinstance(cooldown, (int, float)) else None,
            'last_error_code': status.get('lastErrorCode') or None,
        })
    if not records:
        return None, 'прокси не вернул ни одного аккаунта'
    return records, None


def waf_retry_wait_seconds(base_url, api_key=None, log_callback=None, fallback_wait=15):
    """Пауза перед повтором после WAF-челленджа ``qwen2api`` с учётом ротации.

    Вместо слепого ожидания :data:`WAF_CHALLENGE_WAIT_SECONDS` NPA-ZS
    запрашивает у прокси статус аккаунтов (:func:`qwen2api_account_stats`):

    * есть свободный аккаунт → ``0``: сработавший аккаунт уже исключён
      из ротации, повтор сразу пойдёт на следующий;
    * все аккаунты в cooldown → время до выхода ближайшего (+ буфер),
      но не дольше :data:`WAF_CHALLENGE_WAIT_SECONDS`;
    * статус получить не удалось (прокси не запущен / ключ не admin) →
      ``fallback_wait`` (обычный бэк-офф) — однозначного ожидания 330 с
      больше нет.

    Проблемный аккаунт (с кодом ошибки) печатается в лог.
    """
    records, error = qwen2api_account_stats(base_url, api_key)
    if records is None:
        if log_callback:
            log_callback(
                f'  Прокси qwen2api: статус аккаунтов недоступен ({error}) — '
                f'обычная пауза {fallback_wait} с. Для доступа к /api/accountStats '
                'QWEN2API_API_KEY должен быть первым ключом API_KEY в .env прокси.',
                'warning')
        return fallback_wait
    now_ms = time.time() * 1000

    def _in_cooldown(rec):
        return (rec['kind'] == 'cooldown'
                and rec['cooldown_ends_at'] is not None
                and rec['cooldown_ends_at'] > now_ms)

    cooling = [rec for rec in records if _in_cooldown(rec)]
    free = [rec for rec in records if not _in_cooldown(rec)]
    for rec in cooling:
        if log_callback:
            until = time.strftime('%H:%M:%S', time.localtime(rec['cooldown_ends_at'] / 1000))
            log_callback(
                f"  Прокси qwen2api: аккаунт {rec['email'] or '?'} в cooldown до {until} "
                f"(причина: {rec['last_error_code'] or 'неизвестна'})", 'warning')
    if free:
        if log_callback:
            log_callback(
                f'  Прокси qwen2api: свободных аккаунтов {len(free)} из {len(records)} — '
                'повтор запроса без паузы (ротация на следующий аккаунт)', 'info')
        return 0
    earliest = min(rec['cooldown_ends_at'] for rec in cooling)
    # +5 с — буфер на сетевую задержку, чтобы прокси точно вышел из cooldown.
    wait = int(round((earliest - now_ms) / 1000)) + 5
    wait = max(1, min(wait, WAF_CHALLENGE_WAIT_SECONDS))
    if log_callback:
        log_callback(
            f'  Прокси qwen2api: все {len(records)} аккаунтов в cooldown — '
            f'повтор через {wait} с (до выхода ближайшего)', 'info')
    return wait


def retry_wait_seconds(attempt, retry_delay, backoff_factor, backend_name='', error=None,
                       base_url=None, api_key=None, log_callback=None):
    """Секунд до следующей попытки: обычный бэк-офф, но с учётом WAF-ротации.

    ``attempt`` — уже увеличенный номер попытки (1 после первой ошибки),
    формула совпадает с историческим ``retry_delay * backoff ** (attempt - 1)``.
    Для WAF-челленджа ``qwen2api`` пауза определяется по статусу аккаунтов
    прокси (см. :func:`waf_retry_wait_seconds`): если есть свободный аккаунт,
    повтор идёт без паузы — NPA-ZS НЕ ждёт 330 секунд слепо.
    """
    wait = retry_delay * (backoff_factor ** (attempt - 1))
    if is_waf_challenge_error(backend_name, error):
        return waf_retry_wait_seconds(
            base_url, api_key, log_callback=log_callback, fallback_wait=wait)
    return wait


def _ask_invalid_json_action(log_callback, answer, error):
    """Зафиксировать отказ от невалидного JSON-ответа ИИ.

    Ответ без валидного JSON не принимается ни в каком виде: вызывающий цикл
    (``ask_kilo_gateway`` / ``ask_ollama``) поднимает
    :class:`InvalidJsonAnswerError` и повторяет запрос — «пропускать ответ
    модели и продолжаем программно» больше нельзя.
    """
    if log_callback:
        log_callback(
            "  Невалидный JSON-ответ ИИ: ответ отклонён (валидный JSON обязателен)",
            'warning')
    return False


def _invalid_json_reason(answer):
    """Короткое описание невалидного ответа для текста ошибки повтора."""
    text = answer or ''
    preview = ' '.join(text.split())[:160]
    return f'невалидный JSON-ответ ИИ ({len(text)} симв.): {preview}'


def _extract_prompt_inputs(prompt_text):
    tags = [
        'input_data', 'input_document', 'change_doc', 'change_json', 'input_json',
        'date_pub', 'law_number', 'article_number', 'doc_text',
        'change_npa_number', 'change_date_pub', 'change_date_effective', 'valid_from',
    ]
    input_parts = []
    for tag in tags:
        pattern = rf'<({tag})>(.*?)</\1>'
        matches = re.findall(pattern, prompt_text, re.DOTALL | re.IGNORECASE)
        for m in matches:
            input_parts.append(f"<{m[0]}>\n{m[1]}\n</{m[0]}>")
    if input_parts:
        return '\n'.join(input_parts).strip()
    return None


def _extract_first_json_value(text):
    """Вырезать первый сбалансированный JSON-объект/массив из текста.

    Возвращает ``(тело, хвост)``; если значение не найдено — ``(None, '')``.

    Нужно для бэкендов с «поисковым» хвостом: после валидного JSON модель
    дописывает цитаты ссылок (``---\\n[1] … | 来源: 未知来源``). Точный
    ``json.loads`` на таком тексте падает с ``Extra data``, а ``repair_json``
    дочитывает хвост как продолжение структуры и превращает вердикт
    пост-анализа ``{"status", "summary", "issues"}`` в мусорный массив —
    пост-анализ при этом падал в ``status отсутствует`` и отбрасывал все
    найденные коррекции (кейс 516-ЗС → 127-ЗС, прогон 23.09.2026:
    ``8861 → 8143`` символов, ``issues=0, corrected_path=null``).

    Счёт ведётся с учётом строк и экранирования, поэтому фигурные/квадратные
    скобки внутри строк значений на баланс не влияют.
    """
    if not text:
        return None, ''
    start = 0
    end = len(text)
    while start < end and text[start].isspace():
        start += 1
    if start >= end or text[start] not in '{[':
        return None, ''
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, end):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in '{[':
            depth += 1
        elif char in '}]':
            depth -= 1
            if depth == 0:
                return text[start:index + 1], text[index + 1:]
    return None, ''


def _repair_json_answer(answer, log_callback=None):
    """Repair JSON returned by the model when possible; otherwise skip the response."""
    if not answer:
        return answer
    cleaned = strip_thinking_tags(answer).strip()
    # Снимаем fences ```json … ``` даже если после закрывающей пары ИИ дописал
    # «поисковый» хвост (цитаты ссылок) — иначе остаётся и fences, и хвост,
    # и JSON не находится вовсе.
    fence = re.search(r'```(?:json)?[ \t]*\r?\n?', cleaned, re.IGNORECASE)
    if fence:
        after_fence = cleaned[fence.end():]
        close = after_fence.find('```')
        cleaned = (after_fence[:close] if close >= 0 else after_fence).strip()
    # Ответ вида «json\\n{…}» (типичный подсказочный префикс моделей).
    if cleaned[:5].lower() == 'json' and (
            len(cleaned) == 5 or cleaned[5] in '\r\n \t{['):
        cleaned = cleaned[5:].lstrip('\r\n \t') or cleaned

    body, tail = _extract_first_json_value(cleaned)
    if body is None:
        # Не нашли сбалансированного значения — работаем со всем текстом.
        body, tail = cleaned, ''
    if tail.strip() and log_callback:
        preview = ' '.join(tail.split())[:160]
        log_callback(
            f"  ⚠ Отброшен хвост после JSON-ответа ИИ: {len(tail)} симв. "
            f"(начало: {preview})",
            'warning',
        )

    try:
        try:
            parsed = json.loads(body)
            exact = True
        except json.JSONDecodeError:
            # Оборванный JSON (обрыв по токенам/лимиту) чиним как раньше.
            parsed = json.loads(repair_json(body))
            exact = False
        if not isinstance(parsed, (dict, list)):
            raise TypeError(
                f'JSON-ответ разобран как {type(parsed).__name__}, ожидался '
                f'объект или массив')
        repaired = json.dumps(parsed, ensure_ascii=False)
        if not exact and log_callback:
            log_callback(
                f"  ⚠ Автоматически исправлен JSON-ответ ИИ: {len(body)} → {len(repaired)} символов",
                'warning',
            )
        return repaired
    except Exception as exc:
        if log_callback:
            log_callback(f"  ❌ Невалидный JSON-ответ ИИ после repair_json: {exc}", 'error')
        if _ask_invalid_json_action(log_callback, cleaned, exc):
            return cleaned
        return None


def _reapply_request_after_switch(
    backend_name, model, base_url, api_key, agent_session,
    prompt, extra_options, log_callback,
):
    """Перечитать настройки провайдера после выбора «Переключить бэкенд».

    Вызывается из ``ask_kilo_gateway`` / ``ask_ollama``, когда пользователь в
    диалоге нажал «Переключить бэкенд».  Через
    ``_constants._settings_provider`` (регистрируется GUI) читаются свежие
    backend/model/URL/key/agent_session, из них пересобирается HTTP-запрос, и
    цикл повторов продолжается **без** установки ``stop_event`` — прогон не
    прерывается.

    Смена засчитывается, если изменился ЛЮБОЙ параметр: бэкенд, **модель**,
    URL или API-ключ. Раньше проверялся только бэкенд, поэтому выбор другой
    модели того же провайдера (частый случай при исчерпании дневной квоты
    ``qwen2api`` — лимиты там модельные) отклонялся как «Бэкенд не изменён»,
    после чего прогон останавливался целиком (лог прогона 27.09.2026: «Бэкенд
    не изменён — остановка прогона» → «Обработка прервана пользователем»,
    хотя модель в GUI была переключена).

    Возвращает кортеж ``(backend_name, model, base_url, api_key,
    agent_session, url, headers, body, temperature, top_p)`` либо ``None``,
    если сменить нечего (или провайдер настроек недоступен — headless).
    """
    provider = _constants._settings_provider
    if provider is None:
        if log_callback:
            log_callback(
                '  Настройки провайдера недоступны (нет GUI-провайдера) — '
                'применить смену бэкенда/модели невозможно',
                'warning')
        return None
    new_settings = provider() or {}
    new_backend = (new_settings.get('backend') or '').strip().lower() or backend_name
    new_model = (new_settings.get('model') or '').strip() or model
    new_base_url = (new_settings.get('base_url') or '').strip().rstrip('/') or base_url
    new_api_key = new_settings.get('api_key')
    if new_api_key is None:
        new_api_key = api_key
    new_session = new_settings.get('agent_session')
    if new_session is None:
        new_session = agent_session

    # Что именно изменилось — по этому списку решаем, применять ли смену.
    changed = []
    if new_backend != backend_name:
        changed.append('бэкенд')
    if new_model != model:
        changed.append('модель')
    if (new_base_url or '').rstrip('/') != (base_url or '').rstrip('/'):
        changed.append('URL')
    if (new_api_key or '') != (api_key or ''):
        changed.append('API-ключ')
    if not changed:
        if log_callback:
            log_callback(
                '  Смена провайдера не применена: бэкенд, модель, URL и ключ '
                'остались прежними. Выберите ДРУГУЮ модель (например, другую '
                'модель того же бэкенда — лимиты в qwen2api модельные) или '
                'другой бэкенд и нажмите «Готово».',
                'warning')
        return None

    backend_name = new_backend
    model = new_model
    base_url = new_base_url
    api_key = new_api_key
    agent_session = new_session
    temperature = extra_options.get("temperature", 0.0) if extra_options else 0.0
    top_p = extra_options.get("top_p", 0.1) if extra_options else 0.1
    url = f"{base_url}/chat/completions"
    if backend_name in ('free_deepseek', 'qwen2api') and not url.rstrip('/').endswith('/v1/chat/completions'):
        url = f"{base_url}/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if backend_name == 'free_deepseek':
        session = (agent_session or '').strip() if agent_session else ''
        if not session:
            try:
                from npazs.config.ollama import get_free_deepseek_config
                session = str(get_free_deepseek_config().get('session') or '').strip()
            except Exception:  # noqa: BLE001
                session = ''
        headers["x-agent-session"] = session or 'npazs-main'
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "top_p": top_p,
    }
    body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
    if log_callback:
        log_callback(f"  Тело запроса (переключено): {len(body) / 1024:.1f} KiB", 'info')
        log_callback(
            f"  ✅ Провайдер переключён на {backend_name} (модель: {model}) — "
            f"изменено: {', '.join(changed)}. Повтор запроса...", 'result')
    return backend_name, model, base_url, api_key, agent_session, url, headers, body, temperature, top_p


#: Сколько раз подряд диалог смены провайдера может вернуться без изменений,
#: прежде чем программа откажется от этого изменения. Нужно, чтобы «переключи
#: бэкенд, но ничего не переключил» не превращалось в остановку всего прогона.
SWITCH_ASK_LIMIT = 3


def _ask_retry_choice(retry_cb, message, action='retry'):
    """Вызвать GUI-диалог повтора с учётом старых колбэков (без ``action``)."""
    try:
        return retry_cb(message, action=action)
    except TypeError:
        return retry_cb(message)


def _resolve_user_retry(
    retry_cb, backend_name, model, base_url, api_key, agent_session,
    prompt, extra_options, log_callback, change_info, stop_event,
    last_error, reason='failures', max_retries=None,
):
    """Диалог «Повторить / Переключить бэкенд / Остановить» + применение смены.

    ``reason='quota'`` — дневной лимит модели исчерпан (диалог с кнопкой
    «Переключить бэкенд» и подсказкой, что достаточно сменить модель);
    ``reason='failures'`` — исчерпаны все попытки (обычный сбой/HTTP-ошибка).

    Возвращает кортеж ``(outcome, state)``:

    * ``('resume', state)`` — продолжаем: ``state`` — новое состояние запроса
      из :func:`_reapply_request_after_switch` либо ``None``, если пользователь
      выбрал «Повторить» с теми же настройками;
    * ``('stop', None)`` — пользователь явно нажал «Остановить»
      (``stop_event`` выставлен, прогон завершается по воле пользователя);
    * ``('give_up', None)`` — сменить не удалось (headless или пользователь
      ни разу ничего не поменял). ``stop_event`` НЕ выставляется: изменение
      уходит в FAILED, а **прогон продолжается**.
    """
    if reason == 'quota':
        header = f"Лимит модели {model} ({backend_name}) на сегодня исчерпан."
        footer = (
            "\n\nСмените модель или бэкенд в главном окне и нажмите «Готово» — "
            "прогон продолжится.\n(Лимиты qwen2api модельные: достаточно "
            "выбрать другую модель того же бэкенда.)"
        )
        action = 'switch'
    else:
        header = f"Модель {model} ({backend_name}) не отвечает"
        if max_retries:
            header += f": {max_retries} попытки подряд неудачны."
        footer = (
            "\n\nСмените провайдера? Нажмите «Переключить бэкенд» "
            "и выберите другой бэкенд или модель в главном окне, либо "
            "повторите запрос ещё раз."
        )
        action = 'retry'
    extra = f"\n\nИзменение: {change_info}" if change_info else ""

    for _ in range(SWITCH_ASK_LIMIT):
        message = f"{header}\nПоследняя ошибка: {last_error}{extra}{footer}"
        user_choice = _ask_retry_choice(retry_cb, message, action=action)
        if user_choice == 'retry':
            if log_callback:
                log_callback("  Пользователь выбрал повтор", 'info')
            return 'resume', None
        if user_choice == 'switch':
            switched = _reapply_request_after_switch(
                backend_name, model, base_url, api_key, agent_session,
                prompt, extra_options, log_callback,
            )
            if switched is not None:
                return 'resume', switched
            # Ничего не изменилось — спрашиваем ещё раз (лимит попыток
            # ограничен, чтобы не крутить диалог бесконечно).
            continue
        # «Остановить» (или нераспознанный ответ) — останавливаем только тут.
        if log_callback:
            log_callback("  Пользователь остановил процесс", 'warning')
        if stop_event is not None:
            stop_event.set()
        return 'stop', None
    if log_callback:
        log_callback(
            f"  Провайдер так и не изменён после {SWITCH_ASK_LIMIT} попыток — "
            "это изменение будет помечено FAILED, прогон продолжается. "
            "Переключите провайдера и повторите прогон позже.",
            'warning')
    return 'give_up', None


def _reapply_ollama_after_switch(backend, model, log_callback):
    """Применить смену провайдера в нативном пути Ollama (``ask_ollama``).

    Возвращает кортеж ``(backend, model, base_url, api_key, http_redirect)``:

    * ``http_redirect=True`` — пользователь выбрал HTTP-бэкенд, запрос надо
      переадресовать в :func:`ask_kilo_gateway` (``stop_event`` не трогаем);
    * ``http_redirect=False`` и ``backend``/``model`` новые — продолжаем в
      нативном пути Ollama;
    * ``None`` — ничего не изменилось (диалог будет показан ещё раз).
    """
    provider = _constants._settings_provider
    if provider is None:
        if log_callback:
            log_callback(
                '  Настройки провайдера недоступны (нет GUI-провайдера) — '
                'применить смену бэкенда/модели невозможно',
                'warning')
        return None
    new_settings = provider() or {}
    new_backend = (new_settings.get('backend') or '').strip().lower() or backend
    new_model = (new_settings.get('model') or '').strip() or model
    if new_backend in HTTP_BACKENDS:
        if log_callback:
            log_callback(
                f"  Провайдер изменён (бэкенд) → {new_backend} "
                f"(модель: {new_model}). Запрос переадресуется в HTTP-клиент...",
                'result')
        return (new_backend, new_model,
                (new_settings.get('base_url') or '').strip().rstrip('/'),
                new_settings.get('api_key'), True)
    changed = []
    if new_backend != backend:
        changed.append('бэкенд')
    if new_model != model:
        changed.append('модель')
    if not changed:
        if log_callback:
            log_callback(
                '  Смена провайдера не применена: бэкенд и модель остались '
                'прежними. Выберите ДРУГУЮ модель или другой бэкенд и '
                'нажмите «Готово».',
                'warning')
        return None
    if log_callback:
        log_callback(
            f"  ✅ Провайдер изменён ({', '.join(changed)}) → {new_backend} "
            f"(модель: {new_model}). Повтор запроса...", 'result')
    return new_backend, new_model, None, None, False


def ask_kilo_gateway(prompt, model, log_callback, extra_options=None, stop_event=None, max_retries=3, retry_delay=15, backoff_factor=1, change_info=None, base_url=None, api_key=None, backend=None, agent_session=None, repair_json=True):
    """Универсальный HTTP-клиент для OpenAI-compatible /chat/completions.

    Политика повторов: максимум ``max_retries=3`` попытки, пауза между ними
    фиксированная ``retry_delay=15`` с и НЕ растёт от попытки к попытке
    (``backoff_factor=1``). После 3 неудач подряд пользователю задаётся
    вопрос о смене провайдера (диалог с кнопками «Переключить бэкенд» /
    «Повторить» / «Остановить»).

    ``backend`` — имя бэкенда (``kilo_gateway``/``cline``/``openrouter``/
    ``cerebras``/``mistral``/``gemini``/``free_deepseek``/
    ``qwen2api``).
    Используется только для понятных сообщений в логе: без него все
    HTTP-ошибки писались как «Kilo Gateway ошибка», даже когда запрос шёл
    в OpenRouter/Cline/DeepSeek/Gemini.

    ``agent_session`` — значение заголовка ``x-agent-session`` для бэкенда
    ``free_deepseek`` (локальный прокси FreeDeepseekAPI,
    https://github.com/dekrezz/FreeDeepseekAPI). Если не задан — берётся из
    конфигурации ``free_deepseek`` (``FREE_DEEPSEEK_SESSION``, по умолчанию
    ``npazs-main``). Остальные бэкенды заголовок игнорируют.
    """
    backend_name = (backend or '').strip().lower() or 'kilo_gateway'
    if stop_event and stop_event.is_set():
        if log_callback:
            log_callback(f"  Запрос к {backend_name} отменён", 'warning')
        return None
    if not model or not model.strip():
        model = DEFAULT_KILO_GATEWAY_MODEL
    else:
        model = model.strip()
    if not base_url:
        base_url = DEFAULT_KILO_GATEWAY_URL
    base_url = base_url.rstrip('/')
    if log_callback:
        log_callback(f"  Запрос к {backend_name} (модель: {model})", 'info')
        input_content = _extract_prompt_inputs(prompt)
        if input_content:
            log_callback(f"<environment_details>\n  ВХОДНЫЕ ДАННЫЕ (полностью):\n{input_content}\n</environment_details>", 'input')
        else:
            log_callback("  (Входные данные не найдены в промпте)", 'warning')
        log_callback(f"  Параметры: temperature={extra_options.get('temperature', 0.0) if extra_options else 0.0}, top_p={extra_options.get('top_p', 0.1) if extra_options else 0.1}", 'info')
    temperature = extra_options.get("temperature", 0.0) if extra_options else 0.0
    top_p = extra_options.get("top_p", 0.1) if extra_options else 0.1
    url = f"{base_url}/chat/completions"
    # OpenAI-совместимые бэкенды принимают и bare-host, и base с /v1:
    # прокси FreeDeepseekAPI слушает на http://127.0.0.1:9655 (эндпоинты
    # под /v1/*), поэтому bare-host дополняем суффиксом /v1.
    if backend_name in ('free_deepseek', 'qwen2api') and not url.rstrip('/').endswith('/v1/chat/completions'):
        url = f"{base_url}/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if backend_name == 'free_deepseek':
        session = (agent_session or '').strip() if agent_session else ''
        if not session:
            try:
                from npazs.config.ollama import get_free_deepseek_config
                session = str(get_free_deepseek_config().get('session') or '').strip()
            except Exception:  # noqa: BLE001 — любой сбой → дефолтная сессия
                session = ''
        headers["x-agent-session"] = session or 'npazs-main'
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "top_p": top_p,
    }
    # Тело шлём UTF-8-байтами сами: requests.post(json=...) сериализует с
    # ensure_ascii=True, а кириллица в таком виде занимает 6 байт вместо 2
    # (``Р`` → ``\u0420``) — промпт stage 3 раздувался с 87.7 KB до 124.3 KiB
    # при пороге капчи Aliyun WAF ~128 KiB (см. WAF_BODY_LIMIT_BYTES).
    body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
    if log_callback:
        log_callback(f"  Тело запроса: {len(body) / 1024:.1f} KiB", 'info')
        size_hint = waf_body_size_hint(len(body), backend_name)
        if size_hint:
            log_callback(size_hint, 'warning')
    attempt = 0
    while True:
        try:
            response = requests.post(url, data=body, headers=headers, timeout=900)
            raw_text = response.text[:500]
            # Дневной лимит модели через qwen2api: OpenAI-путь доставляет его как
            # HTTP 429 (insufficient_quota), а в streaming/agent-пути статус может
            # быть 200 с error-frame внутри тела. Оба случая — квота, а не
            # временный сбой: ретраи и диалог «Повторить?» только расходуют лимит.
            if response.status_code == 429:
                err = f"HTTP 429: {raw_text}"
                if is_quota_exhausted_error(backend_name, err):
                    raise QuotaExhaustedError(err, backend=backend_name, model=model)
                raise Exception(err)
            elif response.status_code != 200:
                if response.status_code == 403 and log_callback:
                    log_callback(
                        f"  {backend_name} инфраструктурная ошибка: HTTP 403 (доступ запрещён)",
                        'error',
                    )
                err = f"HTTP {response.status_code}: {raw_text}"
                if is_quota_exhausted_error(backend_name, err):
                    raise QuotaExhaustedError(err, backend=backend_name, model=model)
                raise Exception(err)
            data = response.json()
            choices = data.get("choices", [])
            if not choices:
                err = f'{backend_name} вернул пустой ответ; error={data.get("error", "")}'
                if is_quota_exhausted_error(backend_name, err):
                    raise QuotaExhaustedError(err, backend=backend_name, model=model)
                raise ValueError(err)
            answer = choices[0].get("message", {}).get("content", "").strip()
            if not answer:
                raise ValueError(f"{backend_name} вернул пустой текст")
            if log_callback:
                log_callback(f"  Получен ответ (длина {len(answer)} символов):\n{answer}", 'result')
            cleaned_answer = strip_thinking_tags(answer)
            if cleaned_answer != answer:
                if log_callback:
                    log_callback(f"  ⚠ Обнаружены и удалены <thinking>-теги из ответа ИИ (было {len(answer)} симв. → стало {len(cleaned_answer)} симв.)", 'warning')
                answer = cleaned_answer
            # Пост-анализ сам разбирает и валидирует вердикт. repair_json=False
            # сохраняет для него исходный ответ, включая возможный хвост.
            if not repair_json:
                return answer
            repaired_answer = _repair_json_answer(answer, log_callback)
            if repaired_answer is None:
                # Валидный JSON обязателен: ответ нельзя «пропускать» с
                # продолжением программно — поднимаем ошибку, чтобы запрос
                # повторился в общем цикле ретраев (кейс openrouter/free:
                # «User Safety: safe» вместо JSON → изменение уходило в FAILED).
                raise InvalidJsonAnswerError(_invalid_json_reason(answer))
            return repaired_answer
        except Exception as e:
            if isinstance(e, QuotaExhaustedError) or is_quota_exhausted_error(backend_name, e):
                # Дневная квота модели исчерпана: никаких повторов — сразу
                # сообщаем пользователю и предлагаем сменить модель/бэкенд.
                # Квота МОДЕЛЬНАЯ (qwen2api), поэтому смена модели того же
                # провайдера полностью решает проблему.
                if log_callback:
                    log_callback(f"  {backend_name} лимит исчерпан: {e}", 'error')
                    hint = quota_exhausted_hint(backend_name, e, model)
                    if hint:
                        log_callback(hint, 'warning')
                retry_cb = _constants._user_retry_callback
                if retry_cb is not None and not (stop_event and stop_event.is_set()):
                    if log_callback:
                        log_callback(
                            "  Все попытки исчерпаны. Запрос к пользователю...",
                            'warning')
                    outcome, switched = _resolve_user_retry(
                        retry_cb, backend_name, model, base_url, api_key,
                        agent_session, prompt, extra_options, log_callback,
                        change_info, stop_event, last_error=str(e),
                        reason='quota',
                    )
                    if outcome == 'resume':
                        if switched is not None:
                            (backend_name, model, base_url, api_key,
                             agent_session, url, headers, body, temperature,
                             top_p) = switched
                            if backend_name not in HTTP_BACKENDS:
                                # Переключились на не-HTTP бэкенд (ollama) —
                                # переадресуем запрос в его собственный клиент.
                                return ask_ollama(
                                    prompt, model, log_callback, extra_options,
                                    stop_event, max_retries, retry_delay,
                                    backoff_factor, change_info,
                                    backend=backend_name,
                                    kilo_gateway_url=base_url, api_key=api_key,
                                    agent_session=agent_session,
                                    repair_json=repair_json)
                        attempt = 0
                        continue
                    # 'stop' — пользователь сам нажал «Остановить».
                    return None
                # Диалога нет (headless) или он недоступен: прогон НЕ
                # останавливаем — это изменение просто не выполнится.
                if log_callback:
                    log_callback(
                        "  Изменение пропущено: дневной лимит модели исчерпан. "
                        "Прогон продолжается — смените провайдера/модель, чтобы "
                        "следующие изменения выполнялись.",
                        'warning',
                    )
                return None
            attempt += 1
            if log_callback:
                msg = f"  {backend_name} ошибка (попытка {attempt}/{max_retries}): {e}"
                if change_info:
                    msg += f" [изменение: {change_info}]"
                log_callback(msg, 'error')
                hint = tls_interception_hint(backend_name, e)
                if hint:
                    log_callback(hint, 'warning')
                waf_hint = waf_challenge_hint(backend_name, e)
                if waf_hint:
                    log_callback(waf_hint, 'warning')
                    size_hint = waf_body_size_hint(len(body), backend_name)
                    if size_hint:
                        log_callback(size_hint, 'warning')
            if attempt < max_retries:
                wait = retry_wait_seconds(
                    attempt, retry_delay, backoff_factor, backend_name, e,
                    base_url=base_url, api_key=api_key, log_callback=log_callback,
                )
                if log_callback:
                    if wait > 0:
                        log_callback(f"  Повтор через {wait} секунд...", 'info')
                    else:
                        log_callback(
                            "  Повтор без паузы: прокси ротирует на следующий аккаунт",
                            'info')
                if stop_event and stop_event.is_set():
                    if log_callback:
                        log_callback("  Запрос отменён во время ожидания повторной попытки", 'warning')
                    return None
                for _ in range(wait):
                    if stop_event and stop_event.is_set():
                        return None
                    time.sleep(1)
                continue
            else:
                retry_cb = _constants._user_retry_callback
                if retry_cb is not None and not (stop_event and stop_event.is_set()):
                    if log_callback:
                        log_callback(f"  Все попытки ({max_retries}) исчерпаны. Запрос к пользователю...", 'warning')
                    outcome, switched = _resolve_user_retry(
                        retry_cb, backend_name, model, base_url, api_key,
                        agent_session, prompt, extra_options, log_callback,
                        change_info, stop_event, last_error=str(e),
                        reason='failures', max_retries=max_retries,
                    )
                    if outcome == 'resume':
                        if switched is not None:
                            (backend_name, model, base_url, api_key,
                             agent_session, url, headers, body, temperature,
                             top_p) = switched
                            if backend_name not in HTTP_BACKENDS:
                                # Переключились на не-HTTP бэкенд (ollama) —
                                # переадресуем запрос в его собственный клиент.
                                return ask_ollama(
                                    prompt, model, log_callback, extra_options,
                                    stop_event, max_retries, retry_delay,
                                    backoff_factor, change_info,
                                    backend=backend_name,
                                    kilo_gateway_url=base_url, api_key=api_key,
                                    agent_session=agent_session,
                                    repair_json=repair_json)
                        attempt = 0
                        continue
                    # 'stop' — останавливаем только по явному выбору пользователя.
                    return None
                else:
                    if log_callback:
                        log_callback(f"  Все попытки ({max_retries}) исчерпаны, callback не установлен", 'error')
                    return None


def _resolve_http_credentials(backend: str) -> dict:
    """Разрешить base_url и api_key для HTTP-бэкенда из констант.

    Используется как fallback, когда GUI не передаёт URL/key явно
    (например, вызов из verify/runner.py или post_analysis.py).
    Для ``free_deepseek`` дополнительно возвращается ``session``
    (``FREE_DEEPSEEK_SESSION`` → ``x-agent-session``).
    """
    defn = HTTP_BACKEND_DEFS.get(backend)
    if defn is None:
        from npazs.config.ollama import get_active_llm_config
        config = get_active_llm_config()
        resolved = {
            'base_url': config.get('base_url', DEFAULT_KILO_GATEWAY_URL),
            'api_key': config.get('api_key', ''),
        }
        if backend == 'free_deepseek':
            resolved['session'] = str(config.get('session') or 'npazs-main')
        return resolved
    resolved = {
        'base_url': defn['base_url'],
        'api_key': defn['api_key'],
    }
    if backend == 'free_deepseek':
        resolved['session'] = str(defn.get('session') or 'npazs-main')
    return resolved


def ask_ollama(prompt, model, log_callback, extra_options=None, stop_event=None, max_retries=3, retry_delay=15, backoff_factor=1, change_info=None, backend="ollama", kilo_gateway_url=None, api_key=None, agent_session=None, repair_json=True):
    # --- HTTP-бэкенды: kilo_gateway, cline, openrouter, cerebras, ---
    # --- mistral, gemini, free_deepseek (прокси FreeDeepseekAPI), qwen2api ---
    # Все они используют OpenAI-compatible /chat/completions, поэтому
    # маршрутизируются через ask_kilo_gateway с соответствующим base_url/api_key.
    if backend in HTTP_BACKENDS:
        # Если URL/api_key не переданы явно, подставляем из настроек.
        resolved = _resolve_http_credentials(backend) if (not kilo_gateway_url or not api_key) else {}
        if not kilo_gateway_url:
            kilo_gateway_url = resolved.get('base_url', '')
        # free_deepseek: PROXY_API_KEY опционален — пустой ключ НЕ подменяем
        # дефолтом, иначе requests ушёл бы с чужим Bearer. Остальные бэкенды —
        # как раньше: пустой ключ добирается из настроек.
        if not api_key and backend != 'free_deepseek':
            api_key = resolved.get('api_key', '')
        if backend == 'free_deepseek' and not (agent_session or '').strip():
            agent_session = resolved.get('session', '') if resolved else None
            if not (agent_session or '').strip():
                try:
                    from npazs.config.ollama import get_free_deepseek_config
                    agent_session = get_free_deepseek_config().get('session', '')
                except Exception:  # noqa: BLE001 — любой сбой → дефолтная сессия
                    agent_session = 'npazs-main'
        return ask_kilo_gateway(prompt, model, log_callback, extra_options, stop_event, max_retries, retry_delay, backoff_factor, change_info, kilo_gateway_url, api_key, backend=backend, agent_session=agent_session, repair_json=repair_json)
    if stop_event and stop_event.is_set():
        if log_callback:
            log_callback("  Запрос к Ollama отменён", 'warning')
        return None
    if not model or not model.strip():
        try:
            resp = requests.get(f"{_ollama_base_url}/api/tags", timeout=2)
            if resp.status_code == 200:
                data = resp.json()
                models = [m['name'] for m in data.get('models', [])]
                if models:
                    model = models[0]
                else:
                    model = DEFAULT_OLLAMA_MODEL
            else:
                model = DEFAULT_OLLAMA_MODEL
        except Exception:
            model = DEFAULT_OLLAMA_MODEL
    else:
        model = model.strip()
    if log_callback:
        log_callback(f"  Запрос к Ollama (модель: {model})", 'info')
        tags = ['input_data', 'input_document', 'change_doc', 'change_json', 'input_json', 'date_pub', 'law_number', 'article_number', 'doc_text', 'change_npa_number', 'change_date_pub', 'change_date_effective', 'valid_from']
        input_parts = []
        for tag in tags:
            pattern = rf'<({tag})>(.*?)</\1>'
            matches = re.findall(pattern, prompt, re.DOTALL | re.IGNORECASE)
            for m in matches:
                input_parts.append(f"<{m[0]}>\n{m[1]}\n</{m[0]}>")
        if input_parts:
            input_content = '\n'.join(input_parts).strip()
            log_callback(f"<environment_details>\n  ВХОДНЫЕ ДАННЫЕ (полностью):\n{input_content}\n</environment_details>", 'input')
        else:
            log_callback("  (Входные данные не найдены в промпте)", 'warning')
        log_callback(f"  Параметры: temperature={extra_options.get('temperature', 0.0) if extra_options else 0.0}, top_p={extra_options.get('top_p', 0.1) if extra_options else 0.1}", 'info')
    temperature = extra_options.get("temperature", 0.0) if extra_options else 0.0
    top_p = extra_options.get("top_p", 0.1) if extra_options else 0.1
    url = f"{_ollama_base_url}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "top_p": top_p,
        }
    }
    attempt = 0
    while True:
        try:
            response = requests.post(url, json=payload, timeout=900)
            if response.status_code != 200:
                if response.status_code == 403:
                    # Облако Ollama отклоняет: нет входа на ollama.com.
                    raise _OllamaAuthError(
                        f"HTTP 403 (доступ запрещён): модель {model} требует "
                        f"авторизации ollama.com. {OLLAMA_SIGNIN_HINT}"
                    )
                raise Exception(f"HTTP {response.status_code}: {response.text}")
            data = response.json()
            answer = data.get("response", "").strip()
            if not answer:
                raise ValueError("Ollama вернул пустой текст")
            if log_callback:
                log_callback(f"  Получен ответ (длина {len(answer)} символов):\n{answer}", 'result')
            cleaned_answer = strip_thinking_tags(answer)
            if cleaned_answer != answer:
                if log_callback:
                    log_callback(f"  ⚠ Обнаружены и удалены <thinking>-теги из ответа ИИ (было {len(answer)} симв. → стало {len(cleaned_answer)} симв.)", 'warning')
                answer = cleaned_answer
            if not repair_json:
                return answer
            repaired_answer = _repair_json_answer(answer, log_callback)
            if repaired_answer is None:
                # Валидный JSON обязателен — повторяем запрос, а не принимаем
                # мусорный ответ (см. InvalidJsonAnswerError).
                raise InvalidJsonAnswerError(_invalid_json_reason(answer))
            return repaired_answer
        except _OllamaAuthError as e:
            # Нет авторизации: повторы бесполезны до `ollama signin`.
            if log_callback:
                msg = f"  Ollama авторизация не пройдена: {e}"
                if change_info:
                    msg += f" [изменение: {change_info}]"
                log_callback(msg, 'error')
            _offer_ollama_signin_once()
            return None
        except Exception as e:
            attempt += 1
            if log_callback:
                msg = f"  Ollama ошибка (попытка {attempt}/{max_retries}): {e}"
                if change_info:
                    msg += f" [изменение: {change_info}]"
                log_callback(msg, 'error')
            if attempt < max_retries:
                wait = retry_delay * (backoff_factor ** (attempt - 1))
                if log_callback:
                    log_callback(f"  Повтор через {wait} секунд...", 'info')
                if stop_event and stop_event.is_set():
                    if log_callback:
                        log_callback("  Запрос отменён во время ожидания повторной попытки", 'warning')
                    return None
                for _ in range(wait):
                    if stop_event and stop_event.is_set():
                        return None
                    time.sleep(1)
                continue
            else:
                retry_cb = _constants._user_retry_callback
                if retry_cb is not None and not (stop_event and stop_event.is_set()):
                    if log_callback:
                        log_callback(f"  Все попытки ({max_retries}) исчерпаны. Запрос к пользователю...", 'warning')
                    outcome = None
                    state = None
                    for _ask in range(SWITCH_ASK_LIMIT):
                        message = (
                            f"Модель {model} не отвечает: {max_retries} "
                            f"попытки подряд неудачны.\n"
                            f"Последняя ошибка: {e}"
                            + (f"\n\nИзменение: {change_info}" if change_info else "")
                            + "\n\nСмените провайдера? Нажмите «Переключить бэкенд» "
                            "и выберите другой бэкенд или модель в главном окне, "
                            "либо повторите запрос ещё раз."
                        )
                        user_choice = _ask_retry_choice(retry_cb, message)
                        if user_choice == 'retry':
                            if log_callback:
                                log_callback("  Пользователь выбрал повтор", 'info')
                            outcome, state = 'resume', None
                            break
                        if user_choice == 'switch':
                            state = _reapply_ollama_after_switch(
                                backend, model, log_callback)
                            if state is not None:
                                outcome = 'resume'
                                break
                            # Ничего не изменилось — спрашиваем ещё раз.
                            continue
                        if log_callback:
                            log_callback("  Пользователь остановил процесс", 'warning')
                        if stop_event is not None:
                            stop_event.set()
                        return None
                    if outcome == 'resume':
                        if state is not None:
                            (backend, model, _url, _key, redirect) = state
                            if redirect:
                                if not _url:
                                    # URL не пришёл из GUI — берём из .env/констант.
                                    _creds = _resolve_http_credentials(backend)
                                    _url = _creds.get('base_url') or ''
                                    _key = _key or _creds.get('api_key') or ''
                                return ask_kilo_gateway(
                                    prompt, model, log_callback, extra_options,
                                    stop_event, max_retries, retry_delay,
                                    backoff_factor, change_info,
                                    _url, _key, backend=backend,
                                    agent_session=agent_session,
                                    repair_json=repair_json)
                            payload["model"] = model
                        attempt = 0
                        continue
                    if log_callback:
                        log_callback(
                            f"  Провайдер так и не изменён после "
                            f"{SWITCH_ASK_LIMIT} попыток — это изменение будет "
                            "помечено FAILED, прогон продолжается.",
                            'warning')
                    return None
                else:
                    if log_callback:
                        log_callback(f"  Все попытки ({max_retries}) исчерпаны, callback не установлен", 'error')
                    return None
