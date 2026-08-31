"""Логирование в очередь для потокобезопасного вывода в GUI.

Класс :class:`QueueHandler` — стандартный ``logging.Handler``, который вместо
записи в файл/поток кладёт отформатированное сообщение в ``queue.Queue``.

Это позволяет фоновым рабочим потокам (парсер HTML, MODX-процессор, AI-пайплайн)
писать логи, а Tk-потоку — безопасно их читать и отображать, не нарушая правило
«обращаться к виджетам Tk только из главного потока».

Формат элемента очереди::

    ('log', <отформатированное сообщение>, <имя уровня>)

Исторически класс жил в ``npa_processor/core/html_parser.py``. В NPA-ZS он
вынесен в отдельный модуль, а ``npazs.core.html_parser`` реэкспортирует его для
обратной совместимости (``from npazs.core.html_parser import QueueHandler``).
"""

import logging

__all__ = ['QueueHandler']


class QueueHandler(logging.Handler):
    """Обработчик логов, складывающий записи в очередь для GUI."""

    def __init__(self, log_queue, level=logging.NOTSET):
        super().__init__(level)
        self.log_queue = log_queue

    def emit(self, record):
        msg = self.format(record)
        self.log_queue.put(('log', msg, record.levelname))
