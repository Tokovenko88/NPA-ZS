"""Настройка логирования NPA-ZS.

В проекте исторически используются два стиля логирования:

1. **``log_callback(message, level)``** — колбэк, который передаётся сквозь весь
   слой ``revision`` и пайплайн. ``level`` — строка вида ``'info'``,
   ``'warning'``, ``'error'``, ``'result'``, ``'section'``.
2. **``logging``** — стандартный модуль, используемый парсером HTML и
   MODX-процессором (там же :class:`npazs.core.queue_handler.QueueHandler`).

Модуль связывает оба стиля: :func:`callback_to_logger` превращает логгер в
``log_callback``, а :class:`CallbackHandler` — наоборот, направляет записи
``logging`` в произвольный колбэк.

Файлы логов складываются в ``data/logs`` с ротацией.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from typing import Callable, Optional

__all__ = [
    'LEVEL_MAP',
    'DEFAULT_FORMAT',
    'CallbackHandler',
    'callback_to_logger',
    'get_logger',
    'setup_logging',
    'log_path',
]

#: Отображение «уровень проекта» -> «уровень logging».
LEVEL_MAP = {
    'debug': logging.DEBUG,
    'info': logging.INFO,
    'section': logging.INFO,
    'result': logging.INFO,
    'ok': logging.INFO,
    'warning': logging.WARNING,
    'warn': logging.WARNING,
    'error': logging.ERROR,
    'critical': logging.CRITICAL,
}

DEFAULT_FORMAT = '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s'
DEFAULT_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

_DEFAULT_MAX_BYTES = 5 * 1024 * 1024
_DEFAULT_BACKUPS = 5

_configured = False


def _logs_dir() -> str:
    """Каталог ``data/logs`` (создаётся при необходимости)."""
    try:
        from npazs.constants import LOGS_DIR
    except Exception:  # pragma: no cover - fallback для запуска вне пакета
        LOGS_DIR = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            '..', 'data', 'logs',
        )
        LOGS_DIR = os.path.abspath(LOGS_DIR)
    os.makedirs(LOGS_DIR, exist_ok=True)
    return LOGS_DIR


def log_path(name: str = 'npazs.log') -> str:
    """Полный путь к файлу лога в ``data/logs``."""
    return os.path.join(_logs_dir(), name)


class CallbackHandler(logging.Handler):
    """Направляет записи ``logging`` в ``log_callback(message, level)``."""

    def __init__(self, callback: Callable[[str, str], None], level: int = logging.NOTSET):
        super().__init__(level)
        self._callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._callback(self.format(record), record.levelname.lower())
        except Exception:  # pragma: no cover - логирование не должно ломать поток
            self.handleError(record)


def callback_to_logger(logger: logging.Logger) -> Callable[..., None]:
    """Вернуть ``log_callback``-совместимую функцию, пишущую в ``logger``.

    Сигнатура результата: ``callback(message, level='info')`` — ровно то, что
    ожидает код в :mod:`npazs.revision`.
    """

    def _callback(message: str, level: str = 'info') -> None:
        logger.log(LEVEL_MAP.get(str(level).lower(), logging.INFO), '%s', message)

    return _callback


def setup_logging(
    level: Optional[str] = None,
    *,
    filename: str = 'npazs.log',
    console: bool = True,
    force: bool = False,
) -> logging.Logger:
    """Настроить корневой логгер проекта (идемпотентно).

    ``level`` по умолчанию берётся из ``LOG_LEVEL`` (``.env``).
    """
    global _configured

    root = logging.getLogger('npazs')
    if _configured and not force:
        return root

    if level is None:
        try:
            from npazs.config import get_settings

            level = get_settings().log_level
        except Exception:  # pragma: no cover
            level = 'INFO'

    numeric_level = getattr(logging, str(level).upper(), logging.INFO)
    root.setLevel(numeric_level)
    root.handlers.clear()
    root.propagate = False

    formatter = logging.Formatter(DEFAULT_FORMAT, DEFAULT_DATE_FORMAT)

    file_handler = logging.handlers.RotatingFileHandler(
        log_path(filename),
        maxBytes=_DEFAULT_MAX_BYTES,
        backupCount=_DEFAULT_BACKUPS,
        encoding='utf-8',
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    if console:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)

    _configured = True
    return root


def get_logger(name: str = 'npazs') -> logging.Logger:
    """Получить логгер проекта, настроив логирование при первом вызове."""
    setup_logging()
    return logging.getLogger(name if name.startswith('npazs') else f'npazs.{name}')
