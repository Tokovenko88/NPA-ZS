"""Слой пользовательского интерфейса NPA-ZS (Tkinter).

Модули:

:mod:`npazs.ui.revision_app`
    Класс ``App`` — главное окно внесения изменений в НПА. Собран из примесей::

        App(GuiBuilderMixin, AiPipelineMixin, FileOpsMixin)

    * ``GuiBuilderMixin`` (:mod:`npazs.ui.gui_builder`) — построение виджетов;
    * ``AiPipelineMixin`` (:mod:`npazs.pipeline.orchestrator`) — этапы 1-5;
    * ``FileOpsMixin`` (:mod:`npazs.revision.file_ops`) — открытие/сохранение.

:mod:`npazs.ui.parser_app`
    Обёртка запуска GUI парсера HTML -> JSON (``MODXProcessorGUI``).

:mod:`npazs.ui.gui_builder`
    ``GuiBuilderMixin`` — раскладка панелей, полей и журнала.

:mod:`npazs.ui.dialogs`
    Модальные диалоги, через которые пайплайн задаёт вопросы оператору.

Сравнение редакций НПА живёт в отдельном пакете — :mod:`npazs.compare`
(GUI: :mod:`npazs.compare.gui`, запуск: ``scripts/run_compare.py``), —
но построено на тех же правилах потоков, что описаны ниже.

Правило потоков
---------------
Вся работа пайплайна идёт в фоновом потоке, а виджеты Tk трогает только
главный поток. Обмен — через ``queue.Queue``:

* ``log_queue``    — сообщения журнала (см. :class:`npazs.core.queue_handler.QueueHandler`);
* ``answer_queue`` — ответы оператора на вопросы пайплайна;
* ``stop_event``   — ``threading.Event`` для отмены прогона.

Нарушение этого правила приводит к неустойчивым падениям Tk, которые почти
невозможно воспроизвести.
"""

__all__ = [
    'revision_app',
    'parser_app',
    'gui_builder',
    'dialogs',
]
