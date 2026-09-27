"""Главный класс приложения для внесения изменений в НПА."""

import json
import os
import queue
import re
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import requests
from bs4 import BeautifulSoup
from npazs._bootstrap import _bootstrap_project_root

_bootstrap_project_root()

import npazs.constants as _constants
from npazs.config.env_store import (
        BACKEND_ENV_KEYS,
        load_active_backend,
        load_backend_settings,
        load_post_analysis_backend,
        load_post_analysis_base_url,
        load_post_analysis_model,
        save_backend_settings,
)
from npazs.constants import (
        DEFAULT_BACKEND,
        DEFAULT_EXTRA_OPTIONS,
        DEFAULT_KILO_GATEWAY_URL,
        HTTP_BACKEND_DEFS,
        LAST_PATHS_FILE,
        PROMPT_1,
        PROMPT_2,
        PROMPT_3,
        PROMPT_4,
        STAGE_ANSWERS_FILE,
        TYPE_TO_RUSSIAN,
        _ollama_base_url,
        save_last_run_log,
        settings,
)
from npazs.llm_models import (
        OLLAMA_SIGNIN_HINT,
        fetch_cerebras_models,
        fetch_cline_models,
        fetch_free_deepseek_models,
        fetch_gemini_models,
        fetch_kilo_gateway_free_models,
        fetch_mistral_models,
        fetch_ollama_models,
        fetch_openrouter_free_models,
        fetch_qwen2api_models,
        verify_ollama_cloud_models,
)
from npazs.pipeline.orchestrator import AiPipelineMixin
from npazs.revision.ai_utils import reset_ollama_signin_notice
from npazs.revision.engine import *
from npazs.revision.file_ops import FileOpsMixin
from npazs.revision.html_utils import get_clean_text_from_block, get_full_element_html
from npazs.revision.json_utils import extract_html_from_json_response, load_json
from npazs.revision.text_utils import safe_re_sub
from npazs.revision.tree_utils import find_item_by_id
from npazs.ui.dialogs.manual_mapping import ManualMappingDialog
from npazs.ui.dialogs.source_mapping import SourceMappingDialog
from npazs.ui.gui_builder import GuiBuilderMixin
from npazs.ui.ollama_signin import offer_ollama_signin


class App(GuiBuilderMixin, AiPipelineMixin, FileOpsMixin):
        def __init__(self, root):
            self.root = root
            self.root.title("Внесение изменений в НПА в формате JSON на основе другого НПА")
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            self.root.geometry(f"{screen_width}x{screen_height}+0+0")
            self.root.state('zoomed')
            self.left_frame = ttk.Frame(self.root)
            self.right_frame = ttk.Frame(self.root)
            self.left_frame.grid(row=0, column=0, sticky='nsew')
            self.right_frame.grid(row=0, column=1, sticky='nsew')
            self.root.grid_rowconfigure(0, weight=1)
            self.root.grid_columnconfigure(0, weight=1)
            self.root.grid_columnconfigure(1, weight=3)
            self.original_path = tk.StringVar()
            self.change_path = tk.StringVar()
            self.law_ref = tk.StringVar(value="№ 0000-ЗС от 00.00.0000")
            self.original_law_ref = tk.StringVar(value="№ 0000-ЗС")
            # Автозагрузка сохранённых настроек бэкенда из .env: активный бэкенд,
            # его URL, API-ключ и модель — как при последнем сохранении. Это
            # позволяет, например, переключиться на OpenRouter (с ключом в .env)
            # и не вводить его заново после перезапуска окна.
            _saved_backend = load_active_backend()
            if _saved_backend not in BACKEND_ENV_KEYS:
                _saved_backend = DEFAULT_BACKEND
            _saved = load_backend_settings(_saved_backend)
            _defn = HTTP_BACKEND_DEFS.get(_saved_backend) or {}
            self.backend = tk.StringVar(value=_saved_backend)
            # Для ollama base_url читается из её настроек/констант, а для HTTP-бэкендов — из их base_url
            _init_url = _saved.get('base_url') or _defn.get('base_url')
            if not _init_url and _saved_backend == 'ollama':
                from npazs.constants import _ollama_base_url
                _init_url = _ollama_base_url
            self.kilo_gateway_url = tk.StringVar(
                value=_init_url or DEFAULT_KILO_GATEWAY_URL
            )
            _saved_model = _saved.get('model') or _defn.get('default_model') or ''
            if not _saved_model and _saved_backend == 'ollama':
                from npazs.constants import DEFAULT_OLLAMA_MODEL
                _saved_model = DEFAULT_OLLAMA_MODEL
            self.ollama_model = tk.StringVar(value=_saved_model)
            # Пост-анализ — независимый провайдер: свой бэкенд
            # (POST_ANALYSIS_BACKEND), своя модель (POST_ANALYSIS_MODEL).
            # Ключи берутся из .env (POST_ANALYSIS_API_KEY/POST_ANALYSIS_BASE_URL).
            _pa_backend = load_post_analysis_backend()
            if _pa_backend not in BACKEND_ENV_KEYS:
                _pa_backend = _saved_backend
            _pa_saved = load_backend_settings(_pa_backend)
            _pa_defn = HTTP_BACKEND_DEFS.get(_pa_backend) or {}
            self.post_analysis_backend = tk.StringVar(value=_pa_backend)
            _pa_model = (
                load_post_analysis_model()
                or _pa_saved.get('model')
                or _pa_defn.get('default_model')
                or _saved_model
            )
            self.post_analysis_model = tk.StringVar(value=_pa_model)
            self.post_gateway_url = tk.StringVar(
                value=load_post_analysis_base_url()
                or _pa_saved.get('base_url')
                or _pa_defn.get('base_url')
                or ''
            )
            self._prev_post_backend = _pa_backend
            self.pub_date = tk.StringVar()
            self.last_paths = load_json(LAST_PATHS_FILE, {})
            # Восстанавливаем последние пути, только если файлы ещё существуют:
            # после переноса базы на другой диск устаревшая запись просто
            # игнорируется, а диалог выбора откроется в вычисляемой рабочей базе
            # (Base рядом с папкой проекта).
            for _key, _var in (('original', self.original_path),
                               ('change', self.change_path)):
                _saved = str(self.last_paths.get(_key) or '')
                if _saved and os.path.exists(_saved):
                    _var.set(_saved)
            self.prompt_1 = PROMPT_1
            self.prompt_2 = PROMPT_2
            self.prompt_3 = PROMPT_3
            self.prompt_4 = PROMPT_4
            self.elementwise_mode = tk.BooleanVar(value=False)
            self.stage1_answer = tk.StringVar()
            self.stage2_answer = tk.StringVar()
            self.stage3_answer = tk.StringVar()
            self.use_stage1_answer = tk.BooleanVar(value=False)
            self.use_stage2_answer = tk.BooleanVar(value=False)
            self.use_stage3_answer = tk.BooleanVar(value=False)
            self.load_stage_answers()
            self.ollama_models = []
            self.post_analysis_models = []
            self.model_params_cache = {}
            self.stop_event = threading.Event()
            self.thread = None
            self.current_dialog = None
            self.manual_mapping_cache = {}
            self.logs = []
            self.message_queue = queue.Queue()
            self.answer_queue = queue.Queue()
            self.create_widgets()
            self.check_queue()
            threading.Thread(target=lambda: self._fetch_models(try_api=True, target='all'), daemon=True).start()
            _constants._user_retry_callback = self._ask_user_retry
            _constants._ollama_signin_callback = self._request_ollama_signin

        def _request_ollama_signin(self) -> None:
            """Показать диалог `ollama signin` в главном потоке Tk.

            Вызывается из рабочего потока `ask_ollama` при HTTP 403.
            """
            self.root.after(0, self._show_ollama_signin_dialog)

        def _show_ollama_signin_dialog(self) -> None:
            from npazs.revision.ai_utils import reset_ollama_signin_notice

            started = offer_ollama_signin(
                lambda msg, level='info': self.log(msg, level), parent=self.root)
            if started:
                reset_ollama_signin_notice()

        def _ask_user_retry(self, error_message, action='retry'):
            event = threading.Event()
            choice = {'value': 'stop'}
            # Область смены провайдера: '' — основной прогон, 'post' —
            # пост-анализ (диалог подсказывает менять именно пост-бэкенд).
            scope = getattr(_constants, '_settings_provider_scope', '') or ''
            scope_note = " (пост-анализ)" if scope == 'post' else ""
            switch_hint = (
                "Выберите новый бэкенд и модель в блоке «Пост-анализ»\n"
                "главного окна, затем нажмите «Готово» для продолжения."
                if scope == 'post' else
                "Выберите новый бэкенд и модель в главном окне,\n"
                "затем нажмите «Готово» для продолжения."
            )
            def show_dialog():
                dialog = tk.Toplevel(self.root)
                dialog.title(
                    ("Лимит модели исчерпан" if action == 'switch'
                     else "Ошибка запроса к модели") + scope_note
                )
                dialog.geometry("560x240" if action == 'switch' else "500x200")
                dialog.transient(self.root)
                dialog.grab_set()
                msg = tk.Label(dialog, text=error_message, wraplength=500, justify=tk.LEFT)
                msg.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
                btn_frame = tk.Frame(dialog)
                btn_frame.pack(pady=10)
                def on_retry():
                    choice['value'] = 'retry'
                    dialog.destroy()
                    event.set()
                def on_stop():
                    choice['value'] = 'stop'
                    dialog.destroy()
                    event.set()
                def on_switch():
                    # User picks a new backend/model in the main GUI; we must
                    # not terminate the pipeline (stop_event stays clear).
                    choice['value'] = 'switch'
                    dialog.destroy()
                    # Show a non-modal waiting dialog so the user can interact
                    # with the main window's backend radio buttons.
                    switch_dialog = tk.Toplevel(self.root)
                    switch_dialog.title("Переключение бэкенда")
                    switch_dialog.geometry("420x160")
                    switch_dialog.transient(self.root)
                    tk.Label(
                        switch_dialog,
                        text=switch_hint,
                        wraplength=400, justify=tk.LEFT,
                    ).pack(padx=10, pady=10)
                    def on_ready():
                        switch_dialog.destroy()
                    tk.Button(switch_dialog, text="Готово", command=on_ready, width=12).pack(pady=10)
                    switch_dialog.protocol("WM_DELETE_WINDOW", on_ready)
                    switch_dialog.wait_window()
                    event.set()
                if action == 'switch':
                    tk.Button(btn_frame, text="Переключить бэкенд", command=on_switch, width=18).pack(side=tk.LEFT, padx=5)
                    tk.Button(btn_frame, text="Повторить", command=on_retry, width=12).pack(side=tk.LEFT, padx=5)
                    tk.Button(btn_frame, text="Остановить", command=on_stop, width=12).pack(side=tk.LEFT, padx=5)
                else:
                    tk.Button(btn_frame, text="Переключить бэкенд", command=on_switch, width=15).pack(side=tk.LEFT, padx=10)
                    tk.Button(btn_frame, text="Повторить", command=on_retry, width=15).pack(side=tk.LEFT, padx=10)
                    tk.Button(btn_frame, text="Остановить", command=on_stop, width=15).pack(side=tk.LEFT, padx=10)
                dialog.protocol("WM_DELETE_WINDOW", on_stop)
            self.root.after(0, show_dialog)
            event.wait()
            return choice['value']

        def _api_key_for(self, backend_name, target='main'):
            """API key для бэкенда: читаем из .env (GUI не хранит ключи)."""
            name = (backend_name or '').strip().lower()
            if target == 'post':
                # Для пост-анализа сначала проверяем POST_ANALYSIS_API_KEY
                from npazs.config.env_store import load_post_analysis_api_key
                pa_key = load_post_analysis_api_key()
                if pa_key:
                    return pa_key
            try:
                return (load_backend_settings(name).get('api_key') or '').strip()
            except ValueError:
                return ''

        def _fetch_models(self, try_api=True, target='main'):
            if target == 'post':
                self._fetch_models_for(
                    self.post_analysis_backend.get(), try_api=try_api, target='post')
                return
            backend = self.backend.get()
            self._fetch_models_for(backend, try_api=try_api, target='main')
            if target == 'all':
                self._fetch_models_for(
                    self.post_analysis_backend.get(), try_api=try_api, target='post')

        def _fetch_models_for(self, backend, try_api=True, target='main'):
            if backend == "ollama":
                self._fetch_ollama_models(target=target)
            elif backend == "kilo_gateway":
                self._fetch_kilo_gateway_models(try_api=try_api, target=target)
            elif backend == "openrouter":
                _url, _key = self._kilo_credentials_for('openrouter', target=target)
                self._fetch_http_models('openrouter', fetch_openrouter_free_models,
                                        _url, _key, try_api,
                                        target=target)
            elif backend == "cline":
                _url, _key = self._kilo_credentials_for('cline', target=target)
                self._fetch_http_models('cline', fetch_cline_models,
                                        _url, _key, try_api,
                                        target=target)
            elif backend == "cerebras":
                _url, _key = self._kilo_credentials_for('cerebras', target=target)
                self._fetch_http_models('cerebras', fetch_cerebras_models,
                                        _url, _key, try_api,
                                        target=target)
            elif backend == "mistral":
                _url, _key = self._kilo_credentials_for('mistral', target=target)
                self._fetch_http_models('mistral', fetch_mistral_models,
                                        _url, _key, try_api,
                                        target=target)
            elif backend == "gemini":
                _url, _key = self._kilo_credentials_for('gemini', target=target)
                self._fetch_http_models('gemini', fetch_gemini_models,
                                        _url, _key, try_api,
                                        target=target)
            elif backend == "free_deepseek":
                # Локальный прокси FreeDeepseekAPI: ключ опционален, URL важен.
                # fetcher сам ходит в GET {base}/models, fallback — константы.
                # Для пост-анализа URL берётся из его редактора (креды пост-анализа
                # независимы от основного бэкенда) — см. _kilo_credentials_for.
                if target == 'post':
                    # URL из редактора пост-кредов, иначе — URL пост-бэкенда.
                    _fd_url, _ = self._kilo_credentials_for('free_deepseek', target='post')
                    if not _fd_url:
                        try:
                            _fd_url = (load_backend_settings('free_deepseek').get('base_url') or '')
                        except ValueError:
                            _fd_url = ''
                    _fd_key = self._api_key_for('free_deepseek', target='post')
                else:
                    _fd_url = self.kilo_gateway_url.get().strip()
                    _fd_key = self._api_key_for('free_deepseek')
                    if not _fd_url:
                        try:
                            _fd_url = (load_backend_settings('free_deepseek').get('base_url') or '')
                        except ValueError:
                            _fd_url = ''
                from npazs.constants import HTTP_BACKEND_DEFS as _DEFS
                _fd_url = _fd_url or (_DEFS.get('free_deepseek') or {}).get('base_url', '')
                self._fetch_http_models('free_deepseek', fetch_free_deepseek_models,
                                        _fd_url, _fd_key, try_api,
                                        target=target)
            elif backend == "qwen2api":
                # Локальный прокси Qwen2API: URL важен, API_KEY обязателен
                # (задаётся в самом прокси). fetcher сам ходит в GET {base}/models,
                # fallback — константы. Для пост-анализа URL берётся из его
                # редактора (креды пост-анализа независимы) — см. _kilo_credentials_for.
                if target == 'post':
                    _qw_url, _ = self._kilo_credentials_for('qwen2api', target='post')
                    if not _qw_url:
                        try:
                            _qw_url = (load_backend_settings('qwen2api').get('base_url') or '')
                        except ValueError:
                            _qw_url = ''
                    _qw_key = self._api_key_for('qwen2api', target='post')
                else:
                    _qw_url = self.kilo_gateway_url.get().strip()
                    _qw_key = self._api_key_for('qwen2api')
                    if not _qw_url:
                        try:
                            _qw_url = (load_backend_settings('qwen2api').get('base_url') or '')
                        except ValueError:
                            _qw_url = ''
                from npazs.constants import HTTP_BACKEND_DEFS as _DEFS
                _qw_url = _qw_url or (_DEFS.get('qwen2api') or {}).get('base_url', '')
                self._fetch_http_models('qwen2api', fetch_qwen2api_models,
                                        _qw_url, _qw_key, try_api,
                                        target=target)
            else:
                self._fetch_ollama_models(target=target)

        def _set_models_for_target(self, models, target):
            """Записать список моделей только в main- или post-список."""
            if target == 'post':
                self.post_analysis_models = list(models)
                if models and self.post_analysis_model.get() not in models:
                    self.root.after(0, lambda: self.post_analysis_model.set(models[0]))
            else:
                self.ollama_models = list(models)
                if models and self.ollama_model.get() not in models:
                    self.root.after(0, lambda: self.ollama_model.set(models[0]))

        def _fetch_http_models(self, backend_name, fetcher, base_url, api_key, try_api=True, target='main'):
            """Загрузить РЕАЛЬНЫЕ модели HTTP-бэкенда строго из API.

            ``base_url``/``api_key`` — строго из ``.env`` (через
            ``load_backend_settings``). Никаких fallback-списков: при ошибке
            показывается пустой список + честная ошибка.
            """
            if not try_api:
                self._set_models_for_target([], target)
                self.root.after(0, self.log, f"Модели {backend_name}: live-запрос отключён — список пуст.", 'warning')
                return
            if not (base_url or '').strip():
                self.root.after(0, self.log, f"Модели {backend_name}: пустой base_url в .env — список пуст.", 'error')
                self._set_models_for_target([], target)
                return
            try:
                models = fetcher(base_url, api_key)
                self._set_models_for_target(models, target)
                if models:
                    self.root.after(0, self.log, f"Выбрано моделей {backend_name}: {models}", 'info')
                else:
                    self.root.after(0, self.log, f"Нет доступных моделей в {backend_name}. Проверьте API ключ или URL.", 'warning')
            except Exception as e:
                if backend_name == 'free_deepseek':
                    hint = ('Локальный прокси FreeDeepseekAPI не запущен? '
                            'Выполните: cd tools/FreeDeepseekAPI && npm start '
                            '(первый раз — сначала `npm run auth`). '
                            'URL по умолчанию: http://127.0.0.1:9655/v1.')
                elif backend_name == 'qwen2api':
                    hint = ('Локальный прокси Qwen2API не запущен или неверный ключ? '
                            'Проверьте, что сервер на 127.0.0.1:3000 запущен и '
                            'QWEN2API_API_KEY в .env NPA-ZS совпадает с API_KEY в .env прокси.')
                elif backend_name == 'ollama':
                    hint = 'Убедитесь, что сервер Ollama запущен.'
                else:
                    hint = 'Проверьте URL и API ключ.'
                self.root.after(0, self.log, f"Ошибка подключения к {backend_name}: {e}. {hint}", 'error')
                self._set_models_for_target([], target)

        def _fetch_ollama_models(self, target='main'):
            # base_url строго из .env (OLLAMA_BASE_URL)
            try:
                _ollama_url = (load_backend_settings('ollama').get('base_url') or '').strip()
            except ValueError:
                _ollama_url = ''
            try:
                # Только облачные модели: локальные в NPA-ZS не используются.
                models = fetch_ollama_models(_ollama_url, cloud_only=True)
                self.root.after(0, self.log, f"Получено {len(models)} cloud-моделей от Ollama", 'info')
                self._set_models_for_target(models, target)
                if not models:
                    self.root.after(
                        0, self.log,
                        "Облачные модели Ollama не найдены. Установите, например: "
                        "ollama pull gpt-oss:20b-cloud",
                        'warning')
                    return
                # Проба авторизации: POST /api/show отвечает 403 без входа на ollama.com.
                blocked = verify_ollama_cloud_models(_ollama_url, models)
                if blocked:
                    self.root.after(
                        0, self.log,
                        f"Ollama cloud: нет авторизации для {len(blocked)} моделей "
                        f"({', '.join(blocked)}). {OLLAMA_SIGNIN_HINT}",
                        'error')
                    self._offer_ollama_signin()
                else:
                    # Авторизация есть — разрешаем повторное предложение при
                    # следующем HTTP 403 (например, после истечения сессии).
                    reset_ollama_signin_notice()
                    self.root.after(0, self.log, "Ollama cloud: авторизация активна — модели доступны.", 'info')
            except Exception as e:
                self.root.after(0, self.log, f"Ошибка подключения к Ollama: {e}. Убедитесь, что сервер запущен.", 'error')
                self._set_models_for_target([], target)

        def _offer_ollama_signin(self):
            """Предложить вход в Ollama Cloud.

            Метод вызывается из рабочего потока загрузки списка моделей,
            поэтому диалог показывается через ``root.after`` в главном потоке Tk.
            """
            self.root.after(0, self._show_ollama_signin_dialog)

        def _kilo_credentials_for(self, backend_name, target='main'):
            """URL/ключ Kilo-совместимого бэкенда: GUI для URL, .env для ключа."""
            name = (backend_name or '').strip().lower()
            if target == 'post':
                _pa_url = self.post_gateway_url.get().strip() if hasattr(self, 'post_gateway_url') else ''
                from npazs.config.env_store import load_post_analysis_api_key
                _pa_key = load_post_analysis_api_key()
            else:
                _pa_url = ''
                _pa_key = ''
            if name == (self.backend.get() or '').strip().lower():
                return (
                    _pa_url or self.kilo_gateway_url.get().strip(),
                    _pa_key or self._api_key_for(name),
                )
            try:
                saved = load_backend_settings(name)
            except ValueError:
                saved = {}
            defn = HTTP_BACKEND_DEFS.get(name) or {}
            return (
                _pa_url or saved.get('base_url') or defn.get('base_url') or '',
                _pa_key or saved.get('api_key') or defn.get('api_key') or '',
            )

        def _fetch_kilo_gateway_models(self, try_api=True, target='main'):
            if not try_api:
                self._set_models_for_target([], target)
                self.root.after(0, self.log, "Модели Kilo Gateway: live-запрос отключён — список пуст.", 'warning')
                return
            try:
                _url, _key = self._kilo_credentials_for('kilo_gateway', target=target)
                models = fetch_kilo_gateway_free_models(_url, _key)
                self._set_models_for_target(models, target)
                if models:
                    self.root.after(0, self.log, f"Выбрано бесплатных моделей: {models}", 'info')
                else:
                    self.root.after(0, self.log, "Нет доступных бесплатных моделей в Kilo Gateway. Проверьте API ключ или URL.", 'warning')
            except Exception as e:
                self.root.after(0, self.log, f"Ошибка подключения к Kilo Gateway: {e}. Проверьте URL и API ключ.", 'error')
                self._set_models_for_target([], target)

        def _validate_html_marker(self, html, item_type, item_number, change_info):
            if item_type not in ('point', 'subpoint', 'part'):
                return html, True
            if not item_number:
                return html, True
            expected_marker = str(item_number).strip()
            expected_marker = expected_marker.removesuffix(')')
            soup = BeautifulSoup(html, 'html.parser')
            first_text = soup.get_text(strip=True)
            if not first_text:
                return html, True
            marker_match = re.match(r'^([0-9а-яА-Яё]+)\s*[.)]', first_text)
            if marker_match:
                actual_marker = marker_match.group(1)
                if actual_marker != expected_marker:
                    msg = f"Несоответствие маркера: ожидается '{expected_marker}', фактически '{actual_marker}' для изменения {change_info}"
                    self.log(msg, 'warning')
                    return html, False
            return html, True

        def resolve_ambiguous_element(self, item_type, item_number, candidates, structural_path, revision_number=None, change_info=None, target_element_id=None):
            evt = threading.Event()
            result = {'item_id': None}
            temp_change_data = {'npa_items_revision': candidates}
            display_rev = revision_number if revision_number else structural_path
            def show_dialog():
                try:
                    dialog = SourceMappingDialog(
                        parent=self.root,
                        revision_number=display_rev,
                        change_data=temp_change_data,
                        evt=evt,
                        result_dict=result,
                        type_to_russian=TYPE_TO_RUSSIAN,
                        find_item_by_id_func=find_item_by_id,
                        stop_event=self.stop_event,
                        change_info=change_info,
                        target_element_id=target_element_id,
                        is_ambiguity=True
                    )
                    self.current_dialog = dialog
                except Exception as e:
                    self.log(f"Ошибка при открытии диалога: {e}", 'error')
                    evt.set()
                finally:
                    self.current_dialog = None
            self.root.after(0, show_dialog)
            evt.wait()
            if self.stop_event.is_set():
                self.log(f"  Процесс остановлен, выбор для {item_type} {item_number} отменён", 'warning')
                return None
            if result['item_id']:
                self.log(f"  Выбран элемент {result['item_id']} для {item_type} {item_number}", 'result')
                return result['item_id']
            else:
                self.log(f"  Выбор отменён для {item_type} {item_number}. Изменение будет пропущено.", 'warning')
                return None

        def _extract_parent_for_paragraph(self, structural):
            if 'абзац' not in structural.lower():
                return None, None
            match = re.search(r'(.*?)\s+абзац\s+(\d+|первый|второй|третий|четвертый|пятый|шестой|седьмой|восьмой|девятый|десятый)\s*$', structural, re.IGNORECASE)
            if not match:
                return None, None
            parent_structural = match.group(1).strip()
            para_num_str = match.group(2)
            if para_num_str.isdigit():
                para_num = int(para_num_str)
            else:
                numbers = {
                    'первый': 1, 'второй': 2, 'третий': 3, 'четвертый': 4, 'пятый': 5,
                    'шестой': 6, 'седьмой': 7, 'восьмой': 8, 'девятый': 9, 'десятый': 10
                }
                para_num = numbers.get(para_num_str.lower(), None)
            return parent_structural, para_num

        def resolve_revision_manually(self, revision_number, change_data, log_callback, stop_event=None, change_info=""):
            if stop_event and stop_event.is_set():
                return None
            evt = threading.Event()
            result = {'item_id': None}
            def show_dialog():
                try:
                    if stop_event and stop_event.is_set():
                        evt.set()
                        return
                    dialog = SourceMappingDialog(
                        parent=self.root,
                        revision_number=revision_number,
                        change_data=change_data,
                        evt=evt,
                        result_dict=result,
                        type_to_russian=TYPE_TO_RUSSIAN,
                        find_item_by_id_func=find_item_by_id,
                        stop_event=stop_event,
                        change_info=change_info,
                        is_ambiguity=False
                    )
                    self.current_dialog = dialog
                except Exception as e:
                    log_callback(f"Ошибка при открытии диалога: {e}", 'error')
                    evt.set()
                finally:
                    self.current_dialog = None
            self.root.after(0, show_dialog)
            while not evt.wait(0.1):
                if stop_event and stop_event.is_set():
                    if self.current_dialog:
                        self.root.after(0, self.current_dialog.destroy)
                    return None
            return result['item_id']

        def resolve_target_element_manually(self, change_data, stop_event=None):
            if stop_event and stop_event.is_set():
                return None
            evt = threading.Event()
            result = {'element': None}
            def show_dialog():
                if stop_event and stop_event.is_set():
                    evt.set()
                    return
                dialog = tk.Toplevel(self.root)
                dialog.title("Выбор целевого элемента в изменяющем законе")
                dialog.geometry("600x500")
                dialog.transient(self.root)
                dialog.grab_set()
                tree = ttk.Treeview(dialog, columns=("id", "type", "number"), show="tree headings")
                tree.heading("#0", text="Путь")
                tree.heading("id", text="ID")
                tree.heading("type", text="Тип")
                tree.heading("number", text="Номер")
                tree.column("#0", width=300)
                tree.column("id", width=150)
                tree.column("type", width=100)
                tree.column("number", width=100)
                scroll_y = ttk.Scrollbar(dialog, orient="vertical", command=tree.yview)
                scroll_x = ttk.Scrollbar(dialog, orient="horizontal", command=tree.xview)
                tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
                tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)
                scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
                scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
                def add_items(parent_item, items, path=""):
                    for item in items:
                        item_id = item.get('item_id', '')
                        item_type = item.get('item_type', '')
                        item_number = item.get('item_number', '')
                        type_rus = TYPE_TO_RUSSIAN.get(item_type, item_type)
                        node_name = f"{type_rus} {item_number}" if item_number else type_rus
                        full_path = f"{path}/{node_name}" if path else node_name
                        node = tree.insert(parent_item, "end", text=full_path, values=(item_id, type_rus, item_number))
                        add_items(node, item.get('item_children', []), full_path)
                root_items = change_data.get('npa_items_revision', [])
                add_items("", root_items)
                btn_frame = tk.Frame(dialog)
                btn_frame.pack(fill=tk.X, pady=10)
                def on_ok():
                    selected = tree.selection()
                    if not selected:
                        messagebox.showwarning("Выбор", "Пожалуйста, выберите элемент.")
                        return
                    item = tree.item(selected[0])
                    item_id = item['values'][0]
                    result['element'] = find_item_by_id(change_data, item_id)
                    evt.set()
                    dialog.destroy()
                def on_cancel():
                    result['element'] = None
                    evt.set()
                    dialog.destroy()
                tk.Button(btn_frame, text="Выбрать", command=on_ok, width=15).pack(side=tk.LEFT, padx=10)
                tk.Button(btn_frame, text="Отмена", command=on_cancel, width=15).pack(side=tk.LEFT, padx=10)
                dialog.protocol("WM_DELETE_WINDOW", on_cancel)
            self.root.after(0, show_dialog)
            while not evt.wait(0.1):
                if stop_event and stop_event.is_set():
                    if 'dialog' in locals() and dialog.winfo_exists():
                        dialog.destroy()
                    return None
            return result['element']

        def load_stage_answers(self):
            data = load_json(STAGE_ANSWERS_FILE, {})
            self.stage1_answer.set(data.get('stage1_answer', ''))
            self.stage2_answer.set(data.get('stage2_answer', ''))
            self.stage3_answer.set(data.get('stage3_answer', ''))
            self.use_stage1_answer.set(data.get('use_stage1_answer', False))
            self.use_stage2_answer.set(data.get('use_stage2_answer', False))
            self.use_stage3_answer.set(data.get('use_stage3_answer', False))

        def _normalize_text(self, text):
            if not text:
                return ""
            text = safe_re_sub(r'<[^>]+>', '', text)
            text = ' '.join(text.split())
            text = text.lower()
            text = safe_re_sub(r'[^\w\s]', '', text)
            return text

        def _extract_paragraphs_from_html(self, html):
            from bs4 import BeautifulSoup
            if not html:
                return []
            soup = BeautifulSoup(html, 'html.parser')
            paragraphs = []
            for p in soup.find_all('p'):
                html_str = str(p)
                text = p.get_text(' ', strip=True)
                if text.strip():
                    normalized = self._normalize_text(text)
                    paragraphs.append({'html': html_str, 'normalized': normalized})
            return paragraphs

        def _split_ai_answer_into_paragraphs(self, ai_answer_text):
            if not ai_answer_text:
                return []
            import re

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(ai_answer_text, 'html.parser')
            paragraphs = soup.find_all('p')
            if paragraphs:
                return [p.decode_contents().strip() for p in paragraphs if p.get_text(strip=True)]
            blocks = re.split(r'\n\s*\n', ai_answer_text)
            result = []
            for block in blocks:
                block = block.strip()
                if block:
                    result.append(block)
            return result

        def _assemble_html_from_ai_answer(self, source_element, ai_answer_text, log_callback):
            if not ai_answer_text:
                return None
            ai_answer_text = extract_html_from_json_response(ai_answer_text, log_callback)
            full_html = get_full_element_html(source_element, use_original_structure=False)
            if not full_html:
                if log_callback:
                    log_callback(f"  Не удалось получить HTML для элемента {source_element.get('item_id')}", 'error')
                return None
            soup = BeautifulSoup(full_html, 'html.parser')
            paragraphs = soup.find_all(['p', 'div', 'li'])
            if not paragraphs:
                if log_callback:
                    log_callback(f"  В исходном элементе {source_element.get('item_id')} нет абзацев", 'error')
                return None
            source_paragraphs = []
            for p in paragraphs:
                html_str = str(p)
                clean_text = get_clean_text_from_block({'html_text': html_str})
                source_paragraphs.append({'html': html_str, 'clean': clean_text})
            ai_paragraphs = self._split_ai_answer_into_paragraphs(ai_answer_text)
            if not ai_paragraphs:
                if log_callback:
                    log_callback("  Ответ ИИ не содержит текста, используем как есть", 'warning')
                    return ai_answer_text
            n = len(ai_paragraphs)
            src_count = len(source_paragraphs)
            if log_callback:
                log_callback(f"  Абзацев ИИ: {n}, абзацев в источнике: {src_count}", 'debug')
            if n > src_count:
                if log_callback:
                    log_callback(f"  Абзацев ИИ ({n}) больше, чем абзацев в источнике ({src_count})", 'error')
                return None
            start_idx = -1
            for i, p in enumerate(source_paragraphs):
                clean = p['clean'].lstrip()
                if clean.startswith('«'):
                    start_idx = i
                    if log_callback:
                        preview = clean[:50].replace('\n', ' ')
                        log_callback(f"  Найден начальный абзац с '«' на позиции {i+1}: '{preview}...'", 'debug')
                    break
            if start_idx == -1:
                if log_callback:
                    log_callback("  Не найден абзац, начинающийся с '«' в элементе-источнике", 'error')
                return None
            if start_idx + n > src_count:
                if log_callback:
                    log_callback(f"  Не хватает абзацев: нужно {n}, доступно {src_count - start_idx}. Возьмём сколько есть.", 'warning')
                n = src_count - start_idx
                if n <= 0:
                    return None
            result_paragraphs = []
            for k in range(n):
                original_html = source_paragraphs[start_idx + k]['html']
                soup_p = BeautifulSoup(original_html, 'html.parser')
                tag = soup_p.find()
                if tag:
                    tag.clear()
                    tag.append(BeautifulSoup(ai_paragraphs[k], 'html.parser'))
                    result_paragraphs.append(str(tag))
                else:
                    result_paragraphs.append(f"<p>{ai_paragraphs[k]}</p>")
            if log_callback:
                log_callback(f"  Взяты абзацы {start_idx+1}–{start_idx+n} (всего {n})", 'result')
            return '\n'.join(result_paragraphs)

        def resolve_change_manually(self, change, original_data, stop_event=None):
            if stop_event and stop_event.is_set():
                self.log("resolve_change_manually: процесс остановлен, диалог не открывается", 'warning')
                return None, None, None, None
            evt = threading.Event()
            result = {'target_id': None, 'structural': None, 'description': None, 'type': None}
            is_title_change = change.get('structural_element', '').lower().startswith('наименование')
            def show_dialog():
                try:
                    if stop_event and stop_event.is_set():
                        evt.set()
                        return
                    dialog = ManualMappingDialog(
                        parent=self.root,
                        change=change,
                        original_data=original_data,
                        evt=evt,
                        result_dict=result,
                        is_title_change=is_title_change,
                        type_to_russian=TYPE_TO_RUSSIAN,
                        find_item_by_id_func=find_item_by_id,
                        stop_event=stop_event
                    )
                    self.current_dialog = dialog
                    self.root.wait_window(dialog.window)
                except Exception as e:
                    self.log(f"Ошибка при открытии диалога: {e}", 'error')
                    evt.set()
                finally:
                    self.current_dialog = None
            self.root.after(0, show_dialog)
            while not evt.wait(0.1):
                if stop_event and stop_event.is_set():
                    if self.current_dialog:
                        self.root.after(0, self.current_dialog.destroy)
                    return None, None, None, None

            if result['target_id'] is not None:
                change['_resolved_item_id'] = result['target_id']
                if result['structural']:
                    change['structural_element'] = result['structural']
                if result['description'] is not None:
                    change['description'] = result['description']
                if result['type'] is not None:
                    change['type'] = result['type']
                self.log(f"  → Установлен _resolved_item_id = {result['target_id']}", 'result')
            else:
                self.log("  → Пользователь отменил выбор", 'warning')

            return (result['target_id'], result['structural'], result['description'], result['type'])

        def check_queue(self):
            try:
                while True:
                    msg = self.message_queue.get_nowait()
                    self.process_message(msg)
            except queue.Empty:
                pass
            finally:
                self.root.after(100, self.check_queue)

        def _copy_to_clipboard(self, text):
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update()
            messagebox.showinfo("Скопировано", "HTML скопирован в буфер обмена")

        def _show_full_html(self, html):
            if not html:
                messagebox.showinfo("Информация", "HTML отсутствует")
                return
            win = tk.Toplevel(self.root)
            win.title("Полный HTML")
            win.geometry("800x600")
            win.transient(self.root)
            frame = ttk.Frame(win, padding="10")
            frame.pack(fill=tk.BOTH, expand=True)
            text_widget = tk.Text(frame, wrap=tk.WORD, font=("Consolas", 9))
            scrollbar = ttk.Scrollbar(frame, command=text_widget.yview)
            text_widget.config(yscrollcommand=scrollbar.set)
            text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            text_widget.insert('1.0', html)
            text_widget.config(state=tk.DISABLED)
            btn_frame = ttk.Frame(win)
            btn_frame.pack(pady=5)
            ttk.Button(btn_frame, text="Копировать", command=lambda: self._copy_to_clipboard(html)).pack(side=tk.LEFT, padx=5)
            ttk.Button(btn_frame, text="Закрыть", command=win.destroy).pack(side=tk.LEFT, padx=5)

        def process_message(self, msg):
            try:
                while True:
                    msg = self.message_queue.get_nowait()
                    if isinstance(msg, dict) and msg.get('type') == 'question_appendix_title':
                        appendix_title = msg.get('appendix_title', '')
                        question_id = msg.get('question_id')
                        has_title = self.ask_appendix_title_confirmation(appendix_title)
                        if self.answer_queue:
                            self.answer_queue.put({'question_id': question_id, 'has_title': has_title})
                    elif isinstance(msg, dict) and msg.get('type') == 'question':
                        candidate_text = msg.get('candidate_text', '')
                        adjacent_text = msg.get('adjacent_text', '')
                        question_id = msg.get('question_id')
                        change_info = msg.get('change_info', '')
                        target_element_id = msg.get('target_element_id', '')
                        source_revision = msg.get('source_revision', '')
                        full_html = msg.get('full_html', '')
                        dialog = tk.Toplevel(self.root)
                        dialog.title("Неоднозначная структура")
                        dialog.geometry("700x600")
                        dialog.transient(self.root)
                        dialog.grab_set()
                        dialog.lift()
                        dialog.focus_force()
                        frame = ttk.Frame(dialog, padding="10")
                        frame.pack(fill=tk.BOTH, expand=True)
                        ttk.Label(frame, text="Парсер не может определить иерархию:").pack(anchor=tk.W, pady=(0,5))
                        info_text = (
                            f"Изменение: {change_info if change_info else 'не указано'}\n"
                            f"Целевой элемент: {target_element_id if target_element_id else 'не указан'}\n"
                            f"Источник: revision_number = {source_revision if source_revision else 'не указан'}"
                        )
                        ttk.Label(frame, text=info_text, wraplength=650, justify=tk.LEFT).pack(anchor=tk.W, pady=2)
                        ttk.Label(frame, text=f"Предыдущий элемент: {adjacent_text[:100] if adjacent_text else '(пусто)'}", wraplength=650).pack(anchor=tk.W, pady=2)
                        ttk.Label(frame, text=f"Текущий элемент: {candidate_text[:100] if candidate_text else '(пусто)'}", wraplength=650).pack(anchor=tk.W, pady=2)
                        html_frame = ttk.Frame(frame)
                        html_frame.pack(fill=tk.BOTH, expand=True, pady=5)
                        show_html_var = tk.BooleanVar(value=False)
                        def toggle_html():
                            if show_html_var.get():
                                html_text_widget.pack_forget()
                                show_html_btn.config(text="Показать полный HTML")
                                show_html_var.set(False)
                            else:
                                html_text_widget.pack(fill=tk.BOTH, expand=True, pady=5)
                                show_html_btn.config(text="Скрыть полный HTML")
                                show_html_var.set(True)
                            dialog.update()
                        show_html_btn = ttk.Button(html_frame, text="Показать полный HTML", command=toggle_html)
                        show_html_btn.pack(anchor=tk.W, pady=2)
                        html_text_widget = tk.Text(html_frame, wrap=tk.WORD, height=10, font=("Consolas", 9))
                        html_text_widget.insert('1.0', full_html if full_html else "(HTML отсутствует)")
                        html_text_widget.config(state=tk.DISABLED)
                        ttk.Label(frame, text="Должен ли текущий элемент быть дочерним по отношению к предыдущему или находиться на том же уровне?").pack(pady=10)
                        result = tk.StringVar()
                        def set_child():
                            result.set('child')
                            dialog.destroy()
                        def set_sibling():
                            result.set('sibling')
                            dialog.destroy()
                        def set_skip():
                            result.set('skip')
                            dialog.destroy()
                        def set_edit():
                            edit_dialog = tk.Toplevel(dialog)
                            edit_dialog.title("Редактирование HTML")
                            edit_dialog.geometry("600x400")
                            edit_dialog.transient(dialog)
                            edit_dialog.grab_set()
                            text_widget = tk.Text(edit_dialog, wrap=tk.WORD)
                            text_widget.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
                            text_widget.insert('1.0', full_html if full_html else "")
                            def save_edit():
                                new_html = text_widget.get('1.0', tk.END).strip()
                                result.set('edit')
                                result.new_html = new_html
                                edit_dialog.destroy()
                                dialog.destroy()
                            ttk.Button(edit_dialog, text="Сохранить и применить", command=save_edit).pack(pady=5)
                            ttk.Button(edit_dialog, text="Отмена", command=edit_dialog.destroy).pack(pady=5)
                        btn_frame = ttk.Frame(frame)
                        btn_frame.pack(pady=10)
                        ttk.Button(btn_frame, text="Дочерний", command=set_child).pack(side=tk.LEFT, padx=5)
                        ttk.Button(btn_frame, text="Тот же уровень", command=set_sibling).pack(side=tk.LEFT, padx=5)
                        ttk.Button(btn_frame, text="Пропустить", command=set_skip).pack(side=tk.LEFT, padx=5)
                        ttk.Button(btn_frame, text="Исправить HTML", command=set_edit).pack(side=tk.LEFT, padx=5)
                        dialog.protocol("WM_DELETE_WINDOW", set_skip)
                        self.root.wait_window(dialog)
                        relation = result.get()
                        if relation == 'edit' and hasattr(result, 'new_html'):
                            if self.answer_queue:
                                self.answer_queue.put({'question_id': question_id, 'relation': 'edit', 'new_html': result.new_html})
                        elif relation:
                            if self.answer_queue:
                                self.answer_queue.put({'question_id': question_id, 'relation': relation})
                    elif isinstance(msg, tuple) and len(msg) >= 3:
                        _, text, level = msg
                        self.log(text, level)
                    else:
                        msg_type = msg.get('type') if isinstance(msg, dict) else None
                        if msg_type == 'status':
                            self.status_var.set(msg.get('text', ''))
                            self.log(msg.get('text', ''))
                        elif msg_type == 'log':
                            self.log(msg.get('text', ''), msg.get('level', 'INFO'))
                        elif msg_type == 'done':
                            self.processing_done(msg.get('success', False))
                        elif msg_type == 'load_complete':
                            self.load_resources_complete(msg.get('resources'), msg.get('error'))
                        elif msg_type == 'error':
                            self.log(msg.get('text', ''), 'ERROR')
                            self.status_var.set("Ошибка")
            except queue.Empty:
                pass

        def ask_appendix_title_confirmation(self, appendix_title):
            return messagebox.askyesno(
                "Подтверждение заголовка приложения",
                f"Найден заголовок приложения:\n\n{appendix_title}\n\nСчитать этот текст заголовком приложения?"
            )

        def ask_ambiguity(self, candidate_text, adjacent_text):
            dialog = tk.Toplevel(self.root)
            dialog.title("Неоднозначная структура")
            dialog.geometry("600x250")
            dialog.transient(self.root)
            dialog.grab_set()
            ttk.Label(dialog, text="Парсер не может определить иерархию:").pack(pady=5)
            ttk.Label(dialog, text=f"Предыдущий элемент: {adjacent_text[:100]}", wraplength=550).pack(pady=2)
            ttk.Label(dialog, text=f"Текущий элемент: {candidate_text[:100]}", wraplength=550).pack(pady=2)
            ttk.Label(dialog, text="Должен ли текущий элемент быть дочерним по отношению к предыдущему или находиться на том же уровне?").pack(pady=10)
            result = tk.StringVar()
            def set_child():
                result.set('child')
                dialog.destroy()
            def set_sibling():
                result.set('sibling')
                dialog.destroy()
            btn_frame = tk.Frame(dialog)
            btn_frame.pack(pady=10)
            ttk.Button(btn_frame, text="Дочерний (увеличить отступ)", command=set_child).pack(side=tk.LEFT, padx=10)
            ttk.Button(btn_frame, text="Тот же уровень", command=set_sibling).pack(side=tk.LEFT, padx=10)
            dialog.protocol("WM_DELETE_WINDOW", set_sibling)
            self.root.wait_window(dialog)
            return result.get() or 'sibling'

        def processing_done(self, success):
            self.run_btn.config(state=tk.NORMAL)
            self.cancel_btn.config(state=tk.DISABLED)
            if success:
                self.status_var.set("Обработка завершена успешно")
                self.log("Обработка завершена успешно")
            else:
                self.status_var.set("Обработка завершена с ошибками")
                self.log("Обработка завершена с ошибками", 'WARNING')
            try:
                log_content = self.log_text.get('1.0', tk.END)
                save_last_run_log(log_content)
            except Exception:
                pass

        def load_resources_complete(self, resources, error):
            self.is_loading_resources = False
            self.load_button.config(state=tk.NORMAL)
            self.status_var.set("Готов к работе")
            if error:
                self.log(f"Ошибка при загрузке списка ресурсов: {error}", 'ERROR')
                return
            if resources is not None:
                self.all_resources = resources
                years = sorted(set([r['year'] for r in self.all_resources if r['year']]), reverse=True)
                self.year_filter['values'] = ["Все"] + years
                self.display_resources()
                self.log(f"Загружено {len(resources)} ресурсов")

        def cancel(self):
            self.stop_event.set()
            self.cancel_btn.config(state='disabled')
            if self.current_dialog:
                self.root.after(0, self.current_dialog.destroy)
                self.current_dialog = None
            self.log("Отмена запрошена...", 'warning')

def main():
    root = tk.Tk()
    app = App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
