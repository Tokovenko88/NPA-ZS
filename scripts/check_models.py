"""Проверка: какие модели реально отдаёт каждый провайдер из .env NPA-ZS.

Строго: base_url/api_key/default_model берутся из E:\\NPA-ZS\\.env,
списки моделей — только из живых GET /models (или /api/tags для Ollama).
Никаких захардкоженных списков здесь нет.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from npazs.config.settings import get_settings, ENV_PATH
from npazs import llm_models as M

s = get_settings()
print(f".env: {ENV_PATH}")
print(f"LLM_BACKEND={s.llm_backend!r} POST_ANALYSIS_BACKEND={s.post_analysis_backend!r}")
print("=" * 100)

FETCHERS = {
    'ollama': ('OLLAMA', s.ollama_base_url, '', M.fetch_ollama_models),
    'kilo_gateway': ('KILO', s.kilo_gateway_base_url, '***' if s.kilo_gateway_api_key else '', None),
    'cline': ('CLINE', s.cline_base_url, '***' if s.cline_api_key else '', M.fetch_cline_models),
    'openrouter': ('OPENROUTER', s.openrouter_base_url, '***' if s.openrouter_api_key else '', M.fetch_openrouter_free_models),
    'cerebras': ('CEREBRAS', s.cerebras_base_url, '***' if s.cerebras_api_key else '', M.fetch_cerebras_models),
    'mistral': ('MISTRAL', s.mistral_base_url, '***' if s.mistral_api_key else '', M.fetch_mistral_models),
    'gemini': ('GEMINI', s.gemini_base_url, '***' if s.gemini_api_key else '', M.fetch_gemini_models),
    'free_deepseek': ('FREE_DEEPSEEK', s.free_deepseek_base_url, '', None),
    'qwen2api': ('QWEN2API', s.qwen2api_base_url, '***' if s.qwen2api_api_key else '', None),
}
DEFAULTS = {
    'ollama': s.ollama_base_url and s.default_ollama_model if hasattr(s, 'default_ollama_model') else '',
    'kilo_gateway': s.kilo_gateway_default_model,
    'cline': s.cline_default_model,
    'openrouter': s.openrouter_default_model,
    'cerebras': s.cerebras_default_model,
    'mistral': s.mistral_default_model,
    'gemini': s.gemini_default_model,
    'free_deepseek': s.free_deepseek_default_model,
    'qwen2api': s.qwen2api_default_model,
}

for backend, (prefix, url, key, fetcher) in FETCHERS.items():
    dflt = DEFAULTS.get(backend)
    print(f"\n[{backend}] base_url={url!r} key={'yes' if key else 'NO'} default_model={dflt!r}")
    try:
        if backend == 'ollama':
            models = M.fetch_ollama_models(url)
        elif backend == 'kilo_gateway':
            models = M.fetch_kilo_gateway_free_models(url, getattr(s, 'kilo_gateway_api_key', ''))
        elif backend == 'free_deepseek':
            models = M.fetch_free_deepseek_models(url, '')
        elif backend == 'qwen2api':
            models = M.fetch_qwen2api_models(url, getattr(s, 'qwen2api_api_key', ''))
        elif backend in ('cline', 'openrouter'):
            models = fetcher(getattr(s, f'{backend}_api_key', ''))
        else:
            models = fetcher(getattr(s, f'{backend}_api_key', ''))
        ok = 'OK live' if models else 'EMPTY live'
        shown = models if len(models) <= 30 else models[:30] + [f'... total {len(models)}']
        print(f"  {ok}: {shown}")
        if dflt and models and dflt not in models:
            print(f"  !!! default_model {dflt!r} NOT in live list")
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")
