"""Графический интерфейс модуля сравнения редакций НПА.

Окно: два поля выбора файлов (документ проекта / документ правовой
системы), параметры запуска, кнопка «Сравнить» и журнал работы. Сравнение
выполняется в фоновом потоке; журнал читается из очереди в главном потоке
(тот же приём, что в ``npazs.ui.revision_app``).
"""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

from .runner import CompareOptions, run_compare

__all__ = ['CompareApp', 'main']

FILETYPES = [
    ('Документы НПА (RTF/DOCX/DOC)', '*.rtf *.docx *.doc'),
    ('RTF', '*.rtf'),
    ('DOCX', '*.docx'),
    ('DOC', '*.doc'),
    ('HTML', '*.html *.htm'),
    ('Текст', '*.txt *.md'),
    ('Все файлы', '*.*'),
]

_LEVEL_TAGS = {
    'info': ('info',),
    'warning': ('warning',),
    'error': ('error',),
    'success': ('success',),
}


class CompareApp:
    """Главное окно модуля сравнения."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title('NPA-ZS — Сравнение редакций НПА')
        root.geometry('860x640')

        self.ours_path = tk.StringVar()
        self.theirs_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.target_number = tk.StringVar()
        self.model = tk.StringVar()
        self.mode = tk.StringVar(value='agent')
        self.resume = tk.BooleanVar(value=True)

        self.log_queue: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None

        self._create_widgets()
        self._poll_log()

    # ------------------------------------------------------------- widgets
    def _create_widgets(self) -> None:
        pad = {'padx': 8, 'pady': 4}

        frame = tk.Frame(self.root)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        tk.Label(frame, text='Документ проекта (RTF/DOCX/DOC):').grid(
            row=0, column=0, sticky='e', **pad
        )
        tk.Entry(frame, textvariable=self.ours_path).grid(
            row=0, column=1, sticky='ew', **pad
        )
        tk.Button(frame, text='Выбрать…', command=self._browse_ours).grid(
            row=0, column=2, **pad
        )

        tk.Label(frame, text='Документ правовой системы:').grid(
            row=1, column=0, sticky='e', **pad
        )
        tk.Entry(frame, textvariable=self.theirs_path).grid(
            row=1, column=1, sticky='ew', **pad
        )
        tk.Button(frame, text='Выбрать…', command=self._browse_theirs).grid(
            row=1, column=2, **pad
        )

        tk.Label(frame, text='Отчёт (Markdown):').grid(
            row=2, column=0, sticky='e', **pad
        )
        tk.Entry(frame, textvariable=self.output_path).grid(
            row=2, column=1, sticky='ew', **pad
        )
        tk.Button(frame, text='Сохранить как…', command=self._browse_output).grid(
            row=2, column=2, **pad
        )

        tk.Label(frame, text='Номер целевого НПА (пусто — авто):').grid(
            row=3, column=0, sticky='e', **pad
        )
        tk.Entry(frame, textvariable=self.target_number, width=20).grid(
            row=3, column=1, sticky='w', **pad
        )

        mode_frame = tk.Frame(frame)
        mode_frame.grid(row=4, column=0, columnspan=3, sticky='w', **pad)
        tk.Label(mode_frame, text='Режим:').pack(side=tk.LEFT, padx=(0, 8))
        tk.Radiobutton(
            mode_frame, text='Агент (ИИ)', variable=self.mode, value='agent'
        ).pack(side=tk.LEFT, padx=4)
        tk.Radiobutton(
            mode_frame, text='Механический (без ИИ)', variable=self.mode,
            value='mechanical',
        ).pack(side=tk.LEFT, padx=4)
        tk.Label(mode_frame, text='Модель:').pack(side=tk.LEFT, padx=(16, 4))
        tk.Entry(mode_frame, textvariable=self.model, width=24).pack(side=tk.LEFT)
        tk.Checkbutton(
            mode_frame, text='Возобновлять с чекпойнта', variable=self.resume
        ).pack(side=tk.LEFT, padx=(16, 0))

        btn_frame = tk.Frame(frame)
        btn_frame.grid(row=5, column=0, columnspan=3, sticky='w', **pad)
        self.run_button = tk.Button(
            btn_frame, text='Сравнить', command=self._start, width=18,
            bg='#e8f0e8',
        )
        self.run_button.pack(side=tk.LEFT, padx=(0, 8))
        self.stop_button = tk.Button(
            btn_frame, text='Остановить', command=self._stop, width=14,
            state=tk.DISABLED,
        )
        self.stop_button.pack(side=tk.LEFT)

        tk.Label(frame, text='Журнал работы:').grid(
            row=6, column=0, sticky='w', **pad
        )
        log_frame = tk.Frame(frame)
        log_frame.grid(row=7, column=0, columnspan=3, sticky='nsew', **pad)
        frame.grid_rowconfigure(7, weight=1)
        frame.grid_columnconfigure(1, weight=1)

        scrollbar = tk.Scrollbar(log_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text = tk.Text(
            log_frame, height=16, wrap='word', state=tk.DISABLED,
            yscrollcommand=scrollbar.set,
        )
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.log_text.yview)

        for tag, cfg in (
            ('warning', {'foreground': '#b06000'}),
            ('error', {'foreground': '#a01010'}),
            ('success', {'foreground': '#107010'}),
        ):
            self.log_text.tag_configure(tag, **cfg)

    # ------------------------------------------------------------ browsing
    def _browse_ours(self) -> None:
        path = filedialog.askopenfilename(title='Документ проекта', filetypes=FILETYPES)
        if path:
            self.ours_path.set(path)

    def _browse_theirs(self) -> None:
        path = filedialog.askopenfilename(
            title='Документ правовой системы', filetypes=FILETYPES
        )
        if path:
            self.theirs_path.set(path)

    def _browse_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title='Куда сохранить отчёт',
            defaultextension='.md',
            filetypes=[('Markdown', '*.md'), ('Все файлы', '*.*')],
        )
        if path:
            self.output_path.set(path)

    # ------------------------------------------------------------- actions
    def _append_log(self, msg: str, level: str = 'info') -> None:
        self.log_text.config(state=tk.NORMAL)
        tags = _LEVEL_TAGS.get(level, ('info',))
        self.log_text.insert(tk.END, msg + '\n', tags)
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

    def _set_running(self, running: bool) -> None:
        self.run_button.config(state=tk.DISABLED if running else tk.NORMAL)
        self.stop_button.config(state=tk.NORMAL if running else tk.DISABLED)

    def _start(self) -> None:
        ours = self.ours_path.get().strip()
        theirs = self.theirs_path.get().strip()
        if not ours or not theirs:
            messagebox.showwarning(
                'Сравнение', 'Выберите оба файла: документ проекта и документ правовой системы.'
            )
            return
        for path in (ours, theirs):
            if not os.path.isfile(path):
                messagebox.showerror('Сравнение', f'Файл не найден:\n{path}')
                return

        options = CompareOptions(
            ours_path=ours,
            theirs_path=theirs,
            output_path=self.output_path.get().strip(),
            target_number=self.target_number.get().strip(),
            mode=self.mode.get(),
            model=self.model.get().strip(),
            resume=bool(self.resume.get()),
        )
        self.stop_event.clear()
        self._set_running(True)
        self._append_log('=== Запуск сравнения ===')
        self.worker = threading.Thread(target=self._worker, args=(options,), daemon=True)
        self.worker.start()

    def _stop(self) -> None:
        self.stop_event.set()
        self._append_log('Остановка запрошена…', 'warning')

    def _worker(self, options: CompareOptions) -> None:
        def log(msg: str, level: str = 'info') -> None:
            self.log_queue.put((level, msg))

        try:
            result = run_compare(options, log=log, stop_event=self.stop_event)
            self.log_queue.put(('done', result))
        except Exception as error:
            self.log_queue.put(('error', f'Ошибка: {error}'))
            self.log_queue.put(('failed', None))

    def _on_done(self, result) -> None:
        self._set_running(False)
        stats = result.diff_stats
        self._append_log(
            f"Готово. Различий: {result.diffs_count} "
            f"(замена={stats.get('change', 0)}, добавление={stats.get('add', 0)}, "
            f"удаление={stats.get('remove', 0)}).",
            'success',
        )
        if result.stopped:
            self._append_log('Сравнение остановлено — чекпойнт сохранён.', 'warning')
        messagebox.showinfo('Сравнение завершено', f'Отчёт сохранён:\n{result.output_path}')


def main() -> None:
    """Запустить GUI сравнения."""
    root = tk.Tk()
    CompareApp(root)
    root.mainloop()
