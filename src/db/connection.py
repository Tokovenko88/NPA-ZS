"""Подключение к MySQL-базе НПА-ЗС.

Источник: JSON-To-DB/src/main.py (модульная часть + класс ``DBConnection``).
Модуль содержит конфигурацию подключения, цветовую схему GUI, справочные
константы и низкоуровневый класс работы с MySQL (``DBConnection``).

Класс ``NpaImporter`` и GUI-приложение вынесены в ``npazs.db.importer``.
"""
import json
import re
import sys
import threading
import traceback
import functools
import tempfile
import os
import queue
import time
from dotenv import load_dotenv
from datetime import datetime, date, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from tkinter.scrolledtext import ScrolledText
from typing import Dict, List, Tuple, Optional, Set, Union

try:
    import pymysql
    import pymysql.cursors
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'pymysql'])
    import pymysql
    import pymysql.cursors

DB_DEFAULTS = {
    'host': 'localhost',
    'port': '3306',
    'user': '',
    'password': '',
    'database': '',
}

env_path = Path(__file__).resolve().parents[2] / '.env'
if not env_path.exists():
    env_path = Path.cwd() / '.env'
if not env_path.exists() and getattr(sys, 'frozen', False):
    env_path = Path(sys.executable).parent / '.env'
load_dotenv(dotenv_path=env_path)

DB_CONFIG = {
    'host': os.getenv('DB_HOST', DB_DEFAULTS['host']),
    'port': int(os.getenv('DB_PORT', DB_DEFAULTS['port'])),
    'user': os.getenv('DB_USER', DB_DEFAULTS['user']),
    'password': os.getenv('DB_PASSWORD', DB_DEFAULTS['password']),
    'database': os.getenv('DB_NAME', DB_DEFAULTS['database']),
} 

COLOR = {
    'bg': '#1E1E2E',
    'panel': '#2A2A3E',
    'border': '#3A3A5E',
    'accent': '#7C6AF7',
    'accent2': '#5A9CF8',
    'ok': '#4EC994',
    'warn': '#F0C040',
    'error': '#F05050',
    'info': '#A8B8D0',
    'text': '#E8E8F0',
    'muted': '#6A7A9A',
    'input_bg': '#252538',
    'btn': '#7C6AF7',
    'btn_txt': '#FFFFFF',
    'log_bg': '#141420',
}

LOG_TAGS = {
    'INFO': {'fg': COLOR['info']},
    'OK': {'fg': COLOR['ok']},
    'WARN': {'fg': COLOR['warn']},
    'ERROR': {'fg': COLOR['error']},
    'SECTION': {'fg': COLOR['accent'], 'font_bold': True},
    'DIM': {'fg': COLOR['muted']},
}

ROMAN_RE = re.compile(r'\b([IVXLCDM]+)\s*созыв', re.IGNORECASE)

ITEM_TYPE_MAP = {
    'preamble': 'preamble',
    'chapter': 'chapter',
    'section': 'section',
    'article': 'article',
    'part': 'part',
    'point': 'point',
    'subpoint': 'subpoint',
    'appendix': 'appendix',
    'structured_table': 'structured_table',
}

SERVICE_POSITIONS = {
    'Прокурор города Севастополя',
    'Правительство Севастополя',
}

def normalize_fio(fio: str) -> str:
    if not fio:
        return fio
    fio = re.sub(r'\s+', ' ', fio.strip())
    match = re.match(r'^([А-Яа-я]\.)([А-Яа-я]\.)([А-Яа-я]+)$', fio)
    if match:
        return f"{match.group(1)}{match.group(2)} {match.group(3)}"
    match2 = re.match(r'^([А-Яа-я]\.)([А-Яа-я]\.)\s+([А-Яа-я]+)$', fio)
    if match2:
        return f"{match2.group(1)}{match2.group(2)} {match2.group(3)}"
    match3 = re.match(r'^([А-Яа-я])\.\s*([А-Яа-я])\.\s*([А-Яа-я]+)$', fio)
    if match3:
        return f"{match3.group(1)}.{match3.group(2)}. {match3.group(3)}"
    return fio

@functools.lru_cache(maxsize=None)
def parse_date_cached(s: str) -> date | None:
    if not s:
        return None
    s = str(s).strip()
    for fmt in ('%d.%m.%Y', '%Y-%m-%d', '%d.%m.%y', '%d/%m/%Y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None

parse_date = parse_date_cached


def parse_note_payload(note: Optional[dict]) -> Tuple[str, Optional[date], Optional[date]]:
    if not isinstance(note, dict):
        return '', None, None
    text = str(note.get('text') or '').strip()
    valid_from = parse_date(note.get('valid_from') or note.get('valid_date'))
    valid_to = parse_date(note.get('valid_to')) if note.get('valid_to') else None
    return text, valid_from, valid_to


def date_plus_one(d: date) -> date:
    return d + timedelta(days=1)

def compute_valid_from(prev_valid_to: date | None, root_valid_from: date) -> date:
    if prev_valid_to is not None:
        return date_plus_one(prev_valid_to)
    return root_valid_from

# Коды ошибок MySQL, которые можно безопасно повторить (lock wait timeout / deadlock)
RETRYABLE_ERRCODES = {1205, 1213}

class DBConnection:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.conn = None

    def connect(self):
        self.conn = pymysql.connect(
            host=self.cfg['host'],
            port=int(self.cfg['port']),
            user=self.cfg['user'],
            password=self.cfg['password'],
            database=self.cfg['database'],
            charset='utf8mb4',
            cursorclass=pymysql.cursors.Cursor,
            connect_timeout=30,
            read_timeout=300,
            write_timeout=300,
            autocommit=False,
            local_infile=1,
        )

    def disconnect(self):
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None

    def ping(self):
        try:
            self.conn.ping(reconnect=True)
        except Exception:
            self.connect()

    def _ensure_connection(self):
        try:
            self.conn.ping(reconnect=True)
        except Exception:
            self.connect()

    def exec(self, sql: str, params=(), attempts: int = 3, delay: float = 1.0) -> int:
        self._ensure_connection()
        for attempt in range(1, attempts + 1):
            try:
                with self.conn.cursor() as cur:
                    cur.execute(sql, params)
                    return cur.lastrowid
            except Exception as e:
                if self._is_retryable(e) and attempt < attempts:
                    time.sleep(delay * attempt)
                    try:
                        self.conn.rollback()
                    except Exception:
                        pass
                    continue
                raise

    def exec_many(self, sql: str, data: list, attempts: int = 3, delay: float = 1.0) -> int:
        if not data:
            return 0
        self._ensure_connection()
        for attempt in range(1, attempts + 1):
            try:
                with self.conn.cursor() as cur:
                    cur.executemany(sql, data)
                    return cur.lastrowid
            except Exception as e:
                if self._is_retryable(e) and attempt < attempts:
                    time.sleep(delay * attempt)
                    try:
                        self.conn.rollback()
                    except Exception:
                        pass
                    continue
                raise

    @staticmethod
    def _is_retryable(e: Exception) -> bool:
        try:
            return e.args[0] in RETRYABLE_ERRCODES
        except Exception:
            return False

    def fetch_one(self, sql: str, params=()) -> Optional[dict]:
        self._ensure_connection()
        with self.conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    def fetch_all(self, sql: str, params=()) -> list:
        self._ensure_connection()
        with self.conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def disable_checks(self):
        self.exec('SET FOREIGN_KEY_CHECKS=0')
        self.exec('SET UNIQUE_CHECKS=0')

    def enable_checks(self):
        self.exec('SET FOREIGN_KEY_CHECKS=1')
        self.exec('SET UNIQUE_CHECKS=1')

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def bulk_load_csv(self, table: str, columns: List[str], rows: List[Tuple], sep: str = '\t') -> int:
        if not rows:
            return 0
        fd, path = tempfile.mkstemp(suffix='.csv', text=True)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                for row in rows:
                    line = []
                    for v in row:
                        if v is None:
                            line.append(r'\N')
                        else:
                            line.append(str(v))
                    f.write(sep.join(line) + '\n')
            cols_sql = ','.join(columns)
            sql = f"LOAD DATA LOCAL INFILE %s INTO TABLE {table} FIELDS TERMINATED BY '{sep}' ESCAPED BY '\\\\' ({cols_sql})"
            with self.conn.cursor() as cur:
                cur.execute(sql, (path,))
            return len(rows)
        finally:
            os.unlink(path)

