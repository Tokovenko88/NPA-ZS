"""Файловые операции NPA-ZS: JSON в UTF-8, атомарная запись, обход базы.

Все JSON-файлы проекта — UTF-8 без BOM, с отступом 2 и ``ensure_ascii=False``:
русский текст должен читаться в diff'ах, иначе ревью изменений НПА невозможно.

Не путайте с :mod:`npazs.revision.file_ops` — там ``FileOpsMixin`` для GUI
(диалоги «Открыть»/«Сохранить», запоминание последних путей). Здесь — чистые
функции без Tk.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Optional, Union

__all__ = [
    'JSON_INDENT',
    'read_json',
    'write_json',
    'write_text_atomic',
    'read_text',
    'backup_file',
    'ensure_dir',
    'iter_base_documents',
    'find_base_document',
    'timestamp_slug',
]

#: Отступ JSON во всех файлах проекта.
JSON_INDENT = 2

PathLike = Union[str, os.PathLike]


def ensure_dir(path: PathLike) -> Path:
    """Создать каталог (включая родителей) и вернуть его как :class:`Path`."""
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def read_json(path: PathLike, default: Any = None) -> Any:
    """Прочитать JSON. Если файла нет — вернуть ``default``.

    Ошибки разбора НЕ подавляются: битый JSON НПА должен падать громко,
    иначе можно молча импортировать половину документа.
    """
    file_path = Path(path)
    if not file_path.exists():
        return default
    with file_path.open('r', encoding='utf-8') as handle:
        return json.load(handle)


def write_json(path: PathLike, data: Any, *, atomic: bool = True) -> Path:
    """Записать JSON в UTF-8 (``ensure_ascii=False``, отступ 2).

    При ``atomic=True`` данные пишутся во временный файл в том же каталоге и
    затем переименовываются: прерывание процесса не оставит обрезанный JSON.
    """
    payload = json.dumps(data, ensure_ascii=False, indent=JSON_INDENT)
    return write_text_atomic(path, payload, atomic=atomic)


def write_text_atomic(path: PathLike, text: str, *, atomic: bool = True) -> Path:
    """Записать текст в UTF-8 без BOM, при необходимости атомарно."""
    file_path = Path(path)
    ensure_dir(file_path.parent)

    if not atomic:
        with file_path.open('w', encoding='utf-8', newline='\n') as handle:
            handle.write(text)
        return file_path

    fd, tmp_name = tempfile.mkstemp(
        dir=str(file_path.parent), prefix=f'.{file_path.name}.', suffix='.tmp'
    )
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, file_path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return file_path


def read_text(path: PathLike, default: Optional[str] = None) -> Optional[str]:
    """Прочитать текстовый файл в UTF-8 (BOM отбрасывается)."""
    file_path = Path(path)
    if not file_path.exists():
        return default
    return file_path.read_text(encoding='utf-8-sig')


def timestamp_slug(moment: Optional[datetime] = None) -> str:
    """Метка времени для имён файлов/каталогов: ``YYYY-MM-DD_HH-MM-SS``."""
    return (moment or datetime.now()).strftime('%Y-%m-%d_%H-%M-%S')


def backup_file(path: PathLike, *, suffix: Optional[str] = None) -> Optional[Path]:
    """Создать резервную копию файла рядом с оригиналом.

    Возвращает путь копии или ``None``, если исходного файла нет.
    """
    file_path = Path(path)
    if not file_path.exists():
        return None
    marker = suffix or timestamp_slug()
    backup_path = file_path.with_name(f'{file_path.stem}.{marker}{file_path.suffix}.bak')
    shutil.copy2(file_path, backup_path)
    return backup_path


def iter_base_documents(
    root: Optional[PathLike] = None,
    doc_type: Optional[str] = None,
) -> Iterator[Path]:
    """Перебрать JSON-файлы НПА в ``data/base``.

    ``doc_type`` — ``'law'``, ``'resolution'`` либо ``None`` (все).
    Обход рекурсивный: документы с историей изменений лежат в подкаталогах,
    названных по номеру базового НПА (например, ``law/110/110_....json``).
    """
    if root is None:
        from npazs.constants import BASE_DIR

        root = BASE_DIR
    base = Path(root)
    if doc_type:
        base = base / doc_type
    if not base.exists():
        return
    yield from sorted(base.rglob('*.json'))


def find_base_document(number: str, doc_type: str = 'law') -> Optional[Path]:
    """Найти файл базового НПА по номеру в ``data/base/<doc_type>``.

    Сначала проверяется ``<number>/<number>.json`` (документ с историей),
    затем плоский ``<number>.json``.
    """
    from npazs.constants import BASE_DIR

    base = Path(BASE_DIR) / doc_type
    nested = base / str(number) / f'{number}.json'
    if nested.exists():
        return nested
    flat = base / f'{number}.json'
    return flat if flat.exists() else None
