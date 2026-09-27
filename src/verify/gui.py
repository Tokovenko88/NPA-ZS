"""Графический интерфейс модуля AI-пост-анализа внесённых изменений."""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from npazs import constants as _constants
from npazs.config.env_store import (
    BACKEND_ENV_KEYS,
    load_active_backend,
    load_backend_settings,
)
from npazs.constants import (
    DEFAULT_BACKEND,
    DEFAULT_KILO_GATEWAY_MODEL,
    DEFAULT_KILO_GATEWAY_URL,
    HTTP_BACKEND_DEFS,
    HTTP_BACKENDS,
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
from npazs.ui.ollama_signin import offer_ollama_signin

from .runner import PostAnalysisOptions, run_post_analysis_standalone

__all__ = ['VerifyApp', 'main']

FILETYPES = [
    ('JSON НПА', '*.json'),
    ('Все файлы', '*.*'),
]


def _initial_backend_settings() -> dict[str, str]:
    """Настройки бэкенда при старте окна: из ``.env`` (без захардкоженных fallback-списков моделей).

    Возвращает ``backend`` (сохранённый ``LLM_BACKEND`` или ``DEFAULT_BACKEND``)
    и его ``base_url``; при отсутствии ``base_url`` в ``.env`` используется
    URL из :data:`HTTP_BACKEND_DEFS` (справочная константа), но **список
    моделей никогда не подставляется из констант** — он берётся только live
    из API (см. ``_fetch_models_worker``).
    """
    backend = load_active_backend()
    if backend not in BACKEND_ENV_KEYS:
        backend = DEFAULT_BACKEND
    saved = load_backend_settings(backend)
    defn = HTTP_BACKEND_DEFS.get(backend) or {}
    return {
        'backend': backend,
        'base_url': saved.get('base_url') or defn.get('base_url') or DEFAULT_KILO_GATEWAY_URL,
        'model': saved.get('model', ''),
    }


class VerifyApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title('NPA-ZS — AI пост-анализ внесённых изменений')
        root.geometry('920x660')

        self.result_path = tk.StringVar()
        self.original_path = tk.StringVar()
        self.change_path = tk.StringVar()
        self.work_json_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.mode = tk.StringVar(value='full')
        # Автозагрузка сохранённых настроек бэкенда из .env: активный бэкенд,
        # его URL и модель — как при последнем сохранении.
        saved = _initial_backend_settings()
        self.backend = tk.StringVar(value=saved['backend'])
        self.kilo_gateway_url = tk.StringVar(value=saved['base_url'])
        self.available_models = []
        self._models_backend = None
        self.model = tk.StringVar(
            value=saved['model']
            or (DEFAULT_KILO_GATEWAY_MODEL if saved['backend'] == 'kilo_gateway' else '')
        )

        self.log_queue: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self._models_fetching = False

        self._create_widgets()
        self._on_backend_changed()
        _constants._ollama_signin_callback = self._request_ollama_signin
        # Диалог «Переключить бэкенд / Повторить / Остановить» после 3
        # неудачных попыток + live-снимок настроек для повтора после
        # переключения (как в основном окне ревизии): пост-анализ не должен
        # завершать работу приложения без варианта смены провайдера.
        _constants._user_retry_callback = self._ask_user_retry
        _constants._settings_provider = self._settings_provider_snapshot
        self._poll_log()

    def _settings_provider_snapshot(self) -> dict:
        """Live-снимок настроек бэкенда для повтора после переключения.

        В этом окне пост-анализ работает на единственном выбранном бэкенде,
        поэтому возвращаем текущие значения его полей (URL/модель добираются
        из ``.env``/констант, как при смене бэкенда в ``_on_backend_changed``).
        """
        backend = self.backend.get().strip()
        defn = HTTP_BACKEND_DEFS.get(backend) or {}
        saved: dict = {}
        if backend in HTTP_BACKENDS:
            try:
                saved = load_backend_settings(backend)
            except ValueError:
                saved = {}
        return {
            'backend': backend,
            'model': (self.model.get().strip()
                      or saved.get('model')
                      or defn.get('default_model') or ''),
            'base_url': (self.kilo_gateway_url.get().strip()
                         or saved.get('base_url')
                         or defn.get('base_url') or ''),
            'api_key': saved.get('api_key') or defn.get('api_key') or '',
            'agent_session': None,
        }

    def _ask_user_retry(self, error_message: str, action: str = 'retry') -> str:
        """Диалог смены провайдера после неудачных попыток (из рабочего потока).

        Как в ``revision_app.App._ask_user_retry``: блокирующее ожидание
        ответа пользователя, показ диалога — через ``root.after``.
        """
        event = threading.Event()
        choice = {'value': 'stop'}

        def show_dialog():
            dialog = tk.Toplevel(self.root)
            dialog.title(
                "Лимит модели исчерпан" if action == 'switch'
                else "Ошибка запроса к модели"
            )
            dialog.transient(self.root)
            dialog.grab_set()
            tk.Label(
                dialog, text=error_message, wraplength=500, justify=tk.LEFT,
            ).pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
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
                # Пользователь выбирает новый бэкенд в ЭТОМ окне; прогон
                # (пост-анализ) не должен завершаться.
                choice['value'] = 'switch'
                dialog.destroy()
                switch_dialog = tk.Toplevel(self.root)
                switch_dialog.title("Переключение бэкенда")
                switch_dialog.geometry("440x160")
                switch_dialog.transient(self.root)
                tk.Label(
                    switch_dialog,
                    text="Выберите другой бэкенд и модель в главном окне,\n"
                         "затем нажмите «Готово» для продолжения.",
                    wraplength=400, justify=tk.LEFT,
                ).pack(padx=10, pady=10)
                tk.Button(
                    switch_dialog, text="Готово",
                    command=switch_dialog.destroy, width=12,
                ).pack(pady=10)
                switch_dialog.protocol(
                    "WM_DELETE_WINDOW", switch_dialog.destroy)
                switch_dialog.wait_window()
                event.set()

            tk.Button(
                btn_frame, text="Переключить бэкенд", command=on_switch,
                width=18,
            ).pack(side=tk.LEFT, padx=5)
            tk.Button(
                btn_frame, text="Повторить", command=on_retry, width=12,
            ).pack(side=tk.LEFT, padx=5)
            tk.Button(
                btn_frame, text="Остановить", command=on_stop, width=12,
            ).pack(side=tk.LEFT, padx=5)
            dialog.protocol("WM_DELETE_WINDOW", on_stop)

        self.root.after(0, show_dialog)
        event.wait()
        return choice['value']

    def _request_ollama_signin(self) -> None:
        """Из рабочего потока поставить в очередь показ диалога `ollama signin`."""
        self.log_queue.put(('signin', None))

    def _show_ollama_signin_dialog(self) -> None:
        from npazs.revision.ai_utils import reset_ollama_signin_notice

        started = offer_ollama_signin(
            lambda msg, level='info': self._append_log(msg, level), parent=self.root)
        if started:
            reset_ollama_signin_notice()

    def _create_widgets(self) -> None:
        pad = {'padx': 8, 'pady': 4}

        frame = tk.Frame(self.root)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        tk.Label(frame, text='Файл результата (izm_...json):').grid(
            row=0, column=0, sticky='e', **pad
        )
        tk.Entry(frame, textvariable=self.result_path).grid(
            row=0, column=1, sticky='ew', **pad
        )
        tk.Button(frame, text='Выбрать…', command=self._browse_result).grid(
            row=0, column=2, **pad
        )

        tk.Label(frame, text='Оригинальный НПА (target):').grid(
            row=1, column=0, sticky='e', **pad
        )
        tk.Entry(frame, textvariable=self.original_path).grid(
            row=1, column=1, sticky='ew', **pad
        )
        tk.Button(frame, text='Выбрать…', command=self._browse_original).grid(
            row=1, column=2, **pad
        )

        tk.Label(frame, text='НПА с изменениями (source):').grid(
            row=2, column=0, sticky='e', **pad
        )
        tk.Entry(frame, textvariable=self.change_path).grid(
            row=2, column=1, sticky='ew', **pad
        )
        tk.Button(frame, text='Выбрать…', command=self._browse_change).grid(
            row=2, column=2, **pad
        )

        tk.Label(frame, text='Файл работы (_work.json):').grid(
            row=3, column=0, sticky='e', **pad
        )
        tk.Entry(frame, textvariable=self.work_json_path).grid(
            row=3, column=1, sticky='ew', **pad
        )
        tk.Button(frame, text='Выбрать…', command=self._browse_work).grid(
            row=3, column=2, **pad
        )

        tk.Label(frame, text='Отчёт (Markdown):').grid(
            row=4, column=0, sticky='e', **pad
        )
        tk.Entry(frame, textvariable=self.output_path).grid(
            row=4, column=1, sticky='ew', **pad
        )
        tk.Button(frame, text='Сохранить как…', command=self._browse_output).grid(
            row=4, column=2, **pad
        )

        backend_frame = tk.Frame(frame)
        backend_frame.grid(row=5, column=0, columnspan=3, sticky='w', **pad)
        tk.Label(backend_frame, text='Бэкенд:').pack(side=tk.LEFT, padx=(0, 8))
        tk.Radiobutton(
            backend_frame, text='Kilo Gateway', variable=self.backend,
            value='kilo_gateway', command=self._on_backend_changed,
        ).pack(side=tk.LEFT, padx=4)
        tk.Radiobutton(
            backend_frame, text='Ollama', variable=self.backend, value='ollama',
            command=self._on_backend_changed,
        ).pack(side=tk.LEFT, padx=4)
        tk.Radiobutton(
            backend_frame, text='Cline API', variable=self.backend,
            value='cline', command=self._on_backend_changed,
        ).pack(side=tk.LEFT, padx=4)
        tk.Radiobutton(
            backend_frame, text='OpenRouter', variable=self.backend,
            value='openrouter', command=self._on_backend_changed,
        ).pack(side=tk.LEFT, padx=4)
        tk.Radiobutton(
            backend_frame, text='Cerebras', variable=self.backend,
            value='cerebras', command=self._on_backend_changed,
        ).pack(side=tk.LEFT, padx=4)
        tk.Radiobutton(
            backend_frame, text='Mistral', variable=self.backend,
            value='mistral', command=self._on_backend_changed,
        ).pack(side=tk.LEFT, padx=4)
        tk.Radiobutton(
            backend_frame, text='Gemini', variable=self.backend,
            value='gemini', command=self._on_backend_changed,
        ).pack(side=tk.LEFT, padx=4)
        tk.Radiobutton(
            backend_frame, text='FreeDeepseek', variable=self.backend,
            value='free_deepseek', command=self._on_backend_changed,
        ).pack(side=tk.LEFT, padx=4)
        tk.Radiobutton(
            backend_frame, text='Qwen2API', variable=self.backend,
            value='qwen2api', command=self._on_backend_changed,
        ).pack(side=tk.LEFT, padx=4)

        # Поле ввода BASE_URL убрано из GUI: URL берётся из .env
        # (load_backend_settings / HTTP_BACKEND_DEFS), переменная
        # self.kilo_gateway_url сохранена — на ней держатся запросы моделей
        # и запуск пост-анализа.

        model_frame = tk.Frame(frame)
        model_frame.grid(row=6, column=0, columnspan=3, sticky='w', **pad)
        tk.Label(model_frame, text='Модель:').pack(side=tk.LEFT, padx=(0, 8))
        self.model_combo = ttk.Combobox(
            model_frame, textvariable=self.model, values=self.available_models, width=50
        )
        self.model_combo.pack(side=tk.LEFT)

        btn_frame = tk.Frame(frame)
        btn_frame.grid(row=7, column=0, columnspan=3, sticky='w', **pad)
        self.run_button = tk.Button(
            btn_frame, text='Запустить пост-анализ', command=self._start, width=20,
            bg='#e8f0e8',
        )
        self.run_button.pack(side=tk.LEFT, padx=(0, 8))
        self.stop_button = tk.Button(
            btn_frame, text='Остановить', command=self._stop, width=14,
            state=tk.DISABLED,
        )
        self.stop_button.pack(side=tk.LEFT)

        tk.Label(frame, text='Журнал работы:').grid(
            row=9, column=0, sticky='w', **pad
        )
        log_frame = tk.Frame(frame)
        log_frame.grid(row=10, column=0, columnspan=3, sticky='nsew', **pad)
        frame.grid_rowconfigure(10, weight=1)
        frame.grid_columnconfigure(1, weight=1)

        scrollbar = tk.Scrollbar(log_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text = tk.Text(
            log_frame, height=18, wrap='word', state=tk.DISABLED,
            yscrollcommand=scrollbar.set,
        )
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.log_text.yview)

        self.log_menu = tk.Menu(self.log_text, tearoff=0)
        self.log_menu.add_command(label='Копировать', command=self._copy_log_selection)
        self.log_menu.add_command(label='Выделить всё', command=self._select_all_log)
        self.log_text.bind('<Button-3>', self._show_log_menu)
        self.log_text.bind('<Control-c>', self._copy_log_selection)
        self.log_text.bind('<Control-a>', self._select_all_log)

        for tag, cfg in (
            ('warning', {'foreground': '#b06000'}),
            ('error', {'foreground': '#a01010'}),
            ('success', {'foreground': '#107010'}),
        ):
            self.log_text.tag_configure(tag, **cfg)

    def _browse_result(self) -> None:
        path = filedialog.askopenfilename(
            title='Файл результата (izm_...json)', filetypes=FILETYPES
        )
        if path:
            self.result_path.set(path)

    def _browse_original(self) -> None:
        path = filedialog.askopenfilename(
            title='Оригинальный НПА', filetypes=FILETYPES
        )
        if path:
            self.original_path.set(path)

    def _browse_change(self) -> None:
        path = filedialog.askopenfilename(
            title='НПА с изменениями', filetypes=FILETYPES
        )
        if path:
            self.change_path.set(path)

    def _browse_work(self) -> None:
        path = filedialog.askopenfilename(
            title='Файл работы (_work.json)', filetypes=FILETYPES
        )
        if path:
            self.work_json_path.set(path)

    def _browse_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title='Куда сохранить отчёт',
            defaultextension='.md',
            filetypes=[('Markdown', '*.md'), ('Все файлы', '*.*')],
        )
        if path:
            self.output_path.set(path)

    def _append_log(self, msg: str, level: str = 'info') -> None:
        self.log_text.config(state=tk.NORMAL)
        tags = {'info': (), 'warning': ('warning',), 'error': ('error',), 'success': ('success',)}
        self.log_text.insert(tk.END, msg + '\n', tags.get(level, ()))
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _show_log_menu(self, event) -> None:
        self.log_menu.post(event.x_root, event.y_root)

    def _copy_log_selection(self, event=None) -> str:
        try:
            selected = self.log_text.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            selected = self.log_text.get('1.0', tk.END).rstrip('\n')
        if selected:
            self.root.clipboard_clear()
            self.root.clipboard_append(selected)
            self.root.update()
        return 'break'

    def _select_all_log(self, event=None) -> str:
        self.log_text.config(state=tk.NORMAL)
        self.log_text.tag_add(tk.SEL, '1.0', tk.END)
        self.log_text.config(state=tk.DISABLED)
        return 'break'

    def _set_running(self, running: bool) -> None:
        self.run_button.config(state=tk.DISABLED if running else tk.NORMAL)
        self.stop_button.config(state=tk.NORMAL if running else tk.DISABLED)

    def _on_backend_changed(self) -> None:
        # Поле URL убрано из GUI — для HTTP-бэкендов только синхронизируем
        # self.kilo_gateway_url из .env/констант (оно используется ниже
        # при загрузке моделей и запуске пост-анализа).
        backend = self.backend.get()
        if backend in HTTP_BACKENDS:
            # Автоподстановка URL выбранного бэкенда из .env/констант.
            defn = HTTP_BACKEND_DEFS.get(backend)
            if defn:
                saved = load_backend_settings(backend)
                current_url = self.kilo_gateway_url.get().strip()
                default_url = defn['base_url']
                if not current_url or current_url != default_url:
                    self.kilo_gateway_url.set(saved.get('base_url') or default_url)
                if saved.get('model'):
                    self.model.set(saved['model'])
        if getattr(self, '_models_backend', None) != backend:
            self._fetch_models()
        self._update_model_combo()

    def _update_model_combo(self) -> None:
        self.model_combo['values'] = self.available_models
        if self.available_models:
            current = self.model.get()
            if current not in self.available_models:
                self.model.set(self.available_models[0])
        else:
            self.model.set('')

    def _fetch_models(self) -> None:
        if getattr(self, '_models_fetching', False):
            return
        self._models_fetching = True
        backend = self.backend.get()
        url = self.kilo_gateway_url.get().strip()
        # API key читается из .env в фоновом потоке
        threading.Thread(
            target=self._fetch_models_worker,
            args=(backend, url),
            daemon=True,
        ).start()

    def _fetch_models_worker(self, backend, kilo_gateway_url) -> None:
        """Фоновый поток: получить реальные модели для выбранного бэкенда.

        URL и API key **строго из `.env`** — прочитаны через
        ``load_backend_settings``. Модели берутся только live из API
        (``GET /models``); при недоступности API выпадает пустой список
        и честная ошибка в журнал — ни в коем случае не «запасной»
        захардкоженный набор.
        """
        saved = load_backend_settings(backend)
        api_key = saved.get('api_key') or ''
        base_url = (kilo_gateway_url or saved.get('base_url') or '').rstrip('/')
        try:
            if backend == 'ollama':
                self._fetch_ollama_models(base_url)
            elif backend == 'kilo_gateway':
                self._fetch_kilo_gateway_models(base_url, api_key)
            elif backend == 'openrouter':
                self._fetch_openrouter_models(base_url, api_key)
            elif backend == 'cline':
                self._fetch_cline_models(base_url, api_key)
            elif backend == 'cerebras':
                self._fetch_cerebras_models(base_url, api_key)
            elif backend == 'mistral':
                self._fetch_mistral_models(base_url, api_key)
            elif backend == 'gemini':
                self._fetch_gemini_models(base_url, api_key)
            elif backend == 'free_deepseek':
                self._fetch_free_deepseek_models(base_url, api_key)
            elif backend == 'qwen2api':
                self._fetch_qwen2api_models(base_url, api_key)
            else:
                self._fetch_ollama_models(base_url)
        finally:
            self._models_fetching = False

    def _fetch_openrouter_models(self, base_url: str, api_key: str) -> None:
        """Загрузить РЕАЛЬНЫЕ free-модели OpenRouter строго из API."""
        try:
            models = fetch_openrouter_free_models(base_url, api_key)
            self.log_queue.put(('info', f"OpenRouter: получено {len(models)} free-моделей"))
            self.log_queue.put(('models', ('openrouter', models)))
        except Exception as e:  # noqa: BLE001
            self.log_queue.put(('error', f"Ошибка подключения к OpenRouter: {e}"))
            self.log_queue.put(('warning', 'OpenRouter недоступен — список пуст, показаны только live-модели из API.'))
            self.log_queue.put(('models', ('openrouter', [])))

    def _fetch_cline_models(self, base_url: str, api_key: str) -> None:
        """Загрузить РЕАЛЬНЫЕ модели Cline API строго из API."""
        try:
            models = fetch_cline_models(base_url, api_key)
            self.log_queue.put(('models', ('cline', models)))
        except Exception as e:  # noqa: BLE001
            self.log_queue.put(('error', f"Ошибка подключения к Cline API: {e}"))
            self.log_queue.put(('warning', 'Cline API недоступен — список пуст, показаны только live-модели из API.'))
            self.log_queue.put(('models', ('cline', [])))

    def _fetch_cerebras_models(self, base_url: str, api_key: str) -> None:
        """Загрузить РЕАЛЬНЫЕ модели Cerebras строго из API."""
        try:
            models = fetch_cerebras_models(base_url, api_key)
            self.log_queue.put(('models', ('cerebras', models)))
        except Exception as e:  # noqa: BLE001
            self.log_queue.put(('error', f"Ошибка подключения к Cerebras: {e}"))
            self.log_queue.put(('warning', 'Cerebras недоступен — список пуст, показаны только live-модели из API.'))
            self.log_queue.put(('models', ('cerebras', [])))

    def _fetch_mistral_models(self, base_url: str, api_key: str) -> None:
        """Загрузить РЕАЛЬНЫЕ модели Mistral AI строго из API."""
        try:
            models = fetch_mistral_models(base_url, api_key)
            self.log_queue.put(('models', ('mistral', models)))
        except Exception as e:  # noqa: BLE001
            self.log_queue.put(('error', f"Ошибка подключения к Mistral AI: {e}"))
            self.log_queue.put(('warning', 'Mistral AI недоступен — список пуст, показаны только live-модели из API.'))
            self.log_queue.put(('models', ('mistral', [])))

    def _fetch_gemini_models(self, base_url: str, api_key: str) -> None:
        """Загрузить РЕАЛЬНЫЕ модели Gemini строго из API."""
        try:
            models = fetch_gemini_models(base_url, api_key)
            self.log_queue.put(('models', ('gemini', models)))
        except Exception as e:  # noqa: BLE001
            self.log_queue.put(('error', f"Ошибка подключения к Gemini: {e}"))
            self.log_queue.put(('warning', 'Gemini недоступен — список пуст, показаны только live-модели из API.'))
            self.log_queue.put(('models', ('gemini', [])))

    def _fetch_free_deepseek_models(self, base_url: str, api_key: str) -> None:
        """Загрузить РЕАЛЬНЫЕ модели локального прокси FreeDeepseekAPI."""
        try:
            models = fetch_free_deepseek_models(base_url, api_key)
            self.log_queue.put(('models', ('free_deepseek', models)))
        except Exception as e:  # noqa: BLE001
            self.log_queue.put(('error', f"Ошибка подключения к FreeDeepseekAPI: {e}"))
            self.log_queue.put(('warning', 'FreeDeepseekAPI недоступен — список пуст, показаны только live-модели из API.'))
            self.log_queue.put(('models', ('free_deepseek', [])))

    def _fetch_qwen2api_models(self, base_url: str, api_key: str) -> None:
        """Загрузить РЕАЛЬНЫЕ модели локального прокси Qwen2API."""
        try:
            models = fetch_qwen2api_models(base_url, api_key)
            self.log_queue.put(('models', ('qwen2api', models)))
        except Exception as e:  # noqa: BLE001
            self.log_queue.put(('error', f"Ошибка подключения к Qwen2API: {e}"))
            self.log_queue.put(('warning', 'Qwen2API недоступен — список пуст, показаны только live-модели из API.'))
            self.log_queue.put(('models', ('qwen2api', [])))

    def _fetch_ollama_models(self, base_url: str) -> None:
        """Загрузить облачные (cloud) модели Ollama и проверить авторизацию."""
        try:
            models = fetch_ollama_models(base_url, cloud_only=True)
            self.log_queue.put(('info', f"Получено {len(models)} cloud-моделей от Ollama"))
            self.log_queue.put(('models', ('ollama', models)))
            if not models:
                self.log_queue.put(('warning', 'Облачные модели Ollama не найдены. Установите, например: ollama pull gpt-oss:20b-cloud'))
                return
            # Проба авторизации: POST /api/show отвечает 403 без входа на ollama.com.
            blocked = verify_ollama_cloud_models(base_url, models)
            if blocked:
                self.log_queue.put(('error', f"Ollama cloud: нет авторизации для {len(blocked)} моделей ({', '.join(blocked)}). {OLLAMA_SIGNIN_HINT}"))
                self.log_queue.put(('signin', True))
            else:
                # Авторизация есть — разрешаем повторное предложение при 403.
                self.log_queue.put(('reset-signin', None))
                self.log_queue.put(('info', 'Ollama cloud: авторизация активна — модели доступны.'))

        except Exception as e:  # noqa: BLE001
            self.log_queue.put(('error', f"Ошибка подключения к Ollama: {e}. Убедитесь, что сервер запущен."))
            self.log_queue.put(('warning', 'Ollama недоступен — список пуст, показаны только live-модели из API.'))
            self.log_queue.put(('models', ('ollama', [])))

    def _fetch_kilo_gateway_models(self, base_url: str, api_key: str) -> None:
        """Загрузить РЕАЛЬНЫЕ free-модели Kilo Gateway строго из API."""
        try:
            models = fetch_kilo_gateway_free_models(base_url, api_key)
            if models:
                self.log_queue.put(('info', f"Выбрано бесплатных моделей: {models}"))
            else:
                self.log_queue.put(('warning', 'Free-модели в списке Kilo Gateway не найдены — поле выбора пусто.'))
            self.log_queue.put(('models', ('kilo_gateway', models)))
        except Exception as e:  # noqa: BLE001
            self.log_queue.put(('error', f"Ошибка подключения к Kilo Gateway: {e}. Проверьте URL и API ключ."))
            self.log_queue.put(('warning', 'Kilo Gateway недоступен — список пуст, показаны только live-модели из API.'))
            self.log_queue.put(('models', ('kilo_gateway', [])))




    def _start(self) -> None:
        result = self.result_path.get().strip()
        original = self.original_path.get().strip()
        change = self.change_path.get().strip()
        if not result or not os.path.isfile(result):
            messagebox.showwarning('Пост-анализ', 'Выберите файл результата (izm_...json).')
            return
        if not original or not os.path.isfile(original):
            messagebox.showwarning('Пост-анализ', 'Выберите оригинальный НПА.')
            return
        if not change or not os.path.isfile(change):
            messagebox.showwarning('Пост-анализ', 'Выберите НПА с изменениями.')
            return

        options = PostAnalysisOptions(
            result_path=result,
            original_path=original,
            change_path=change,
            work_json_path=self.work_json_path.get().strip(),
            output_path=self.output_path.get().strip(),
            model=self.model.get().strip(),
            backend=self.backend.get().strip(),
            kilo_gateway_url=self.kilo_gateway_url.get().strip(),
        )
        self.stop_event.clear()
        self._set_running(True)
        self._append_log('=== Запуск AI пост-анализа ===')
        self.worker = threading.Thread(target=self._worker, args=(options,), daemon=True)
        self.worker.start()

    def _stop(self) -> None:
        self.stop_event.set()
        self._append_log('Остановка запрошена…', 'warning')

    def _worker(self, options: PostAnalysisOptions) -> None:
        def log(msg: str, level: str = 'info') -> None:
            self.log_queue.put((level, msg))

        try:
            res = run_post_analysis_standalone(options, log=log, stop_event=self.stop_event)
            self.log_queue.put(('done', res))
        except Exception as error:  # noqa: BLE001 - GUI worker
            self.log_queue.put(('error', f'Ошибка: {error}'))
            self.log_queue.put(('failed', None))

    def _on_done(self, result) -> None:
        self._set_running(False)
        status = str(result.status or 'unknown')
        if status == 'correct':
            level = 'success'
            msg = '✅ Изменения внесены корректно.'
        elif status == 'incorrect':
            level = 'warning'
            msg = f"❌ Выявлены проблемы ({result.issues}). Исправленный файл: {result.corrected_path or 'не создан'}"
        elif status == 'skipped':
            level = 'warning'
            msg = '⚠️ Пост-анализ пропущен.'
        else:
            level = 'error'
            msg = '⚠️ Пост-анализ завершился с ошибкой.'
        self._append_log(msg, level)
        if result.errors:
            for err in result.errors:
                self._append_log(err, 'error')
        if result.output_path:
            messagebox.showinfo('Пост-анализ завершён', f'Отчёт сохранён:\n{result.output_path}')
        else:
            messagebox.showinfo('Пост-анализ завершён', msg)

    def _on_models_loaded(self, payload) -> None:
        backend, models = payload
        self._models_backend = backend
        if backend == self.backend.get():
            self.available_models = models
            self._update_model_combo()

    def _poll_log(self) -> None:
        try:
            while True:
                level, payload = self.log_queue.get_nowait()
                if level == 'done':
                    self._on_done(payload)
                    continue
                if level == 'failed':
                    self._set_running(False)
                    continue
                if level == 'models':
                    self._on_models_loaded(payload)
                    continue
                if level == 'reset-signin':
                    # Авторизация Ollama Cloud активна — разрешаем повторное
                    # предложение `ollama signin` при следующем HTTP 403.
                    from npazs.revision.ai_utils import reset_ollama_signin_notice

                    reset_ollama_signin_notice()
                    continue
                if level == 'signin':
                    self._show_ollama_signin_dialog()
                    continue
                self._append_log(str(payload), level)
        except queue.Empty:
            pass
        self.root.after(150, self._poll_log)


def main() -> None:
    root = tk.Tk()
    VerifyApp(root)
    root.mainloop()
