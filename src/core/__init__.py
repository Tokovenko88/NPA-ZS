"""Ядро NPA-ZS: парсинг HTML НПА в JSON и интеграция с MODX.

Модули:

:mod:`npazs.core.html_parser`
    Класс ``NpaToJsonGenerator`` — основной парсер HTML нормативного правового
    акта в каноническую JSON-структуру (иерархия ``item_children``, ревизии,
    примечания). Самый крупный модуль проекта.

:mod:`npazs.core.html_to_json`
    Тонкий совместимый фасад над ``html_parser`` (историческое имя модуля).

:mod:`npazs.core.modx_processor`
    Класс ``MODXHTMLProcessor`` — выгрузка ресурсов НПА из MODX (SSH + MySQL)
    и подготовка HTML к парсингу.

:mod:`npazs.core.modx_gui`
    Класс ``MODXProcessorGUI`` — Tk-интерфейс парсера/выгрузки из MODX.

:mod:`npazs.core.queue_handler`
    Класс ``QueueHandler`` — потокобезопасное логирование в ``queue.Queue``
    для отображения в GUI.

Импорт подмодулей намеренно ленивый: ``html_parser`` тянет ``paramiko``,
``pymysql`` и ``tkinter``, поэтому ``import npazs.core`` не должен требовать
установленного GUI-стека.
"""

__all__ = [
    'html_parser',
    'html_to_json',
    'modx_processor',
    'modx_gui',
    'queue_handler',
]
