"""Общие утилиты NPA-ZS: логирование, файловые операции, валидация, отчёты.

Пакет содержит инфраструктурный код, не привязанный к предметной области НПА.
Логику работы с ревизиями и HTML ищите в :mod:`npazs.revision`.

:mod:`npazs.utils.logging`
    Настройка логгеров, ротация файлов в ``data/logs``, мост ``log_callback``
    (сигнатура ``(message, level)``, принятая во всём проекте) <-> ``logging``.

:mod:`npazs.utils.file_ops`
    Безопасное чтение/запись JSON в UTF-8, атомарная замена файлов, резервные
    копии, обход каталога ``data/base``.

:mod:`npazs.utils.validation`
    Проверки каноничной JSON-структуры НПА: уникальность ``item_id``,
    целостность ``child_ref``, корректность и хронология ревизий.

:mod:`npazs.utils.reporting`
    Сборка отчёта о прогоне в Markdown (``data/work_tools/report.md``).
"""

__all__ = [
    'logging',
    'file_ops',
    'validation',
    'reporting',
]
