"""Конфигурация NPA-ZS.

Пакет заменяет исторический модуль ``npa_processor/config.py`` и разделён по
областям ответственности:

* :mod:`npazs.config.settings` — загрузка ``.env``, сводный объект настроек;
* :mod:`npazs.config.db`       — параметры MySQL-базы НПА (``DB_*``);
* :mod:`npazs.config.ollama`   — параметры LLM-бэкендов (Ollama / Kilo Gateway);
* :mod:`npazs.config.env_store` — запись/чтение API-ключей и параметров бэкендов в ``.env``;
* :mod:`npazs.config.modx`     — параметры MODX (SSH и БД сайта).

Обратная совместимость: имена ``get_settings`` и ``get_modx_db_config``
реэкспортируются здесь, поэтому исторический вызов
``from npazs.config import get_settings`` продолжает работать.

.. note::
   В каноническом дереве проекта значился и модуль ``src/config.py``, и пакет
   ``src/config/``. В Python это взаимоисключающие сущности (одно и то же имя
   ``npazs.config``), поэтому реализован пакет, а API «плоского» модуля
   сохранён через реэкспорт в этом ``__init__``.
"""

from npazs.config.db import DB_ENV_KEYS, get_db_config, get_db_config_dict
from npazs.config.env_store import (
    ACTIVE_BACKEND_ENV,
    BACKEND_ENV_KEYS,
    POST_ANALYSIS_BACKEND_ENV,
    POST_ANALYSIS_MODEL_ENV,
    load_active_backend,
    load_backend_settings,
    load_post_analysis_backend,
    load_post_analysis_model,
    save_backend_settings,
    save_env_values,
    save_post_analysis_settings,
)
from npazs.config.modx import get_modx_db_config, get_modx_ssh_config
from npazs.config.ollama import (
    get_kilo_gateway_config,
    get_llm_backend,
    get_llm_config,
    get_ollama_config,
    get_post_analysis_backend,
    get_post_analysis_llm_config,
)
from npazs.config.settings import (
    ENV_PATH,
    PROJECT_ROOT,
    Settings,
    get_settings,
    load_env,
    reload_settings,
)

__all__ = [
    "ACTIVE_BACKEND_ENV",
    "BACKEND_ENV_KEYS",
    "DB_ENV_KEYS",
    "ENV_PATH",
    "POST_ANALYSIS_BACKEND_ENV",
    "POST_ANALYSIS_MODEL_ENV",
    "PROJECT_ROOT",
    "Settings",
    "get_db_config",
    "get_db_config_dict",
    "get_kilo_gateway_config",
    "get_llm_backend",
    "get_llm_config",
    "get_modx_db_config",
    "get_modx_ssh_config",
    "get_ollama_config",
    "get_post_analysis_backend",
    "get_post_analysis_llm_config",
    "get_settings",
    "load_active_backend",
    "load_backend_settings",
    "load_env",
    "load_post_analysis_backend",
    "load_post_analysis_model",
    "reload_settings",
    "save_backend_settings",
    "save_env_values",
    "save_post_analysis_settings",
]
