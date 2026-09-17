"""Графический интерфейс модуля AI-пост-анализа внесённых изменений."""

from __future__ import annotations

import json
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from npazs.config.env_store import (
    BACKEND_ENV_KEYS,
    load_active_backend,
    load_backend_settings,
    save_backend_settings,
)
from npazs.constants import (
    DEFAULT_BACKEND,
    DEFAULT_KILO_GATEWAY_MODEL,
    DEFAULT_KILO_GATEWAY_URL,
    HTTP_BACKEND_DEFS,
    HTTP_BACKENDS,
    KILO_GATEWAY_FREE_MODELS,
)
from npazs.llm_models import (
        fetch_cline_models,
        fetch_cerebras_models,
        fetch_gemini_models,
        fetch_kilo_gateway_free_models,
        fetch_mistral_models,
        fetch_ollama_models,
        fetch_openrouter_free_models,
        fetch_together_models,
        get_free_models_for_backend,
)

from .runner import PostAnalysisOptions, run_post_analysis_standalone

__all__ = ['VerifyApp', 'main']

FILETYPES = [
    ('JSON НПА', '*.json'),
    ('Все файлы', '*.*'),
]


def _initial_backend_settings() -> dict[str, str]:
    """Настройки бэкенда при старте окна: из ``.env``, с fallback на константы.

    Возвращает ``backend`` (сохранённый ``LLM_BACKEND`` или ``DEFAULT_BACKEND``)
    и его ``api_key`` / ``base_url`` / ``model``; отсутствующие в ``.env``
    значения подставляются из :data:`HTTP_BACKEND_DEFS`.
    """
    backend = load_active_backend()
    if backend not in BACKEND_ENV_KEYS:
        backend = DEFAULT_BACKEND
    saved = load_backend_settings(backend)
    defn = HTTP_BACKEND_DEFS.get(backend) or {}
    return {
        'backend': backend,
        'api_key': saved.get('api_key') or defn.get('api_key', ''),
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
        # его URL, API-ключ и модель — как при последнем сохранении.
        saved = _initial_backend_settings()
        self.backend = tk.StringVar(value=saved['backend'])
        self.kilo_gateway_url = tk.StringVar(value=saved['base_url'])
        self.kilo_gateway_api_key = tk.StringVar(value=saved['api_key'])
        self.available_models = []
        self._models_backend = None
        self.model = tk.StringVar(
            value=saved['model']
            or (DEFAULT_KILO_GATEWAY_MODEL if saved['backend'] == 'kilo_gateway' else '')
        )
        self.extra_options = tk.StringVar(value=json.dumps({'temperature': 0.0, 'top_p': 0.1}))

        self.log_queue: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self._models_fetching = False

        self._create_widgets()
        self._on_backend_changed()
        self._poll_log()

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
            backend_frame, text='Together', variable=self.backend,
            value='together', command=self._on_backend_changed,
        ).pack(side=tk.LEFT, padx=4)
        tk.Radiobutton(
            backend_frame, text='Mistral', variable=self.backend,
            value='mistral', command=self._on_backend_changed,
        ).pack(side=tk.LEFT, padx=4)
        tk.Radiobutton(
            backend_frame, text='Gemini', variable=self.backend,
            value='gemini', command=self._on_backend_changed,
        ).pack(side=tk.LEFT, padx=4)

        self.kg_url_label = tk.Label(backend_frame, text='API URL:')
        self.kg_url_label.pack(side=tk.LEFT, padx=(16, 4))
        self.kg_url_entry = tk.Entry(
            backend_frame, textvariable=self.kilo_gateway_url, width=40
        )
        self.kg_url_entry.pack(side=tk.LEFT)

        self.kg_key_label = tk.Label(backend_frame, text='API Key:')
        self.kg_key_label.pack(side=tk.LEFT, padx=(16, 4))
        self.kg_key_entry = tk.Entry(
            backend_frame, textvariable=self.kilo_gateway_api_key, width=20,
            show='*',
        )
        self.kg_key_entry.pack(side=tk.LEFT)

        self.save_env_btn = tk.Button(
            backend_frame, text='Сохранить в .env', command=self._save_env_settings,
        )
        self.save_env_btn.pack(side=tk.LEFT, padx=(8, 0))

        self.fetch_models_btn = tk.Button(
            backend_frame, text='Обновить модели', command=self._refresh_models
        )
        self.fetch_models_btn.pack(side=tk.LEFT, padx=(16, 0))

        model_frame = tk.Frame(frame)
        model_frame.grid(row=6, column=0, columnspan=3, sticky='w', **pad)
        tk.Label(model_frame, text='Модель:').pack(side=tk.LEFT, padx=(0, 8))
        self.model_combo = ttk.Combobox(
            model_frame, textvariable=self.model, values=self.available_models, width=50
        )
        self.model_combo.pack(side=tk.LEFT)

        tk.Label(frame, text='Доп. параметры (JSON):').grid(
            row=7, column=0, sticky='e', **pad
        )
        tk.Entry(frame, textvariable=self.extra_options).grid(
            row=7, column=1, sticky='ew', **pad
        )
        tk.Label(frame, text='Напр.: {"temperature": 0.0, "top_p": 0.1}', fg='gray').grid(
            row=7, column=2, sticky='w', **pad
        )

        btn_frame = tk.Frame(frame)
        btn_frame.grid(row=8, column=0, columnspan=3, sticky='w', **pad)
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
                self._append_log(str(payload), level)
        except queue.Empty:
            pass
        self.root.after(150, self._poll_log)

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
        # Для HTTP-бэкендов (kilo_gateway, cline, openrouter, deepseek, gemini)
        # показываем URL/API Key поля. Для ollama скрываем и используем локальный сервер.
        backend = self.backend.get()
        if backend in HTTP_BACKENDS:
            self.kg_url_label.config(state=tk.NORMAL)
            self.kg_url_entry.config(state=tk.NORMAL)
            self.kg_key_label.config(state=tk.NORMAL)
            self.kg_key_entry.config(state=tk.NORMAL)
            # Автоподстановка URL по умолчанию, если поле пусто или совпадает
            # с URL другого бэкенда.
            defn = HTTP_BACKEND_DEFS.get(backend)
            if defn:
                saved = load_backend_settings(backend)
                current_url = self.kilo_gateway_url.get().strip()
                default_url = defn['base_url']
                default_key = saved.get('api_key') or defn.get('api_key', '')
                if not current_url or current_url != default_url:
                    self.kilo_gateway_url.set(saved.get('base_url') or default_url)
                    self.kilo_gateway_api_key.set(str(default_key or ''))
                if saved.get('model'):
                    self.model.set(saved['model'])
        else:
            self.kg_url_label.config(state=tk.DISABLED)
            self.kg_url_entry.config(state=tk.DISABLED)
            self.kg_key_label.config(state=tk.DISABLED)
            self.kg_key_entry.config(state=tk.DISABLED)
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

    def _refresh_models(self) -> None:
        """Кнопка «Обновить модели»: сначала сохранить ключ в ``.env``."""
        self._save_env_settings()
        self._fetch_models()

    def _save_env_settings(self) -> bool:
        """Сохранить параметры текущего бэкенда (ключ, URL, модель) в ``.env``.

        Вызывается кнопкой «Сохранить в .env», кнопкой «Обновить модели» и
        автоматически при запуске пост-анализа — API-ключ моделей не нужно
        вводить заново после перезапуска окна.
        """
        backend = self.backend.get().strip() or DEFAULT_BACKEND
        if backend not in BACKEND_ENV_KEYS:
            return False
        try:
            written = save_backend_settings(
                backend,
                api_key=self.kilo_gateway_api_key.get().strip(),
                base_url=self.kilo_gateway_url.get().strip(),
                model=self.model.get().strip(),
            )
        except (OSError, ValueError) as e:
            self.log_queue.put(('error', f'Не удалось сохранить настройки в .env: {e}'))
            return False
        self.log_queue.put((
            'info',
            'Настройки бэкенда сохранены в .env: ' + ', '.join(sorted(written)),
        ))
        return bool(written)

    def _fetch_models(self) -> None:
        if getattr(self, '_models_fetching', False):
            return
        self._models_fetching = True
        self.fetch_models_btn.config(state=tk.DISABLED, text='Загрузка...')
        backend = self.backend.get()
        url = self.kilo_gateway_url.get().strip()
        api_key = self.kilo_gateway_api_key.get().strip()
        threading.Thread(
            target=self._fetch_models_worker,
            args=(backend, url, api_key),
            daemon=True,
        ).start()

    def _fetch_models_worker(self, backend, kilo_gateway_url, kilo_gateway_api_key) -> None:
        """Фоновый поток: получить модели для выбранного бэкенда."""
        try:
            if backend == 'ollama':
                self._fetch_ollama_models()
            elif backend == 'kilo_gateway':
                self._fetch_kilo_gateway_models(kilo_gateway_url, kilo_gateway_api_key)
            elif backend == 'openrouter':
                self._fetch_openrouter_models(kilo_gateway_api_key)
            elif backend == 'cline':
                self._fetch_cline_models(kilo_gateway_api_key)
            elif backend == 'cerebras':
                self._fetch_cerebras_models(kilo_gateway_api_key)
            elif backend == 'together':
                self._fetch_together_models(kilo_gateway_api_key)
            elif backend == 'mistral':
                self._fetch_mistral_models(kilo_gateway_api_key)
            elif backend == 'gemini':
                self._fetch_gemini_models(kilo_gateway_api_key)
            else:
                self._fetch_ollama_models()
        finally:
            self._models_fetching = False
            self.log_queue.put(('button', 'Обновить модели'))

    def _fetch_openrouter_models(self, api_key: str) -> None:
        """Загрузить free-модели OpenRouter."""
        try:
            models = fetch_openrouter_free_models(api_key)
            self.log_queue.put(('info', f"OpenRouter: получено {len(models)} free-моделей"))
            self.log_queue.put(('models', ('openrouter', models)))
        except Exception as e:  # noqa: BLE001
            self.log_queue.put(('error', f"Ошибка подключения к OpenRouter: {e}"))
            fallback = get_free_models_for_backend('openrouter')
            self.log_queue.put(('warning', 'OpenRouter недоступен — показан запасной список моделей.'))
            self.log_queue.put(('models', ('openrouter', fallback)))

    def _fetch_cline_models(self, api_key: str) -> None:
        """Загрузить модели Cline API."""
        try:
            models = fetch_cline_models(api_key)
            self.log_queue.put(('models', ('cline', models)))
        except Exception as e:  # noqa: BLE001
            self.log_queue.put(('error', f"Ошибка подключения к Cline API: {e}"))
            fallback = get_free_models_for_backend('cline')
            self.log_queue.put(('warning', 'Cline API недоступен — показан запасной список моделей.'))
            self.log_queue.put(('models', ('cline', fallback)))

    def _fetch_cerebras_models(self, api_key: str) -> None:
        """Загрузить модели Cerebras."""
        try:
            models = fetch_cerebras_models(api_key)
            self.log_queue.put(('models', ('cerebras', models)))
        except Exception as e:  # noqa: BLE001
            self.log_queue.put(('error', f"Ошибка подключения к Cerebras: {e}"))
            fallback = get_free_models_for_backend('cerebras')
            self.log_queue.put(('warning', 'Cerebras недоступен — показан запасной список моделей.'))
            self.log_queue.put(('models', ('cerebras', fallback)))

    def _fetch_together_models(self, api_key: str) -> None:
        """Загрузить модели Together AI."""
        try:
            models = fetch_together_models(api_key)
            self.log_queue.put(('models', ('together', models)))
        except Exception as e:  # noqa: BLE001
            self.log_queue.put(('error', f"Ошибка подключения к Together AI: {e}"))
            fallback = get_free_models_for_backend('together')
            self.log_queue.put(('warning', 'Together AI недоступен — показан запасной список моделей.'))
            self.log_queue.put(('models', ('together', fallback)))

    def _fetch_mistral_models(self, api_key: str) -> None:
        """Загрузить модели Mistral AI."""
        try:
            models = fetch_mistral_models(api_key)
            self.log_queue.put(('models', ('mistral', models)))
        except Exception as e:  # noqa: BLE001
            self.log_queue.put(('error', f"Ошибка подключения к Mistral AI: {e}"))
            fallback = get_free_models_for_backend('mistral')
            self.log_queue.put(('warning', 'Mistral AI недоступен — показан запасной список моделей.'))
            self.log_queue.put(('models', ('mistral', fallback)))

    def _fetch_gemini_models(self, api_key: str) -> None:
        """Загрузить модели Gemini."""
        try:
            models = fetch_gemini_models(api_key)
            self.log_queue.put(('models', ('gemini', models)))
        except Exception as e:  # noqa: BLE001
            self.log_queue.put(('error', f"Ошибка подключения к Gemini: {e}"))
            fallback = get_free_models_for_backend('gemini')
            self.log_queue.put(('warning', 'Gemini недоступен — показан запасной список моделей.'))
            self.log_queue.put(('models', ('gemini', fallback)))

    def _fetch_ollama_models(self) -> None:
        try:
            models = fetch_ollama_models()
            self.log_queue.put(('info', f"Получено {len(models)} моделей от Ollama (после фильтрации)"))
            self.log_queue.put(('models', ('ollama', models)))
        except Exception as e:  # noqa: BLE001
            self.log_queue.put(('error', f"Ошибка подключения к Ollama: {e}. Убедитесь, что сервер запущен."))
            self.log_queue.put(('models', ('ollama', [])))

    def _fetch_kilo_gateway_models(self, kilo_gateway_url, kilo_gateway_api_key) -> None:
        try:
            models = fetch_kilo_gateway_free_models(kilo_gateway_url, kilo_gateway_api_key)
            if models:
                self.log_queue.put(('info', f"Выбрано бесплатных моделей: {models}"))
            else:
                self.log_queue.put(('warning', 'Free-модели в списке Kilo Gateway не найдены — поле выбора пусто.'))
            self.log_queue.put(('models', ('kilo_gateway', models)))
        except Exception as e:  # noqa: BLE001
            self.log_queue.put(('error', f"Ошибка подключения к Kilo Gateway: {e}. Проверьте URL и API ключ."))
            self.log_queue.put(('warning', 'Kilo Gateway недоступен — показан запасной список моделей.'))
            self.log_queue.put(('models', ('kilo_gateway', sorted(KILO_GATEWAY_FREE_MODELS))))

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

        # Ключ и параметры бэкенда фиксируем в .env, чтобы следующий запуск
        # поднял их из настроек, а не требовал повторного ввода.
        self._save_env_settings()

        options = PostAnalysisOptions(
            result_path=result,
            original_path=original,
            change_path=change,
            work_json_path=self.work_json_path.get().strip(),
            output_path=self.output_path.get().strip(),
            model=self.model.get().strip(),
            backend=self.backend.get().strip(),
            extra_options=self.extra_options.get().strip(),
            kilo_gateway_url=self.kilo_gateway_url.get().strip(),
            kilo_gateway_api_key=self.kilo_gateway_api_key.get().strip(),
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
                if level == 'button':
                    self.fetch_models_btn.config(state=tk.NORMAL, text=payload)
                    continue
                self._append_log(str(payload), level)
        except queue.Empty:
            pass
        self.root.after(150, self._poll_log)


def main() -> None:
    root = tk.Tk()
    VerifyApp(root)
    root.mainloop()
