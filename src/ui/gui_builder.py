"""Mixin для создания графического интерфейса приложения."""

import json
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from npazs._bootstrap import _bootstrap_project_root

_bootstrap_project_root()

from npazs.config.env_store import (
    BACKEND_ENV_KEYS,
    load_backend_settings,
    save_backend_settings,
)
from npazs.constants import (
        BASE_LAW_DIR,
        HTTP_BACKEND_DEFS,
        HTTP_BACKENDS,
        LAST_PATHS_FILE,
        PRODUCTION_BASE_DIR,
        PRODUCTION_BASE_LAW_DIR,
        STAGE_ANSWERS_FILE,
)
from npazs.revision.engine import *
from npazs.revision.json_utils import save_json
from npazs.revision.ui_utils import add_context_menu, add_hotkeys


class GuiBuilderMixin:
        def create_widgets(self):
            row = 0
            self.left_frame.grid_columnconfigure(1, weight=1)
            tk.Label(self.left_frame, text="Оригинальный JSON файл закона:").grid(row=row, column=0, padx=10, pady=8, sticky='e')
            self.entry_orig = tk.Entry(self.left_frame, textvariable=self.original_path)
            self.entry_orig.grid(row=row, column=1, padx=10, pady=8, sticky='ew')
            add_context_menu(self.entry_orig, allow_edit=True)
            add_hotkeys(self.entry_orig, allow_edit=True)
            tk.Button(self.left_frame, text="Выбрать", command=self.browse_original).grid(row=row, column=2, padx=5, pady=8)
            row += 1
            tk.Label(self.left_frame, text="JSON файл с изменениями:").grid(row=row, column=0, padx=10, pady=8, sticky='e')
            self.entry_change = tk.Entry(self.left_frame, textvariable=self.change_path)
            self.entry_change.grid(row=row, column=1, padx=10, pady=8, sticky='ew')
            add_context_menu(self.entry_change, allow_edit=True)
            add_hotkeys(self.entry_change, allow_edit=True)
            tk.Button(self.left_frame, text="Выбрать", command=self.browse_change).grid(row=row, column=2, padx=5, pady=8)
            row += 1
            tk.Label(self.left_frame, text="Реквизиты изменяющего закона:").grid(row=row, column=0, padx=10, pady=8, sticky='e')
            self.entry_law_ref = tk.Entry(self.left_frame, textvariable=self.law_ref)
            self.entry_law_ref.grid(row=row, column=1, padx=10, pady=8, sticky='ew', columnspan=2)
            add_context_menu(self.entry_law_ref, allow_edit=True)
            add_hotkeys(self.entry_law_ref, allow_edit=True)
            row += 1
            tk.Label(self.left_frame, text="Номер оригинального закона:").grid(row=row, column=0, padx=10, pady=8, sticky='e')
            self.entry_original_law = tk.Entry(self.left_frame, textvariable=self.original_law_ref)
            self.entry_original_law.grid(row=row, column=1, padx=10, pady=8, sticky='ew', columnspan=2)
            add_context_menu(self.entry_original_law, allow_edit=True)
            add_hotkeys(self.entry_original_law, allow_edit=True)
            row += 1
            tk.Label(self.left_frame, text="Дата публикации изменяющего закона:").grid(row=row, column=0, padx=10, pady=8, sticky='e')
            self.entry_pub_date = tk.Entry(self.left_frame, textvariable=self.pub_date, width=20, state='readonly')
            self.entry_pub_date.grid(row=row, column=1, padx=10, pady=8, sticky='w', columnspan=2)
            row += 1
            tk.Label(self.left_frame, text="Бэкенд пост-анализа:").grid(row=row, column=0, padx=10, pady=8, sticky='e')
            frame_pa_backend = tk.Frame(self.left_frame)
            frame_pa_backend.grid(row=row, column=1, columnspan=2, sticky='ew', padx=10, pady=8)
            self._pa_backend_buttons = {}
            for _label, _value in (
                ("Ollama", "ollama"),
                ("Kilo", "kilo_gateway"),
                ("Cline", "cline"),
                ("OpenRouter", "openrouter"),
                ("Cerebras", "cerebras"),
                ("Mistral", "mistral"),
                ("Gemini", "gemini"),
                ("FreeDeepseek", "free_deepseek"),
                ("Qwen2API", "qwen2api"),
            ):
                _btn = tk.Radiobutton(
                    frame_pa_backend, text=_label, variable=self.post_analysis_backend,
                    value=_value, command=self.on_post_backend_changed)
                _btn.pack(side=tk.LEFT, padx=3)
                self._pa_backend_buttons[_value] = _btn
            row += 1
            tk.Label(self.left_frame, text="Модель для пост-анализа:").grid(row=row, column=0, padx=10, pady=8, sticky='e')
            frame_post_model = tk.Frame(self.left_frame)
            frame_post_model.grid(row=row, column=1, columnspan=2, sticky='ew', padx=10, pady=8)
            self.post_model_entry = tk.Entry(frame_post_model, textvariable=self.post_analysis_model)
            self.post_model_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,5))
            add_context_menu(self.post_model_entry, allow_edit=True)
            add_hotkeys(self.post_model_entry, allow_edit=True)
            self.post_model_dropdown_btn = tk.Button(frame_post_model, text="▼", width=3, command=self.show_post_model_dropdown)
            self.post_model_dropdown_btn.pack(side=tk.LEFT, padx=(0,5))
            self.post_model_refresh_btn = tk.Button(frame_post_model, text="⟲", width=3, command=self.refresh_post_models)
            self.post_model_refresh_btn.pack(side=tk.LEFT, padx=(0,5))
            row += 1
            # Поля ввода BASE_URL убраны из GUI: URL бэкенда берётся из .env
            # (load_backend_settings / HTTP_BACKEND_DEFS), переменные
            # self.post_gateway_url / self.kilo_gateway_url сохранены —
            # на них опирается логика смены бэкенда и запросов.
            backend_frame = tk.Frame(self.left_frame)
            backend_frame.grid(row=row, column=0, columnspan=3, sticky='w', padx=10, pady=5)
            tk.Label(backend_frame, text="Бэкенд (основной):").pack(side=tk.LEFT, padx=(0,10))
            tk.Radiobutton(backend_frame, text="Ollama", variable=self.backend, value="ollama", command=self.on_backend_changed).pack(side=tk.LEFT, padx=5)
            tk.Radiobutton(backend_frame, text="Kilo Gateway", variable=self.backend, value="kilo_gateway", command=self.on_backend_changed).pack(side=tk.LEFT, padx=5)
            tk.Radiobutton(backend_frame, text="Cline", variable=self.backend, value="cline", command=self.on_backend_changed).pack(side=tk.LEFT, padx=5)
            tk.Radiobutton(backend_frame, text="OpenRouter", variable=self.backend, value="openrouter", command=self.on_backend_changed).pack(side=tk.LEFT, padx=5)
            tk.Radiobutton(backend_frame, text="Cerebras", variable=self.backend, value="cerebras", command=self.on_backend_changed).pack(side=tk.LEFT, padx=5)
            tk.Radiobutton(backend_frame, text="Mistral", variable=self.backend, value="mistral", command=self.on_backend_changed).pack(side=tk.LEFT, padx=5)
            tk.Radiobutton(backend_frame, text="Gemini", variable=self.backend, value="gemini", command=self.on_backend_changed).pack(side=tk.LEFT, padx=5)
            tk.Radiobutton(backend_frame, text="FreeDeepseek", variable=self.backend, value="free_deepseek", command=self.on_backend_changed).pack(side=tk.LEFT, padx=5)
            tk.Radiobutton(backend_frame, text="Qwen2API", variable=self.backend, value="qwen2api", command=self.on_backend_changed).pack(side=tk.LEFT, padx=5)
            row += 1
            tk.Label(self.left_frame, text="Модель:").grid(row=row, column=0, padx=10, pady=8, sticky='e')
            frame_model = tk.Frame(self.left_frame)
            frame_model.grid(row=row, column=1, columnspan=2, sticky='ew', padx=10, pady=8)
            self.model_entry = tk.Entry(frame_model, textvariable=self.ollama_model)
            self.model_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,5))
            add_context_menu(self.model_entry, allow_edit=True)
            add_hotkeys(self.model_entry, allow_edit=True)
            self.model_dropdown_btn = tk.Button(frame_model, text="▼", width=3, command=self.show_model_dropdown)
            self.model_dropdown_btn.pack(side=tk.LEFT, padx=(0,5))
            self.model_refresh_btn = tk.Button(frame_model, text="⟲", width=3, command=self.refresh_models)
            self.model_refresh_btn.pack(side=tk.LEFT, padx=(0,5))
            row += 1
            chk_frame = tk.Frame(self.left_frame)
            chk_frame.grid(row=row, column=0, columnspan=3, sticky='w', padx=10, pady=5)
            tk.Label(chk_frame, text="Режим анализа этапа 3:").pack(side=tk.LEFT, padx=(0,10))
            tk.Radiobutton(chk_frame, text="Целый документ", variable=self.elementwise_mode, value=False).pack(side=tk.LEFT, padx=5)
            tk.Radiobutton(chk_frame, text="Поэлементно", variable=self.elementwise_mode, value=True).pack(side=tk.LEFT, padx=5)
            row += 1
            notebook = ttk.Notebook(self.left_frame)
            notebook.grid(row=row, column=0, columnspan=3, sticky='nsew', padx=10, pady=5)
            self.left_frame.grid_rowconfigure(row, weight=1)
            frame1 = tk.Frame(notebook)
            notebook.add(frame1, text="Этап 1 (утрата силы)")
            tk.Label(frame1, text="Вставьте ответ ИИ для этапа 1 (JSON):").pack(anchor='w', padx=5, pady=2)
            self.stage1_answer_text = tk.Text(frame1, height=10, wrap='word')
            self.stage1_answer_text.pack(fill='both', expand=True, padx=5, pady=2)
            self.stage1_answer_text.insert('1.0', self.stage1_answer.get())
            add_context_menu(self.stage1_answer_text, allow_edit=True)
            add_hotkeys(self.stage1_answer_text, allow_edit=True)
            self.use_stage1_check = tk.Checkbutton(frame1, text="Использовать вставленный ответ (вместо запроса к ИИ)",
                                                    variable=self.use_stage1_answer)
            self.use_stage1_check.pack(anchor='w', padx=5, pady=5)
            tk.Button(frame1, text="Сохранить введённый ответ", command=self.save_stage_answers).pack(pady=5)
            frame2 = tk.Frame(notebook)
            notebook.add(frame2, text="Этап 2 (даты/правоотношения)")
            tk.Label(frame2, text="Вставьте ответ ИИ для этапа 2 (JSON):").pack(anchor='w', padx=5, pady=2)
            self.stage2_answer_text = tk.Text(frame2, height=10, wrap='word')
            self.stage2_answer_text.pack(fill='both', expand=True, padx=5, pady=2)
            self.stage2_answer_text.insert('1.0', self.stage2_answer.get())
            add_context_menu(self.stage2_answer_text, allow_edit=True)
            add_hotkeys(self.stage2_answer_text, allow_edit=True)
            self.use_stage2_check = tk.Checkbutton(frame2, text="Использовать вставленный ответ (вместо запроса к ИИ)",
                                                    variable=self.use_stage2_answer)
            self.use_stage2_check.pack(anchor='w', padx=5, pady=5)
            tk.Button(frame2, text="Сохранить введённый ответ", command=self.save_stage_answers).pack(pady=5)
            frame3 = tk.Frame(notebook)
            notebook.add(frame3, text="Этап 3 (изменения из статьи)")
            tk.Label(frame3, text="Вставьте ответ ИИ для этапа 3 (JSON):").pack(anchor='w', padx=5, pady=2)
            self.stage3_answer_text = tk.Text(frame3, height=10, wrap='word')
            self.stage3_answer_text.pack(fill='both', expand=True, padx=5, pady=2)
            self.stage3_answer_text.insert('1.0', self.stage3_answer.get())
            add_context_menu(self.stage3_answer_text, allow_edit=True)
            add_hotkeys(self.stage3_answer_text, allow_edit=True)
            self.use_stage3_check = tk.Checkbutton(frame3, text="Использовать вставленный ответ (вместо запроса к ИИ)",
                                                    variable=self.use_stage3_answer)
            self.use_stage3_check.pack(anchor='w', padx=5, pady=5)
            tk.Button(frame3, text="Сохранить введённый ответ", command=self.save_stage_answers).pack(pady=5)
            row += 1
            btn_frame = tk.Frame(self.left_frame)
            btn_frame.grid(row=row+1, column=0, columnspan=3, pady=10)
            self.run_btn = tk.Button(btn_frame, text="Запустить", command=self.run_all, bg="#4CAF50", fg="white", font=("Arial", 10, "bold"))
            self.run_btn.pack(side=tk.LEFT, padx=5)
            self.cancel_btn = tk.Button(btn_frame, text="Отмена", command=self.cancel, bg="#f44336", fg="white", font=("Arial", 10, "bold"), state='disabled')
            self.cancel_btn.pack(side=tk.LEFT, padx=5)
            self.status_var = tk.StringVar(value="Готов к работе")
            log_frame = ttk.Frame(self.right_frame)
            log_frame.pack(fill='both', expand=True, padx=5, pady=5)
            scrollbar = ttk.Scrollbar(log_frame)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            self.log_text = tk.Text(log_frame, height=12, wrap='word', font=("Consolas", 9), yscrollcommand=scrollbar.set)
            self.log_text.pack(side=tk.LEFT, fill='both', expand=True)
            scrollbar.config(command=self.log_text.yview)
            add_context_menu(self.log_text, allow_edit=False)
            add_hotkeys(self.log_text, allow_edit=False)
            self.log_text.tag_config('error', foreground='red')
            self.log_text.tag_config('warning', foreground='orange')
            self.log_text.tag_config('info', foreground='gray')
            self.log_text.tag_config('input', foreground='blue')
            self.log_text.tag_config('result', foreground='green')
            self.log_text.tag_config('source', foreground='purple')

        def save_stage_answers(self):
            self.stage1_answer.set(self.stage1_answer_text.get('1.0', tk.END).strip())
            self.stage2_answer.set(self.stage2_answer_text.get('1.0', tk.END).strip())
            self.stage3_answer.set(self.stage3_answer_text.get('1.0', tk.END).strip())
            data = {
                'stage1_answer': self.stage1_answer.get(),
                'stage2_answer': self.stage2_answer.get(),
                'stage3_answer': self.stage3_answer.get(),
                'use_stage1_answer': self.use_stage1_answer.get(),
                'use_stage2_answer': self.use_stage2_answer.get(),
                'use_stage3_answer': self.use_stage3_answer.get(),
            }
            save_json(STAGE_ANSWERS_FILE, data)

        def reset_extra_options(self):
            self.extra_options.set(json.dumps(DEFAULT_EXTRA_OPTIONS))
            self.log("Параметры сброшены к стандартным", 'info')

        def show_model_dropdown(self):
            # Fetch fresh models for the current backend before showing the dropdown
            # so the selector always reflects the active provider's model list.
            threading.Thread(target=lambda: self._fetch_models(try_api=True, target='main'), daemon=True).start()
            menu = tk.Menu(self.root, tearoff=0)
            for model in self.ollama_models:
                menu.add_command(label=model, command=lambda m=model: self.on_model_selected(m))
            if not self.ollama_models:
                self.log("Список моделей пуст. Нажмите кнопку обновления.", 'warning')
            x = self.model_dropdown_btn.winfo_rootx()
            y = self.model_dropdown_btn.winfo_rooty() + self.model_dropdown_btn.winfo_height()
            menu.post(x, y)

        def on_model_selected(self, model):
            self.ollama_model.set(model)

        def show_post_model_dropdown(self):
            # Fetch fresh models for the current post-analysis backend before
            # showing the dropdown so the selector always reflects the active
            # provider's model list.
            threading.Thread(target=lambda: self._fetch_models(try_api=True, target='post'), daemon=True).start()
            menu = tk.Menu(self.root, tearoff=0)
            for model in self.post_analysis_models:
                menu.add_command(label=model, command=lambda m=model: self.on_post_model_selected(m))
            if not self.post_analysis_models:
                self.log("Список моделей пост-анализа пуст. Нажмите кнопку обновления.", 'warning')
            x = self.post_model_dropdown_btn.winfo_rootx()
            y = self.post_model_dropdown_btn.winfo_rooty() + self.post_model_dropdown_btn.winfo_height()
            menu.post(x, y)

        def on_post_model_selected(self, model):
            self.post_analysis_model.set(model)

        def refresh_post_models(self):
            self.log("Обновление списка моделей пост-анализа...", 'info')
            threading.Thread(target=lambda: self._fetch_models(try_api=True, target='post'), daemon=True).start()

        def refresh_models(self):
            self.log("Обновление списка моделей...", 'info')
            threading.Thread(target=lambda: self._fetch_models(try_api=True, target='main'), daemon=True).start()

        def on_post_backend_changed(self):
            backend = self.post_analysis_backend.get()
            # Clear stale models from the previous post-analysis backend so the
            # dropdown doesn't show another provider's models while the fresh
            # fetch (started below) is still in progress.
            self.post_analysis_models = []
            self.log(f"Пост-анализ переключён на {backend}", 'info')
            # Подтянуть модель по умолчанию для пост-бэкенда из .env/констант,
            # только если текущая модель не из его списка.
            try:
                saved = load_backend_settings(backend)
            except ValueError:
                saved = {}
            defn = HTTP_BACKEND_DEFS.get(backend) or {}
            candidates = [m for m in (
                self.post_analysis_model.get().strip(),
                saved.get('model') or '',
                defn.get('default_model') or '',
            ) if m]
            if candidates and not self.post_analysis_model.get().strip():
                # Не затираем введённую вручную модель: меняем только если
                # текущее значение пустое (тогда candidates[0] != '' по фильтру).
                self.post_analysis_model.set(candidates[0])
            if hasattr(self, 'post_gateway_url'):
                # Редактор пост-URL — переопределение поверх бэкенда:
                # значения, равные собственным кредам СТАРОГО пост-бэкенда,
                # считаем наследованием и не тянем за собой.
                _prev = getattr(self, '_prev_post_backend', None)
                if _prev and _prev != backend:
                    try:
                        _prev_saved = load_backend_settings(_prev)
                    except ValueError:
                        _prev_saved = {}
                    _prev_defn = HTTP_BACKEND_DEFS.get(_prev) or {}
                    _prev_url = (_prev_saved.get('base_url')
                                 or _prev_defn.get('base_url') or '').strip()
                    if self.post_gateway_url.get().strip() in ('', _prev_url):
                        self.post_gateway_url.set(
                            saved.get('base_url') or defn.get('base_url') or '')
                self._prev_post_backend = backend
            threading.Thread(target=lambda: self._fetch_models(try_api=True, target='post'), daemon=True).start()

        def on_backend_changed(self):
            backend = self.backend.get()
            # Clear stale models from the previous backend so the dropdown
            # doesn't show another provider's models while the fresh fetch
            # (started below) is still in progress.
            self.ollama_models = []
            if backend in HTTP_BACKENDS:
                self.log(f"Переключено на {backend}", 'info')
                # Автоподстановка URL выбранного бэкенда: сначала
                # сохранённые в .env значения, затем константы HTTP_BACKEND_DEFS.
                defn = HTTP_BACKEND_DEFS.get(backend)
                if defn:
                    saved = load_backend_settings(backend)
                    current_url = self.kilo_gateway_url.get().strip()
                    default_url = defn['base_url']
                    if not current_url or current_url != default_url:
                        self.kilo_gateway_url.set(saved.get('base_url') or default_url)
                    if saved.get('model'):
                        self.ollama_model.set(saved['model'])
            else:
                self.log("Переключено на Ollama", 'info')
                saved = load_backend_settings('ollama')
                if saved.get('model'):
                    self.ollama_model.set(saved['model'])
            # Выбранный бэкенд фиксируем в .env (LLM_BACKEND), но не перезаписываем
            # параметры бэкенда (URL/модель) без явного сохранения.
            self.save_env_settings(quiet=True)
            threading.Thread(target=lambda: self._fetch_models(try_api=True, target='main'), daemon=True).start()

        def save_env_settings(self, quiet=False) -> bool:
            """Сохранить параметры текущего бэкенда (URL, модель) в ``.env``.

            Вызывается при смене бэкенда/модели — API-ключ не сохраняется через GUI.
            Для Ollama URL не перезаписывается переменной kilo_gateway_url.
            """
            backend = self.backend.get().strip() or DEFAULT_BACKEND
            if backend not in BACKEND_ENV_KEYS:
                if not quiet:
                    self.log(f'Неизвестный бэкенд {backend!r}, сохранять нечего', 'warning')
                return False
            try:
                base_url = None if backend == 'ollama' else self.kilo_gateway_url.get().strip()
                written = save_backend_settings(
                    backend,
                    base_url=base_url,
                    model=self.ollama_model.get().strip(),
                )
            except (OSError, ValueError) as e:
                if not quiet:
                    self.log(f'Не удалось сохранить настройки в .env: {e}', 'error')
                return False
            if not quiet:
                self.log(
                    'Настройки бэкенда сохранены в .env: ' + ', '.join(sorted(written)),
                    'info',
                )
            return bool(written)

        def _dialog_initial_dir(self, current_value=''):
            """Каталог для диалога выбора JSON-файла (без привязки к диску).

            Приоритет: каталог текущего значения поля → каталоги из
            ``last_paths`` (только если файлы ещё существуют) → вычисляемая
            рабочая база JSON (``Base`` в том же каталоге, что и папка проекта)
            → база внутри ``data/`` проекта.
            """
            for candidate in (
                current_value,
                (self.last_paths or {}).get('original'),
                (self.last_paths or {}).get('change'),
            ):
                path = str(candidate or '').strip()
                if path and os.path.exists(path):
                    return os.path.dirname(path)
            for directory in (PRODUCTION_BASE_LAW_DIR, PRODUCTION_BASE_DIR, BASE_LAW_DIR):
                if os.path.isdir(directory):
                    return directory
            return ''

        def browse_original(self):
            path = filedialog.askopenfilename(
                initialdir=self._dialog_initial_dir(self.original_path.get()),
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            )
            if path:
                self.original_path.set(path)
                self.last_paths['original'] = path
                save_json(LAST_PATHS_FILE, self.last_paths)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    npa_number = data.get('npa_number', '')
                    if npa_number:
                        self.original_law_ref.set(npa_number)
                        self.log(f"Номер оригинального закона: {npa_number}", 'info')
                    else:
                        self.log("Не удалось извлечь номер оригинального закона.", 'warning')
                except Exception as e:
                    self.log(f"Ошибка при чтении JSON: {e}", 'error')

        def browse_change(self):
            if not self.original_path.get().strip():
                messagebox.showwarning("Внимание", "Сначала выберите оригинальный JSON файл закона.")
                return
            path = filedialog.askopenfilename(
                initialdir=self._dialog_initial_dir(self.change_path.get()),
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            )
            if path:
                self.change_path.set(path)
                self.last_paths['change'] = path
                save_json(LAST_PATHS_FILE, self.last_paths)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        change_data = json.load(f)
                    npa_number = change_data.get('npa_number', '').strip()
                    date_signed = change_data.get('date_signed', '').strip()
                    if npa_number:
                        if date_signed:
                            self.law_ref.set(f"№ {npa_number} от {date_signed}")
                        else:
                            self.law_ref.set(npa_number)
                    else:
                        self.log("Не удалось извлечь номер закона из JSON изменений.", 'warning')
                    pub_date_str = change_data.get('date_pub', '').strip()
                    if not pub_date_str:
                        pub_date_str = change_data.get('date_signed', '').strip()
                    if not pub_date_str:
                        pub_date_str = change_data.get('valid_from', '').strip()
                    if pub_date_str:
                        self.pub_date.set(pub_date_str)
                        self.log(f"Установлена дата публикации изменяющего закона: {pub_date_str}", 'info')
                    else:
                        self.log("В JSON изменений не найдено поле с датой (date_pub, date_signed, valid_from).", 'warning')
                except Exception as e:
                    self.log(f"Ошибка при обработке файла изменений: {e}", 'error')

        def log(self, message, tag=None):
            if not hasattr(self, 'logs'):
                self.logs = []
            self.logs.append((tag, message))
            def _log():
                self.log_text.config(state='normal')
                if tag:
                    self.log_text.insert(tk.END, message + '\n', tag)
                else:
                    if 'ошибка' in message.lower() or '❌' in message or 'failed' in message.lower():
                        self.log_text.insert(tk.END, message + '\n', 'error')
                    elif '⚠' in message or 'warning' in message.lower():
                        self.log_text.insert(tk.END, message + '\n', 'warning')
                    else:
                        self.log_text.insert(tk.END, message + '\n', 'info')
                self.log_text.see(tk.END)
                self.log_text.config(state='normal')
            self.root.after(0, _log)
