"""Утилиты для взаимодействия с Ollama API."""

import os
import sys
import re
import json
import time
import requests
import threading
import copy
from datetime import datetime, timedelta, date
import traceback
from collections import defaultdict
from bs4 import BeautifulSoup
import json5
import queue
import difflib
from json_repair import repair_json

import npazs.constants as _constants

from npazs.constants import (
    PROMPTS_DIR,
    LAST_PATHS_FILE,
    STAGE_ANSWERS_FILE,
    DEFAULT_EXTRA_OPTIONS,
    DEFAULT_KILO_GATEWAY_MODEL,
    DEFAULT_KILO_GATEWAY_URL,
    TYPE_TO_RUSSIAN,
    PLURAL_TO_SINGULAR,
    DEFAULT_OLLAMA_MODEL,
    _ollama_base_url,
    load_prompt_from_file,
    PROMPT_1,
    PROMPT_2,
    PROMPT_3,
    PROMPT_4,
)

from npazs.revision.text_utils import strip_thinking_tags


def _ask_invalid_json_action(log_callback, answer, error):
    """Log invalid JSON and skip the AI response; processing continues programmatically."""
    if log_callback:
        log_callback("  Невалидный JSON-ответ ИИ: пропускаем ответ модели и продолжаем программно", 'warning')
    return False


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


def _repair_json_answer(answer, log_callback=None):
    """Repair JSON returned by the model when possible; otherwise skip the response."""
    if not answer:
        return answer
    cleaned = strip_thinking_tags(answer).strip()
    if cleaned.startswith("```json") and cleaned.endswith("```"):
        cleaned = cleaned[7:-3].strip()
    elif cleaned.startswith("```") and cleaned.endswith("```"):
        cleaned = cleaned[3:-3].strip()

    try:
        repaired = repair_json(cleaned)
        json.loads(repaired)
        repaired = json.dumps(json.loads(repaired), ensure_ascii=False)
        if repaired != cleaned and log_callback:
            log_callback(
                f"  ⚠ Автоматически исправлен JSON-ответ ИИ: {len(cleaned)} → {len(repaired)} символов",
                'warning',
            )
        return repaired
    except Exception as exc:
        if log_callback:
            log_callback(f"  ❌ Невалидный JSON-ответ ИИ после repair_json: {exc}", 'error')
        if _ask_invalid_json_action(log_callback, cleaned, exc):
            return cleaned
        return None


def ask_kilo_gateway(prompt, model, log_callback, extra_options=None, stop_event=None, max_retries=5, retry_delay=15, backoff_factor=2, change_info=None, base_url=None, api_key=None):
    if stop_event and stop_event.is_set():
        if log_callback:
            log_callback("  Запрос к Kilo Gateway отменён", 'warning')
        return None
    if not model or not model.strip():
        model = DEFAULT_KILO_GATEWAY_MODEL
    else:
        model = model.strip()
    if not base_url:
        base_url = DEFAULT_KILO_GATEWAY_URL
    base_url = base_url.rstrip('/')
    if log_callback:
        log_callback(f"  Запрос к Kilo Gateway (модель: {model})", 'info')
        input_content = _extract_prompt_inputs(prompt)
        if input_content:
            log_callback(f"<environment_details>\n  ВХОДНЫЕ ДАННЫЕ (полностью):\n{input_content}\n</environment_details>", 'input')
        else:
            log_callback(f"  (Входные данные не найдены в промпте)", 'warning')
        log_callback(f"  Параметры: temperature={extra_options.get('temperature', 0.0) if extra_options else 0.0}, top_p={extra_options.get('top_p', 0.1) if extra_options else 0.1}", 'info')
    temperature = extra_options.get("temperature", 0.0) if extra_options else 0.0
    top_p = extra_options.get("top_p", 0.1) if extra_options else 0.1
    url = f"{base_url}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "top_p": top_p,
    }
    attempt = 0
    while True:
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=900)
            if response.status_code == 429:
                raise Exception(f"HTTP 429 (rate limit): {response.text[:200]}")
            if response.status_code != 200:
                if response.status_code == 403 and log_callback:
                    log_callback("  Kilo Gateway инфраструктурная ошибка: HTTP 403 (доступ запрещён)", 'error')
                raise Exception(f"HTTP {response.status_code}: {response.text}")
            data = response.json()
            choices = data.get("choices", [])
            if not choices:
                raise ValueError("Kilo Gateway вернул пустой ответ")
            answer = choices[0].get("message", {}).get("content", "").strip()
            if not answer:
                raise ValueError("Kilo Gateway вернул пустой текст")
            if log_callback:
                log_callback(f"  Получен ответ (длина {len(answer)} символов):\n{answer}", 'result')
            cleaned_answer = strip_thinking_tags(answer)
            if cleaned_answer != answer:
                if log_callback:
                    log_callback(f"  ⚠ Обнаружены и удалены <thinking>-теги из ответа ИИ (было {len(answer)} симв. → стало {len(cleaned_answer)} симв.)", 'warning')
                answer = cleaned_answer
            repaired_answer = _repair_json_answer(answer, log_callback)
            if repaired_answer is None:
                return None
            return repaired_answer
        except Exception as e:
            attempt += 1
            if log_callback:
                msg = f"  Kilo Gateway ошибка (попытка {attempt}/{max_retries}): {e}"
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
                    user_choice = retry_cb(
                        f"Модель {model} не отвечает после {max_retries} попыток.\n"
                        f"Последняя ошибка: {e}"
                        + (f"\n\nИзменение: {change_info}" if change_info else "")
                        + "\n\nПовторить запрос?"
                    )
                    if user_choice == 'retry':
                        attempt = 0
                        if log_callback:
                            log_callback("  Пользователь выбрал повтор", 'info')
                        continue
                    else:
                        if log_callback:
                            log_callback("  Пользователь остановил процесс", 'warning')
                        if stop_event is not None:
                            stop_event.set()
                        return None
                else:
                    if log_callback:
                        log_callback(f"  Все попытки ({max_retries}) исчерпаны, callback не установлен", 'error')
                    return None


def ask_ollama(prompt, model, log_callback, extra_options=None, stop_event=None, max_retries=5, retry_delay=15, backoff_factor=2, change_info=None, backend="ollama", kilo_gateway_url=None, api_key=None):
    if backend == "kilo_gateway":
        return ask_kilo_gateway(prompt, model, log_callback, extra_options, stop_event, max_retries, retry_delay, backoff_factor, change_info, kilo_gateway_url, api_key)
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
            log_callback(f"  (Входные данные не найдены в промпте)", 'warning')
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
                if response.status_code == 403 and log_callback:
                    log_callback("  Ollama инфраструктурная ошибка: HTTP 403 (доступ запрещён)", 'error')
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
            repaired_answer = _repair_json_answer(answer, log_callback)
            if repaired_answer is None:
                return None
            return repaired_answer
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
                    user_choice = retry_cb(
                        f"Модель {model} не отвечает после {max_retries} попыток.\n"
                        f"Последняя ошибка: {e}"
                        + (f"\n\nИзменение: {change_info}" if change_info else "")
                        + "\n\nПовторить запрос?"
                    )
                    if user_choice == 'retry':
                        attempt = 0
                        if log_callback:
                            log_callback("  Пользователь выбрал повтор", 'info')
                        continue
                    else:
                        if log_callback:
                            log_callback("  Пользователь остановил процесс", 'warning')
                        if stop_event is not None:
                            stop_event.set()
                        return None
                else:
                    if log_callback:
                        log_callback(f"  Все попытки ({max_retries}) исчерпаны, callback не установлен", 'error')
                    return None
