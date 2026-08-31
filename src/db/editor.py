import sys
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog
from tkinter.constants import *
from datetime import date, timedelta
from typing import Dict, List, Tuple, Any, Optional
import re
import os
from pathlib import Path

try:
    import pymysql
except ImportError:
    pymysql = None

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from npazs.db.schema import is_known_table, ALL_TABLES

_IDENTIFIER_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')


def _validate_table_name(table_name: str) -> str:
    if not _IDENTIFIER_RE.match(table_name):
        raise ValueError(f'Недопустимое имя таблицы: {table_name!r}')
    if table_name not in ALL_TABLES:
        raise ValueError(f'Неизвестная таблица: {table_name!r}')
    return table_name


def _validate_column_name(column_name: str) -> str:
    if not _IDENTIFIER_RE.match(column_name):
        raise ValueError(f'Недопустимое имя колонки: {column_name!r}')
    return column_name


def get_display_field_for_table(table_name: str) -> str:
    table_name = _validate_table_name(table_name)
    display_map = {
        'person': 'fio',
        'convocation': 'name',
        'person_post': 'name',
        'committees': 'name',
        'npa_base': 'npa_number',
        'npa_item': 'item_id',
        'npa_law': 'npa_id',
        'npa_regulation': 'npa_id',
        'npa_author_link': 'id',
        'npa_signatory': 'id',
        'npa_committee_link': 'id',
        'npa_note_unified': 'note_text',
        'npa_item_number_revision': 'number_text',
        'npa_item_revision': 'rev_id',
        'npa_item_head_revision': 'head_text',
        'npa_item_prefix_revision': 'prefix_text',
        'npa_head_revision': 'npa_title',
        'npa_paragraph': 'para_id',
        'npa_revision_info': 'revision_number',
    }
    return display_map.get(table_name, 'id')


def load_db_config() -> Dict[str, Any]:
    env_path = Path(__file__).resolve().parents[2] / '.env'
    if not env_path.exists():
        env_path = Path.cwd() / '.env'
    if not env_path.exists() and getattr(sys, 'frozen', False):
        env_path = Path(sys.executable).parent / '.env'
    if load_dotenv is not None:
        load_dotenv(dotenv_path=env_path, override=False)

    cursorclass = pymysql.cursors.DictCursor if pymysql is not None else None
    config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', '3306')),
        'user': os.getenv('DB_USER', ''),
        'password': os.getenv('DB_PASSWORD', ''),
        'database': os.getenv('DB_NAME', ''),
        'charset': 'utf8mb4',
        'cursorclass': cursorclass,
        'autocommit': False,
    }

    missing = [name for name, value in [('DB_HOST', config['host']), ('DB_USER', config['user']), ('DB_PASSWORD', config['password']), ('DB_NAME', config['database'])] if not value]
    if missing:
        messagebox.showerror('Ошибка', 'Отсутствуют обязательные переменные окружения для подключения к БД:\n' + ', '.join(missing))
        sys.exit(1)

    return config


DB_CONFIG = load_db_config()

FIELD_LABELS = {
    'npa_base': {
        'npa_id': 'ID НПА',
        'npa_type': 'Тип',
        'npa_number': 'Номер',
        'npa_url': 'URL',
        'date_reg': 'Дата регистрации',
        'date_passed': 'Дата принятия',
        'date_pub': 'Дата публикации',
        'valid_from': 'Дата вступления в силу',
        'not_valid': 'Дата утраты силы',
        'not_valid_note': 'Примечание об утрате',
        'not_valid_npa_id': 'ID НПА-замены',
        'pub_info': 'Публикация',
        'pub_filepath': 'Путь к публикации',
        'date_cons': 'Дата подготовки',
        'date_format': 'Формат дат',
        'no_name': 'no_name',
        'npa_signer_post': 'Должность подписанта',
        'npa_signer': 'Подписант',
        'term_number': 'Номер созыва',
        'session_number': 'Номер сессии',
        'npa_author': 'Автор',
        'npa_npa_committee': 'Комитет',
    },
    'npa_item': {
        'id': 'Внутренний ID',
        'npa_id': 'ID НПА',
        'item_id': 'item_id',
        'parent_id': 'Родитель',
        'item_type': 'Тип элемента',
        'item_number': 'Номер',
        'item_level': 'Уровень',
        'sort_order': 'Порядок',
    },
    'npa_note_unified': {
        'id': 'ID записи',
        'npa_id': 'ID НПА',
        'target_type': 'Тип объекта',
        'target_id': 'ID объекта',
        'note_text': 'Текст примечания',
        'valid_from': 'Действует с',
        'valid_to': 'Действует до',
    },
    'person': {'fio': 'ФИО'},
    'person_post': {'name': 'Должность', 'convocation_id': 'Созыв', 'display_mode': 'Режим отображения', 'is_active': 'Активна'},
    'committees': {'name': 'Название комитета'},
    'convocation': {'name': 'Название созыва'},
    'npa_law': {'date_1st_reading': '1 чтение', 'date_2nd_reading': '2 чтение', 'date_signed': 'Дата подписания'},
    'npa_regulation': {'term_number': 'Номер созыва', 'session_number': 'Номер сессии'},
    'npa_author_link': {'person_id': 'Лицо', 'person_post_id': 'Должность'},
    'npa_signatory': {'person_id': 'Подписант', 'person_post_id': 'Должность'},
    'npa_committee_link': {'committee_id': 'Комитет'},
}

TABLE_FIELD_ORDER = {
    'npa_note_unified': ['note_text', 'valid_from', 'valid_to', 'target_type', 'target_id'],
    'npa_item': ['item_id', 'item_type', 'item_number', 'parent_id', 'item_level', 'sort_order'],
    'npa_base': ['npa_number', 'npa_type', 'npa_url', 'date_reg', 'date_passed', 'date_pub', 'valid_from', 'not_valid', 'npa_author', 'npa_npa_committee', 'npa_signer_post', 'npa_signer', 'pub_info', 'pub_filepath'],
}

SKIP_FIELDS = {
    'npa_note_unified': {'id', 'npa_id'},
    'npa_item': {'id', 'npa_id'},
}


def get_column_display_name(table_name: str, column_name: str) -> str:
    labels = FIELD_LABELS.get(table_name, {})
    if column_name in labels:
        return labels[column_name]
    return column_name.replace('_', ' ').title()


class DatabaseManager:
    def __init__(self):
        self.connection = None

    def connect(self):
        if pymysql is None:
            messagebox.showerror("Ошибка подключения", "Библиотека pymysql не установлена")
            return False
        try:
            self.connection = pymysql.connect(**DB_CONFIG)
            return True
        except Exception as e:
            messagebox.showerror("Ошибка подключения", f"Не удалось подключиться к БД:\n{e}")
            return False

    def execute_query(self, query: str, params: tuple = ()) -> List[Dict]:
        if not self.connection and not self.connect():
            return []
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, params)
                return cursor.fetchall()
        except Exception as e:
            messagebox.showerror("Ошибка запроса", f"Ошибка при выполнении запроса:\n{query}\n{e}")
            return []

    def execute_update(self, query: str, params: tuple = ()) -> bool:
        if not self.connection and not self.connect():
            return False
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, params)
                self.connection.commit()
                return True
        except pymysql.err.IntegrityError as e:
            messagebox.showerror("Ошибка целостности", f"Невозможно выполнить операцию из-за внешних ключей:\n{e}")
            return False
        except Exception as e:
            messagebox.showerror("Ошибка запроса", f"Ошибка при выполнении запроса:\n{query}\n{e}")
            return False

    def get_table_columns(self, table_name: str) -> List[Dict]:
        query = """
            SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_KEY, EXTRA
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
        """
        rows = self.execute_query(query, (DB_CONFIG['database'], table_name))
        if rows:
            return rows
        return []

    def get_foreign_keys(self, table_name: str) -> Dict[str, Dict]:
        query = """
            SELECT 
                kcu.COLUMN_NAME,
                kcu.REFERENCED_TABLE_NAME,
                kcu.REFERENCED_COLUMN_NAME
            FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
            WHERE kcu.TABLE_SCHEMA = %s 
              AND kcu.TABLE_NAME = %s
              AND kcu.REFERENCED_TABLE_NAME IS NOT NULL
        """
        rows = self.execute_query(query, (DB_CONFIG['database'], table_name))
        return {row['COLUMN_NAME']: {
            'referenced_table': row['REFERENCED_TABLE_NAME'],
            'referenced_column': row['REFERENCED_COLUMN_NAME']
        } for row in rows}

    def get_choices_for_fk(self, referenced_table: str, referenced_column: str) -> List[Tuple[Any, str]]:
        display_field = get_display_field_for_table(referenced_table)
        referenced_column = _validate_column_name(referenced_column)
        query = f"SELECT {referenced_column} as id, {display_field} as display FROM {_validate_table_name(referenced_table)}"
        rows = self.execute_query(query)
        return [(row['id'], row['display']) for row in rows]

    def get_all_table_names(self) -> List[str]:
        query = """
            SELECT TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_NAME
        """
        rows = self.execute_query(query, (DB_CONFIG['database'],))
        exclude = ['npa_item_revision', 'npa_item_head_revision', 'npa_item_number_revision',
                   'npa_item_prefix_revision', 'npa_head_revision', 'npa_paragraph',
                   'npa_rendered_cache', 'npa_revision_info']
        return [row['TABLE_NAME'] for row in rows if row['TABLE_NAME'] not in exclude]

    def get_npa_list_by_type_year(self, npa_type: str, year: int) -> List[Dict]:
        if npa_type == 'law':
            query = """
                SELECT b.npa_id, b.npa_number, b.npa_type, l.date_signed as relevant_date
                FROM npa_base b
                JOIN npa_law l ON b.npa_id = l.npa_id
                WHERE b.npa_type = %s AND YEAR(l.date_signed) = %s
                ORDER BY b.npa_number
            """
        else:
            query = """
                SELECT b.npa_id, b.npa_number, b.npa_type, b.date_passed as relevant_date
                FROM npa_base b
                WHERE b.npa_type = %s AND YEAR(b.date_passed) = %s
                ORDER BY b.npa_number
            """
        return self.execute_query(query, (npa_type, year))

    def get_npa_full_data(self, npa_id: int) -> Dict:
        base = self.execute_query("SELECT * FROM npa_base WHERE npa_id = %s", (npa_id,))
        if not base:
            return {}
        data = base[0]
        if data['npa_type'] == 'law':
            law = self.execute_query("SELECT * FROM npa_law WHERE npa_id = %s", (npa_id,))
            if law:
                data.update(law[0])
        else:
            reg = self.execute_query("SELECT * FROM npa_regulation WHERE npa_id = %s", (npa_id,))
            if reg:
                data.update(reg[0])
        return data

    def get_npa_items(self, npa_id: int) -> List[Dict]:
        query = """
            SELECT id, item_id, parent_id, item_type, item_number, item_level, sort_order
            FROM npa_item
            WHERE npa_id = %s
            ORDER BY sort_order, id
        """
        return self.execute_query(query, (npa_id,))

    def get_npa_notes(self, npa_id: int, target_type: Optional[str] = None, target_id: Optional[str] = None) -> List[Dict]:
        query = "SELECT id, npa_id, target_type, target_id, note_text, valid_from, valid_to FROM npa_note_unified WHERE npa_id = %s"
        params: Tuple[Any, ...] = (npa_id,)
        if target_type is not None:
            query += " AND target_type = %s"
            params = params + (target_type,)
        if target_id is not None:
            query += " AND target_id = %s"
            params = params + (target_id,)
        query += " ORDER BY valid_from, id"
        return self.execute_query(query, params)

    def add_note(self, npa_id: int, target_type: str, target_id: Optional[str], note_text: str,
                 valid_from: Optional[date], valid_to: Optional[date]) -> bool:
        query = """
            INSERT INTO npa_note_unified (npa_id, target_type, target_id, note_text, valid_from, valid_to)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        return self.execute_update(query, (npa_id, target_type, target_id, note_text, valid_from, valid_to))

    def update_note(self, note_id: int, target_type: str, target_id: Optional[str], note_text: str,
                    valid_from: Optional[date], valid_to: Optional[date]) -> bool:
        query = """
            UPDATE npa_note_unified
            SET target_type = %s, target_id = %s, note_text = %s, valid_from = %s, valid_to = %s
            WHERE id = %s
        """
        return self.execute_update(query, (target_type, target_id, note_text, valid_from, valid_to, note_id))

    def delete_note(self, note_id: int) -> bool:
        return self.execute_update("DELETE FROM npa_note_unified WHERE id = %s", (note_id,))

    def get_item_revision_history(self, item_internal_id: int) -> List[Dict]:
        query = """
            SELECT rev_id, valid_from, valid_to, mod_type, modified_by_id, highlights, not_valid
            FROM npa_item_revision
            WHERE item_internal_id = %s
            ORDER BY valid_from DESC, rev_id DESC
        """
        return self.execute_query(query, (item_internal_id,))

    def get_item_head_history(self, item_internal_id: int) -> List[Dict]:
        query = """
            SELECT id, head_text, valid_from, valid_to, mod_type, modified_by_id, highlights, not_valid
            FROM npa_item_head_revision
            WHERE item_internal_id = %s
            ORDER BY valid_from DESC, id DESC
        """
        return self.execute_query(query, (item_internal_id,))

    def add_npa_item(self, data: Dict) -> bool:
        query = """
            INSERT INTO npa_item (npa_id, item_id, parent_id, item_type, item_number, item_level, sort_order)
            VALUES (%(npa_id)s, %(item_id)s, %(parent_id)s, %(item_type)s, %(item_number)s, %(item_level)s, %(sort_order)s)
        """
        return self.execute_update(query, data)

    def update_npa_item(self, item_id: int, data: Dict) -> bool:
        set_clause = ', '.join([f"{k}=%({k})s" for k in data.keys()])
        query = f"UPDATE npa_item SET {set_clause} WHERE id = %(id)s"
        data['id'] = item_id
        return self.execute_update(query, data)

    def delete_npa_item(self, item_id: int) -> bool:
        return self.execute_update("DELETE FROM npa_item WHERE id = %s", (item_id,))

    def get_current_item_revision(self, item_internal_id: int) -> Optional[Dict]:
        query = """
            SELECT rev_id, valid_from, valid_to, mod_type, highlights, modified_by_id, not_valid
            FROM npa_item_revision
            WHERE item_internal_id = %s AND (valid_to IS NULL OR valid_to >= CURDATE())
            ORDER BY valid_from DESC
            LIMIT 1
        """
        rows = self.execute_query(query, (item_internal_id,))
        return rows[0] if rows else None

    def get_item_head_revision(self, item_internal_id: int) -> Optional[Dict]:
        query = """
            SELECT id, head_text, valid_from, valid_to
            FROM npa_item_head_revision
            WHERE item_internal_id = %s AND (valid_to IS NULL OR valid_to >= CURDATE())
            ORDER BY valid_from DESC
            LIMIT 1
        """
        rows = self.execute_query(query, (item_internal_id,))
        return rows[0] if rows else None

    def get_paragraphs_for_revision(self, rev_id: int) -> List[Dict]:
        query = """
            SELECT para_id, block_type, sort_order, html_text, plain_text, ref_item_internal_id
            FROM npa_paragraph
            WHERE rev_id = %s
            ORDER BY sort_order
        """
        return self.execute_query(query, (rev_id,))

    def create_new_item_revision(self, item_internal_id: int, npa_id: int,
                                 valid_from: date, mod_type: str = 'change',
                                 modified_by_id: str = None) -> Optional[int]:
        prev = self.get_current_item_revision(item_internal_id)
        if prev and prev.get('valid_to') is None:
            self.execute_update("""
                UPDATE npa_item_revision
                SET valid_to = %s
                WHERE rev_id = %s
            """, (valid_from - timedelta(days=1), prev['rev_id']))
        query = """
            INSERT INTO npa_item_revision
            (item_internal_id, npa_id, valid_from, valid_to, mod_type, modified_by_id)
            VALUES (%s, %s, %s, NULL, %s, %s)
        """
        if self.execute_update(query, (item_internal_id, npa_id, valid_from, mod_type, modified_by_id)):
            res = self.execute_query("SELECT LAST_INSERT_ID() as rev_id")
            return res[0]['rev_id'] if res else None
        return None

    def save_paragraphs_for_revision(self, rev_id: int, paragraphs: List[Dict]):
        self.execute_update("DELETE FROM npa_paragraph WHERE rev_id = %s", (rev_id,))
        for para in paragraphs:
            self.execute_update("""
                INSERT INTO npa_paragraph
                (rev_id, item_internal_id, block_type, sort_order, html_text, plain_text, ref_item_internal_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (rev_id, para['item_internal_id'], para['block_type'], para['sort_order'],
                  para.get('html_text'), para.get('plain_text'), para.get('ref_item_internal_id')))

    def create_new_head_revision(self, item_internal_id: int, npa_id: int, head_text: str,
                                  valid_from: date, mod_type: str = 'change') -> bool:
        self.execute_update("""
            UPDATE npa_item_head_revision
            SET valid_to = %s
            WHERE item_internal_id = %s AND valid_to IS NULL
        """, (valid_from - timedelta(days=1), item_internal_id))
        return self.execute_update("""
            INSERT INTO npa_item_head_revision
            (item_internal_id, npa_id, head_text, valid_from, mod_type)
            VALUES (%s, %s, %s, %s, %s)
        """, (item_internal_id, npa_id, head_text, valid_from, mod_type))

class RecordEditor(tk.Toplevel):
    def __init__(self, parent, db: DatabaseManager, table_name: str, record_id: Any = None, log_callback=None):
        super().__init__(parent)
        self.db = db
        self.table_name = table_name
        self.record_id = record_id
        self.log_callback = log_callback
        self.fk_info = self.db.get_foreign_keys(table_name)
        self.columns = self.db.get_table_columns(table_name)
        self.entry_widgets = {}
        self.result = False

        self.title(f"{'Редактирование' if record_id else 'Добавление'} записи в {table_name}")
        self.geometry("700x500")
        self.columns = self._prepare_columns(self.db.get_table_columns(table_name))
        self.create_widgets()
        if record_id:
            self.load_record()

    def _prepare_columns(self, columns: List[Dict]) -> List[Dict]:
        ordered = []
        order_names = TABLE_FIELD_ORDER.get(self.table_name, [])
        present_names = {col['COLUMN_NAME'] for col in columns}
        for name in order_names:
            if name in present_names:
                ordered.append(next(col for col in columns if col['COLUMN_NAME'] == name))
        for col in columns:
            if col['COLUMN_NAME'] not in {item['COLUMN_NAME'] for item in ordered}:
                ordered.append(col)
        return ordered

    def create_widgets(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=BOTH, expand=True)

        canvas = tk.Canvas(main_frame)
        scrollbar = ttk.Scrollbar(main_frame, orient=VERTICAL, command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)

        row = 0
        for col in self.columns:
            col_name = col['COLUMN_NAME']
            if self.record_id is None and col['EXTRA'] == 'auto_increment':
                continue
            if col_name in ('modified_by_id', 'highlights', 'not_valid'):
                continue
            if col_name in SKIP_FIELDS.get(self.table_name, set()):
                continue

            label = ttk.Label(scrollable_frame, text=get_column_display_name(self.table_name, col_name))
            label.grid(row=row, column=0, sticky=W, pady=5, padx=5)

            if col_name in self.fk_info:
                ref_table = self.fk_info[col_name]['referenced_table']
                self.entry_widgets[col_name] = self._create_fk_combobox(scrollable_frame, ref_table, row, col_name)
            else:
                var = tk.StringVar()
                entry = ttk.Entry(scrollable_frame, textvariable=var, width=50)
                entry.grid(row=row, column=1, sticky=W, pady=5, padx=5)
                self.entry_widgets[col_name] = entry
            row += 1

        btn_frame = ttk.Frame(scrollable_frame)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=20)
        ttk.Button(btn_frame, text="Сохранить", command=self.save_record).pack(side=LEFT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=self.destroy).pack(side=LEFT, padx=5)

    def _create_fk_combobox(self, parent, ref_table: str, row: int, col_name: str):
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=1, sticky=W, pady=5, padx=5)
        var = tk.StringVar()
        combo = ttk.Combobox(frame, textvariable=var, width=40)
        combo.pack(side=LEFT, padx=(0,5))
        choices = self.db.get_choices_for_fk(ref_table, 'id')
        self.fk_choices = {display: id_val for id_val, display in choices}
        combo['values'] = list(self.fk_choices.keys())
        col_info = next((c for c in self.columns if c['COLUMN_NAME'] == col_name), None)
        if col_info and col_info['IS_NULLABLE'] == 'YES':
            ttk.Button(frame, text="Очистить", command=lambda: var.set("")).pack(side=LEFT, padx=2)
        ttk.Button(frame, text="Новая запись",
                   command=lambda: self.add_fk_record(ref_table, var, col_name)).pack(side=LEFT, padx=2)
        return combo

    def add_fk_record(self, ref_table: str, var: tk.StringVar, col_name: str):
        editor = RecordEditor(self, self.db, ref_table, record_id=None, log_callback=self.log_callback)
        self.wait_window(editor)
        if editor.result:
            choices = self.db.get_choices_for_fk(ref_table, 'id')
            self.fk_choices = {display: id_val for id_val, display in choices}
            combo = self.entry_widgets[col_name]
            combo['values'] = list(self.fk_choices.keys())

    def load_record(self):
        pk_name = 'npa_id' if self.table_name == 'npa_base' else 'id'
        record = self.db.execute_query(f"SELECT * FROM {self.table_name} WHERE {pk_name}=%s", (self.record_id,))
        if record:
            rec = record[0]
            for col_name, widget in self.entry_widgets.items():
                value = rec.get(col_name)
                if value is None:
                    value = ''
                if col_name in self.fk_info:
                    ref_table = self.fk_info[col_name]['referenced_table']
                    display_field = get_display_field_for_table(ref_table)
                    lookup = self.db.execute_query(
                        f"SELECT {display_field} as display FROM {ref_table} WHERE id = %s", (value,)
                    )
                    display_value = lookup[0]['display'] if lookup else ''
                    widget.set(display_value)
                else:
                    widget.delete(0, END)
                    widget.insert(0, str(value))

    def save_record(self):
        data = {}
        for col_name, widget in self.entry_widgets.items():
            if col_name in self.fk_info:
                display_value = widget.get().strip()
                if display_value == '':
                    data[col_name] = None
                else:
                    choices = self.db.get_choices_for_fk(self.fk_info[col_name]['referenced_table'], 'id')
                    fk_map = {display: id_val for id_val, display in choices}
                    data[col_name] = fk_map.get(display_value)
            else:
                val = widget.get().strip()
                if col_name in ('valid_from', 'valid_to') and val:
                    data[col_name] = val
                else:
                    data[col_name] = val if val != '' else None

        pk_name = 'npa_id' if self.table_name == 'npa_base' else 'id'
        if self.record_id is None:
            columns = ', '.join(_validate_column_name(k) for k in data.keys())
            placeholders = ', '.join(['%s'] * len(data))
            query = f"INSERT INTO {_validate_table_name(self.table_name)} ({columns}) VALUES ({placeholders})"
            success = self.db.execute_update(query, tuple(data.values()))
            if success:
                messagebox.showinfo("Успех", "Запись добавлена")
                self.result = True
                self.destroy()
        else:
            set_clause = ', '.join([f"{_validate_column_name(k)}=%s" for k in data.keys()])
            query = f"UPDATE {_validate_table_name(self.table_name)} SET {set_clause} WHERE {_validate_column_name(pk_name)}=%s"
            params = tuple(list(data.values()) + [self.record_id])
            success = self.db.execute_update(query, params)
            if success:
                messagebox.showinfo("Успех", "Запись обновлена")
                self.result = True
                self.destroy()

class ContentEditor(tk.Toplevel):
    def __init__(self, parent, db: DatabaseManager, item_internal_id: int, npa_id: int, log_callback=None):
        super().__init__(parent)
        self.db = db
        self.item_internal_id = item_internal_id
        self.npa_id = npa_id
        self.log_callback = log_callback
        self.title(f"Редактирование содержимого id={item_internal_id}")
        self.geometry("850x650")

        self.current_head = self.db.get_item_head_revision(item_internal_id)
        self.current_rev = self.db.get_current_item_revision(item_internal_id)
        self.paragraphs = self.db.get_paragraphs_for_revision(self.current_rev['rev_id']) if self.current_rev else []

        self._create_widgets()
        self._load_data()

    def _create_widgets(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill=BOTH, expand=True, padx=5, pady=5)

        head_frame = ttk.Frame(notebook)
        notebook.add(head_frame, text="Заголовок")
        self.head_text = scrolledtext.ScrolledText(head_frame, height=10)
        self.head_text.pack(fill=BOTH, expand=True, padx=5, pady=5)

        content_notebook = ttk.Notebook(notebook)
        notebook.add(content_notebook, text="Содержание")

        plain_frame = ttk.Frame(content_notebook)
        content_notebook.add(plain_frame, text="Текст")
        self.plain_text = scrolledtext.ScrolledText(plain_frame, height=20)
        self.plain_text.pack(fill=BOTH, expand=True, padx=5, pady=5)

        html_frame = ttk.Frame(content_notebook)
        content_notebook.add(html_frame, text="HTML")
        self.html_text = scrolledtext.ScrolledText(html_frame, height=20)
        self.html_text.pack(fill=BOTH, expand=True, padx=5, pady=5)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=X, pady=10)
        ttk.Button(btn_frame, text="Сохранить изменения", command=self.save).pack(side=LEFT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=self.destroy).pack(side=LEFT, padx=5)

    def _load_data(self):
        if self.current_head:
            self.head_text.insert(1.0, self.current_head.get('head_text', ''))
        html_parts = []
        plain_parts = []
        for p in self.paragraphs:
            if p.get('html_text'):
                html_parts.append(p['html_text'])
            if p.get('plain_text'):
                plain_parts.append(p['plain_text'])
        separator = "\n\n<hr>\n\n" if len(html_parts) > 1 else ""
        self.html_text.insert(1.0, separator.join(html_parts))
        self.plain_text.insert(1.0, "\n\n".join(plain_parts))

    def save(self):
        valid_from = date.today()
        mod_type = 'change'

        new_head = self.head_text.get(1.0, tk.END).strip()
        old_head = self.current_head.get('head_text', '') if self.current_head else ''
        if new_head != old_head:
            self.db.create_new_head_revision(self.item_internal_id, self.npa_id, new_head, valid_from, mod_type)
            if self.log_callback:
                self.log_callback(f"Обновлён заголовок элемента {self.item_internal_id}")

        new_html = self.html_text.get(1.0, tk.END).strip()
        if not new_html:
            messagebox.showwarning("Предупреждение", "HTML-содержимое пусто. Операция отменена.")
            return

        plain = re.sub(r'<[^>]+>', ' ', new_html)
        plain = re.sub(r'\s+', ' ', plain).strip()

        new_rev_id = self.db.create_new_item_revision(self.item_internal_id, self.npa_id, valid_from, mod_type)
        if new_rev_id:
            paragraphs = [{
                'item_internal_id': self.item_internal_id,
                'block_type': 'paragraph',
                'sort_order': 0,
                'html_text': new_html,
                'plain_text': plain,
                'ref_item_internal_id': None
            }]
            self.db.save_paragraphs_for_revision(new_rev_id, paragraphs)
            messagebox.showinfo("Успех", "Изменения сохранены")
            if self.log_callback:
                self.log_callback(f"Сохранена новая редакция контента элемента {self.item_internal_id}")
            self.destroy()
        else:
            messagebox.showerror("Ошибка", "Не удалось создать ревизию")

class FullItemEditor(tk.Toplevel):
    def __init__(self, parent, db: DatabaseManager, item_internal_id: int, npa_id: int, log_callback=None):
        super().__init__(parent)
        self.db = db
        self.item_internal_id = item_internal_id
        self.npa_id = npa_id
        self.log_callback = log_callback
        self.title(f"Полное редактирование элемента id={item_internal_id}")
        self.geometry("950x750")

        self.item_data = self._load_item_data()
        self.current_head = self.db.get_item_head_revision(item_internal_id)
        self.current_rev = self.db.get_current_item_revision(item_internal_id)
        self.paragraphs = self.db.get_paragraphs_for_revision(self.current_rev['rev_id']) if self.current_rev else []

        self._create_widgets()
        self._load_initial_data()

    def _load_item_data(self) -> dict:
        rows = self.db.execute_query("SELECT * FROM npa_item WHERE id = %s", (self.item_internal_id,))
        return rows[0] if rows else {}

    def _create_widgets(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill=BOTH, expand=True, padx=5, pady=5)

        attr_frame = ttk.Frame(notebook, padding="10")
        notebook.add(attr_frame, text="Атрибуты")
        row = 0

        ttk.Label(attr_frame, text="item_id").grid(row=row, column=0, sticky=W, pady=2)
        self.item_id_var = tk.StringVar()
        ttk.Entry(attr_frame, textvariable=self.item_id_var, width=40).grid(row=row, column=1, sticky=W, pady=2)
        row += 1

        ttk.Label(attr_frame, text="item_type").grid(row=row, column=0, sticky=W, pady=2)
        self.item_type_var = tk.StringVar()
        types = ['preamble','chapter','section','article','part','point','subpoint','appendix','nested_appendix','structured_table']
        ttk.Combobox(attr_frame, textvariable=self.item_type_var, values=types, state="readonly", width=37).grid(row=row, column=1, sticky=W, pady=2)
        row += 1

        ttk.Label(attr_frame, text="item_number").grid(row=row, column=0, sticky=W, pady=2)
        self.item_number_var = tk.StringVar()
        ttk.Entry(attr_frame, textvariable=self.item_number_var, width=40).grid(row=row, column=1, sticky=W, pady=2)
        row += 1

        ttk.Label(attr_frame, text="parent_id").grid(row=row, column=0, sticky=W, pady=2)
        self.parent_id_var = tk.StringVar()
        self.parent_combo = ttk.Combobox(attr_frame, textvariable=self.parent_id_var, state="readonly", width=37)
        self.parent_combo.grid(row=row, column=1, sticky=W, pady=2)
        self._load_parent_choices()
        row += 1

        ttk.Label(attr_frame, text="item_level").grid(row=row, column=0, sticky=W, pady=2)
        self.item_level_var = tk.IntVar()
        ttk.Spinbox(attr_frame, from_=0, to=100, textvariable=self.item_level_var, width=38).grid(row=row, column=1, sticky=W, pady=2)
        row += 1

        ttk.Label(attr_frame, text="sort_order").grid(row=row, column=0, sticky=W, pady=2)
        self.sort_order_var = tk.IntVar()
        ttk.Spinbox(attr_frame, from_=0, to=32767, textvariable=self.sort_order_var, width=38).grid(row=row, column=1, sticky=W, pady=2)
        row += 1

        ttk.Button(attr_frame, text="Сохранить атрибуты", command=self.save_attributes).grid(row=row, column=0, columnspan=2, pady=10)

        head_frame = ttk.Frame(notebook, padding="10")
        notebook.add(head_frame, text="Заголовок")
        self.head_text = scrolledtext.ScrolledText(head_frame, height=15)
        self.head_text.pack(fill=BOTH, expand=True)
        ttk.Button(head_frame, text="Сохранить заголовок", command=self.save_head).pack(pady=5)

        content_notebook = ttk.Notebook(notebook)
        notebook.add(content_notebook, text="Содержание")

        plain_frame = ttk.Frame(content_notebook)
        content_notebook.add(plain_frame, text="Текст (plain)")
        self.plain_text = scrolledtext.ScrolledText(plain_frame, height=20)
        self.plain_text.pack(fill=BOTH, expand=True, padx=5, pady=5)

        html_frame = ttk.Frame(content_notebook)
        content_notebook.add(html_frame, text="HTML-код")
        self.html_text = scrolledtext.ScrolledText(html_frame, height=20)
        self.html_text.pack(fill=BOTH, expand=True, padx=5, pady=5)

        ttk.Button(content_notebook, text="Сохранить содержание", command=self.save_content).pack(pady=5)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=X, pady=10)
        ttk.Button(btn_frame, text="Сохранить всё", command=self.save_all).pack(side=LEFT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=self.destroy).pack(side=LEFT, padx=5)

    def _load_parent_choices(self):
        items = self.db.execute_query(
            "SELECT id, item_id, item_number FROM npa_item WHERE npa_id = %s AND id != %s",
            (self.npa_id, self.item_internal_id)
        )
        choices = [("(нет)", "")]
        for it in items:
            display = f"{it['item_id']} (id={it['id']})" + (f" [{it['item_number']}]" if it['item_number'] else "")
            choices.append((display, str(it['id'])))
        self.parent_combo['values'] = [c[0] for c in choices]
        self.parent_map = {c[0]: c[1] for c in choices}

    def _load_initial_data(self):
        self.item_id_var.set(self.item_data.get('item_id', ''))
        self.item_type_var.set(self.item_data.get('item_type', ''))
        self.item_number_var.set(self.item_data.get('item_number', ''))
        parent_id = self.item_data.get('parent_id')
        if parent_id:
            for display, pid in self.parent_map.items():
                if pid == str(parent_id):
                    self.parent_id_var.set(display)
                    break
        else:
            self.parent_id_var.set("(нет)")
        self.item_level_var.set(self.item_data.get('item_level', 1))
        self.sort_order_var.set(self.item_data.get('sort_order', 0))

        if self.current_head:
            self.head_text.insert(1.0, self.current_head.get('head_text', ''))

        html_parts = []
        plain_parts = []
        for p in self.paragraphs:
            if p.get('html_text'):
                html_parts.append(p['html_text'])
            if p.get('plain_text'):
                plain_parts.append(p['plain_text'])
        self.html_text.insert(1.0, "\n\n<hr>\n\n".join(html_parts))
        self.plain_text.insert(1.0, "\n\n".join(plain_parts))

    def save_attributes(self):
        new_parent_display = self.parent_id_var.get()
        parent_id_val = None if new_parent_display == "(нет)" else int(self.parent_map.get(new_parent_display, 0))
        update_data = {
            'item_id': self.item_id_var.get().strip(),
            'item_type': self.item_type_var.get(),
            'item_number': self.item_number_var.get().strip() or None,
            'parent_id': parent_id_val,
            'item_level': self.item_level_var.get(),
            'sort_order': self.sort_order_var.get()
        }
        if parent_id_val and self._is_descendant(parent_id_val, self.item_internal_id):
            messagebox.showerror("Ошибка", "Нельзя сделать родителем своего потомка")
            return
        set_clause = ', '.join([f"{k}=%s" for k in update_data.keys()])
        query = f"UPDATE npa_item SET {set_clause} WHERE id = %s"
        params = tuple(list(update_data.values()) + [self.item_internal_id])
        if self.db.execute_update(query, params):
            messagebox.showinfo("Успех", "Атрибуты сохранены")
            if self.log_callback:
                self.log_callback(f"Обновлены атрибуты элемента {self.item_internal_id}")
        else:
            messagebox.showerror("Ошибка", "Не удалось сохранить атрибуты")

    def _is_descendant(self, potential_parent_id: int, child_id: int) -> bool:
        if potential_parent_id == child_id:
            return True
        descendants = self.db.execute_query("SELECT id FROM npa_item WHERE parent_id = %s", (child_id,))
        for desc in descendants:
            if self._is_descendant(potential_parent_id, desc['id']):
                return True
        return False

    def save_head(self):
        new_head = self.head_text.get(1.0, tk.END).strip()
        old_head = self.current_head.get('head_text', '') if self.current_head else ''
        if new_head == old_head:
            messagebox.showinfo("Информация", "Заголовок не изменился")
            return
        valid_from = date.today()
        if self.db.create_new_head_revision(self.item_internal_id, self.npa_id, new_head, valid_from, 'change'):
            messagebox.showinfo("Успех", "Заголовок сохранён")
            if self.log_callback:
                self.log_callback(f"Сохранён новый заголовок элемента {self.item_internal_id}")
        else:
            messagebox.showerror("Ошибка", "Не удалось сохранить заголовок")

    def save_content(self):
        new_html = self.html_text.get(1.0, tk.END).strip()
        if not new_html:
            messagebox.showwarning("Предупреждение", "HTML-содержимое пусто. Отмена.")
            return
        plain = re.sub(r'<[^>]+>', ' ', new_html)
        plain = re.sub(r'\s+', ' ', plain).strip()

        valid_from = date.today()
        new_rev_id = self.db.create_new_item_revision(self.item_internal_id, self.npa_id, valid_from, 'change')
        if new_rev_id:
            paragraphs = [{
                'item_internal_id': self.item_internal_id,
                'block_type': 'paragraph',
                'sort_order': 0,
                'html_text': new_html,
                'plain_text': plain,
                'ref_item_internal_id': None
            }]
            self.db.save_paragraphs_for_revision(new_rev_id, paragraphs)
            messagebox.showinfo("Успех", "Содержание сохранено")
            if self.log_callback:
                self.log_callback(f"Сохранена новая редакция контента элемента {self.item_internal_id}")
        else:
            messagebox.showerror("Ошибка", "Не удалось создать ревизию")

    def save_all(self):
        self.save_attributes()
        self.save_head()
        self.save_content()
        self.destroy()

class NotesEditorDialog(tk.Toplevel):
    def __init__(self, parent, db: DatabaseManager, npa_id: int, target_type: str, target_id: Optional[str] = None, note_id: Optional[int] = None):
        super().__init__(parent)
        self.db = db
        self.npa_id = npa_id
        self.target_type = target_type
        self.target_id = target_id
        self.note_id = note_id
        self.title('Примечание' if note_id else 'Новое примечание')
        self.geometry('500x320')
        self.create_ui()
        if note_id:
            self.load_note()

    def create_ui(self):
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill=BOTH, expand=True)

        ttk.Label(frm, text='Текст').grid(row=0, column=0, sticky=W, pady=2)
        self.text_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.text_var, width=60).grid(row=0, column=1, pady=2)

        ttk.Label(frm, text='Дата с').grid(row=1, column=0, sticky=W, pady=2)
        self.valid_from_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.valid_from_var, width=20).grid(row=1, column=1, sticky=W, pady=2)

        ttk.Label(frm, text='Дата по').grid(row=2, column=0, sticky=W, pady=2)
        self.valid_to_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.valid_to_var, width=20).grid(row=2, column=1, sticky=W, pady=2)

        ttk.Button(frm, text='Сохранить', command=self.save).grid(row=3, column=0, columnspan=2, pady=12)

    def load_note(self):
        notes = self.db.get_npa_notes(self.npa_id, target_type=self.target_type, target_id=self.target_id)
        for note in notes:
            if note['id'] == self.note_id:
                self.text_var.set(note.get('note_text', ''))
                self.valid_from_var.set(note.get('valid_from') or '')
                self.valid_to_var.set(note.get('valid_to') or '')
                break

    def save(self):
        text = self.text_var.get().strip()
        if not text:
            messagebox.showwarning('Предупреждение', 'Текст примечания обязателен')
            return
        valid_from = self.valid_from_var.get().strip() or None
        valid_to = self.valid_to_var.get().strip() or None
        if self.note_id is None:
            success = self.db.add_note(self.npa_id, self.target_type, self.target_id, text, valid_from, valid_to)
        else:
            success = self.db.update_note(self.note_id, self.target_type, self.target_id, text, valid_from, valid_to)
        if success:
            self.destroy()
        else:
            messagebox.showerror('Ошибка', 'Не удалось сохранить примечание')


class HistoryTab(ttk.Frame):
    def __init__(self, parent, db: DatabaseManager, app):
        super().__init__(parent)
        self.db = db
        self.app = app
        self.current_item_id = None
        self.create_ui()

    def create_ui(self):
        top = ttk.Frame(self)
        top.pack(fill=X, padx=5, pady=5)
        ttk.Label(top, text='Элемент').pack(side=LEFT)
        self.item_var = tk.StringVar()
        self.item_entry = ttk.Entry(top, textvariable=self.item_var, width=30)
        self.item_entry.pack(side=LEFT, padx=5)
        ttk.Button(top, text='Загрузить', command=self.load_history).pack(side=LEFT, padx=5)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=BOTH, expand=True, padx=5, pady=5)

        self.head_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.head_frame, text='Заголовки')
        self.head_tree = ttk.Treeview(self.head_frame, show='headings')
        self.head_tree.pack(fill=BOTH, expand=True)

        self.rev_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.rev_frame, text='Ревизии')
        self.rev_tree = ttk.Treeview(self.rev_frame, show='headings')
        self.rev_tree.pack(fill=BOTH, expand=True)

    def load_history(self):
        try:
            item_internal_id = int(self.item_var.get().strip())
        except ValueError:
            messagebox.showwarning('Предупреждение', 'Введите внутренний id элемента')
            return
        self.current_item_id = item_internal_id
        head_rows = self.db.get_item_head_history(item_internal_id)
        self._populate_tree(self.head_tree, head_rows, ['id', 'head_text', 'valid_from', 'valid_to', 'mod_type'])
        rev_rows = self.db.get_item_revision_history(item_internal_id)
        self._populate_tree(self.rev_tree, rev_rows, ['rev_id', 'valid_from', 'valid_to', 'mod_type', 'modified_by_id'])

    def _populate_tree(self, tree, rows, columns):
        for item in tree.get_children():
            tree.delete(item)
        tree['columns'] = columns
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=120, anchor=W)
        for row in rows:
            tree.insert('', END, values=[row.get(col) for col in columns])


class NotesTab(ttk.Frame):
    def __init__(self, parent, db: DatabaseManager, app):
        super().__init__(parent)
        self.db = db
        self.app = app
        self.create_ui()

    def create_ui(self):
        top = ttk.Frame(self)
        top.pack(fill=X, padx=5, pady=5)
        ttk.Button(top, text='Добавить примечание к НПА', command=self.add_npa_note).pack(side=LEFT, padx=5)
        ttk.Button(top, text='Добавить примечание к элементу', command=self.add_item_note).pack(side=LEFT, padx=5)
        ttk.Button(top, text='Обновить', command=self.load_notes).pack(side=LEFT, padx=5)

        self.tree = ttk.Treeview(self, show='headings')
        self.tree.pack(fill=BOTH, expand=True, padx=5, pady=5)
        self.load_notes()

    def load_notes(self):
        if not self.app.current_npa_id:
            return
        rows = self.db.get_npa_notes(self.app.current_npa_id)
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.tree['columns'] = ['id', 'target_type', 'target_id', 'note_text', 'valid_from', 'valid_to']
        for col in self.tree['columns']:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=140, anchor=W)
        for row in rows:
            self.tree.insert('', END, values=[row.get(col) for col in self.tree['columns']])

    def add_npa_note(self):
        if not self.app.current_npa_id:
            messagebox.showwarning('Предупреждение', 'Сначала выберите НПА')
            return
        NotesEditorDialog(self, self.db, self.app.current_npa_id, 'npa').wait_window()
        self.load_notes()

    def add_item_note(self):
        if not self.app.current_npa_id:
            messagebox.showwarning('Предупреждение', 'Сначала выберите НПА')
            return
        target_id = simpledialog.askstring('Элемент', 'Введите item_id элемента')
        if not target_id:
            return
        NotesEditorDialog(self, self.db, self.app.current_npa_id, 'item', target_id=target_id).wait_window()
        self.load_notes()

class ElementNotesDialog(tk.Toplevel):
    def __init__(self, parent, db: DatabaseManager, npa_id: int, item_id: str):
        super().__init__(parent)
        self.db = db
        self.npa_id = npa_id
        self.item_id = item_id
        self.title(f'Примечания элемента {item_id}')
        self.geometry('750x420')
        self.create_ui()
        self.load_notes()

    def create_ui(self):
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=X, padx=5, pady=5)
        ttk.Button(btn_frame, text='Добавить', command=self.add_note).pack(side=LEFT, padx=5)
        ttk.Button(btn_frame, text='Редактировать', command=self.edit_note).pack(side=LEFT, padx=5)
        ttk.Button(btn_frame, text='Удалить', command=self.delete_note).pack(side=LEFT, padx=5)

        self.tree = ttk.Treeview(self, show='headings')
        self.tree.pack(fill=BOTH, expand=True, padx=5, pady=5)
        self.tree['columns'] = ['id', 'note_text', 'valid_from', 'valid_to']
        for col in self.tree['columns']:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=150, anchor=W)

    def load_notes(self):
        rows = self.db.get_npa_notes(self.npa_id, target_type='item', target_id=self.item_id)
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in rows:
            self.tree.insert('', END, values=[row.get('id'), row.get('note_text'), row.get('valid_from'), row.get('valid_to')])

    def add_note(self):
        NotesEditorDialog(self, self.db, self.npa_id, 'item', target_id=self.item_id).wait_window()
        self.load_notes()

    def edit_note(self):
        selected = self.tree.selection()
        if not selected:
            return
        note_id = self.tree.item(selected[0])['values'][0]
        NotesEditorDialog(self, self.db, self.npa_id, 'item', target_id=self.item_id, note_id=note_id).wait_window()
        self.load_notes()

    def delete_note(self):
        selected = self.tree.selection()
        if not selected:
            return
        note_id = self.tree.item(selected[0])['values'][0]
        if messagebox.askyesno('Подтверждение', 'Удалить выбранное примечание?'):
            self.db.delete_note(note_id)
            self.load_notes()


class TableTab(ttk.Frame):
    def __init__(self, parent, db: DatabaseManager, app, table_name: str):
        super().__init__(parent)
        self.db = db
        self.app = app
        self.table_name = table_name
        self.columns = []
        self.filter_entries = {}
        self.tree = None
        self.current_data = []
        self.create_ui()

    def create_ui(self):
        filter_frame = ttk.LabelFrame(self, text="Фильтры", padding="5")
        filter_frame.pack(fill=X, padx=5, pady=5)
        self.filter_container = ttk.Frame(filter_frame)
        self.filter_container.pack(fill=X)

        btn_frame = ttk.Frame(filter_frame)
        btn_frame.pack(fill=X, pady=5)
        ttk.Button(btn_frame, text="Применить фильтры", command=self.load_data).pack(side=LEFT, padx=5)
        ttk.Button(btn_frame, text="Сбросить фильтры", command=self.reset_filters).pack(side=LEFT, padx=5)

        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill=BOTH, expand=True, padx=5, pady=5)
        self.tree = ttk.Treeview(tree_frame, show='headings')
        vsb = ttk.Scrollbar(tree_frame, orient=VERTICAL, command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient=HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky=NSEW)
        vsb.grid(row=0, column=1, sticky=NS)
        hsb.grid(row=1, column=0, sticky=EW)
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        self.tree_menu = tk.Menu(self.tree, tearoff=0)
        self.tree_menu.add_command(label="Редактировать", command=self.edit_record)
        self.tree_menu.add_command(label="Удалить", command=self.delete_record)
        self.tree.bind("<Button-3>", self.show_context_menu)

        crud_frame = ttk.Frame(self)
        crud_frame.pack(fill=X, padx=5, pady=5)
        ttk.Button(crud_frame, text="Добавить", command=self.add_record).pack(side=LEFT, padx=5)
        ttk.Button(crud_frame, text="Редактировать", command=self.edit_record).pack(side=LEFT, padx=5)
        ttk.Button(crud_frame, text="Удалить", command=self.delete_record).pack(side=LEFT, padx=5)
        ttk.Button(crud_frame, text="Обновить", command=self.load_data).pack(side=LEFT, padx=5)

        self.load_structure()

    def load_structure(self):
        self.columns = self.db.get_table_columns(self.table_name)
        for widget in self.filter_container.winfo_children():
            widget.destroy()
        self.filter_entries.clear()
        max_cols = 4
        for i, col in enumerate(self.columns):
            col_name = col['COLUMN_NAME']
            row = i // max_cols
            col_idx = (i % max_cols) * 2
            lbl = ttk.Label(self.filter_container, text=get_column_display_name(self.table_name, col_name))
            lbl.grid(row=row, column=col_idx, padx=5, pady=2, sticky=W)
            entry = ttk.Entry(self.filter_container, width=20)
            entry.grid(row=row, column=col_idx+1, padx=5, pady=2)
            self.filter_entries[col_name] = entry
        self.tree['columns'] = [col['COLUMN_NAME'] for col in self.columns]
        for col in self.columns:
            col_name = col['COLUMN_NAME']
            self.tree.heading(col_name, text=get_column_display_name(self.table_name, col_name))
            self.tree.column(col_name, width=100, anchor=W)
        self.load_data()

    def reset_filters(self):
        for entry in self.filter_entries.values():
            entry.delete(0, END)
        self.load_data()

    def load_data(self):
        if not self.tree.winfo_exists():
            return
        conditions = []
        params = []
        if hasattr(self.app, 'current_npa_id') and self.app.current_npa_id and 'npa_id' in [c['COLUMN_NAME'] for c in self.columns]:
            conditions.append("npa_id = %s")
            params.append(self.app.current_npa_id)
        for col, entry in self.filter_entries.items():
            val = entry.get().strip()
            if val:
                conditions.append(f"{_validate_column_name(col)} LIKE %s")
                params.append(f"%{val}%")
        where = " AND ".join(conditions) if conditions else "1"
        query = f"SELECT * FROM {self.table_name} WHERE {where}"
        rows = self.db.execute_query(query, tuple(params))
        self.current_data = rows
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in rows:
            values = [str(row.get(col['COLUMN_NAME'], '')) for col in self.columns]
            self.tree.insert('', tk.END, values=values)
        if self.app:
            self.app.log(f"Загружено {len(rows)} записей из {self.table_name}")

    def add_record(self):
        editor = RecordEditor(self, self.db, self.table_name, record_id=None, log_callback=self.app.log if self.app else None)
        self.wait_window(editor)
        if editor.result:
            self.load_data()

    def edit_record(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Нет выбора", "Выберите запись для редактирования")
            return
        pk_name = 'npa_id' if self.table_name == 'npa_base' else 'id'
        pk_index = next((i for i, col in enumerate(self.columns) if col['COLUMN_NAME'] == pk_name), 0)
        values = self.tree.item(selected[0])['values']
        record_id = values[pk_index]
        editor = RecordEditor(self, self.db, self.table_name, record_id=record_id, log_callback=self.app.log if self.app else None)
        self.wait_window(editor)
        if editor.result:
            self.load_data()

    def delete_record(self):
        selected = self.tree.selection()
        if not selected:
            return
        if not messagebox.askyesno("Подтверждение", "Удалить выбранные записи?"):
            return
        pk_name = 'npa_id' if self.table_name == 'npa_base' else 'id'
        pk_index = next((i for i, col in enumerate(self.columns) if col['COLUMN_NAME'] == pk_name), 0)
        for item in selected:
            values = self.tree.item(item)['values']
            record_id = values[pk_index]
            self.db.execute_update(f"DELETE FROM {_validate_table_name(self.table_name)} WHERE {_validate_column_name(pk_name)}=%s", (record_id,))
        self.load_data()

    def show_context_menu(self, event):
        rowid = self.tree.identify_row(event.y)
        if rowid:
            self.tree.selection_set(rowid)
            self.tree_menu.post(event.x_root, event.y_root)

class StructureTab(ttk.Frame):
    def __init__(self, parent, db: DatabaseManager, app):
        super().__init__(parent)
        self.db = db
        self.app = app
        self.current_npa_id = None
        self.tree = None
        self.create_ui()
        self.bind_npa_change()

    def create_ui(self):
        ctrl = ttk.Frame(self)
        ctrl.pack(fill=X, padx=5, pady=5)
        ttk.Label(ctrl, text="Структура НПА").pack(side=LEFT)
        ttk.Button(ctrl, text="Обновить", command=self.load_structure).pack(side=RIGHT, padx=5)
        ttk.Button(ctrl, text="Примечания элемента", command=self.edit_element_notes).pack(side=RIGHT, padx=5)
        ttk.Button(ctrl, text="Добавить элемент", command=self.add_item).pack(side=RIGHT, padx=5)

        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill=BOTH, expand=True, padx=5, pady=5)
        self.tree = ttk.Treeview(tree_frame, columns=('type', 'number'), show='tree headings')
        self.tree.heading('#0', text='Идентификатор (item_id)')
        self.tree.heading('type', text='Тип')
        self.tree.heading('number', text='Номер')
        self.tree.column('#0', width=300)
        self.tree.column('type', width=120)
        self.tree.column('number', width=100)
        scroll = ttk.Scrollbar(tree_frame, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.pack(side=RIGHT, fill=Y)

        self.tree_menu = tk.Menu(self.tree, tearoff=0)
        self.tree_menu.add_command(label="Редактировать элемент", command=self.edit_item)
        self.tree_menu.add_command(label="Редактировать содержимое", command=self.edit_content)
        self.tree_menu.add_command(label="Редактировать всё", command=self.edit_full_item)
        self.tree_menu.add_command(label="Примечания элемента", command=self.edit_element_notes)
        self.tree_menu.add_command(label="Удалить", command=self.delete_item)
        self.tree.bind("<Button-3>", self.show_context_menu)
        self.tree.bind("<Double-1>", lambda e: self.edit_full_item())

    def bind_npa_change(self):
        pass

    def load_structure(self):
        try:
            if not self.tree.winfo_exists():
                self.app.log("Виджет дерева уничтожен, пересоздаём UI")
                self.create_ui()
                return
        except (AttributeError, RuntimeError):
            self.app.log("Ошибка доступа к виджету дерева, пересоздаём UI")
            self.create_ui()
            return

        if not self.app.current_npa_id:
            messagebox.showinfo("Информация", "Сначала выберите НПА на вкладке 'Выбор НПА'")
            return
        self.current_npa_id = self.app.current_npa_id
        for item in self.tree.get_children():
            self.tree.delete(item)

        items = self.db.get_npa_items(self.current_npa_id)
        if not items:
            self.app.log(f"Нет элементов структуры для НПА {self.current_npa_id}")
            return

        children_map = {}
        for it in items:
            parent = it['parent_id']
            children_map.setdefault(parent, []).append(it)

        def add_nodes(parent_iid, parent_id):
            for it in children_map.get(parent_id, []):
                iid = f"item_{it['id']}"
                display = f"{it['item_id']} [{it['id']}]"
                self.tree.insert(parent_iid, 'end', iid=iid, text=display,
                                 values=(it['item_type'], it['item_number'] or ''))
                add_nodes(iid, it['id'])

        add_nodes('', None)
        self.app.log(f"Загружена структура НПА {self.current_npa_id} (элементов: {len(items)})")

    def add_item(self):
        if not self.current_npa_id:
            messagebox.showinfo("Информация", "Сначала выберите НПА")
            return
        win = tk.Toplevel(self)
        win.title("Добавление элемента")
        win.geometry("400x300")
        fields = ['item_id', 'parent_id', 'item_type', 'item_number', 'item_level', 'sort_order']
        entries = {}
        row = 0
        for f in fields:
            ttk.Label(win, text=f).grid(row=row, column=0, padx=5, pady=5, sticky=W)
            if f == 'parent_id':
                items = self.db.get_npa_items(self.current_npa_id)
                choices = [('(нет)', None)] + [(f"{it['item_id']} (id={it['id']})", it['id']) for it in items]
                var = tk.StringVar()
                combo = ttk.Combobox(win, textvariable=var, values=[c[0] for c in choices], width=30)
                combo.grid(row=row, column=1, padx=5, pady=5)
                entries[f] = (var, choices)
            elif f == 'item_type':
                var = tk.StringVar(value='article')
                combo = ttk.Combobox(win, textvariable=var, values=['preamble','chapter','section','article','part','point','subpoint','appendix','nested_appendix','structured_table'])
                combo.grid(row=row, column=1, padx=5, pady=5)
                entries[f] = var
            else:
                var = tk.StringVar()
                entry = ttk.Entry(win, textvariable=var, width=30)
                entry.grid(row=row, column=1, padx=5, pady=5)
                entries[f] = var
            row += 1
        def save():
            data = {'npa_id': self.current_npa_id}
            for f in fields:
                if f == 'parent_id':
                    var, choices = entries[f]
                    selected = var.get()
                    parent_id = None
                    for disp, val in choices:
                        if disp == selected:
                            parent_id = val
                            break
                    data[f] = parent_id
                else:
                    val = entries[f].get().strip()
                    if f in ('item_level', 'sort_order'):
                        try:
                            val = int(val) if val else 0
                        except ValueError:
                            val = 0
                    data[f] = val if val != '' else None
            if not data.get('item_id'):
                messagebox.showerror("Ошибка", "Поле item_id обязательно")
                return
            if self.db.add_npa_item(data):
                win.destroy()
                self.load_structure()
                self.app.log(f"Добавлен элемент {data['item_id']}")
            else:
                messagebox.showerror("Ошибка", "Не удалось добавить элемент")
        ttk.Button(win, text="Сохранить", command=save).grid(row=row, column=0, columnspan=2, pady=20)

    def edit_item(self):
        selected = self.tree.selection()
        if not selected:
            return
        item_id = int(selected[0].split('_')[1])
        editor = RecordEditor(self, self.db, 'npa_item', record_id=item_id, log_callback=self.app.log)
        self.wait_window(editor)
        if editor.result:
            self.load_structure()

    def edit_content(self):
        selected = self.tree.selection()
        if not selected:
            return
        item_id = int(selected[0].split('_')[1])
        ContentEditor(self, self.db, item_id, self.current_npa_id, self.app.log)

    def edit_element_notes(self):
        selected = self.tree.selection()
        if not selected:
            return
        try:
            item_internal_id = int(selected[0].split('_')[1])
        except ValueError:
            messagebox.showwarning('Предупреждение', 'Не удалось определить элемент')
            return
        item_row = self.db.execute_query("SELECT item_id FROM npa_item WHERE id = %s", (item_internal_id,))
        if not item_row:
            messagebox.showwarning('Предупреждение', 'Элемент не найден')
            return
        item_id = item_row[0].get('item_id')
        if not item_id:
            messagebox.showwarning('Предупреждение', 'У элемента нет item_id')
            return
        ElementNotesDialog(self, self.db, self.current_npa_id, item_id).wait_window()

    def edit_full_item(self):
        selected = self.tree.selection()
        if not selected:
            return
        try:
            item_id = int(selected[0].split('_')[1])
        except (IndexError, ValueError):
            return
        editor = FullItemEditor(self, self.db, item_id, self.current_npa_id, self.app.log)
        self.wait_window(editor)
        try:
            if self.tree.winfo_exists():
                self.load_structure()
            else:
                self.app.log("Дерево уничтожено, пересоздаём")
                self.create_ui()
        except (AttributeError, RuntimeError):
            self.app.log("Ошибка при обновлении структуры, пересоздаём UI")
            self.create_ui()

    def delete_item(self):
        selected = self.tree.selection()
        if not selected:
            return
        if messagebox.askyesno("Подтверждение", "Удалить выбранный элемент и всех его потомков?"):
            item_id = int(selected[0].split('_')[1])
            if self.db.delete_npa_item(item_id):
                self.load_structure()
                self.app.log(f"Элемент {item_id} удалён")
            else:
                messagebox.showerror("Ошибка", "Не удалось удалить элемент")

    def show_context_menu(self, event):
        rowid = self.tree.identify_row(event.y)
        if rowid:
            self.tree.selection_set(rowid)
            self.tree_menu.post(event.x_root, event.y_root)

class NpaSelectTab(ttk.Frame):
    def __init__(self, parent, db: DatabaseManager, app):
        super().__init__(parent)
        self.db = db
        self.app = app
        self.create_ui()

    def create_ui(self):
        frame = ttk.LabelFrame(self, text="Выбор НПА", padding="10")
        frame.pack(fill=BOTH, expand=True, padx=10, pady=10)

        ttk.Label(frame, text="Тип:").grid(row=0, column=0, padx=5, pady=5, sticky=W)
        self.type_var = tk.StringVar(value="law")
        type_combo = ttk.Combobox(frame, textvariable=self.type_var, values=["law", "regulation"], state="readonly")
        type_combo.grid(row=0, column=1, padx=5, pady=5)
        type_combo.bind("<<ComboboxSelected>>", self.on_type_changed)

        ttk.Label(frame, text="Год:").grid(row=0, column=2, padx=5, pady=5, sticky=W)
        self.year_var = tk.StringVar()
        self.year_combo = ttk.Combobox(frame, textvariable=self.year_var, state="readonly")
        self.year_combo.grid(row=0, column=3, padx=5, pady=5)
        self.year_combo.bind("<<ComboboxSelected>>", self.on_year_changed)

        ttk.Label(frame, text="Номер НПА:").grid(row=0, column=4, padx=5, pady=5, sticky=W)
        self.npa_number_var = tk.StringVar()
        self.npa_combo = ttk.Combobox(frame, textvariable=self.npa_number_var, state="readonly")
        self.npa_combo.grid(row=0, column=5, padx=5, pady=5)

        ttk.Button(frame, text="Загрузить НПА", command=self.load_npa).grid(row=0, column=6, padx=10, pady=5)

        self.info_frame = ttk.LabelFrame(frame, text="Данные НПА", padding="5")
        self.info_frame.grid(row=1, column=0, columnspan=7, sticky=NSEW, pady=10)
        frame.columnconfigure(1, weight=1)

        self.load_years()

    def load_years(self):
        query = """
            SELECT DISTINCT YEAR(date_signed) as yr FROM npa_law
            UNION
            SELECT DISTINCT YEAR(date_passed) as yr FROM npa_base WHERE npa_type='regulation'
            ORDER BY yr DESC
        """
        rows = self.db.execute_query(query)
        years = [str(row['yr']) for row in rows if row['yr']]
        self.year_combo['values'] = years
        if years:
            self.year_combo.set(years[0])
            self.on_type_changed()

    def on_type_changed(self, event=None):
        self.load_npa_numbers()

    def on_year_changed(self, event=None):
        self.load_npa_numbers()

    def load_npa_numbers(self):
        npa_type = self.type_var.get()
        year = self.year_var.get()
        if not year.isdigit():
            return
        npa_list = self.db.get_npa_list_by_type_year(npa_type, int(year))
        numbers = [item['npa_number'] for item in npa_list]
        self.npa_combo['values'] = numbers
        if numbers:
            self.npa_combo.set(numbers[0])

    def load_npa(self):
        npa_number = self.npa_number_var.get()
        npa_type = self.type_var.get()
        year = self.year_var.get()
        if not npa_number or not year.isdigit():
            messagebox.showwarning("Некорректный выбор", "Выберите НПА")
            return
        if npa_type == 'law':
            query = """
                SELECT b.npa_id
                FROM npa_base b
                JOIN npa_law l ON b.npa_id = l.npa_id
                WHERE b.npa_type = %s AND b.npa_number = %s AND YEAR(l.date_signed) = %s
            """
        else:
            query = """
                SELECT b.npa_id
                FROM npa_base b
                WHERE b.npa_type = %s AND b.npa_number = %s AND YEAR(b.date_passed) = %s
            """
        res = self.db.execute_query(query, (npa_type, npa_number, int(year)))
        if not res:
            messagebox.showerror("Ошибка", "НПА не найден")
            return
        npa_id = res[0]['npa_id']
        self.app.current_npa_id = npa_id
        data = self.db.get_npa_full_data(npa_id)
        for widget in self.info_frame.winfo_children():
            widget.destroy()
        row = 0
        for key, val in data.items():
            if key in ('npa_id', 'npa_type', 'authors', 'signatories', 'committees'):
                continue
            if val is not None:
                ttk.Label(self.info_frame, text=f"{key}:").grid(row=row, column=0, sticky=W, padx=5, pady=2)
                ttk.Label(self.info_frame, text=str(val)).grid(row=row, column=1, sticky=W, padx=5, pady=2)
                row += 1
        self.app.log(f"Выбран НПА: {npa_number} (id={npa_id})")
        self.app.on_npa_changed()

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Редактор базы данных НПА - Новая версия")
        self.geometry("1300x800")
        self.db = DatabaseManager()
        if not self.db.connect():
            sys.exit(1)
        self.current_npa_id = None

        self.log_text = scrolledtext.ScrolledText(self, height=8, wrap=tk.WORD)
        self.log_text.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=5)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.npa_select_tab = NpaSelectTab(self.notebook, self.db, self)
        self.notebook.add(self.npa_select_tab, text="Выбор НПА")

        self.main_work_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.main_work_tab, text="Главная")

        self.main_work_notebook = ttk.Notebook(self.main_work_tab)
        self.main_work_notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.reference_tab = ttk.Frame(self.main_work_notebook)
        self.main_work_notebook.add(self.reference_tab, text="Справочники")
        self._create_reference_tab()

        self.npa_content_tab = ttk.Frame(self.main_work_notebook)
        self.main_work_notebook.add(self.npa_content_tab, text="НПА")
        self._create_npa_content_tab()

        self.log("Приложение запущено. Выберите НПА на первой вкладке.")

    def _create_reference_tab(self):
        frame = ttk.Frame(self.reference_tab)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.reference_notebook = ttk.Notebook(frame)
        self.reference_notebook.pack(fill=tk.BOTH, expand=True)

        self.person_tab = TableTab(self.reference_notebook, self.db, self, 'person')
        self.reference_notebook.add(self.person_tab, text="Лица")

        self.post_tab = TableTab(self.reference_notebook, self.db, self, 'person_post')
        self.reference_notebook.add(self.post_tab, text="Должности")

        self.committees_tab = TableTab(self.reference_notebook, self.db, self, 'committees')
        self.reference_notebook.add(self.committees_tab, text="Комитеты")

        self.convocation_tab = TableTab(self.reference_notebook, self.db, self, 'convocation')
        self.reference_notebook.add(self.convocation_tab, text="Созывы")

        self.authors_tab = TableTab(self.reference_notebook, self.db, self, 'npa_author_link')
        self.reference_notebook.add(self.authors_tab, text="Авторы")

        self.signatories_tab = TableTab(self.reference_notebook, self.db, self, 'npa_signatory')
        self.reference_notebook.add(self.signatories_tab, text="Подписанты")

        self.committee_link_tab = TableTab(self.reference_notebook, self.db, self, 'npa_committee_link')
        self.reference_notebook.add(self.committee_link_tab, text="Комитеты НПА")

    def _create_npa_content_tab(self):
        frame = ttk.Frame(self.npa_content_tab)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.npa_content_notebook = ttk.Notebook(frame)
        self.npa_content_notebook.pack(fill=tk.BOTH, expand=True)

        self.npa_base_tab = TableTab(self.npa_content_notebook, self.db, self, 'npa_base')
        self.npa_content_notebook.add(self.npa_base_tab, text="Основное")

        self.spec_frame = ttk.Frame(self.npa_content_notebook)
        self.npa_content_notebook.add(self.spec_frame, text="Спец. поля")
        self.create_spec_tab()

        self.structure_tab = StructureTab(self.npa_content_notebook, self.db, self)
        self.npa_content_notebook.add(self.structure_tab, text="Структура НПА")

        self.notes_tab = NotesTab(self.npa_content_notebook, self.db, self)
        self.npa_content_notebook.add(self.notes_tab, text="Примечания")

        self.history_tab = HistoryTab(self.npa_content_notebook, self.db, self)
        self.npa_content_notebook.add(self.history_tab, text="История")

    def create_spec_tab(self):
        frame = ttk.Frame(self.spec_frame)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        ttk.Label(frame, text="Специфические поля для законов/постановлений").pack()
        self.spec_text = scrolledtext.ScrolledText(frame, height=20)
        self.spec_text.pack(fill=tk.BOTH, expand=True)
        ttk.Button(frame, text="Сохранить", command=self.save_spec_fields).pack(pady=5)
        self.update_spec_fields()

    def update_spec_fields(self):
        if not self.current_npa_id:
            self.spec_text.delete(1.0, tk.END)
            self.spec_text.insert(1.0, "НПА не выбран")
            return
        data = self.db.get_npa_full_data(self.current_npa_id)
        self.spec_text.delete(1.0, tk.END)
        if data.get('npa_type') == 'law':
            fields = ['date_1st_reading', 'date_2nd_reading', 'date_signed']
        else:
            fields = ['term_number', 'session_number']
        for f in fields:
            val = data.get(f, '')
            self.spec_text.insert(tk.END, f"{f}: {val}\n")
        self.spec_text.insert(tk.END, "\nВведите новые значения в формате поле=значение, каждое с новой строки")

    def save_spec_fields(self):
        if not self.current_npa_id:
            return
        data = self.db.get_npa_full_data(self.current_npa_id)
        npa_type = data.get('npa_type')
        lines = self.spec_text.get(1.0, tk.END).strip().split('\n')
        updates = {}
        for line in lines:
            if '=' in line and not line.startswith('Введите'):
                key, val = line.split('=', 1)
                key = key.strip()
                val = val.strip()
                if val:
                    updates[key] = val
        if npa_type == 'law':
            table = 'npa_law'
            pk = 'npa_id'
        else:
            table = 'npa_regulation'
            pk = 'npa_id'
        for key, val in updates.items():
            query = f"UPDATE {table} SET {key}=%s WHERE {pk}=%s"
            self.db.execute_update(query, (val, self.current_npa_id))
        self.log("Специфические поля сохранены")
        self.update_spec_fields()

    def on_npa_changed(self):
        for tab in [self.npa_base_tab, self.authors_tab, self.signatories_tab,
                    self.committee_link_tab, self.structure_tab, self.notes_tab, self.history_tab]:
            if hasattr(tab, 'load_data'):
                tab.load_data()
            elif hasattr(tab, 'load_structure'):
                tab.load_structure()
        self.update_spec_fields()
        self.log(f"Текущий НПА изменён на id={self.current_npa_id}")

    def log(self, message: str):
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)

if __name__ == "__main__":
    app = App()
    app.mainloop()