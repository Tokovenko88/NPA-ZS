"""Импортёр НПА из JSON в MySQL (NPA-ZS).

Источник: JSON-To-DB/src/main.py (классы ``NpaImporter`` и ``ImporterApp``).
Общие константы, помощники и класс подключения импортируются из
``npazs.db.connection``, чтобы не дублировать конфигурацию.
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
from datetime import datetime, date, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from tkinter.scrolledtext import ScrolledText
from typing import Dict, List, Tuple, Optional, Set, Union

import pymysql
import pymysql.cursors

from npazs.db.connection import (
    DB_DEFAULTS,
    DB_CONFIG,
    COLOR,
    LOG_TAGS,
    ROMAN_RE,
    ITEM_TYPE_MAP,
    SERVICE_POSITIONS,
    RETRYABLE_ERRCODES,
    DBConnection,
    normalize_fio,
    parse_date,
    parse_date_cached,
    parse_note_payload,
    date_plus_one,
    compute_valid_from,
)
class NpaImporter:
    CHUNK_SIZE = 5000

    def __init__(self, db: DBConnection, log_cb):
        self.db = db
        self.log = log_cb
        self._tables_cache = {}
        self._item_id_cache: Dict[str, int] = {}
        self._person_cache: Dict[str, int] = {}
        self._post_cache: Dict[Tuple[str, Optional[int], int], int] = {}
        self._conv_cache: Dict[str, int] = {}
        self._committee_cache: Dict[str, int] = {}
        self._revision_exists_cache: Dict[int, bool] = {}
        self._load_lookup_tables()

    def _normalize_highlights(self, val):
        if val is None:
            return None
        try:
            if isinstance(val, (dict, list)):
                s = json.dumps(val, ensure_ascii=False)
            elif isinstance(val, str):
                s = val.strip()
                if not s:
                    return None
                try:
                    parsed = json.loads(s)
                    s = json.dumps(parsed, ensure_ascii=False)
                except json.JSONDecodeError:
                    s = json.dumps(s, ensure_ascii=False)
            else:
                return None
            json.loads(s)
            return s
        except Exception as e:
            self.log('WARN', f'Некорректное значение highlights: {e} -> установлено NULL')
            return None

    def _table_exists(self, name: str) -> bool:
        if name in self._tables_cache:
            return self._tables_cache[name]
        with self.db.conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM information_schema.tables "
                "WHERE table_schema = DATABASE() AND table_name = %s", (name,)
            )
            exists = cur.fetchone()[0] > 0
            self._tables_cache[name] = exists
            return exists

    def _require_table(self, name: str) -> bool:
        if not self._table_exists(name):
            self.log('ERROR', f'Таблица «{name}» не найдена в БД — пропущена.')
            return False
        return True

    def _check_required_tables(self) -> bool:
        required = [
            'npa_base', 'npa_item', 'npa_item_revision', 'npa_paragraph',
            'npa_head_revision', 'npa_item_head_revision', 'npa_item_prefix_revision',
            'person', 'person_post', 'npa_author_link', 'npa_signatory',
            'convocation', 'committees', 'npa_committee_link', 'npa_revision_info',
            'npa_item_number_revision'
        ]
        missing = [t for t in required if not self._table_exists(t)]
        if missing:
            self.log('ERROR', f'Отсутствуют обязательные таблицы: {", ".join(missing)}')
            return False
        return True

    def _revision_exists(self, rev_id: int) -> bool:
        if rev_id in self._revision_exists_cache:
            return self._revision_exists_cache[rev_id]
        row = self.db.fetch_one('SELECT 1 FROM npa_base WHERE npa_id = %s', (rev_id,))
        exists = row is not None
        self._revision_exists_cache[rev_id] = exists
        return exists

    def _load_lookup_tables(self):
        rows = self.db.fetch_all('SELECT id, fio FROM person')
        for r in rows:
            self._person_cache[r['fio']] = r['id']
        rows = self.db.fetch_all('SELECT id, name, convocation_id, display_mode FROM person_post')
        for r in rows:
            key = (r['name'], r['convocation_id'], r['display_mode'])
            self._post_cache[key] = r['id']
        rows = self.db.fetch_all('SELECT id, name FROM convocation')
        for r in rows:
            self._conv_cache[r['name']] = r['id']
        rows = self.db.fetch_all('SELECT id, name FROM committees')
        for r in rows:
            self._committee_cache[r['name']] = r['id']
        rows = self.db.fetch_all('SELECT id, item_id FROM npa_item')
        for r in rows:
            self._item_id_cache[r['item_id']] = r['id']
        self.log('OK', f'Справочники загружены (persons={len(self._person_cache)}, posts={len(self._post_cache)}, conv={len(self._conv_cache)}, committees={len(self._committee_cache)}, npa_item={len(self._item_id_cache)})')

    def _find_or_create_convocation(self, raw: str, npa_type: str = None) -> int | None:
        if not self._require_table('convocation'):
            return None
        raw = raw or ''
        m = ROMAN_RE.search(raw)
        if npa_type == 'law':
            name = f'{m.group(1).upper()} созыв' if m else 'I созыв'
        else:
            name = f'{m.group(1).upper()} созыв' if m else (raw.strip()[:50] if raw else 'Не указан')
        if name in self._conv_cache:
            return self._conv_cache[name]
        with self.db.conn.cursor() as cur:
            cur.execute(
                'INSERT INTO convocation (name) VALUES (%s) '
                'ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)', (name,)
            )
            cur.execute('SELECT LAST_INSERT_ID()')
            new_id = cur.fetchone()[0]
        self._conv_cache[name] = new_id
        self.log('OK', f'Создан/найден созыв «{name}» (id={new_id})')
        return new_id

    def _find_or_create_person(self, fio: str) -> int | None:
        if not fio or not self._require_table('person'):
            return None
        fio = normalize_fio(fio)
        if fio in self._person_cache:
            return self._person_cache[fio]
        with self.db.conn.cursor() as cur:
            cur.execute(
                'INSERT INTO person (fio) VALUES (%s) '
                'ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)', (fio,)
            )
            cur.execute('SELECT LAST_INSERT_ID()')
            new_id = cur.fetchone()[0]
        self._person_cache[fio] = new_id
        self.log('OK', f'Создана/найдена персона «{fio}» (id={new_id})')
        return new_id

    def _find_or_create_person_post(self, name: str, conv_id: int | None, display_mode: int, fallback_to_global: bool = False) -> int | None:
        if not name or not self._require_table('person_post'):
            return None
        name = re.sub(r'\s+', ' ', name.strip())
        if name in ("Депутат", "Губернатор города Севастополя"):
            conv_id = None
        cache_key = (name, conv_id, display_mode)
        if cache_key in self._post_cache:
            return self._post_cache[cache_key]
        if fallback_to_global and conv_id is not None:
            fallback_key = (name, None, display_mode)
            if fallback_key in self._post_cache:
                self._post_cache[cache_key] = self._post_cache[fallback_key]
                return self._post_cache[cache_key]
        with self.db.conn.cursor() as cur:
            cur.execute(
                'INSERT INTO person_post (name, convocation_id, display_mode, is_active) '
                'VALUES (%s, %s, %s, 1) '
                'ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)',
                (name, conv_id, display_mode)
            )
            cur.execute('SELECT LAST_INSERT_ID()')
            new_id = cur.fetchone()[0]
        self._post_cache[cache_key] = new_id
        self.log('OK', f'Создана/найдена должность «{name[:60]}» (id={new_id}, mode={display_mode})')
        return new_id

    def _find_or_create_committee(self, name: str) -> int | None:
        if not name or not self._require_table('committees'):
            return None
        name = re.sub(r'\s+', ' ', name.strip())
        if name in self._committee_cache:
            return self._committee_cache[name]
        with self.db.conn.cursor() as cur:
            cur.execute(
                'INSERT INTO committees (name) VALUES (%s) '
                'ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)', (name,)
            )
            cur.execute('SELECT LAST_INSERT_ID()')
            new_id = cur.fetchone()[0]
        self._committee_cache[name] = new_id
        self.log('OK', f'Создан/найден комитет id={new_id}')
        return new_id

    def _npa_exists(self, npa_id: int) -> bool:
        row = self.db.fetch_one('SELECT npa_id FROM npa_base WHERE npa_id = %s', (npa_id,))
        return row is not None

    def _clear_npa_data(self, npa_id: int) -> None:
        self.log('WARN', f'Очистка всех данных НПА npa_id={npa_id} (кроме самой записи npa_base)')
        self.db.exec('DELETE FROM npa_paragraph WHERE rev_id IN (SELECT rev_id FROM npa_item_revision WHERE npa_id = %s)', (npa_id,))
        self.db.exec('DELETE FROM npa_item_revision WHERE npa_id = %s', (npa_id,))
        self.db.exec('DELETE FROM npa_item_head_revision WHERE npa_id = %s', (npa_id,))
        self.db.exec('DELETE FROM npa_item_prefix_revision WHERE npa_id = %s', (npa_id,))
        self.db.exec('DELETE FROM npa_head_revision WHERE npa_id = %s', (npa_id,))
        self.db.exec('DELETE FROM npa_law WHERE npa_id = %s', (npa_id,))
        self.db.exec('DELETE FROM npa_regulation WHERE npa_id = %s', (npa_id,))
        self.db.exec('DELETE FROM npa_revision_info WHERE base_npa_id = %s', (npa_id,))
        self.db.exec('DELETE FROM npa_revision_info WHERE revision_id = %s', (npa_id,))
        self.db.exec('DELETE FROM npa_author_link WHERE npa_id = %s', (npa_id,))
        self.db.exec('DELETE FROM npa_signatory WHERE npa_id = %s', (npa_id,))
        self.db.exec('DELETE FROM npa_committee_link WHERE npa_id = %s', (npa_id,))
        self.db.exec('DELETE FROM npa_note_unified WHERE npa_id = %s', (npa_id,))
        self.db.exec('DELETE FROM npa_rendered_cache WHERE npa_id = %s', (npa_id,))
        self.db.exec('DELETE FROM npa_item_number_revision WHERE npa_id = %s', (npa_id,))
        self.db.exec('DELETE FROM npa_item WHERE npa_id = %s', (npa_id,))
        self.log('OK', f'Все данные НПА {npa_id} очищены (базовая запись сохранена)')

    def delete_npa_completely(self, npa_id: int) -> bool:
        if not self._npa_exists(npa_id):
            self.log('ERROR', f'НПА с npa_id={npa_id} не существует')
            return False
        self.log('SECTION', f'Полное удаление НПА npa_id={npa_id}')
        try:
            self._clear_npa_data(npa_id)
            self.db.exec('DELETE FROM npa_base WHERE npa_id = %s', (npa_id,))
            self.db.commit()
            self.log('OK', f'НПА {npa_id} полностью удалён из БД')
            return True
        except Exception as e:
            self.db.rollback()
            self.log('ERROR', f'Ошибка при полном удалении: {e}')
            self.log('DIM', traceback.format_exc())
            return False

    def _process_author(self, author_raw: str, conv_id: int, signer_fio: str | None = None) -> tuple[int | None, int | None]:
        author_raw = re.sub(r'\s+', ' ', author_raw.strip())
        if not author_raw:
            return None, None
        if author_raw == "Губернатор города Севастополя":
            person_id = self._find_or_create_person(signer_fio) if signer_fio else None
            post_name = "Губернатор города Севастополя"
            display_mode = 0
            post_id = self._find_or_create_person_post(post_name, conv_id, display_mode)
            return person_id, post_id
        for service in SERVICE_POSITIONS:
            if service in author_raw:
                person_id = None
                post_name = service
                display_mode = 2
                post_id = self._find_or_create_person_post(post_name, conv_id, display_mode)
                return person_id, post_id
        person_id = self._find_or_create_person(author_raw)
        post_name = "Депутат"
        display_mode = 1
        post_id = self._find_or_create_person_post(post_name, conv_id, display_mode)
        return person_id, post_id

    def _insert_author_link(self, npa_id: int, person_id: int | None, person_post_id: int | None):
        if not person_id or not person_post_id or not self._require_table('npa_author_link'):
            return
        self.db.exec(
            'INSERT INTO npa_author_link (npa_id, person_id, person_post_id) VALUES (%s, %s, %s)',
            (npa_id, person_id, person_post_id)
        )

    def _insert_signatory(self, npa_id: int, fio: str, post: str, conv_id: int):
        if not fio or not post or not self._require_table('npa_signatory'):
            return
        post = re.sub(r'\s+', ' ', post.strip())
        person_id = self._find_or_create_person(fio)
        person_post_id = self._find_or_create_person_post(post, conv_id=None, display_mode=0, fallback_to_global=True)
        if not person_id or not person_post_id:
            self.log('WARN', f'Не удалось создать/найти должность подписанта: "{post}"')
            return
        self.db.exec(
            'INSERT INTO npa_signatory (npa_id, person_id, person_post_id) VALUES (%s, %s, %s)',
            (npa_id, person_id, person_post_id)
        )
        self.log('OK', f'npa_signatory: подписант «{fio}», должность «{post}»')

    def _insert_committee_link(self, npa_id: int, committee_id: int | None):
        if not committee_id or not self._require_table('npa_committee_link'):
            return
        self.db.exec('INSERT INTO npa_committee_link (npa_id, committee_id) VALUES (%s, %s)', (npa_id, committee_id))

    def _update_or_insert_npa_base(self, d: dict) -> int | None:
        if not self._require_table('npa_base'):
            return None
        npa_type = d.get('npa_type', 'law')
        if npa_type not in ('law', 'regulation'):
            npa_type = 'law'
        npa_id = d.get('npa_id')
        if npa_id is None:
            self.log('ERROR', 'Отсутствует npa_id в JSON')
            return None
        npa_number = d.get('npa_number', '')
        npa_url = d.get('npa_url', '')
        date_reg = parse_date(d.get('date_reg'))
        date_passed = parse_date(d.get('date_passed'))
        date_pub = parse_date(d.get('date_pub'))
        valid_from = parse_date(d.get('valid_from'))
        date_format = d.get('date_format', 0)
        pub_info = d.get('pub_info')
        pub_filepath = d.get('pub_filepath')
        date_cons = parse_date(d.get('date_cons'))
        not_valid = parse_date(d.get('not_valid'))
        not_valid_note = d.get('not_valid_note')
        no_name = d.get('no_name')

        not_valid_npa_id_raw = d.get('not_valid_npa_id')
        if not_valid_npa_id_raw is None:
            not_valid_npa_id_raw = d.get('not_valid_npa')
        if not_valid_npa_id_raw is not None:
            try:
                not_valid_npa_id = int(not_valid_npa_id_raw)
            except (ValueError, TypeError):
                self.log('WARN', f'Некорректное значение not_valid_npa_id: "{not_valid_npa_id_raw}" → установлено NULL')
                not_valid_npa_id = None
        else:
            not_valid_npa_id = None

        if not date_reg:
            date_reg = date_passed
        if not date_passed:
            self.log('ERROR', 'date_passed обязателен')
            return None
        if not date_pub:
            date_pub = date_passed
        if not valid_from:
            valid_from = date_passed

        sql = """
        INSERT INTO npa_base
        (npa_id, npa_type, npa_number, pub_info, pub_filepath, npa_url,
        date_reg, date_cons, date_passed, date_pub, valid_from,
        not_valid, date_format, not_valid_note, not_valid_npa_id, no_name)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
        npa_type = VALUES(npa_type),
        npa_number = VALUES(npa_number),
        pub_info = VALUES(pub_info),
        pub_filepath = VALUES(pub_filepath),
        npa_url = VALUES(npa_url),
        date_reg = VALUES(date_reg),
        date_cons = VALUES(date_cons),
        date_passed = VALUES(date_passed),
        date_pub = VALUES(date_pub),
        valid_from = VALUES(valid_from),
        not_valid = VALUES(not_valid),
        date_format = VALUES(date_format),
        not_valid_note = VALUES(not_valid_note),
        not_valid_npa_id = VALUES(not_valid_npa_id),
        no_name = VALUES(no_name)
        """
        params = (
            npa_id, npa_type, npa_number, pub_info, pub_filepath, npa_url,
            date_reg, date_cons, date_passed, date_pub, valid_from,
            not_valid, date_format, not_valid_note, not_valid_npa_id, no_name
        )
        self.db.exec(sql, params)
        if not_valid_npa_id is not None:
            self.log('OK', f'npa_base: обновлён/вставлен npa_id={npa_id}, not_valid_npa_id={not_valid_npa_id}')
        else:
            self.log('OK', f'npa_base: обновлён/вставлен npa_id={npa_id}')
        return npa_id

    def _insert_specific_fields(self, npa_id: int, npa_type: str, d: dict, conv_id: int | None = None):
        if npa_type == 'law':
            if not self._table_exists('npa_law'):
                self.log('WARN', 'Таблица npa_law не найдена, пропуск')
                return
            date_1st = parse_date(d.get('date_1st_reading'))
            date_2nd = parse_date(d.get('date_2nd_reading'))
            date_signed = parse_date(d.get('date_signed'))
            self.db.exec(
                """INSERT INTO npa_law (npa_id, date_1st_reading, date_2nd_reading, date_signed)
                VALUES (%s, %s, %s, %s)""",
                (npa_id, date_1st, date_2nd, date_signed)
            )
            self.log('OK', f'npa_law: вставлена для npa_id={npa_id}')
        elif npa_type == 'regulation':
            if not self._table_exists('npa_regulation'):
                self.log('WARN', 'Таблица npa_regulation не найдена, пропуск')
                return
            term_raw = d.get('term_number') or ''
            if not term_raw and conv_id:
                conv_row = self.db.fetch_one('SELECT name FROM convocation WHERE id = %s', (conv_id,))
                if conv_row:
                    term_raw = conv_row['name']
            term_number = None
            if term_raw:
                m = ROMAN_RE.search(term_raw)
                term_number = m.group(1).upper() if m else term_raw.strip()[:10]
            session_number = d.get('session_number')
            if session_number:
                session_number = str(session_number).strip()[:10]
            self.db.exec(
                "INSERT INTO npa_regulation (npa_id, term_number, session_number) VALUES (%s, %s, %s)",
                (npa_id, term_number, session_number)
            )
            self.log('OK', f'npa_regulation: вставлена для npa_id={npa_id}')

    def _insert_revision_info(self, base_npa_id: int, revisions_info: list, npa_type: str):
        if not revisions_info or not self._require_table('npa_revision_info'):
            return
        data = []
        skipped = 0
        for rev in revisions_info:
            rev_id = rev.get('revision_id')
            if rev_id is None:
                continue
            try:
                rev_id = int(rev_id)
            except (ValueError, TypeError):
                self.log('WARN', f'Некорректный revision_id "{rev.get("revision_id")}" – пропуск')
                continue
            if not self._revision_exists(rev_id):
                self.log('WARN', f'revision_id={rev_id} не найден в npa_base – запись пропущена')
                skipped += 1
                continue
            date_reg = parse_date(rev.get('revision_date_reg'))
            if date_reg is None and npa_type == 'regulation':
                date_reg = parse_date(rev.get('revision_date_valid'))
            date_valid = parse_date(rev.get('revision_date_valid'))
            data.append((
                base_npa_id,
                rev_id,
                rev.get('revision_number', ''),
                date_reg,
                date_valid,
                rev.get('revision_url', '')
            ))
        if not data:
            if skipped:
                self.log('WARN', f'Все {skipped} записей revision_info пропущены')
            return
        sql = """
            INSERT INTO npa_revision_info
            (base_npa_id, revision_id, revision_number, revision_date_reg, revision_date_valid, revision_url)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        try:
            self.db.exec_many(sql, data)
            self.log('OK', f'npa_revision_info: вставлено {len(data)} записей (пропущено: {skipped})')
        except Exception as e:
            self.log('ERROR', f'Ошибка при вставке npa_revision_info: {e}')

    def _gather_orders_from_body(self, items: List[dict]) -> Dict[str, int]:
        order_map = {}
        for item in items:
            revisions = item.get('revisions', [])
            if revisions:
                current = None
                for rev in revisions:
                    if rev.get('valid_to') is None:
                        current = rev
                        break
                if current is None and revisions:
                    revisions_sorted = sorted(revisions, key=lambda r: parse_date(r.get('valid_from')) or date.min)
                    current = revisions_sorted[-1]
                if current:
                    for block in current.get('body', []):
                        if block.get('type') == 'child_ref':
                            child_id = block.get('item_id')
                            order_val = block.get('order')
                            if child_id is not None and order_val is not None:
                                order_map[child_id] = order_val
            children = item.get('item_children', [])
            if children:
                child_orders = self._gather_orders_from_body(children)
                order_map.update(child_orders)
        return order_map

    def _flatten_items(self, items: List[dict], parent_item_id: str = None, order_map: Dict[str, int] = None) -> List[dict]:
        flat = []
        for idx, item in enumerate(items):
            item_id = item.get('item_id', '')
            sort_order = order_map.get(item_id, idx) if order_map else idx
            flat.append({
                'item_id': item_id,
                'parent_item_id': parent_item_id,
                'item_type': ITEM_TYPE_MAP.get(item.get('item_type', 'article'), 'article'),
                'item_number': item.get('item_number'),
                'item_level': item.get('item_level', 1),
                'sort_order': sort_order,
            })
            for child in item.get('item_children', []):
                flat.extend(self._flatten_items([child], parent_item_id=item_id, order_map=order_map))
        return flat

    def _insert_items_structure_bulk(self, items: List[dict], npa_id: int, mapping: Dict[str, int]):
        order_map = self._gather_orders_from_body(items)
        flat_items = self._flatten_items(items, order_map=order_map)
        if not flat_items:
            return
        rows = []
        for it in flat_items:
            rows.append((
                it['item_id'],
                npa_id,
                it['item_type'],
                it['item_number'],
                it['item_level'],
                it['sort_order'],
            ))
        self.db.bulk_load_csv(
            'npa_item',
            ['item_id', 'npa_id', 'item_type', 'item_number', 'item_level', 'sort_order'],
            rows
        )
        all_ids = [it['item_id'] for it in flat_items]
        placeholders = ','.join(['%s'] * len(all_ids))
        db_rows = self.db.fetch_all(
            f'SELECT id, item_id FROM npa_item WHERE item_id IN ({placeholders})', all_ids
        )
        for row in db_rows:
            mapping[row['item_id']] = row['id']
            self._item_id_cache[row['item_id']] = row['id']
        update_data = []
        for it in flat_items:
            if it['parent_item_id'] is not None:
                parent_internal = mapping.get(it['parent_item_id'])
                if parent_internal:
                    update_data.append((parent_internal, it['item_id']))
        if update_data:
            chunk_size = 1000
            for i in range(0, len(update_data), chunk_size):
                chunk = update_data[i:i + chunk_size]
                self.db.exec_many('UPDATE npa_item SET parent_id = %s WHERE item_id = %s', chunk)
        self.log('OK', f'Вставлено {len(mapping)} элементов в npa_item')

    def _exec_and_get_id(self, sql: str, params, table: str = '') -> int | None:
        if table and not self._require_table(table):
            return None
        try:
            with self.db.conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.lastrowid
        except Exception as e:
            self.log('ERROR', f'DB error ({table}): {e}')
            return None

    def _resolve_modified_by(self, raw_mod, local_mapping: Dict[str, int]) -> Union[str, None]:
        if raw_mod is None:
            return None
        numeric_ids = []
        parts = []
        if isinstance(raw_mod, (list, tuple)):
            parts = [str(p) for p in raw_mod]
        elif isinstance(raw_mod, str):
            parts = [p.strip() for p in raw_mod.split(',') if p.strip()]
        else:
            parts = [str(raw_mod)]
        for part in parts:
            resolved = local_mapping.get(part)
            if resolved is None:
                resolved = self._item_id_cache.get(part)
            if resolved is not None:
                numeric_ids.append(str(resolved))
            else:
                self.log('WARN', f'Не найден id для modified_by_id "{part}" в составе "{raw_mod}"')
        if not numeric_ids:
            return None
        result = ', '.join(numeric_ids)
        if len(numeric_ids) > 1:
            self.log('WARN', f'Несколько modified_by_id преобразованы в строку: "{result}". Убедитесь, что поле modified_by_id в БД имеет тип VARCHAR или TEXT.')
        return result

    def _resolve_not_valid(self, raw_not_valid: Optional[str], local_mapping: Dict[str, int]) -> Optional[int]:
        if not raw_not_valid:
            return None
        resolved = local_mapping.get(raw_not_valid)
        if resolved is None:
            resolved = self._item_id_cache.get(raw_not_valid)
        if resolved is None:
            self.log('WARN', f'Не найден id для not_valid "{raw_not_valid}"')
        return resolved

    def _insert_batch_executemany(self, table: str, columns: List[str], rows: List[tuple]):
        if not rows:
            return
        chunk_size = 1000
        placeholders = ','.join(['%s'] * len(columns))
        sql = f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})"
        for i in range(0, len(rows), chunk_size):
            chunk = rows[i:i+chunk_size]
            self.db.exec_many(sql, chunk)

    def _process_number_revisions(self, item: dict, internal_id: int, npa_id: int):
        number_revisions = item.get('number_revisions')
        if not number_revisions:
            return
        last_number = None
        last_valid_from = None
        for rev in number_revisions:
            vf = parse_date(rev.get('valid_from'))
            vt = parse_date(rev.get('valid_to'))
            if vf and vt and vf > vt:
                self.log('WARN', f'Пропущена number_revision с невалидными датами: valid_from={vf} > valid_to={vt} для {item.get("item_id")}')
                continue
            if vf is None:
                continue
            if vt is None:
                if last_valid_from is None or vf > last_valid_from:
                    last_number = rev.get('number_text')
                    last_valid_from = vf
            else:
                if last_valid_from is None or vf > last_valid_from:
                    last_number = rev.get('number_text')
                    last_valid_from = vf
        if last_number is not None:
            self.db.exec(
                'UPDATE npa_item SET item_number = %s WHERE id = %s',
                (last_number, internal_id)
            )
            self.log('OK', f'Обновлён item_number для {item["item_id"]} → {last_number} (из number_revisions)')
        rows = []
        for rev in number_revisions:
            vf = parse_date(rev.get('valid_from'))
            vt = parse_date(rev.get('valid_to'))
            if vf and vt and vf > vt:
                continue
            if vf is None:
                self.log('WARN', f'Пропущена версия номера для {item["item_id"]}: отсутствует valid_from')
                continue
            rows.append((
                internal_id,
                npa_id,
                rev.get('number_text', ''),
                vf,
                vt,
                rev.get('mod_type'),
                rev.get('modified_by_id'),
                rev.get('not_valid')
            ))
        if rows and self._require_table('npa_item_number_revision'):
            self._insert_batch_executemany(
                'npa_item_number_revision',
                ['item_internal_id', 'npa_id', 'number_text', 'valid_from', 'valid_to',
                 'mod_type', 'modified_by_id', 'not_valid'],
                rows
            )
            self.log('OK', f'Вставлено {len(rows)} записей в npa_item_number_revision для {item["item_id"]}')

    def _process_notes(self, npa_id: int, root_data: dict, items: list, mapping: Dict[str, int]):
        if not self._require_table('npa_note_unified'):
            return
        notes_to_insert = []

        def resolve_source_item_id(source_item_id_str: Optional[str]) -> Optional[int]:
            if not source_item_id_str:
                return None
            resolved = mapping.get(source_item_id_str)
            if resolved is None:
                resolved = self._item_id_cache.get(source_item_id_str)
            if resolved is None:
                self.log('WARN', f'Не найден id для source_item_id "{source_item_id_str}"')
            return resolved

        npa_notes = root_data.get('npa_notes', [])
        for note in npa_notes:
            text, valid_from, valid_to = parse_note_payload(note)
            if not text:
                continue
            source_item_id = resolve_source_item_id(note.get('source_item_id'))
            notes_to_insert.append((npa_id, source_item_id, 'npa', None, text, valid_from, valid_to))

        def traverse(item):
            item_notes = item.get('item_notes', [])
            for note in item_notes:
                text, valid_from, valid_to = parse_note_payload(note)
                if not text:
                    continue
                item_id = item.get('item_id')
                if not item_id:
                    continue
                source_item_id = resolve_source_item_id(note.get('source_item_id'))
                notes_to_insert.append((npa_id, source_item_id, 'item', item_id, text, valid_from, valid_to))
            for child in item.get('item_children', []):
                traverse(child)

        for item in items:
            traverse(item)

        if not notes_to_insert:
            return

        columns = self.db.fetch_all(
            "SELECT COLUMN_NAME FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = 'npa_note_unified'"
        )
        available_columns = {row['COLUMN_NAME'] for row in columns}
        has_source_item_id = 'source_item_id' in available_columns

        if 'valid_from' in available_columns and 'valid_to' in available_columns:
            if has_source_item_id:
                sql = """
                    INSERT INTO npa_note_unified (npa_id, source_item_id, target_type, target_id, note_text, valid_from, valid_to)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
            else:
                sql = """
                    INSERT INTO npa_note_unified (npa_id, target_type, target_id, note_text, valid_from, valid_to)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """
                notes_to_insert = [
                    (npa_id, target_type, target_id, note_text, valid_from, valid_to)
                    for npa_id, source_item_id, target_type, target_id, note_text, valid_from, valid_to in notes_to_insert
                ]
        elif 'note_date' in available_columns:
            if has_source_item_id:
                sql = """
                    INSERT INTO npa_note_unified (npa_id, source_item_id, target_type, target_id, note_text, note_date)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """
                notes_to_insert = [
                    (npa_id, source_item_id, target_type, target_id, note_text, valid_from)
                    for npa_id, source_item_id, target_type, target_id, note_text, valid_from, valid_to in notes_to_insert
                ]
            else:
                sql = """
                    INSERT INTO npa_note_unified (npa_id, target_type, target_id, note_text, note_date)
                    VALUES (%s, %s, %s, %s, %s)
                """
                notes_to_insert = [
                    (npa_id, target_type, target_id, note_text, valid_from)
                    for npa_id, source_item_id, target_type, target_id, note_text, valid_from, valid_to in notes_to_insert
                ]
        else:
            self.log('ERROR', 'Не удалось определить структуру npa_note_unified для вставки примечаний')
            return

        try:
            self.db.exec_many(sql, notes_to_insert)
            self.log('OK', f'Вставлено {len(notes_to_insert)} записей в npa_note_unified')
        except Exception as e:
            self.log('ERROR', f'Ошибка при вставке заметок: {e}')
            raise

    def _insert_items_revisions(self, items, npa_id, root_valid_from, mapping):
        head_data = []
        prefix_data = []

        def process_item(item, internal_id):
            self._process_number_revisions(item, internal_id, npa_id)

            add_date_by_mod = {}
            for rev in item.get('revisions', []):
                if rev.get('mod_type') == 'add':
                    rev_vf_str = rev.get('valid_from')
                    if rev_vf_str:
                        rev_vf = parse_date(rev_vf_str)
                        if rev_vf:
                            mod_by_str = rev.get('modified_by_id')
                            if mod_by_str:
                                for mod_id in (x.strip() for x in str(mod_by_str).split(',') if x.strip()):
                                    add_date_by_mod[mod_id] = rev_vf

            def get_vf(rev_dict, prev_vto):
                explicit_vf = parse_date(rev_dict.get('valid_from'))
                if explicit_vf is not None:
                    return explicit_vf
                if rev_dict.get('mod_type') == 'add':
                    mod_by = rev_dict.get('modified_by_id')
                    if mod_by:
                        mod_ids = [x.strip() for x in str(mod_by).split(',') if x.strip()]
                        for mid in mod_ids:
                            if mid in add_date_by_mod:
                                return add_date_by_mod[mid]
                return compute_valid_from(prev_vto, root_valid_from)

            prev_vto = None
            for hrev in item.get('head_revisions', []):
                hvf = parse_date(hrev.get('valid_from'))
                hvto = parse_date(hrev.get('valid_to'))
                if hvf and hvto and hvf > hvto:
                    self.log('WARN', f'Пропущена head_revision с невалидными датами: valid_from={hvf} > valid_to={hvto} для {item.get("item_id")}')
                    continue
                vfrom = get_vf(hrev, prev_vto)
                vto = hvto
                mod_by = self._resolve_modified_by(hrev.get('modified_by_id'), mapping)
                highlights_json = self._normalize_highlights(hrev.get('highlights'))
                not_valid_id = self._resolve_not_valid(hrev.get('not_valid'), mapping)
                head_data.append((internal_id, npa_id, hrev.get('head_text', ''), vfrom, vto, hrev.get('mod_type') or None, mod_by, highlights_json, not_valid_id))
                prev_vto = vto

            prev_vto = None
            for pref in item.get('item_prefix_revisions', []):
                pvf = parse_date(pref.get('valid_from'))
                pvto = parse_date(pref.get('valid_to'))
                if pvf and pvto and pvf > pvto:
                    self.log('WARN', f'Пропущена prefix_revision с невалидными датами: valid_from={pvf} > valid_to={pvto} для {item.get("item_id")}')
                    continue
                vfrom = get_vf(pref, prev_vto)
                vto = pvto
                mod_by = self._resolve_modified_by(pref.get('modified_by_id'), mapping)
                highlights_json = self._normalize_highlights(pref.get('highlights'))
                not_valid_id = self._resolve_not_valid(pref.get('not_valid'), mapping)
                prefix_data.append((internal_id, npa_id, pref.get('prefix_text', ''), vfrom, vto, pref.get('mod_type') or None, mod_by, highlights_json, not_valid_id))
                prev_vto = vto

            prev_vto = None
            for rev in item.get('revisions', []):
                explicit_vf = parse_date(rev.get('valid_from'))
                vto = parse_date(rev.get('valid_to'))
                
                if explicit_vf and vto and explicit_vf > vto:
                    self.log('WARN', f'Пропущена ревизия с невалидными датами: valid_from={explicit_vf} > valid_to={vto} для {item.get("item_id")}')
                    continue

                if explicit_vf is not None:
                    vfrom = explicit_vf
                else:
                    vfrom = compute_valid_from(prev_vto, root_valid_from)
                
                mod_by = self._resolve_modified_by(rev.get('modified_by_id'), mapping)
                highlights_json = self._normalize_highlights(rev.get('highlights'))
                mod_type = rev.get('mod_type') or None
                not_valid_id = self._resolve_not_valid(rev.get('not_valid'), mapping)

                rev_id = self._exec_and_get_id(
                    'INSERT INTO npa_item_revision '
                    '(item_internal_id, npa_id, valid_from, valid_to, mod_type, modified_by_id, highlights, not_valid) '
                    'VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
                    (internal_id, npa_id, vfrom, vto, mod_type, mod_by, highlights_json, not_valid_id),
                    table='npa_item_revision'
                )
                if rev_id is None:
                    prev_vto = vto
                    continue

                paras = []
                for block in rev.get('body', []):
                    btype = block.get('type') or block.get('block_type', 'paragraph')
                    if btype not in ('paragraph', 'table', 'child_ref', 'table_header', 'table_fragment'):
                        btype = 'paragraph'
                    html_txt = block.get('html_text', '')
                    plain = re.sub(r'<[^>]+>', '', html_txt).strip() if html_txt else ''
                    ref_id = block.get('item_id')
                    ref_internal = mapping.get(ref_id) if ref_id else None
                    order = block.get('order', 0)
                    paras.append((rev_id, internal_id, btype, order, html_txt or None, plain or None, ref_internal))

                if paras and self._require_table('npa_paragraph'):
                    self._insert_batch_executemany(
                        'npa_paragraph',
                        ['rev_id', 'item_internal_id', 'block_type', 'sort_order', 'html_text', 'plain_text', 'ref_item_internal_id'],
                        paras
                    )
                prev_vto = vto

            for child in item.get('item_children', []):
                child_internal = mapping.get(child.get('item_id'))
                if child_internal:
                    process_item(child, child_internal)

        for item in items:
            internal_id = mapping.get(item.get('item_id'))
            if internal_id is None:
                self.log('ERROR', f'Не найден internal_id для {item.get("item_id")}, пропуск ревизий')
                continue
            process_item(item, internal_id)

        if head_data and self._require_table('npa_item_head_revision'):
            self._insert_batch_executemany(
                'npa_item_head_revision',
                ['item_internal_id', 'npa_id', 'head_text', 'valid_from', 'valid_to', 'mod_type', 'modified_by_id', 'highlights', 'not_valid'],
                head_data
            )
            self.log('OK', f'Вставлено {len(head_data)} head_revision')

        if prefix_data and self._require_table('npa_item_prefix_revision'):
            self._insert_batch_executemany(
                'npa_item_prefix_revision',
                ['item_internal_id', 'npa_id', 'prefix_text', 'valid_from', 'valid_to', 'mod_type', 'modified_by_id', 'highlights', 'not_valid'],
                prefix_data
            )
            self.log('OK', f'Вставлено {len(prefix_data)} prefix_revision')

    def _insert_head_revisions(self, npa_id: int, revisions: list, root_valid_from: date, local_mapping: Dict[str, int]):
        if not self._require_table('npa_head_revision'):
            return
        data = []
        prev_valid_to = None
        for rev in revisions:
            vfrom = compute_valid_from(prev_valid_to, root_valid_from)
            vto = parse_date(rev.get('valid_to'))
            raw_mod = rev.get('modified_by_id')
            mod_converted = self._resolve_modified_by(raw_mod, local_mapping) if raw_mod is not None else None
            highlights_json = self._normalize_highlights(rev.get('highlights'))
            not_valid_id = self._resolve_not_valid(rev.get('not_valid'), local_mapping)
            data.append((npa_id, rev.get('npa_head', ''), vfrom, vto, mod_converted, highlights_json, not_valid_id))
            prev_valid_to = vto
        if data:
            self._insert_batch_executemany(
                'npa_head_revision',
                ['npa_id', 'npa_title', 'valid_from', 'valid_to', 'modified_by_id', 'highlights', 'not_valid'],
                data
            )
            self.log('OK', f'npa_head_revision: {len(data)} записей')

    def _count_items(self, items: list) -> int:
        count = len(items)
        for item in items:
            children = item.get('item_children', [])
            if children:
                count += self._count_items(children)
        return count

    def import_file(self, json_path: str) -> bool:
        filename = Path(json_path).name
        self.log('SECTION', f'═══ Начало импорта: {filename} ═══')
        try:
            with open(json_path, encoding='utf-8') as f:
                d = json.load(f)
        except Exception as e:
            self.log('ERROR', f'Не удалось прочитать JSON: {e}')
            return False
        npa_id = int(d.get('npa_id', 0))
        npa_type = d.get('npa_type', 'law')
        root_vf = parse_date(d.get('valid_from')) or parse_date(d.get('date_passed')) or date.today()
        self.log('INFO', f'npa_id={npa_id}, тип={npa_type}, номер={d.get("npa_number")}, valid_from={root_vf}')
        try:
            self.db.enable_checks()
            if not self._check_required_tables():
                return False
            exists = self._npa_exists(npa_id)
            if exists:
                self._clear_npa_data(npa_id)
            self.log('SECTION', '── Справочники ──')
            author_raw = d.get('npa_author', '')
            comm_raw = d.get('npa_npa_committee', '')
            signer_post = d.get('npa_signer_post', '')
            signer_fio = d.get('npa_signer', '')
            conv_id = self._find_or_create_convocation(comm_raw or author_raw, npa_type)
            committee_id = self._find_or_create_committee(comm_raw) if comm_raw else None
            self.log('SECTION', '── Паспорт НПА ──')
            if self._update_or_insert_npa_base(d) is None:
                raise RuntimeError('Не удалось вставить/обновить npa_base')
            revisions_info = d.get('revision_info', []) or d.get('revisions_info', [])
            if revisions_info:
                self._insert_revision_info(npa_id, revisions_info, npa_type)
            self.log('SECTION', '── Специфичные поля ──')
            self._insert_specific_fields(npa_id, npa_type, d, conv_id)
            self.log('SECTION', '── Авторы и подписанты ──')
            if signer_fio and signer_post:
                self._insert_signatory(npa_id, signer_fio, signer_post, conv_id)
            if author_raw:
                authors = [a.strip() for a in author_raw.split(',') if a.strip()]
                for author in authors:
                    person_id, post_id = self._process_author(author, conv_id, signer_fio)
                    self._insert_author_link(npa_id, person_id, post_id)
            else:
                self.log('DIM', 'Нет данных об авторах')
            self._insert_committee_link(npa_id, committee_id)
            self.log('SECTION', '── Структурные элементы ──')
            items = d.get('npa_items_revision', [])
            total_items = self._count_items(items)
            self.log('INFO', f'Элементов верхнего уровня: {len(items)}, всего: {total_items}')
            mapping = {}
            self.log('SECTION', '── Фаза 1: пакетная вставка структуры элементов (npa_item) ──')
            self._insert_items_structure_bulk(items, npa_id, mapping)
            self.log('OK', f'Вставлено {len(mapping)} элементов в npa_item')
            self.log('SECTION', '── Фаза 2: вставка ревизий и параграфов с правильной привязкой ──')
            self._insert_items_revisions(items, npa_id, root_vf, mapping)
            self.log('SECTION', '── Заголовки НПА ──')
            self._insert_head_revisions(npa_id, d.get('head_revision', []), root_vf, mapping)
            self.log('SECTION', '── Примечания (npa_notes / item_notes) ──')
            self._process_notes(npa_id, d, items, mapping)
            self.db.commit()
            self.log('OK', 'Транзакция зафиксирована')
            self.log('SECTION', f'═══ Импорт завершён: npa_id={npa_id} ═══')
            return True
        except Exception as e:
            try:
                self.db.rollback()
            except Exception:
                pass
            self.log('ERROR', f'ROLLBACK. Ошибка: {e}')
            self.log('DIM', traceback.format_exc())
            return False
        finally:
            try:
                self.db.enable_checks()
            except Exception:
                pass

class ImporterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('NPA JSON → MySQL Importer v8.4 (фильтры для удаления)')
        self.geometry('900x750')
        self.minsize(800, 650)
        self.configure(bg=COLOR['bg'])
        self._cfg = {
            'host': tk.StringVar(value=os.getenv('DB_HOST', 'localhost')),
            'port': tk.StringVar(value=os.getenv('DB_PORT', '3306')),
            'user': tk.StringVar(value=os.getenv('DB_USER', '')),
            'password': tk.StringVar(value=os.getenv('DB_PASSWORD', '')),
            'database': tk.StringVar(value=os.getenv('DB_NAME', '')),
        }
        self._json_path = tk.StringVar(value='')
        self._db = None
        self._importing = False
        self._npa_list_var = tk.StringVar()
        self._npa_combobox = None

        self._filter_year = tk.StringVar(value='Все')
        self._filter_type = tk.StringVar(value='Все')
        self._filter_sort = tk.StringVar(value='По номеру (возр.)')
        self._filter_number = tk.StringVar(value='')

        self._log_queue = queue.Queue()
        self._log_scheduled = False

        self._build_ui()
        self._bind_hotkeys()
        self._log('INFO', 'Импортёр готов (полная перезапись данных НПА, удаление любого НПА)')
        self._refresh_npa_list()

    def _bind_hotkeys(self):
        self.bind('<Control-KeyPress>', self._ctrl_keypress)

    def _ctrl_keypress(self, event):
        if event.keycode == 79:
            self._on_browse()
        elif event.keycode == 73:
            self._on_import()
        elif event.keycode == 81:
            self.destroy()
        elif event.keycode == 87:
            self.destroy()

    def _build_ui(self):
        top = tk.Frame(self, bg=COLOR['bg'], pady=8)
        top.pack(fill='x', padx=16)
        tk.Label(top, text='NPA Importer v8.4', bg=COLOR['bg'], fg=COLOR['accent'], font=('Arial', 16, 'bold')).pack(side='left')
        tk.Label(top, text=' полное удаление НПА', bg=COLOR['bg'], fg=COLOR['muted'], font=('Arial', 11)).pack(side='left')
        
        conn_frame = tk.Frame(self, bg=COLOR['border'], pady=8, padx=8)
        conn_frame.pack(fill='x', padx=16, pady=(0, 8))
        conn_inner = tk.Frame(conn_frame, bg=COLOR['panel'])
        conn_inner.pack(fill='x', expand=True)
        grid = tk.Frame(conn_inner, bg=COLOR['panel'])
        grid.pack(fill='x', padx=12, pady=8)
        fields = [('Хост:', 'host', 0, 0), ('Порт:', 'port', 0, 2), ('Пользователь:', 'user', 1, 0), ('Пароль:', 'password', 1, 2), ('База данных:', 'database', 2, 0)]
        for label, key, row, col in fields:
            tk.Label(grid, text=label, bg=COLOR['panel'], fg=COLOR['info'], font=('Arial', 10)).grid(row=row, column=col, sticky='e', padx=(8, 4), pady=4)
            show = '*' if key == 'password' else ''
            e = tk.Entry(grid, textvariable=self._cfg[key], bg=COLOR['input_bg'], fg=COLOR['text'], insertbackground=COLOR['text'], relief='flat', font=('Courier New', 10), show=show, width=28)
            e.grid(row=row, column=col + 1, sticky='ew', padx=(0, 16), pady=4)
            self._add_context_menu(e)
            grid.columnconfigure(col + 1, weight=1)
        btn_row = tk.Frame(conn_inner, bg=COLOR['panel'])
        btn_row.pack(fill='x', padx=12, pady=(0, 8))
        self._btn_connect = tk.Button(btn_row, text='Подключиться', command=self._on_connect, bg=COLOR['accent'], fg='white', relief='flat', padx=12, pady=5, font=('Arial', 10, 'bold'))
        self._btn_connect.pack(side='left', padx=(0, 8))
        self._lbl_status = tk.Label(btn_row, text='● Не подключено', bg=COLOR['panel'], fg=COLOR['error'], font=('Arial', 10))
        self._lbl_status.pack(side='left')
        
        file_frame = tk.Frame(self, bg=COLOR['border'], pady=8, padx=8)
        file_frame.pack(fill='x', padx=16, pady=(0, 8))
        file_inner = tk.Frame(file_frame, bg=COLOR['panel'])
        file_inner.pack(fill='x', expand=True)
        file_row = tk.Frame(file_inner, bg=COLOR['panel'])
        file_row.pack(fill='x', padx=12, pady=8)
        self._entry_file = tk.Entry(file_row, textvariable=self._json_path, bg=COLOR['input_bg'], fg=COLOR['text'], insertbackground=COLOR['text'], relief='flat', font=('Courier New', 10))
        self._entry_file.pack(side='left', fill='x', expand=True, padx=(0, 8))
        self._add_context_menu(self._entry_file)
        tk.Button(file_row, text='Обзор', command=self._on_browse, bg=COLOR['accent2'], fg='white', relief='flat', padx=12, pady=5).pack(side='left', padx=(0, 8))
        self._btn_import = tk.Button(file_row, text='Импортировать', command=self._on_import, bg=COLOR['btn'], fg='white', relief='flat', padx=12, pady=5, font=('Arial', 10, 'bold'))
        self._btn_import.pack(side='left')
        
        delete_frame = tk.Frame(self, bg=COLOR['border'], pady=8, padx=8)
        delete_frame.pack(fill='x', padx=16, pady=(0, 8))
        delete_inner = tk.Frame(delete_frame, bg=COLOR['panel'])
        delete_inner.pack(fill='x', expand=True)

        row1 = tk.Frame(delete_inner, bg=COLOR['panel'])
        row1.pack(fill='x', padx=12, pady=(8, 4))
        tk.Label(row1, text='Выберите НПА для удаления:', bg=COLOR['panel'], fg=COLOR['info'], font=('Arial', 10)).pack(side='left', padx=(0, 8))
        self._npa_combobox = ttk.Combobox(row1, textvariable=self._npa_list_var, state='readonly', width=50)
        self._npa_combobox.pack(side='left', fill='x', expand=True, padx=(0, 8))
        self._btn_refresh_list = tk.Button(row1, text='Обновить список', command=self._refresh_npa_list, bg=COLOR['accent2'], fg='white', relief='flat', padx=12, pady=5)
        self._btn_refresh_list.pack(side='left', padx=(0, 8))
        self._btn_delete = tk.Button(row1, text='Удалить выбранный НПА', command=self._delete_selected_npa, bg=COLOR['error'], fg='white', relief='flat', padx=12, pady=5, font=('Arial', 10, 'bold'))
        self._btn_delete.pack(side='left')

        row2 = tk.Frame(delete_inner, bg=COLOR['panel'])
        row2.pack(fill='x', padx=12, pady=(4, 8))

        tk.Label(row2, text='Год:', bg=COLOR['panel'], fg=COLOR['info'], font=('Arial', 9)).pack(side='left', padx=(0, 4))
        self._year_cb = ttk.Combobox(row2, textvariable=self._filter_year, state='readonly', width=8)
        self._year_cb.pack(side='left', padx=(0, 12))
        self._year_cb.bind('<<ComboboxSelected>>', lambda e: self._refresh_npa_list())

        tk.Label(row2, text='Тип:', bg=COLOR['panel'], fg=COLOR['info'], font=('Arial', 9)).pack(side='left', padx=(0, 4))
        self._type_cb = ttk.Combobox(row2, textvariable=self._filter_type, values=['Все', 'Закон', 'Постановление'], state='readonly', width=14)
        self._type_cb.pack(side='left', padx=(0, 12))
        self._type_cb.bind('<<ComboboxSelected>>', lambda e: self._refresh_npa_list())

        tk.Label(row2, text='Сортировка:', bg=COLOR['panel'], fg=COLOR['info'], font=('Arial', 9)).pack(side='left', padx=(0, 4))
        self._sort_cb = ttk.Combobox(row2, textvariable=self._filter_sort,
                                     values=['По номеру (возр.)', 'По номеру (убыв.)', 'По ID (возр.)', 'По ID (убыв.)'],
                                     state='readonly', width=16)
        self._sort_cb.pack(side='left', padx=(0, 12))
        self._sort_cb.bind('<<ComboboxSelected>>', lambda e: self._refresh_npa_list())

        tk.Label(row2, text='Фильтр по номеру:', bg=COLOR['panel'], fg=COLOR['info'], font=('Arial', 9)).pack(side='left', padx=(0, 4))
        self._number_entry = tk.Entry(row2, textvariable=self._filter_number, bg=COLOR['input_bg'], fg=COLOR['text'],
                                      insertbackground=COLOR['text'], relief='flat', font=('Courier New', 10), width=20)
        self._number_entry.pack(side='left', padx=(0, 8))
        self._add_context_menu(self._number_entry)
        self._number_entry.bind('<KeyRelease>', lambda e: self._refresh_npa_list())

        tk.Button(row2, text='Сбросить фильтры', command=self._reset_filters, bg=COLOR['accent2'], fg='white',
                  relief='flat', padx=8, pady=4, font=('Arial', 9)).pack(side='left')

        log_frame = tk.Frame(self, bg=COLOR['border'], pady=8, padx=8)
        log_frame.pack(fill='both', expand=True, padx=16, pady=(0, 12))
        log_inner = tk.Frame(log_frame, bg=COLOR['panel'])
        log_inner.pack(fill='both', expand=True)
        self._log_text = ScrolledText(log_inner, bg=COLOR['log_bg'], fg=COLOR['text'], font=('Courier New', 10), wrap='word')
        self._log_text.pack(fill='both', expand=True, padx=4, pady=4)
        self._add_context_menu(self._log_text)
        for tag, cfg in LOG_TAGS.items():
            self._log_text.tag_configure(tag, foreground=cfg['fg'], font=('Courier New', 10, 'bold') if cfg.get('font_bold') else ('Courier New', 10))
        self._log_text.tag_configure('DIM', foreground=COLOR['muted'])

    def _reset_filters(self):
        self._filter_year.set('Все')
        self._filter_type.set('Все')
        self._filter_sort.set('По номеру (возр.)')
        self._filter_number.set('')
        self._refresh_npa_list()

    def _add_context_menu(self, widget):
        menu = tk.Menu(widget, tearoff=0)
        menu.add_command(label="Вырезать", command=lambda: widget.event_generate("<<Cut>>"))
        menu.add_command(label="Копировать", command=lambda: widget.event_generate("<<Copy>>"))
        menu.add_command(label="Вставить", command=lambda: widget.event_generate("<<Paste>>"))
        menu.add_separator()
        if hasattr(widget, 'delete'):
            if widget.winfo_class() == 'Entry':
                menu.add_command(label="Очистить", command=lambda: widget.delete(0, tk.END))
            else:
                menu.add_command(label="Очистить", command=lambda: widget.delete('1.0', tk.END))
        def show_context_menu(event):
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
        widget.bind("<Button-3>", show_context_menu)

    def _log(self, level, msg):
        ts = datetime.now().strftime('%H:%M:%S')
        self._log_queue.put((ts, level, msg))
        self._schedule_log_flush()

    def _schedule_log_flush(self):
        if self._log_scheduled:
            return
        self._log_scheduled = True
        self.after(50, self._flush_log_queue)

    def _flush_log_queue(self):
        self._log_scheduled = False
        try:
            while True:
                ts, level, msg = self._log_queue.get_nowait()
                self._log_text.insert('end', f'[{ts}] ', 'DIM')
                self._log_text.insert('end', f'{msg}\n', level)
        except queue.Empty:
            pass
        self._log_text.see('end')
        self.update_idletasks()
        if not self._log_queue.empty():
            self._schedule_log_flush()

    def _on_connect(self):
        try:
            if self._db:
                self._db.disconnect()
            self._db = DBConnection({k: v.get() for k, v in self._cfg.items()})
            try:
                self._db.connect()
            except Exception as e:
                print("Ошибка при connect:", e)
                raise
            self._lbl_status.config(text='● Подключено', fg=COLOR['ok'])
            self._log('OK', 'Соединение установлено')
            self._load_available_years()
            self._refresh_npa_list()
        except Exception as e:
            self._lbl_status.config(text='● Ошибка', fg=COLOR['error'])
            self._log('ERROR', f'Ошибка: {e}')

    def _load_available_years(self):
        if not self._db:
            return
        try:
            rows = self._db.fetch_all('SELECT DISTINCT YEAR(date_passed) AS yr FROM npa_base WHERE date_passed IS NOT NULL ORDER BY yr DESC')
            years = ['Все'] + [str(r['yr']) for r in rows if r['yr']]
            self._year_cb['values'] = years
            if self._filter_year.get() not in years:
                self._filter_year.set('Все')
            self._log('OK', f'Загружено {len(years)-1} годов для фильтра')
        except Exception as e:
            self._log('ERROR', f'Ошибка загрузки годов: {e}')

    def _refresh_npa_list(self):
        if not self._db:
            self._log('ERROR', 'Нет подключения к БД')
            return
        try:
            year = self._filter_year.get()
            typ = self._filter_type.get()
            sort = self._filter_sort.get()
            number_filter = self._filter_number.get().strip()

            sql = "SELECT npa_id, npa_number, npa_type, date_passed FROM npa_base WHERE 1=1"
            params = []

            if year != 'Все' and year.isdigit():
                sql += " AND YEAR(date_passed) = %s"
                params.append(int(year))

            if typ != 'Все':
                type_map = {'Закон': 'law', 'Постановление': 'regulation'}
                if typ in type_map:
                    sql += " AND npa_type = %s"
                    params.append(type_map[typ])

            if number_filter:
                sql += " AND npa_number LIKE %s"
                params.append(f'%{number_filter}%')

            if sort == 'По номеру (возр.)':
                sql += " ORDER BY npa_number ASC"
            elif sort == 'По номеру (убыв.)':
                sql += " ORDER BY npa_number DESC"
            elif sort == 'По ID (возр.)':
                sql += " ORDER BY npa_id ASC"
            elif sort == 'По ID (убыв.)':
                sql += " ORDER BY npa_id DESC"
            else:
                sql += " ORDER BY npa_id DESC"

            rows = self._db.fetch_all(sql, tuple(params))
            if not rows:
                self._npa_combobox['values'] = []
                self._log('WARN', 'Нет НПА, соответствующих фильтрам')
                return

            items = []
            for row in rows:
                type_label = 'закон' if row['npa_type'] == 'law' else 'постановление'
                items.append(f"ID: {row['npa_id']} — № {row['npa_number']} ({type_label})")
            self._npa_combobox['values'] = items
            if items:
                self._npa_combobox.current(0)
            self._log('OK', f'Загружено {len(items)} НПА (фильтры применены)')
        except Exception as e:
            self._log('ERROR', f'Ошибка загрузки списка НПА: {e}')

    def _delete_selected_npa(self):
        if not self._db:
            self._log('ERROR', 'Нет подключения к БД')
            return
        selected = self._npa_list_var.get()
        if not selected:
            self._log('WARN', 'Не выбран НПА для удаления')
            return
        match = re.search(r'ID:\s*(\d+)', selected)
        if not match:
            self._log('ERROR', 'Не удалось определить npa_id из выбранной строки')
            return
        npa_id = int(match.group(1))
        if not messagebox.askyesno('Подтверждение удаления', f'Вы действительно хотите ПОЛНОСТЬЮ удалить НПА с ID={npa_id}?\nЭто действие необратимо.'):
            self._log('INFO', f'Удаление НПА {npa_id} отменено пользователем')
            return
        self._log('WARN', f'Начинаю полное удаление НПА {npa_id}...')
        try:
            importer = NpaImporter(self._db, self._log)
            success = importer.delete_npa_completely(npa_id)
            if success:
                self._log('OK', f'НПА {npa_id} успешно удалён из БД')
                self._refresh_npa_list()
                self._load_available_years()
            else:
                self._log('ERROR', f'Не удалось удалить НПА {npa_id}')
        except Exception as e:
            self._log('ERROR', f'Ошибка при удалении: {e}')

    def _on_browse(self):
        path = filedialog.askopenfilename(filetypes=[('JSON', '*.json')])
        if path:
            self._json_path.set(path)
            self._log('INFO', f'Выбран файл: {path}')

    def _on_import(self):
        if self._importing or not self._db:
            return
        path = self._json_path.get().strip()
        if not path or not Path(path).is_file():
            self._log('ERROR', 'Файл не найден')
            return
        self._importing = True
        self._btn_import.config(state='disabled', text='Импорт...')
        def run():
            importer = NpaImporter(self._db, self._log)
            ok = importer.import_file(path)
            self.after(0, lambda: self._on_import_done(ok))
        threading.Thread(target=run, daemon=True).start()

    def _on_import_done(self, ok):
        self._importing = False
        self._btn_import.config(state='normal', text='Импортировать')
        self._log('OK' if ok else 'ERROR', 'Импорт завершён')
        if ok:
            self._refresh_npa_list()
            self._load_available_years()

if __name__ == '__main__':
    app = ImporterApp()
    app.mainloop()
