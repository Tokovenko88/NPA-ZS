"""Диалог просмотра и правки примечаний элемента НПА.

Примечания в канонической JSON-структуре живут в двух местах:

``item_notes`` элемента
    Примечания к конкретному структурному элементу (статья, часть, пункт...).

``notes`` корня документа
    Примечания к НПА в целом.

Каждое примечание — объект::

    {
      "text": "Действие положений ... распространяется на правоотношения, возникшие с 01.01.2025",
      "valid_from": "01.01.2026",
      "valid_to": "",
      "source_item_id": "768_article_2"
    }

Временная семантика
-------------------
``valid_to`` пустое (``""`` или ``None``) означает «примечание действует».
Когда добавляется новое примечание того же смыслового вида (например, ещё одна
оговорка о распространении на правоотношения), предыдущее закрывается:
``valid_to = дата вступления в силу изменяющего НПА - 1 день`` (если дата
известна; иначе — ``новая valid_from - 1 день``). Автоматически это делает хук
``_append_item_note_with_validity`` в :mod:`npazs.revision`; данный диалог
позволяет проверить и при необходимости поправить результат вручную.

Диалог модальный и всегда создаётся в главном потоке Tk (см.
:mod:`npazs.ui.dialogs`).
"""

from __future__ import annotations

import re
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import messagebox, ttk
from typing import Any, Dict, List, Optional

__all__ = [
    'DATE_FORMAT',
    'NotesDialog',
    'edit_item_notes',
    'parse_date',
    'format_date',
    'close_previous_note',
    'is_active_note',
    'validate_note',
]

#: Единый формат дат в проекте.
DATE_FORMAT = '%d.%m.%Y'

_DATE_RE = re.compile(r'^\d{2}\.\d{2}\.\d{4}$')


def parse_date(value: Any):
    """Разобрать дату ``DD.MM.YYYY``. Вернуть ``date`` или ``None``."""
    text = str(value or '').strip()
    if not _DATE_RE.match(text):
        return None
    try:
        return datetime.strptime(text, DATE_FORMAT).date()
    except ValueError:
        return None


def format_date(value: Any) -> str:
    """Привести ``date``/``datetime`` к строке ``DD.MM.YYYY``."""
    if value is None:
        return ''
    if hasattr(value, 'strftime'):
        return value.strftime(DATE_FORMAT)
    return str(value)


def is_active_note(note: Dict[str, Any]) -> bool:
    """True, если примечание не закрыто (``valid_to`` пустое)."""
    return not str(note.get('valid_to') or '').strip()


def close_previous_note(note: Dict[str, Any], new_valid_from: Any) -> bool:
    """Закрыть примечание днём раньше ``new_valid_from``.

    Возвращает True, если ``valid_to`` был установлен.
    """
    new_date = parse_date(new_valid_from)
    if new_date is None or not is_active_note(note):
        return False
    old_date = parse_date(note.get('valid_from'))
    if old_date is not None and old_date >= new_date:
        return False
    note['valid_to'] = format_date(new_date - timedelta(days=1))
    return True


def validate_note(note: Dict[str, Any]) -> List[str]:
    """Проверить одно примечание. Вернуть список замечаний."""
    problems: List[str] = []
    if not str(note.get('text') or '').strip():
        problems.append('Пустой текст примечания')

    valid_from_raw = str(note.get('valid_from') or '').strip()
    valid_to_raw = str(note.get('valid_to') or '').strip()

    if valid_from_raw and parse_date(valid_from_raw) is None:
        problems.append(f'valid_from="{valid_from_raw}" не в формате ДД.ММ.ГГГГ')
    if valid_to_raw and parse_date(valid_to_raw) is None:
        problems.append(f'valid_to="{valid_to_raw}" не в формате ДД.ММ.ГГГГ')

    start = parse_date(valid_from_raw)
    end = parse_date(valid_to_raw)
    if start and end and end < start:
        problems.append(f'valid_to ({valid_to_raw}) раньше valid_from ({valid_from_raw})')

    return problems


class NotesDialog(tk.Toplevel):
    """Модальное окно списка примечаний с возможностью правки.

    Работает с копией списка. Результат доступен в атрибуте :attr:`result`:
    новый список примечаний при подтверждении либо ``None`` при отмене.
    """

    def __init__(
        self,
        parent: Any,
        notes: Optional[List[Dict[str, Any]]] = None,
        *,
        title: str = 'Примечания элемента',
        element_label: str = '',
        readonly: bool = False,
    ):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.resizable(True, True)
        self.geometry('900x520')

        self.result: Optional[List[Dict[str, Any]]] = None
        self._readonly = readonly
        self._notes: List[Dict[str, Any]] = [dict(n) for n in (notes or [])]

        self._build(element_label)
        self._reload_tree()

        self.protocol('WM_DELETE_WINDOW', self._on_cancel)
        self.grab_set()
        self.wait_visibility()
        self.focus_set()

    # ---------------------------------------------------------------- разметка
    def _build(self, element_label: str) -> None:
        if element_label:
            ttk.Label(self, text=element_label, font=('TkDefaultFont', 10, 'bold')).pack(
                anchor='w', padx=10, pady=(10, 4)
            )

        table_frame = ttk.Frame(self)
        table_frame.pack(fill='both', expand=True, padx=10, pady=4)

        columns = ('valid_from', 'valid_to', 'source', 'text')
        self._tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=10)
        for column, heading, width in (
            ('valid_from', 'Действует с', 100),
            ('valid_to', 'Действует по', 100),
            ('source', 'Источник', 150),
            ('text', 'Текст примечания', 520),
        ):
            self._tree.heading(column, text=heading)
            self._tree.column(column, width=width, anchor='w')

        scroll = ttk.Scrollbar(table_frame, orient='vertical', command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll.set)
        self._tree.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        self._tree.bind('<<TreeviewSelect>>', self._on_select)

        editor = ttk.LabelFrame(self, text='Примечание')
        editor.pack(fill='x', padx=10, pady=4)

        ttk.Label(editor, text='Действует с:').grid(row=0, column=0, sticky='w', padx=6, pady=4)
        self._valid_from = ttk.Entry(editor, width=14)
        self._valid_from.grid(row=0, column=1, sticky='w', padx=6, pady=4)

        ttk.Label(editor, text='Действует по:').grid(row=0, column=2, sticky='w', padx=6, pady=4)
        self._valid_to = ttk.Entry(editor, width=14)
        self._valid_to.grid(row=0, column=3, sticky='w', padx=6, pady=4)

        ttk.Label(editor, text='Источник:').grid(row=0, column=4, sticky='w', padx=6, pady=4)
        self._source = ttk.Entry(editor, width=22)
        self._source.grid(row=0, column=5, sticky='w', padx=6, pady=4)

        ttk.Label(editor, text='Текст:').grid(row=1, column=0, sticky='nw', padx=6, pady=4)
        self._text = tk.Text(editor, height=5, wrap='word')
        self._text.grid(row=1, column=1, columnspan=5, sticky='ew', padx=6, pady=4)
        editor.columnconfigure(5, weight=1)

        buttons = ttk.Frame(self)
        buttons.pack(fill='x', padx=10, pady=(4, 10))

        if not self._readonly:
            ttk.Button(buttons, text='Добавить', command=self._on_add).pack(side='left')
            ttk.Button(buttons, text='Применить', command=self._on_apply).pack(side='left', padx=6)
            ttk.Button(buttons, text='Удалить', command=self._on_delete).pack(side='left')
            ttk.Button(buttons, text='Закрыть примечание', command=self._on_close_note).pack(
                side='left', padx=6
            )
            ttk.Button(buttons, text='Сохранить', command=self._on_ok).pack(side='right')
            ttk.Button(buttons, text='Отмена', command=self._on_cancel).pack(side='right', padx=6)
        else:
            for widget in (self._valid_from, self._valid_to, self._source):
                widget.state(['disabled'])
            self._text.configure(state='disabled')
            ttk.Button(buttons, text='Закрыть', command=self._on_cancel).pack(side='right')

    # ------------------------------------------------------------------ данные
    def _reload_tree(self) -> None:
        self._tree.delete(*self._tree.get_children())
        for index, note in enumerate(self._notes):
            self._tree.insert(
                '',
                'end',
                iid=str(index),
                values=(
                    note.get('valid_from', ''),
                    note.get('valid_to', '') or '— действует —',
                    note.get('source_item_id', '') or '',
                    str(note.get('text', '')).replace('\n', ' ')[:400],
                ),
            )

    def _selected_index(self) -> Optional[int]:
        selection = self._tree.selection()
        if not selection:
            return None
        try:
            return int(selection[0])
        except (TypeError, ValueError):
            return None

    def _form_values(self) -> Dict[str, Any]:
        return {
            'text': self._text.get('1.0', tk.END).strip(),
            'valid_from': self._valid_from.get().strip(),
            'valid_to': self._valid_to.get().strip(),
            'source_item_id': self._source.get().strip(),
        }

    def _fill_form(self, note: Dict[str, Any]) -> None:
        self._valid_from.delete(0, tk.END)
        self._valid_from.insert(0, note.get('valid_from', '') or '')
        self._valid_to.delete(0, tk.END)
        self._valid_to.insert(0, note.get('valid_to', '') or '')
        self._source.delete(0, tk.END)
        self._source.insert(0, note.get('source_item_id', '') or '')
        self._text.delete('1.0', tk.END)
        self._text.insert('1.0', note.get('text', '') or '')

    # ------------------------------------------------------------- обработчики
    def _on_select(self, _event=None) -> None:
        index = self._selected_index()
        if index is None or self._readonly:
            return
        self._fill_form(self._notes[index])

    def _on_add(self) -> None:
        note = self._form_values()
        problems = validate_note(note)
        if problems:
            messagebox.showerror('Некорректное примечание', '\n'.join(problems), parent=self)
            return
        self._notes.append(note)
        self._reload_tree()

    def _on_apply(self) -> None:
        index = self._selected_index()
        if index is None:
            messagebox.showinfo('Примечания', 'Выберите примечание в списке', parent=self)
            return
        note = self._form_values()
        problems = validate_note(note)
        if problems:
            messagebox.showerror('Некорректное примечание', '\n'.join(problems), parent=self)
            return
        self._notes[index] = note
        self._reload_tree()

    def _on_delete(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        if messagebox.askyesno('Удаление', 'Удалить выбранное примечание?', parent=self):
            del self._notes[index]
            self._reload_tree()

    def _on_close_note(self) -> None:
        """Закрыть выбранное примечание датой из поля «Действует с»."""
        index = self._selected_index()
        if index is None:
            messagebox.showinfo('Примечания', 'Выберите примечание в списке', parent=self)
            return
        new_from = self._valid_from.get().strip()
        if parse_date(new_from) is None:
            messagebox.showerror(
                'Некорректная дата',
                'Укажите в поле «Действует с» дату начала нового примечания '
                'в формате ДД.ММ.ГГГГ — выбранное будет закрыто днём раньше.',
                parent=self,
            )
            return
        if close_previous_note(self._notes[index], new_from):
            self._reload_tree()
        else:
            messagebox.showinfo(
                'Примечания',
                'Примечание уже закрыто либо его дата начала не раньше указанной.',
                parent=self,
            )

    def _on_ok(self) -> None:
        problems: List[str] = []
        for index, note in enumerate(self._notes):
            for problem in validate_note(note):
                problems.append(f'[{index + 1}] {problem}')
        if problems:
            messagebox.showerror('Некорректные примечания', '\n'.join(problems), parent=self)
            return
        self.result = self._notes
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()


def edit_item_notes(
    parent: Any,
    element: Dict[str, Any],
    *,
    key: str = 'item_notes',
    element_label: str = '',
    readonly: bool = False,
) -> bool:
    """Открыть диалог примечаний для элемента и записать результат обратно.

    ``element`` изменяется на месте только при подтверждении.
    Возвращает True, если список примечаний был обновлён.
    """
    label = element_label or str(element.get('item_id', '')) or 'НПА'
    dialog = NotesDialog(
        parent,
        element.get(key) or [],
        element_label=label,
        readonly=readonly,
    )
    parent.wait_window(dialog)
    if dialog.result is None:
        return False
    element[key] = dialog.result
    return True
