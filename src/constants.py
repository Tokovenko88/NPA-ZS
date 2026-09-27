"""Общие константы NPA-ZS: пути, промпты, словари типов, модели ИИ.

Модуль — прямой наследник ``npa_processor/constants.py``. Отличия:

* все пути времени выполнения ведут в ``data/`` (а не в каталог пакета);
* промпты читаются из ``data/prompts/prompt_{1..4}.md`` (канонические имена);
* каталоги создаются лениво, чтобы импорт модуля не падал на чистой копии.

Публичный API (имена сохранены ради обратной совместимости с исходным кодом):
``settings``, ``PROMPTS_DIR``, ``LAST_PATHS_FILE``, ``STAGE_ANSWERS_FILE``,
``LAST_RUN_LOG_FILE``, ``DEBUG_RUNS_DIR``, ``DEFAULT_EXTRA_OPTIONS``,
``TYPE_TO_RUSSIAN``, ``PLURAL_TO_SINGULAR``, ``PROMPT_1``..``PROMPT_4``,
``load_prompt_from_file``, ``save_last_run_log``.
"""

import os

from npazs.config import get_settings

settings = get_settings()

# --- Пути -------------------------------------------------------------------
# src/constants.py -> src -> <корень проекта>
PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(PACKAGE_DIR)

DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
PROMPTS_DIR = os.path.join(DATA_DIR, 'prompts')
INPUT_DIR = os.path.join(DATA_DIR, 'input')
OUTPUT_DIR = os.path.join(DATA_DIR, 'output')
STAGE_ANSWERS_DIR = os.path.join(DATA_DIR, 'stage_answers')
WORK_TOOLS_DIR = os.path.join(DATA_DIR, 'work_tools')
DEBUG_RUNS_DIR = os.path.join(DATA_DIR, 'debug_runs')
LOGS_DIR = os.path.join(DATA_DIR, 'logs')
BASE_DIR = os.path.join(DATA_DIR, 'base')
BASE_LAW_DIR = os.path.join(BASE_DIR, 'law')
BASE_RESOLUTION_DIR = os.path.join(BASE_DIR, 'resolution')

# --- Внешняя (рабочая) база JSON --------------------------------------------
# Рабочая база JSON лежит в том же каталоге, что и папка проекта
# (<родитель проекта>/Base), поэтому путь ВЫЧИСЛЯЕТСЯ от PROJECT_ROOT и не
# привязан к конкретному диску (D:\, E:\, ...). При необходимости путь можно
# переопределить переменной окружения NPAZS_BASE_DIR.
PROJECT_PARENT_DIR = os.path.dirname(PROJECT_ROOT)
PRODUCTION_BASE_DIR = (
    os.environ.get('NPAZS_BASE_DIR') or os.path.join(PROJECT_PARENT_DIR, 'Base')
)
PRODUCTION_BASE_LAW_DIR = os.path.join(PRODUCTION_BASE_DIR, 'law')
PRODUCTION_BASE_RESOLUTION_DIR = os.path.join(PRODUCTION_BASE_DIR, 'resolution')

# Историческое имя: каталог, где лежали файлы состояния.
CONFIG_DIR = PACKAGE_DIR

# Файлы состояния времени выполнения.
LAST_PATHS_FILE = os.path.join(LOGS_DIR, 'last_paths.json')
STAGE_ANSWERS_FILE = os.path.join(STAGE_ANSWERS_DIR, 'stage_answers.json')
LAST_RUN_LOG_FILE = os.path.join(LOGS_DIR, 'last_run.log')

_RUNTIME_DIRS = (
    INPUT_DIR,
    OUTPUT_DIR,
    STAGE_ANSWERS_DIR,
    WORK_TOOLS_DIR,
    DEBUG_RUNS_DIR,
    LOGS_DIR,
)


def ensure_runtime_dirs():
    """Создать каталоги времени выполнения (идемпотентно, не бросает исключений)."""
    for path in _RUNTIME_DIRS:
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            pass


ensure_runtime_dirs()

# --- Параметры генерации ----------------------------------------------------
DEFAULT_EXTRA_OPTIONS = {
    "temperature": 0.0,
    "top_p": 0.1,
}

# --- Словари типов структурных элементов ------------------------------------
TYPE_TO_RUSSIAN = {
    'article': 'Статья',
    'part': 'Часть',
    'point': 'Пункт',
    'subpoint': 'Подпункт',
    'chapter': 'Глава',
    'section': 'Раздел',
    'appendix': 'Приложение',
    'paragraph': 'Абзац',
    'preamble': 'Преамбула',
    'structured_table': 'Таблица',
}

PLURAL_TO_SINGULAR = {
    'части': 'часть',
    'пункты': 'пункт',
    'подпункты': 'подпункт',
    'статьи': 'статья',
    'главы': 'глава',
    'разделы': 'раздел',
    'приложения': 'приложение',
}

# --- Бэкенды ИИ -------------------------------------------------------------
# Поддерживаемые HTTP-бэкенды (все используют OpenAI-compatible /chat/completions)
# и локальный Ollama. Список здесь — единственный источник истины для
# SUPPORTED_BACKENDS / DEFAULT_BACKEND / метаданных бэкендов.
DEFAULT_OLLAMA_MODEL = "gpt-oss:20b-cloud"
_ollama_base_url = settings.ollama_base_url
OLLAMA_MODELS_WHITELIST = {
    "gemma4:31b",
    "gpt-oss:120b",
    "gpt-oss:20b",
    "gpt-oss:20b-cloud",
    "nemotron-3-nano:30b",
    "nemotron-3-super",
    "nemotron-3-ultra",
}

# --- HTTP-бэкенды -----------------------------------------------------------
# Каждая запись: (default_base_url, settings_переменные, free-модели, default_model)
HTTP_BACKEND_DEFS = {
    'kilo_gateway': {
        'base_url': settings.kilo_gateway_base_url,
        'api_key': settings.kilo_gateway_api_key,
        'default_model': settings.kilo_gateway_default_model or 'Tencent: Hy3 (free)',
        'free_models': {
            "StepFun: Step 3.7 Flash (free)",
            "Tencent: Hy3 (free)",
            "Poolside: Laguna S 2.1 (free)",
            "Meituan: LongCat 2.0 (free)",
            "Auto Free",
        },
    },
    'cline': {
        'base_url': settings.cline_base_url or 'https://api.cline.bot/api/v1',
        'api_key': settings.cline_api_key,
        'default_model': settings.cline_default_model or 'openrouter/free',
        # Fallback-снимок актуальных free-моделей Cline API (GET /models отдаёт
        # их с суффиксом ':free'; 'openrouter/free' — авто-роутер по free).
        # Основной источник списка — сам API (npazs.llm_models.fetch_cline_models),
        # этот набор используется только если API недоступен.
        'free_models': {
            'cohere/north-mini-code:free',
            'dots-studio/dots-3-note-preview:free',
            'google/gemma-4-26b-a4b-it:free',
            'google/gemma-4-31b-it:free',
            'inclusionai/ling-3.0-flash-fin:free',
            'inclusionai/ling-3.0-flash-sante:free',
            'inclusionai/ling-3.0-flash-vl:free',
            'liquid/lfm-2.5-2.6b:free',
            'nex-agi/nex-n2.5-mini:free',
            'nex-agi/nex-n2.5-pro:free',
            'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free',
            'nvidia/nemotron-3-super-120b-a12b:free',
            'nvidia/nemotron-3-ultra-550b-a55b:free',
            'nvidia/nemotron-3.5-content-safety:free',
            'nvidia/nemotron-3.5-lightning:free',
            'openrouter/free',
            'poolside/laguna-s-2.1:free',
            'poolside/laguna-xs-2.1:free',
            'thinkingmachines/inkling-small:free',
            'thinkingmachines/inkling:free',
            'z-ai/glm-5.2:free',
            # DeepSeek V4.1-Flash (через FreeDeepseekAPI):
            'deepseek-v4-flash',
            'deepseek-flash',
            'deepseek-v4-pro',
            'deepseek-v4-flash-thinking',
            'deepseek-v4-flash-search',
            'deepseek-v4-flash-thinking-search',
        },
    },
    'openrouter': {
        'base_url': settings.openrouter_base_url or 'https://openrouter.ai/api/v1',
        'api_key': settings.openrouter_api_key,
        'default_model': settings.openrouter_default_model or 'openrouter/free',
        'free_models': {
            'google/gemini-2.5-flash:free',
            'google/gemini-2.5-pro:free',
            'meta-llama/llama-4-maverick:free',
            'meta-llama/llama-4-scout:free',
            'nvidia/nemotron-3-ultra-550b-a55b:free',
            'minimax/minimax-m3:free',
            'openrouter/free',
        },
    },
    'cerebras': {
        'base_url': settings.cerebras_base_url or 'https://api.cerebras.ai/v1',
        'api_key': settings.cerebras_api_key,
        # Cerebras — платный pay-per-token, но с generous free tier'ом при
        # регистрации (без карты), контекст до 128K. Fallback-список —
        # популярные модели Cerebras (Llama 3.x, Qwen, Gemma).
        'default_model': settings.cerebras_default_model or 'llama3.1-8b',
        'free_models': {
            'llama3.1-8b',
            'llama3.1-70b',
            'llama3.3-70b',
            'qwen-3-32b',
            'qwen-3-235b-a22b-instruct-2507',
            'gemma-3-12b-it',
        },
    },
    'mistral': {
        'base_url': settings.mistral_base_url or 'https://api.mistral.ai/v1',
        'api_key': settings.mistral_api_key,
        # Mistral AI — платный pay-per-token, но с free tier'ом при регистрации
        # (без карты), контекст до 128K. Fallback-список — популярные модели.
        'default_model': settings.mistral_default_model or 'mistral-large-latest',
        'free_models': {
            'mistral-large-latest',
            'mistral-small-latest',
            'mistral-medium-latest',
            'pixtral-large-latest',
            'ministral-8b-latest',
        },
    },
    'gemini': {
        'base_url': settings.gemini_base_url or 'https://generativelanguage.googleapis.com/v1beta/openai',
        'api_key': settings.gemini_api_key,
        # Gemini имеет бесплатный тариф (1500 запросов/день, 15/минуту без карты).
        # Fallback-список — актуальные text-модели (image/audio/TTS/ embeddings
        # не нужны пайплайну, поэтому они в список не входят).
        'default_model': settings.gemini_default_model or 'gemini-2.5-flash',
        'free_models': {
            'gemini-2.0-flash',
            'gemini-2.5-flash',
            'gemini-2.5-pro',
            'gemini-3.5-flash',
            'gemini-3.5-flash-lite',
            'gemini-3.6-flash',
            'gemini-3.7-flash',
            'gemini-3.1-flash-lite',
            'gemini-3-flash-preview',
        },
    },
    'free_deepseek': {
        # Локальный прокси FreeDeepseekAPI (https://github.com/dekrezz/FreeDeepseekAPI):
        # OpenAI-compatible /chat/completions поверх web-сессии chat.deepseek.com.
        # Запуск: `npm run auth && npm start` в каталоге прокси
        # (по умолчанию http://127.0.0.1:9655, base_url с суффиксом /v1).
        # PROXY_API_KEY опционален; параллельные клиенты обязаны использовать
        # разные x-agent-session (один web-логин = один in-flight чат).
        'base_url': settings.free_deepseek_base_url or 'http://127.0.0.1:9655/v1',
        'api_key': settings.free_deepseek_api_key,
        'default_model': settings.free_deepseek_default_model or 'deepseek-v4-flash',
        'session': settings.free_deepseek_session or 'npazs-main',
        'free_models': {
            'deepseek-v4-flash',
            'deepseek-flash',
            'deepseek-v4-pro',
            'deepseek-v4-flash-thinking',
            'deepseek-v4-flash-search',
            'deepseek-v4-flash-thinking-search',
        },
    },
    'qwen2api': {
        # Локальный прокси Qwen2API / Qwen-Proxy
        # (https://github.com/Rfym21/Qwen2API): OpenAI-compatible /v1/*
        # поверх аккаунтов chat.qwen.ai (и CLI-эндпоинт /cli/v1).
        # Запуск: `bun src/server.js` (или npm start) в каталоге прокси;
        # по умолчанию http://127.0.0.1:3000 (см. SERVICE_PORT).
        # API_KEY прокси обязателен (env API_KEY прокси) — продублируйте
        # его в QWEN2API_API_KEY; аккаунты добавляются через веб-панель.
        'base_url': settings.qwen2api_base_url or 'http://127.0.0.1:3000/v1',
        'api_key': settings.qwen2api_api_key,
        'default_model': settings.qwen2api_default_model or 'qwen3-coder-plus',
        'free_models': {
            'qwen3-coder-plus',
            'qwen3-coder-flash',
            'coder-model',
            'qwen3.5-plus',
            'Qwen3.6-Plus',
            'Qwen3.6-Plus-thinking',
            'Qwen3.6-Plus-search',
        },
    },
}

# Backward-compatible aliases (old code и тесты ссылаются на эти имена).
DEFAULT_KILO_GATEWAY_URL = HTTP_BACKEND_DEFS['kilo_gateway']['base_url']
DEFAULT_KILO_GATEWAY_MODEL = HTTP_BACKEND_DEFS['kilo_gateway']['default_model']
KILO_GATEWAY_FREE_MODELS = HTTP_BACKEND_DEFS['kilo_gateway']['free_models']
DEFAULT_BACKEND = "free_deepseek"

# Набор всех HTTP-бэкендов (все, кроме ollama).
HTTP_BACKENDS = frozenset(HTTP_BACKEND_DEFS.keys())
_user_retry_callback = None

#: Callable set by the GUI to re-read the *current* backend/model/api_key/URL
#: at runtime.  Called by ``ask_kilo_gateway`` when the user chooses to switch
#: provider mid-run so the retry uses the freshly selected backend.
#:  Returns a dict or ``None``.
_settings_provider = None

#: Область действия текущего ``_settings_provider``: '' — основной прогон,
#: 'post' — пост-анализ. GUI берёт её в диалоге смены провайдера, чтобы
#: подсказать менять именно тот бэкенд, который работает прямо сейчас
#: (основной или пост-анализа).
_settings_provider_scope = ''

#: Callable set by the GUI to offer ``ollama signin`` when a cloud request is
#: rejected with HTTP 403 (нет авторизации ollama.com).  Вызывается из
#: ``ask_ollama`` НЕ из рабочего потока напрямую: каждый GUI обязан сам
#: перенести вызов в главный поток Tkinter (root.after / очередь логов).
_ollama_signin_callback = None

# --- Промпты ----------------------------------------------------------------
# Канонические имена файлов в data/prompts/. Вторые элементы — исторические
# имена из E:\NPA-JSON-Processor\03_prompts (fallback при миграции).
PROMPT_FILES = {
    1: ('prompt_1.md', 'prompt_1_revocation_analysis.md'),
    2: ('prompt_2.md', 'prompt_2_dates_analysis.md'),
    3: ('prompt_3.md', 'prompt_3_changes_extraction.md'),
    4: ('prompt_4.md', 'prompt_4_text_processing.md'),
}


def load_prompt_from_file(filename):
    """Прочитать промпт из ``data/prompts``. Вернуть '' если файла нет."""
    path = filename if os.path.isabs(filename) else os.path.join(PROMPTS_DIR, filename)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    return ""


def load_prompt(stage):
    """Прочитать промпт этапа ``stage`` (1..4) с fallback на историческое имя."""
    for name in PROMPT_FILES.get(stage, ()):
        text = load_prompt_from_file(name)
        if text:
            return text
    return ""


def save_last_run_log(log_text):
    """Сохранить лог последнего прогона. Ошибки записи подавляются намеренно."""
    try:
        os.makedirs(os.path.dirname(LAST_RUN_LOG_FILE), exist_ok=True)
        with open(LAST_RUN_LOG_FILE, 'w', encoding='utf-8') as f:
            f.write(log_text)
    except Exception:
        pass


PROMPT_1 = load_prompt(1)
PROMPT_2 = load_prompt(2)
PROMPT_3 = load_prompt(3)
PROMPT_4 = load_prompt(4)
