"""Смена провайдера в ПОСТ-АНАЛИЗЕ: диалог, провайдер, отказ без падения.

Регрессия (лог прогона 27.09.2026):

    Все попытки (3) исчерпаны. Запрос к пользователю...
    Пользователь остановил процесс
    Пост-анализ: ИИ не вернул валидный вердикт (status отсутствует)

Причины, которые закрывают эти тесты:

1. ``orchestrator.py`` обнулял ``_constants._settings_provider`` ДО
   ``run_post_analysis()`` — диалог «Переключить бэкенд» в
   ``_reapply_request_after_switch()`` получал ``None`` и любой выбор
   превращался в «Пользователь остановил процесс».
2. Провайдер должен возвращать НАСТРОЙКИ ПОСТ-АНАЛИЗА (POST_ANALYSIS_*),
   а не основного бэкенда прогона.
3. Отказ модели пост-анализа не должен ронять приложение: ``status='error'``
   и работа продолжается (диалог предлагает сменить провайдера).
"""

import importlib.util
import json
import threading
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "npazs_bootstrap", _ROOT / "src" / "bootstrap.py"
)
assert _spec is not None and _spec.loader is not None
_bootstrap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bootstrap)
_bootstrap.bootstrap()

from npazs import constants
from npazs.revision import ai_utils
from npazs.revision import post_analysis as pa

try:  # тесты — пакет (tests/__init__.py есть)
    from tests.test_post_analysis import _make_result, _write_result_file
except ImportError:  # pragma: no cover — прямой запуск из tests/
    from test_post_analysis import _make_result, _write_result_file


class _Resp:
    """Мини-заглушка ``requests.Response``."""

    def __init__(self, status_code=200, payload=None, text=''):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or json.dumps(self._payload, ensure_ascii=False)

    def json(self):
        return self._payload


def _ok_answer(text='{"status": "correct", "summary": "ok"}'):
    return _Resp(200, {'choices': [{'message': {'content': text}}]})


def _install_posts(monkeypatch, first_status=500):
    """Первый запрос падает, последующие отвечают валидным вердиктом."""
    calls = []

    def fake_post(url, data=None, headers=None, timeout=None):
        calls.append({'url': url, 'headers': dict(headers or {})})
        if len(calls) == 1 and first_status != 200:
            return _Resp(first_status, {'error': 'boom'}, text='HTTP 500: boom')
        return _ok_answer()

    monkeypatch.setattr(ai_utils.requests, 'post', fake_post)
    monkeypatch.setattr(ai_utils.time, 'sleep', lambda _s: None)
    return calls


def test_switch_after_failures_uses_registered_provider(monkeypatch):
    """После 3 неудач выбор «Переключить бэкенд» реально меняет провайдер.

    Провайдер зарегистрирован (как это делает оркестратор на время
    постанализа) → запрос уходит на НОВЫЙ backend/URL/key, ``stop_event``
    НЕ устанавливается, прогон продолжается.
    """
    calls = _install_posts(monkeypatch)
    monkeypatch.setattr(
        constants, '_user_retry_callback',
        lambda msg, action='retry': 'switch',
    )
    monkeypatch.setattr(
        constants, '_settings_provider',
        lambda: {
            'backend': 'openrouter',
            'model': 'new-model',
            'base_url': 'http://new.test/v1',
            'api_key': 'new-key',
            'agent_session': None,
        },
    )
    stop = threading.Event()
    logs = []

    answer = ai_utils.ask_kilo_gateway(
        '{"a": 1}', 'old-model', lambda *a: logs.append(a),
        backend='qwen2api', base_url='http://old.test/v1', api_key='old-key',
        max_retries=1, retry_delay=0, stop_event=stop, repair_json=False,
    )

    assert answer == '{"status": "correct", "summary": "ok"}'
    assert not stop.is_set(), 'переключение не должно останавливать прогон'
    assert len(calls) == 2, f'ожидался повтор после переключения, calls={calls}'
    assert calls[0]['url'] == 'http://old.test/v1/chat/completions'
    assert calls[1]['url'] == 'http://new.test/v1/chat/completions'
    assert calls[1]['headers']['Authorization'] == 'Bearer new-key'
    joined = ' '.join(str(entry) for entry in logs)
    assert 'переключён на openrouter' in joined


def test_switch_without_provider_stops_without_crash(monkeypatch):
    """Без зарегистрированного провайдера — штатная остановка, без исключений.

    Именно так раньше заканчивался пост-анализ (провайдер был обнулён до
    него): выбор «Переключить бэкенд» не должен падать, но и работать без
    провайдера не может — по этой причине оркестратор регистрирует его на
    время ``run_post_analysis()``.
    """
    calls = _install_posts(monkeypatch)
    monkeypatch.setattr(
        constants, '_user_retry_callback',
        lambda msg, action='retry': 'switch',
    )
    monkeypatch.setattr(constants, '_settings_provider', None)
    stop = threading.Event()
    logs = []

    answer = ai_utils.ask_kilo_gateway(
        '{"a": 1}', 'model', lambda *a: logs.append(a),
        backend='qwen2api', base_url='http://old.test/v1', api_key='k',
        max_retries=1, retry_delay=0, stop_event=stop, repair_json=False,
    )

    assert answer is None
    assert stop.is_set()
    assert len(calls) == 1, 'повторов без провайдера быть не должно'
    joined = ' '.join(str(entry) for entry in logs)
    assert 'Пользователь остановил процесс' in joined


class _Var:
    """Заглушка ``tk.StringVar`` (``get()`` без Tk)."""

    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value


def test_post_analysis_settings_provider_returns_post_settings():
    """Провайдер постанализа отдаёт ПОСТ-бэкенд, а не основной.

    ``AiPipelineMixin._post_analysis_settings_provider`` — то, что
    регистрируется оркестратором на время ``run_post_analysis()``.
    """
    from npazs.pipeline.orchestrator import AiPipelineMixin

    class _Stub(AiPipelineMixin):
        def __init__(self):
            self.post_analysis_backend = _Var('qwen2api')
            self.post_analysis_model = _Var('pa-model')
            self.post_gateway_url = _Var('http://pa.test/v1')

        def _api_key_for(self, backend, target='main'):
            assert target == 'post', 'пост-анализ обязан читать ключ пост-бэкенда'
            return 'pa-key'

        def log(self, *args, **kwargs):
            pass

    snap = _Stub()._post_analysis_settings_provider()
    assert snap == {
        'backend': 'qwen2api',
        'model': 'pa-model',
        'base_url': 'http://pa.test/v1',
        'api_key': 'pa-key',
        'agent_session': None,
    }


def test_post_analysis_settings_provider_fills_defaults():
    """Пустые модель/URL добираются из констант, а не остаются пустыми."""
    from npazs.constants import HTTP_BACKEND_DEFS
    from npazs.pipeline.orchestrator import AiPipelineMixin

    class _Stub(AiPipelineMixin):
        post_analysis_backend = _Var('openrouter')
        post_analysis_model = _Var('')
        post_gateway_url = _Var('')

        def _api_key_for(self, backend, target='main'):
            return ''

    snap = _Stub()._post_analysis_settings_provider()
    defn = HTTP_BACKEND_DEFS['openrouter']
    assert snap['model'] == defn['default_model']
    assert snap['base_url'] == defn['base_url']
    assert snap['agent_session'] is None


def test_orchestrator_registers_post_provider_around_run_post_analysis():
    """Структурная защита: провайдер регистрируется ДО постанализа.

    Раньше строка ``_constants._settings_provider = None`` стояла ПЕРЕД
    ``run_post_analysis()`` — из-за этого переключение провайдера в
    постанализе всегда сводилось к «Пользователь остановил процесс».
    """
    src = (_ROOT / 'src' / 'pipeline' / 'orchestrator.py').read_text(
        encoding='utf-8')
    register = src.index('self._post_analysis_settings_provider)')
    call = src.index('pa_result = run_post_analysis(')
    assert register < call, 'провайдер должен регистрироваться до вызова'
    segment = src[register:call]
    assert '_settings_provider = None' not in segment, (
        'провайдер не должен обнуляться между регистрацией и вызовом'
    )
    assert "_settings_provider_scope = 'post'" in segment
    # Финальная очистка есть и идёт ПОСЛЕ вызова постанализа.
    cleanup = src.index('_constants._settings_provider = None', call)
    assert cleanup > call
    # До постанализа провайдер больше не обнуляется (кроме finally внутри
    # блока — он идёт после вызова, что проверено выше).
    assert src.count('_constants._settings_provider = None') == 2


def test_run_post_analysis_ai_failure_returns_error_and_does_not_raise(
        tmp_path, monkeypatch):
    """Модель пост-анализа не ответила → status='error', приложение живо.

    ``run_post_analysis`` не бросает исключение, результат прогона сохранён,
    а в лог идёт понятное сообщение вместо «ИИ не вернул валидный вердикт».
    """
    orig_file, change = _write_result_file(tmp_path, _make_result())
    result_file = tmp_path / '127_2015_04_17_izm_516_2019_07_08.json'
    result_data = json.loads(result_file.read_text(encoding='utf-8'))

    monkeypatch.setattr(pa, 'ask_ollama', lambda *a, **k: None)
    logs = []
    res = pa.run_post_analysis(
        str(orig_file), result_data, change,
        model='stub', backend='kilo_gateway',
        log_callback=lambda msg, level='info': logs.append((level, str(msg))),
    )

    assert isinstance(res, dict)
    assert res['status'] == 'error'
    assert res['corrected_path'] is None
    joined = ' '.join(msg for _level, msg in logs)
    assert 'ИИ не ответил' in joined
    assert 'прогон сохранён' in joined
    # Отчёт пишется и в этом сценарии — падения/исключения нет.
    assert res.get('report_path') and Path(res['report_path']).exists()


def test_retry_dialog_hint_is_scope_aware():
    """Диалог смены провайдера знает область: основной прогон или пост-анализ."""
    src = (_ROOT / 'src' / 'ui' / 'revision_app.py').read_text(encoding='utf-8')
    assert "_settings_provider_scope" in src
    assert 'блоке «Пост-анализ»' in src, (
        'для области post диалог должен подсывать менять пост-бэкенд'
    )


def test_run_post_analysis_switch_provider_end_to_end(tmp_path, monkeypatch):
    """Сценарий из лога: 3x HTTP 401 от qwen2api → диалог → переключение.

    Пост-анализ НЕ завершается: после выбора «Переключить бэкенд» запрос
    уходит на новый провайдер и вердикт получается, ``status == 'correct'``.
    """
    orig_file, change = _write_result_file(tmp_path, _make_result())
    result_file = tmp_path / '127_2015_04_17_izm_516_2019_07_08.json'
    result_data = json.loads(result_file.read_text(encoding='utf-8'))

    calls = []

    def fake_post(url, data=None, headers=None, timeout=None):
        calls.append(url)
        if len(calls) <= 3:
            return _Resp(
                401, {'error': 'Unauthorized'},
                text='HTTP 401: {"error":"Unauthorized"}',
            )
        return _ok_answer('{"status": "correct", "summary": "ok", "issues": []}')

    monkeypatch.setattr(ai_utils.requests, 'post', fake_post)
    monkeypatch.setattr(ai_utils.time, 'sleep', lambda _s: None)
    monkeypatch.setattr(
        constants, '_user_retry_callback',
        lambda msg, action='retry': 'switch',
    )
    monkeypatch.setattr(
        constants, '_settings_provider',
        lambda: {
            'backend': 'openrouter',
            'model': 'pa-2',
            'base_url': 'http://new.test/v1',
            'api_key': 'k2',
            'agent_session': None,
        },
    )

    logs = []
    res = pa.run_post_analysis(
        str(orig_file), result_data, change,
        model='stub', backend='qwen2api',
        kilo_gateway_url='http://old.test/v1', api_key='k1',
        log_callback=lambda msg, level='info': logs.append(str(msg)),
    )

    assert res['status'] == 'correct', f'лог: {logs[-8:]}'
    assert len(calls) == 4, f'3 неудачи + переключение, calls={calls}'
    assert calls[:3] == ['http://old.test/v1/chat/completions'] * 3
    assert calls[3] == 'http://new.test/v1/chat/completions'
    joined = ' '.join(logs)
    assert 'переключён на openrouter' in joined
    assert 'Все попытки' in joined, 'диалог должен появиться после 3 попыток'

