"""Регрессионные тесты диспетчера очереди журнала GUI (verify/compare).

Корневая причина: кнопка ``fetch_models_btn`` («Обновить модели») была удалена
из GUI при рефакторинге настроек, но ``_poll_log`` продолжал обращаться к ней
по событию ``button`` → AttributeError в Tkinter-колбэке и остановка
диспетчера. В ``VerifyApp`` к тому же существовали два определения
``_poll_log`` (второе перекрывало первое).
"""

import importlib.util
import inspect
import queue
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "npazs_bootstrap", _ROOT / "src" / "bootstrap.py"
)
assert _spec is not None and _spec.loader is not None
_bootstrap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bootstrap)
_bootstrap.bootstrap()

from npazs.compare import gui as compare_gui
from npazs.verify import gui as verify_gui

#: События, которые реально кладут продюсеры в ``log_queue`` обоих GUI,
#: плюс легаси-событие ``button``: раньше оно роняло ``_poll_log``
#: на удалённом виджете ``fetch_models_btn``.
_ALL_EVENTS = [
    ('info', 'загружено'),
    ('warning', 'предупреждение'),
    ('error', 'ошибка'),
    ('button', 'Обновить модели'),
    ('models', ('ollama', ['m1'])),
    ('reset-signin', None),
    ('signin', True),
    ('failed', None),
    ('done', 'RESULT'),
]

_GUI_MODULES = [verify_gui, compare_gui]
_GUI_CLASSES = [verify_gui.VerifyApp, compare_gui.CompareApp]


class _FakeRoot:
    """Минимальная замена ``tk.Tk``: записывает ``after``-планировщики."""

    def __init__(self) -> None:
        self.scheduled: list = []

    def after(self, ms: int, callback) -> None:
        self.scheduled.append((ms, callback))


def _make_app(cls, events) -> object:
    """Экземпляр GUI-класса без ``__init__`` (без Tk) с ловушками хендлеров."""
    app = object.__new__(cls)
    app.log_queue: queue.Queue = queue.Queue()
    for event in events:
        app.log_queue.put(event)
    app.root = _FakeRoot()
    app.appended: list = []
    app.done: list = []
    app.running: list = []
    app.models: list = []
    app.signins = 0
    app._append_log = lambda msg, level='info': app.appended.append((level, msg))
    app._on_done = lambda result: app.done.append(result)
    app._set_running = lambda running: app.running.append(running)
    app._on_models_loaded = lambda payload: app.models.append(payload)
    app._show_ollama_signin_dialog = lambda: setattr(app, 'signins', app.signins + 1)
    return app


@pytest.mark.parametrize('cls', _GUI_CLASSES, ids=['verify', 'compare'])
def test_poll_log_dispatches_all_events_without_crash(cls, monkeypatch):
    """``_poll_log`` обязан обработать каждое событие продюсеров без исключений.

    Регрессия: событие ``button`` обращалось к удалённому ``fetch_models_btn``
    (AttributeError обрывал цикл — ``after`` больше не перепланировывался,
    журнал «умирал» навсегда).
    """
    from npazs.revision import ai_utils

    reset_calls: list = []
    monkeypatch.setattr(ai_utils, 'reset_ollama_signin_notice',
                        lambda: reset_calls.append(1))

    app = _make_app(cls, _ALL_EVENTS)
    cls._poll_log(app)

    # Живой цикл: после обработки ``_poll_log`` запланирован снова.
    assert app.root.scheduled and app.root.scheduled[0][0] == 150
    # Легаси-событие button не роняет диспетчер (упало бы AttributeError).
    assert ('button', 'Обновить модели') in app.appended
    # Обычные уровни ушли в журнал.
    assert ('info', 'загружено') in app.appended
    assert ('warning', 'предупреждение') in app.appended
    assert ('error', 'ошибка') in app.appended
    # Служебные события НЕ засоряют журнал (раньше reset-signin писал «None»).
    assert all(level not in ('models', 'reset-signin', 'signin', 'failed', 'done')
               for level, _ in app.appended)
    # Каждый хендлер вызван ровно по назначению.
    assert app.models == [('ollama', ['m1'])]
    assert reset_calls == [1]
    assert app.signins == 1
    assert app.running == [False]
    assert app.done == ['RESULT']


@pytest.mark.parametrize('module', _GUI_MODULES, ids=['verify', 'compare'])
def test_poll_log_defined_exactly_once(module):
    """В модуле не должно быть второго ``_poll_log``, перекрывающего первый."""
    source = inspect.getsource(module)
    assert source.count('def _poll_log(') == 1


@pytest.mark.parametrize('module', _GUI_MODULES, ids=['verify', 'compare'])
def test_no_references_to_removed_fetch_models_button(module):
    """Кнопка ``fetch_models_btn`` удалена из GUI — упоминаний не остаётся."""
    assert 'fetch_models_btn' not in inspect.getsource(module)
