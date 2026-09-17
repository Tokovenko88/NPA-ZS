"""Dialog for resolving deterministic extraction versus AI content."""
from __future__ import annotations

import difflib
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

#: Вариант, выбранный в диалоге по умолчанию (программный кандидат).
DEFAULT_EXTRACTION_CHOICE = "program"

#: Стили подсветки различий между вариантами.
#:
#: Совпадающие фрагменты НЕ закрашиваются: сплошной серый фон на всём тексте
#: маскировал единственное реальное расхождение (например, пропущенную точку),
#: и различие приходилось искать глазами. Теперь подсветка трёхуровневая:
#:   * ``diff_block_*`` — светлый фон абзаца/предложения, в котором есть различие;
#:   * ``diff_exact_*`` — насыщенный фон ровно различающихся символов;
#:   * ``diff_marker``  — место, где у одной стороны символа нет вовсе.
_TAG_STYLES = {
    "diff_block_program": {"background": "#ffe4e4"},
    "diff_block_ai": {"background": "#e4ffe4"},
    "diff_exact_program": {"background": "#ff5f5f", "foreground": "#000000", "underline": True},
    "diff_exact_ai": {"background": "#5fd85f", "foreground": "#000000", "underline": True},
    "diff_marker": {"background": "#ffd24d", "foreground": "#000000", "underline": True},
}

#: Сколько различий перечислять в сводке над панелями.
_DIFF_SUMMARY_LIMIT = 5

#: Поиск края предложения при расширении одиночного различия.
_DIFF_SENTENCE_WINDOW = 90

#: Максимальная длина абзаца, который целиком подсвечивается как «блок различия».
_DIFF_BLOCK_LIMIT = 4000

#: Автоматический пересчёт подсветки после ручной правки поля — только для
#: небольших текстов, чтобы правка не тормозила.
_LIVE_HIGHLIGHT_LIMIT = 60000


def _quote_fragment(text, limit=60):
    """Однострочное представление фрагмента для сводки различий."""
    value = (text or "").replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")
    return value if len(value) <= limit else value[:limit] + "…"


def _expand_range(text, start, end, *, block_limit=_DIFF_BLOCK_LIMIT, window=_DIFF_SENTENCE_WINDOW):
    """Расширить диапазон [start, end) до абзаца, а если он огромный — до предложения.

    Одиночный отличающийся символ (например, пропущенная в конце абзаца точка)
    слишком мал, чтобы заметить его на фоне длинного текста. Поэтому вместе с
    точным различием подсвечивается весь содержащий его ``<p>…</p>``.
    """
    if not text or start >= end:
        return None
    para_start = text.rfind("<p", 0, start + 1)
    # Ищем закрывающий тег от начала диапазона: у стороны без собственных
    # символов точка вставки может стоять прямо перед «</p>».
    para_end = text.find("</p>", start)
    if para_start != -1 and para_end != -1:
        para_end += len("</p>")
        if para_end - para_start <= block_limit:
            return (para_start, para_end)
    sentence_start = start
    floor = max(0, start - window)
    while sentence_start > floor and text[sentence_start - 1] not in ".!?;:\n":
        sentence_start -= 1
    sentence_end = end
    ceiling = min(len(text), end + window)
    while sentence_end < ceiling and text[sentence_end - 1] not in ".!?;:\n":
        sentence_end += 1
    return (sentence_start, min(sentence_end, len(text)))


def _side_block(text, start, end):
    """Блок подсветки для одной стороны: точный диапазон либо окно в точке вставки.

    Если у стороны нет собственных символов в этом различии (например, ИИ
    потерял точку), блок считается вокруг точки вставки — иначе один и тот же
    абзац был бы закрашен только в одной панели, и связь между вариантами
    приходилось бы устанавливать глазами.
    """
    if not text:
        return None
    if end > start:
        return _expand_range(text, start, end)
    point = min(start, len(text) - 1)
    return _expand_range(text, point, point + 1)


def _diff_fragments(prog_text, ai_text):
    """Различия между вариантами: точные диапазоны плюс расширенные «блоки».

    Возвращает список словарей с ключами ``op`` (``replace``/``delete``/``insert``),
    ``prog``/``ai`` (точные диапазоны), ``prog_vis``/``ai_vis`` (расширенные
    диапазоны для закраски фона) и ``position`` (смещение различия).
    """
    matcher = difflib.SequenceMatcher(None, prog_text or "", ai_text or "", autojunk=False)
    fragments = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        fragments.append({
            "op": tag,
            "prog": (i1, i2),
            "ai": (j1, j2),
            "prog_vis": _side_block(prog_text, i1, i2),
            "ai_vis": _side_block(ai_text, j1, j2),
            "position": i1 if i2 > i1 else j1,
        })
    return fragments


def _describe_fragment(prog_text, ai_text, fragment):
    """Текстовая расшифровка одного различия для сводки."""
    i1, i2 = fragment["prog"]
    j1, j2 = fragment["ai"]
    position = fragment["position"] + 1
    op = fragment["op"]
    if op == "delete":
        return (f"поз. {position}: в программе лишнее «{_quote_fragment(prog_text[i1:i2])}» — "
                "в варианте ИИ на этом месте символа нет")
    if op == "insert":
        return (f"поз. {position}: в варианте ИИ лишнее «{_quote_fragment(ai_text[j1:j2])}» — "
                "в программе на этом месте символа нет")
    return (f"поз. {position}: программа «{_quote_fragment(prog_text[i1:i2])}» / "
            f"ИИ «{_quote_fragment(ai_text[j1:j2])}»")


def _diff_summary_lines(prog_text, ai_text, fragments, limit=_DIFF_SUMMARY_LIMIT):
    """Строки сводки различий для панели над полями."""
    lines = [
        (
            f"Различий: {len(fragments)}. Красным выделен фрагмент программы, "
            "зелёным — ИИ, жёлтым — место, где у одной стороны символа нет."
        )
    ]
    for index, fragment in enumerate(fragments[:limit], start=1):
        lines.append(f"{index}) {_describe_fragment(prog_text, ai_text, fragment)}")
    if len(fragments) > limit:
        lines.append(f"… и ещё различий: {len(fragments) - limit}")
    return lines


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

        # Окно comparison-диалога открываем на весь экран: на ноутбуках
        # стандартная ширина 800–900 px оставляла кнопки узными, и приходилось
        # либо жать стрелку, либо расширять вручную. Теперь окно сразу
        # разворачивается на весь экран, сохраняя при этом заголовок ОС и
        # кнопки сворачивания/закрытия (state('zoomed') / attributes('-fullscreen')).
        self.dialog.update_idletasks()
        sw, sh = self.dialog.winfo_screenwidth(), self.dialog.winfo_screenheight()
        try:
            self.dialog.state("zoomed")
        except tk.TclError:
            try:
                self.dialog.attributes("-fullscreen", True)
            except tk.TclError:
                self.dialog.geometry(f"{sw}x{sh}+0+0")

        self.dialog.grab_set()
        parent._extraction_conflict_dialog = self.dialog

        outer = ttk.Frame(self.dialog, padding=12)
        outer.pack(fill="both", expand=True)
        ttk.Label(
            outer,
            text=("Программа и ИИ извлекли разные блоки. Проверьте оба варианта. "
                  "Оба поля можно редактировать. Выберите вариант или отредактируйте его. "
                  "Различия подсвечены: красный фон — фрагмент программы, зелёный — ИИ, "
                  "жёлтый — место, где у одной стороны символа нет."),
            wraplength=max(700, sw - 80),
        ).pack(fill="x", pady=(0, 8))

        info = tk.Text(outer, height=6, wrap="word", undo=False)
        info.insert("1.0", context or "")
        info.configure(state="disabled")
        info.pack(fill="x", pady=(0, 8))

        # Сводка различий: перечисляет каждое расхождение словами, чтобы его не
        # приходилось искать глазами по тексту.
        self.diff_summary = tk.Text(outer, height=3, wrap="word", undo=False, background="#fffbe6")
        self.diff_summary.configure(state="disabled")
        self.diff_summary.pack(fill="x", pady=(0, 8))

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

        # Синхронизировать прокрутку между виджетами
        self.program_text.bind("<MouseWheel>", self._sync_scroll, add="+")
        self.ai_text.bind("<MouseWheel>", self._sync_scroll, add="+")
        self.program_text.bind("<Button-4>", self._sync_scroll, add="+")  # Linux scroll up
        self.ai_text.bind("<Button-4>", self._sync_scroll, add="+")
        self.program_text.bind("<Button-5>", self._sync_scroll, add="+")  # Linux scroll down
        self.ai_text.bind("<Button-5>", self._sync_scroll, add="+")

        # Применяем подсветку различий между вариантами
        self._highlight_job = None
        self._apply_diff_highlight()

        # После ручной правки разметку и сводку нужно пересчитать: иначе
        # пользователь правит поле по устаревшим отметкам различий.
        for widget in (self.program_text, self.ai_text):
            widget.bind("<<Modified>>", self._on_text_modified, add="+")
            widget.edit_modified(False)

        choice = ttk.Frame(outer)
        choice.pack(fill="x", pady=8)
        self.choice = tk.StringVar(value=DEFAULT_EXTRACTION_CHOICE)
        ttk.Radiobutton(choice, text="Выбрать вариант программы", variable=self.choice, value="program").pack(side="left", padx=(0, 16))
        ttk.Radiobutton(choice, text="Выбрать вариант ИИ", variable=self.choice, value="ai").pack(side="left")

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=8)
        # Кнопки на ноутбуке по умолчанию были узкими — приходилось либо
        # расширять вручную, либо пользоваться прокруткой. Делаем их
        # просторными: каждый занимает ~1/3 ширины, с отступами.
        for col in range(3):
            buttons.columnconfigure(col, weight=1)
        self._accept_btn = ttk.Button(buttons, text="Использовать выбранный", command=self._accept)
        self._accept_btn.grid(row=0, column=0, padx=8, sticky="ew")
        self._cancel_btn = ttk.Button(buttons, text="Остановить обработку", command=self._cancel)
        self._cancel_btn.grid(row=0, column=1, padx=8, sticky="ew")
        # Пустая ячейка для баланса ширины.
        ttk.Frame(buttons).grid(row=0, column=2, padx=8, sticky="ew")

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

    def _sync_scroll(self, event=None):
        """Синхронизировать прокрутку между двумя текстовыми виджетами."""
        if event is None:
            return
        # Определяем источник события и синхронизируем другой виджет
        if event.widget == self.program_text:
            target = self.ai_text
        else:
            target = self.program_text
        
        # Получаем позицию прокрутки из источника
        first, last = event.widget.yview()
        target.yview_moveto(first)

    def _apply_diff_highlight(self, *, scroll=True):
        """Подсветить различия между программным и ИИ вариантами.

        Совпадающие фрагменты не закрашиваются. Различие подсвечивается в три
        уровня: ``diff_block_*`` (абзац или предложение, где оно находится),
        ``diff_exact_*`` (точные различающиеся символы) и ``diff_marker``
        (место, где у одной стороны символа нет). Плюс сводка различий над
        панелями и прокрутка к первому из них.
        """
        prog_text = self.program_text.get("1.0", "end-1c") or ""
        ai_text = self.ai_text.get("1.0", "end-1c") or ""

        self._configure_diff_tags()
        self._clear_diff_tags(self.program_text)
        self._clear_diff_tags(self.ai_text)

        if not prog_text or not ai_text:
            self._set_diff_summary("Один из вариантов пуст: различия не подсвечены.")
            return

        fragments = _diff_fragments(prog_text, ai_text)
        if not fragments:
            self._set_diff_summary("Различий нет: варианты совпадают посимвольно.")
            return

        for fragment in fragments:
            self._tag_fragment(fragment, prog_text, ai_text)

        self._set_diff_summary("\n".join(_diff_summary_lines(prog_text, ai_text, fragments)))
        if scroll:
            self._scroll_to_first_difference(fragments)

    def _configure_diff_tags(self):
        """Настроить теги подсветки в обоих полях."""
        bold = tkfont.nametofont("TkDefaultFont").copy()
        bold.configure(weight="bold")
        for widget in (self.program_text, self.ai_text):
            for tag_name, options in _TAG_STYLES.items():
                widget.tag_configure(tag_name, **options)
            for tag_name in ("diff_exact_program", "diff_exact_ai", "diff_marker"):
                widget.tag_configure(tag_name, font=bold)
            # Яркие теги должны перекрывать фоновый блок различия.
            widget.tag_raise("diff_block_program")
            widget.tag_raise("diff_block_ai")
            widget.tag_raise("diff_exact_program")
            widget.tag_raise("diff_exact_ai")
            widget.tag_raise("diff_marker")

    def _tag_fragment(self, fragment, prog_text, ai_text):
        """Отметить одно различие в обоих полях."""
        i1, i2 = fragment["prog"]
        j1, j2 = fragment["ai"]
        prog_vis = fragment["prog_vis"]
        ai_vis = fragment["ai_vis"]
        if prog_vis:
            self._tag_range(self.program_text, "diff_block_program", prog_vis[0], prog_vis[1])
        if ai_vis:
            self._tag_range(self.ai_text, "diff_block_ai", ai_vis[0], ai_vis[1])
        if i2 > i1:
            self._tag_range(self.program_text, "diff_exact_program", i1, i2)
        if j2 > j1:
            self._tag_range(self.ai_text, "diff_exact_ai", j1, j2)
        if fragment["op"] == "delete":
            # Символ есть только у программы — отмечаем место пропуска у ИИ.
            self._tag_range(self.ai_text, "diff_marker", *self._marker_range(ai_text, j1))
        elif fragment["op"] == "insert":
            # Символ есть только у ИИ — отмечаем место пропуска у программы.
            self._tag_range(self.program_text, "diff_marker", *self._marker_range(prog_text, i1))

    @staticmethod
    def _marker_range(text, point):
        """Два символа вокруг места, где у варианта символа нет.

        Пустой диапазон в Tk невидим, поэтому отмечаем соседей точки пропуска.
        """
        if not text:
            return (0, 0)
        return (max(0, point - 1), min(len(text), point + 1))

    def _scroll_to_first_difference(self, fragments):
        """Прокрутить оба поля к первому различию, чтобы оно было на виду."""
        first = fragments[0]
        prog_pos = first["prog_vis"] or first["prog"]
        ai_pos = first["ai_vis"] or first["ai"]
        try:
            self.program_text.see(self._index(prog_pos[0]))
            self.ai_text.see(self._index(ai_pos[0]))
        except tk.TclError:
            pass

    def _set_diff_summary(self, text):
        """Показать сводку различий над панелями."""
        try:
            self.diff_summary.configure(state="normal")
            self.diff_summary.delete("1.0", "end")
            self.diff_summary.insert("1.0", text or "")
            self.diff_summary.configure(state="disabled")
        except tk.TclError:
            pass

    def _on_text_modified(self, event=None):
        """Пересчитать подсветку после ручной правки поля (с задержкой)."""
        widget = event.widget if event is not None else None
        if widget is not None:
            try:
                widget.edit_modified(False)
            except tk.TclError:
                return
        prog_len = len(self.program_text.get("1.0", "end-1c"))
        ai_len = len(self.ai_text.get("1.0", "end-1c"))
        if prog_len + ai_len > _LIVE_HIGHLIGHT_LIMIT:
            return
        if self._highlight_job is not None:
            try:
                self.dialog.after_cancel(self._highlight_job)
            except tk.TclError:
                pass
        self._highlight_job = self.dialog.after(400, self._refresh_highlight)

    def _refresh_highlight(self):
        """Обновить разметку без прокрутки — пользователь правит текст руками."""
        self._highlight_job = None
        try:
            self._apply_diff_highlight(scroll=False)
        except tk.TclError:
            pass

    @staticmethod
    def _index(offset):
        """Индекс Tk по абсолютному смещению символов.

        ``1.<N>`` работает только внутри первой строки: после первого перевода
        строки такой индекс схлопывается в пустой диапазон, и подсветка молча
        пропадала. ``1.0+<N>c`` считает смещение по всему тексту.
        """
        return f"1.0+{max(0, int(offset))}c"

    def _tag_range(self, widget, tag_name, start, end):
        """Добавить тег по абсолютным смещениям символов."""
        if end <= start:
            return
        try:
            widget.tag_add(tag_name, self._index(start), self._index(end))
        except tk.TclError:
            pass

    def _clear_diff_tags(self, text_widget):
        """Удалить все теги подсветки из виджета."""
        for tag_name in _TAG_STYLES:
            try:
                text_widget.tag_remove(tag_name, "1.0", "end")
            except tk.TclError:
                pass

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
        if self._highlight_job is not None:
            try:
                self.dialog.after_cancel(self._highlight_job)
            except tk.TclError:
                pass
            self._highlight_job = None
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
