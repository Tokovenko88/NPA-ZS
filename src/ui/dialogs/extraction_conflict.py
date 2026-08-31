"""Dialog for resolving deterministic extraction versus AI content."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class ExtractionConflictDialog:
    """Editable comparison dialog with normal OS decorations and native-like editing."""

    def __init__(self, parent, *, title, context, program_html, ai_html, stop_event=None):
        self.parent = parent
        self.stop_event = stop_event
        self.result = None
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.resizable(True, True)
        self.dialog.minsize(900, 650)
        self.dialog.overrideredirect(False)
        try:
            self.dialog.attributes("-fullscreen", False)
        except tk.TclError:
            pass
        try:
            self.dialog.attributes("-toolwindow", False)
        except tk.TclError:
            pass
        try:
            self.dialog.wm_attributes("-type", "normal")
        except tk.TclError:
            pass

        # Always start as a normal, decorated window rather than a screen-sized
        # window. This keeps the OS title bar and its minimize/maximize/close
        # controls visible on laptops. The user can maximize it manually.
        self.dialog.update_idletasks()
        sw, sh = self.dialog.winfo_screenwidth(), self.dialog.winfo_screenheight()
        width = min(1280, max(1000, int(sw * 0.88)))
        height = min(820, max(680, int(sh * 0.82)))
        x = max(0, (sw - width) // 2)
        y = max(0, (sh - height) // 2)
        self.dialog.geometry(f"{width}x{height}+{x}+{y}")
        try:
            self.dialog.state("normal")
        except tk.TclError:
            pass

        self.dialog.grab_set()
        parent._extraction_conflict_dialog = self.dialog

        outer = ttk.Frame(self.dialog, padding=12)
        outer.pack(fill="both", expand=True)
        ttk.Label(
            outer,
            text=("Программа и ИИ извлекли разные блоки. Проверьте оба варианта. "
                  "Оба поля можно редактировать. Выберите вариант или отредактируйте его."),
            wraplength=max(700, width - 80),
        ).pack(fill="x", pady=(0, 8))

        info = tk.Text(outer, height=8, wrap="word", undo=False)
        info.insert("1.0", context or "")
        info.configure(state="disabled")
        info.pack(fill="x", pady=(0, 8))

        panes = ttk.Panedwindow(outer, orient="horizontal")
        panes.pack(fill="both", expand=True)
        left = ttk.Frame(panes, padding=5)
        right = ttk.Frame(panes, padding=5)
        panes.add(left, weight=1)
        panes.add(right, weight=1)

        ttk.Label(left, text="Вариант программы", font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        self.program_text = tk.Text(left, wrap="word", undo=True, maxundo=-1)
        self.program_text.pack(fill="both", expand=True)
        self.program_text.insert("1.0", program_html or "")

        ttk.Label(right, text="Вариант ИИ (поле content)", font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        self.ai_text = tk.Text(right, wrap="word", undo=True, maxundo=-1)
        self.ai_text.pack(fill="both", expand=True)
        self.ai_text.insert("1.0", ai_html or "")

        self._install_text_editing(self.program_text)
        self._install_text_editing(self.ai_text)

        choice = ttk.Frame(outer)
        choice.pack(fill="x", pady=8)
        self.choice = tk.StringVar(value="ai")
        ttk.Radiobutton(choice, text="Выбрать вариант программы", variable=self.choice, value="program").pack(side="left", padx=(0, 16))
        ttk.Radiobutton(choice, text="Выбрать вариант ИИ", variable=self.choice, value="ai").pack(side="left")

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Использовать выбранный", command=self._accept).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Остановить обработку", command=self._cancel).pack(side="right")

        self.dialog.protocol("WM_DELETE_WINDOW", self._cancel)
        self.dialog.bind("<Escape>", self._shortcut_cancel)
        self.dialog.bind("<Control-KeyPress>", self._shortcut_control)
        self.dialog.focus_force()

    def _install_text_editing(self, widget):
        menu = tk.Menu(widget, tearoff=False)
        menu.add_command(label="Отменить", command=lambda: self._generate(widget, "<<Undo>>"))
        menu.add_separator()
        menu.add_command(label="Вырезать", command=lambda: self._generate(widget, "<<Cut>>"))
        menu.add_command(label="Копировать", command=lambda: self._generate(widget, "<<Copy>>"))
        menu.add_command(label="Вставить", command=lambda: self._generate(widget, "<<Paste>>"))
        menu.add_separator()
        menu.add_command(label="Выделить всё", command=lambda: self._select_all(widget))
        menu.add_command(label="Повторить", command=lambda: self._generate(widget, "<<Redo>>"))

        def popup(event):
            widget.focus_set()
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
            return "break"

        widget.bind("<Button-3>", popup)
        widget.bind("<Button-2>", popup)
        widget.bind("<Control-KeyPress>", lambda event: self._text_control(widget, event), add="+")

    @staticmethod
    def _generate(widget, virtual_event):
        try:
            widget.event_generate(virtual_event)
        except tk.TclError:
            pass

    @staticmethod
    def _select_all(widget):
        widget.focus_set()
        widget.tag_add("sel", "1.0", "end-1c")
        widget.mark_set("insert", "1.0")

    def _text_control(self, widget, event):
        action = self._control_action(event)
        if action in {"copy", "paste", "cut", "all", "undo", "redo"}:
            if action == "all":
                self._select_all(widget)
            else:
                self._generate(widget, {"copy": "<<Copy>>", "paste": "<<Paste>>", "cut": "<<Cut>>", "undo": "<<Undo>>", "redo": "<<Redo>>"}[action])
            return "break"
        if action == "accept":
            self._accept()
            return "break"
        if action == "cancel":
            self._cancel()
            return "break"
        return None

    @staticmethod
    def _control_action(event):
        key = (event.keysym or "").lower()
        by_keysym = {
            "c": "copy", "с": "copy", "cyrillic_es": "copy",
            "v": "paste", "м": "paste", "cyrillic_em": "paste",
            "x": "cut", "ч": "cut", "cyrillic_che": "cut",
            "a": "all", "ф": "all", "cyrillic_ef": "all",
            "z": "undo", "я": "undo", "cyrillic_ya": "undo",
            "y": "redo", "н": "redo", "cyrillic_en": "redo",
            "s": "accept", "ы": "accept", "cyrillic_yeru": "accept",
            "q": "cancel", "й": "cancel", "cyrillic_shorti": "cancel",
        }
        if key in by_keysym:
            return by_keysym[key]
        by_keycode = {
            67: "copy", 86: "paste", 88: "cut", 65: "all", 90: "undo", 89: "redo", 83: "accept", 81: "cancel",
            54: "copy", 55: "paste", 53: "cut", 38: "all", 52: "undo", 29: "redo", 39: "accept", 24: "cancel",
        }
        return by_keycode.get(getattr(event, "keycode", None))

    def _active(self, event=None):
        if getattr(self.parent, "_extraction_conflict_dialog", None) is not self.dialog:
            return False
        if event is None:
            return True
        try:
            return event.widget.winfo_toplevel() is self.dialog
        except tk.TclError:
            return False

    def _shortcut_control(self, event):
        if not self._active(event):
            return None
        action = self._control_action(event)
        if action == "accept":
            self._accept()
            return "break"
        if action == "cancel":
            self._cancel()
            return "break"
        return None

    def _shortcut_cancel(self, event=None):
        if not self._active(event):
            return None
        self._cancel()
        return "break"

    def _accept(self):
        if not self._active():
            return
        self.result = self.program_text.get("1.0", "end-1c") if self.choice.get() == "program" else self.ai_text.get("1.0", "end-1c")
        self._clear()
        self.dialog.destroy()

    def _cancel(self):
        if not self._active():
            return
        self.result = None
        if self.stop_event is not None:
            self.stop_event.set()
        self._clear()
        self.dialog.destroy()

    def _clear(self):
        if getattr(self.parent, "_extraction_conflict_dialog", None) is self.dialog:
            self.parent._extraction_conflict_dialog = None


def resolve_extraction_conflict(parent, *, title, context, program_html, ai_html, stop_event=None):
    existing = getattr(parent, "_extraction_conflict_dialog", None)
    if existing is not None:
        try:
            existing.lift()
            existing.focus_force()
            parent.wait_window(existing)
        except tk.TclError:
            parent._extraction_conflict_dialog = None
    dlg = ExtractionConflictDialog(
        parent,
        title=title,
        context=context,
        program_html=program_html,
        ai_html=ai_html,
        stop_event=stop_event,
    )
    parent.wait_window(dlg.dialog)
    return dlg.result
