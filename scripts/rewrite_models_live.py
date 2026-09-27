"""Вспомогательный скрипт: перезапись fetch-блоков llm_models.py / gui.

Запуск: python scripts/rewrite_models_live.py
Строгое правило: списки моделей — ТОЛЬКО live из API по base_url из .env.
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
P = ROOT / 'src' / 'llm_models.py'
t = P.read_text(encoding='utf-8')

start = t.find('def fetch_openrouter_free_models')
assert start != -1, 'fetch_openrouter_free_models not found'
head = t[:start]

new_tail = '''def fetch_openrouter_free_models(base_url: str, api_key: str = '') -> list:
    """РЕАЛЬНЫЕ free-модели OpenRouter: ``GET {base_url}/models``, фильтр 'free'.

    ``base_url`` — строго из ``.env`` (``OPENROUTER_BASE_URL``). Ошибки
    не глотаются: уходят в GUI (пустой список + честная ошибка).
    """
    return _fetch_openai_compat_models(base_url, api_key, 'free')


def fetch_cline_models(base_url: str, api_key: str = '') -> list:
    """РЕАЛЬНЫЕ free-модели Cline API: ``GET {base_url}/models``, фильтр 'free'.

    ``base_url`` — строго из ``.env`` (``CLINE_BASE_URL``). Ошибки не глотаются.
    """
    return _fetch_openai_compat_models(base_url, api_key, 'free')


def fetch_cerebras_models(base_url: str, api_key: str = '') -> list:
    """РЕАЛЬНЫЙ список моделей Cerebras: ``GET {base_url}/models`` без фильтра.

    ``base_url`` — строго из ``.env`` (``CEREBRAS_BASE_URL``). Ошибки не глотаются.
    """
    return _fetch_openai_compat_models(base_url, api_key, free_marker=None)


def fetch_mistral_models(base_url: str, api_key: str = '') -> list:
    """РЕАЛЬНЫЙ список моделей Mistral AI: ``GET {base_url}/models`` без фильтра.

    ``base_url`` — строго из ``.env`` (``MISTRAL_BASE_URL``). Ошибки не глотаются.
    """
    return _fetch_openai_compat_models(base_url, api_key, free_marker=None)


def fetch_gemini_models(base_url: str, api_key: str = '') -> list:
    """РЕАЛЬНЫЙ список моделей Gemini: ``GET {base_url}/models`` без фильтра.

    ``base_url`` — строго из ``.env`` (``GEMINI_BASE_URL``). Возвращаются все
    доступные по ключу модели (фильтра по тарифу нет — его знает только
    провайдер/ключ). Ошибки не глотаются.
    """
    return _fetch_openai_compat_models(base_url, api_key, free_marker=None)


def fetch_free_deepseek_models(base_url: str, api_key: str = '') -> list:
    """РЕАЛЬНЫЙ список моделей локального прокси FreeDeepseekAPI.

    ``base_url`` — строго из ``.env`` (``FREE_DEEPSEEK_BASE_URL``, хранится
    с суффиксом ``/v1``; bare-host дополняется до ``/v1``). Без фильтра:
    возвращается всё, что отдал ``GET /v1/models``. Ошибки не глотаются.
    """
    base = (base_url or '').rstrip('/')
    if not base:
        raise RuntimeError('FREE_DEEPSEEK_BASE_URL is not configured in .env')
    # base_url хранится с суффиксом /v1, bare-host дополняем так же.
    root = base if base.endswith('/v1') else f'{base}/v1'
    return _fetch_openai_compat_models(root, api_key, free_marker=None)


def fetch_qwen2api_models(base_url: str, api_key: str = '') -> list:
    """РЕАЛЬНЫЙ список моделей локального прокси Qwen2API (Qwen-Proxy).

    ``base_url`` — строго из ``.env`` (``QWEN2API_BASE_URL``, хранится
    с суффиксом ``/v1``; bare-host дополняется до ``/v1``). Без фильтра:
    список зависит от подключённых аккаунтов chat.qwen.ai.
    Ошибки не глотаются (401 = неверный ``QWEN2API_API_KEY`` в ``.env`` NPA-ZS
    относительно ``API_KEY`` в ``.env`` самого прокси).
    """
    base = (base_url or '').rstrip('/')
    if not base:
        raise RuntimeError('QWEN2API_BASE_URL is not configured in .env')
    # base_url хранится с суффиксом /v1, bare-host дополняем так же.
    root = base if base.endswith('/v1') else f'{base}/v1'
    return _fetch_openai_compat_models(root, api_key, free_marker=None)


def get_free_models_for_backend(backend: str) -> list:
    """Совместимость: выдуманных fallback-списков больше нет — всегда [].

    Оставлена, чтобы старый код не падал с ImportError: при недоступности
    API GUI показывает пустой список + честную ошибку.
    """
    return []
'''
P.write_text(head + new_tail, encoding='utf-8')
print('llm_models.py rewritten OK')
