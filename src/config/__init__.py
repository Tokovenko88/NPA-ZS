"""Конфигурация NPA-ZS.

Пакет заменяет исторический модуль ``npa_processor/config.py`` и разделён по
областям ответственности:

* :mod:`npazs.config.settings` — загрузка ``.env``, сводный объект настроек;
* :mod:`npazs.config.db`       — параметры MySQL-базы НПА (``DB_*``);
* :mod:`npazs.config.ollama`   — параметры LLM-бэкендов (Ollama / Kilo Gateway);
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

from npazs.config.settings import (
    ENV_PATH,
    PROJECT_ROOT,
    Settings,
    get_settings,
    load_env,
    reload_settings,
)
from npazs.config.db import DB_ENV_KEYS, get_db_config, get_db_config_dict
from npazs.config.modx import get_modx_db_config, get_modx_ssh_config
from npazs.config.ollama import (
    get_kilo_gateway_config,
    get_llm_backend,
    get_ollama_config,
)

__all__ = [
    "ENV_PATH",
    "PROJECT_ROOT",
    "Settings",
    "get_settings",
    "load_env",
    "reload_settings",
    "DB_ENV_KEYS",
    "get_db_config",
    "get_db_config_dict",
    "get_modx_db_config",
    "get_modx_ssh_config",
    "get_kilo_gateway_config",
    "get_llm_backend",
    "get_ollama_config",
]
