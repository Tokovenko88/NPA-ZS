"""Тесты записи API-ключей и параметров бэкендов в ``.env`` (``npazs.config.env_store``)."""

import importlib.util
import os
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

from npazs.config.env_store import (
    ACTIVE_BACKEND_ENV,
    BACKEND_ENV_KEYS,
    env_var_names,
    get_env_value,
    load_active_backend,
    load_backend_settings,
    save_backend_settings,
    save_env_values,
)
from npazs.config.ollama import SUPPORTED_BACKENDS


@pytest.fixture()
def env_file(tmp_path):
    """Файл ``.env`` с комментарием, пустой строкой и одним ключом."""
    path = tmp_path / '.env'
    path.write_text(
        '# NPA-ZS — локальные настройки\n'
        '\n'
        'KILO_GATEWAY_API_KEY=old-key\n',
        encoding='utf-8',
    )
    return path


def test_all_supported_backends_are_described():
    for backend in SUPPORTED_BACKENDS:
        assert backend in BACKEND_ENV_KEYS, f"Нет имён переменных для {backend}"
        names = env_var_names(backend)
        assert names['base_url'], f"{backend}: нет переменной base_url"
        assert names['model'], f"{backend}: нет переменной model"
        if backend != 'ollama':
            assert names['api_key'], f"{backend}: нет переменной api_key"


def test_save_env_values_replaces_existing_key(env_file):
    save_env_values({'KILO_GATEWAY_API_KEY': 'new-key'}, env_path=env_file)
    text = env_file.read_text(encoding='utf-8')
    assert 'KILO_GATEWAY_API_KEY=new-key' in text
    assert 'old-key' not in text


def test_save_env_values_keeps_comments_and_order(env_file):
    save_env_values({'KILO_GATEWAY_API_KEY': 'new-key'}, env_path=env_file)
    lines = env_file.read_text(encoding='utf-8').splitlines()
    assert lines[0] == '# NPA-ZS — локальные настройки'
    assert lines[1] == ''
    assert lines[2] == 'KILO_GATEWAY_API_KEY=new-key'


def test_save_env_values_appends_missing_keys(env_file):
    save_env_values({'GEMINI_API_KEY': 'AIza-test'}, env_path=env_file)
    lines = env_file.read_text(encoding='utf-8').splitlines()
    assert lines[-1] == 'GEMINI_API_KEY=AIza-test'
    # Перед новым блоком остаётся ровно одна пустая строка-разделитель.
    assert lines[-2] == ''


def test_save_env_values_skips_empty_and_none(env_file):
    path = save_env_values(
        {'GEMINI_API_KEY': '', 'OPENROUTER_API_KEY': None, 'CLINE_API_KEY': '   '},
        env_path=env_file,
    )
    assert path == env_file
    assert 'GEMINI_API_KEY' not in env_file.read_text(encoding='utf-8')


def test_save_env_values_quotes_unsafe_values(env_file):
    save_env_values({'DB_PASSWORD': 'pa ss#word'}, env_path=env_file)
    assert 'DB_PASSWORD="pa ss#word"' in env_file.read_text(encoding='utf-8')
    # get_env_value снимает кавычки и возвращает исходное значение.
    assert get_env_value('DB_PASSWORD', env_path=env_file) == 'pa ss#word'


def test_save_env_values_creates_file(tmp_path):
    path = save_env_values({'GEMINI_API_KEY': 'k'}, env_path=tmp_path / '.env')
    assert path.read_text(encoding='utf-8') == 'GEMINI_API_KEY=k\n'


def _check_pa_test_env_clean(monkeypatch):
    """Снять влияние репозиторного ``.env`` на тесты пост-конфига.

    ``monkeypatch`` обязан очищать и ``POST_ANALYSIS_*``, и все переменные
    провайдеров, которые могут подхватиться из окружения.
    """
    for var in (
        'POST_ANALYSIS_BACKEND', 'POST_ANALYSIS_MODEL',
        'POST_ANALYSIS_API_KEY', 'POST_ANALYSIS_BASE_URL',
        'OLLAMA_BASE_URL', 'OLLAMA_DEFAULT_MODEL',
        'KILO_GATEWAY_API_KEY', 'KILO_GATEWAY_BASE_URL', 'KILO_GATEWAY_DEFAULT_MODEL',
        'CLINE_API_KEY', 'CLINE_BASE_URL', 'CLINE_DEFAULT_MODEL',
        'OPENROUTER_API_KEY', 'OPENROUTER_BASE_URL', 'OPENROUTER_DEFAULT_MODEL',
        'CEREBRAS_API_KEY', 'CEREBRAS_BASE_URL', 'CEREBRAS_DEFAULT_MODEL',
        'TOGETHER_API_KEY', 'TOGETHER_BASE_URL', 'TOGETHER_DEFAULT_MODEL',
        'MISTRAL_API_KEY', 'MISTRAL_BASE_URL', 'MISTRAL_DEFAULT_MODEL',
        'GEMINI_API_KEY', 'GEMINI_BASE_URL', 'GEMINI_DEFAULT_MODEL',
        'FREE_DEEPSEEK_API_KEY', 'FREE_DEEPSEEK_BASE_URL',
        'FREE_DEEPSEEK_DEFAULT_MODEL', 'FREE_DEEPSEEK_SESSION',
        'LLM_BACKEND',
    ):
        monkeypatch.delenv(var, raising=False)


def test_save_env_values_updates_os_environ(env_file, monkeypatch):
    _check_pa_test_env_clean(monkeypatch)
    save_env_values({'GEMINI_API_KEY': 'AIza-live'}, env_path=env_file)
    assert os.environ['GEMINI_API_KEY'] == 'AIza-live'
    assert get_env_value('GEMINI_API_KEY', env_path=env_file) == 'AIza-live'


def test_save_backend_settings_writes_key_url_model_and_active_backend(env_file):
    written = save_backend_settings(
        'gemini',
        api_key='AIza-test',
        base_url='https://generativelanguage.googleapis.com/v1beta/openai',
        model='gemini-2.0-flash',
        env_path=env_file,
    )
    assert written['GEMINI_API_KEY'] == 'AIza-test'
    assert written['GEMINI_DEFAULT_MODEL'] == 'gemini-2.0-flash'
    assert written[ACTIVE_BACKEND_ENV] == 'gemini'
    text = env_file.read_text(encoding='utf-8')
    assert 'GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai' in text
    assert f'{ACTIVE_BACKEND_ENV}=gemini' in text


def test_save_backend_settings_keeps_existing_key_when_empty(env_file):
    written = save_backend_settings('kilo_gateway', api_key='', env_path=env_file)
    assert 'KILO_GATEWAY_API_KEY' not in written
    assert 'KILO_GATEWAY_API_KEY=old-key' in env_file.read_text(encoding='utf-8')


def test_save_backend_settings_without_active_flag(env_file):
    written = save_backend_settings(
        'openrouter', api_key='or-key', make_active=False, env_path=env_file
    )
    assert ACTIVE_BACKEND_ENV not in written
    assert ACTIVE_BACKEND_ENV not in env_file.read_text(encoding='utf-8')


def test_save_backend_settings_rejects_unknown_backend(env_file):
    with pytest.raises(ValueError):
        save_backend_settings('unknown-backend', api_key='k', env_path=env_file)


def test_get_env_value_reads_file_without_touching_os_environ(env_file, monkeypatch):
    monkeypatch.setenv('KILO_GATEWAY_API_KEY', 'from-os-environ')
    assert get_env_value('KILO_GATEWAY_API_KEY', env_path=env_file) == 'old-key'
    assert get_env_value('MISSING_KEY', env_path=env_file, default='def') == 'def'
    assert get_env_value('MISSING_KEY', env_path=env_file.parent / 'nope') == ''


# --- Проверка автозагрузки сохранённых настроек из .env ----------------------


def test_load_backend_settings_roundtrip(env_file, monkeypatch):
        """Сохранили в .env — загрузили те же значения обратно."""
        save_backend_settings(
            'cerebras',
            api_key='sk-cerebras-test',
            base_url='https://api.cerebras.test/v1',
            model='llama3.1-8b',
            env_path=env_file,
        )
        # save_backend_settings обновляет os.environ; убираем значение, чтобы
        # убедиться, что load_backend_settings читает из файла, а не из окружения.
        monkeypatch.delenv('CEREBRAS_API_KEY', raising=False)
        loaded = load_backend_settings('cerebras', env_path=env_file)
        assert loaded == {
'api_key': 'sk-cerebras-test',
            'base_url': 'https://api.cerebras.test/v1',
            'model': 'llama3.1-8b',
        }
        # Окружение процесса при чтении не затрагивается.


def test_load_backend_settings_missing_values_are_empty(env_file):
    loaded = load_backend_settings('gemini', env_path=env_file)
    assert loaded == {'api_key': '', 'base_url': '', 'model': ''}


def test_load_backend_settings_ollama_has_no_api_key(env_file):
    save_backend_settings('ollama', base_url='http://localhost:11434', env_path=env_file)
    loaded = load_backend_settings('ollama', env_path=env_file)
    assert loaded == {'base_url': 'http://localhost:11434', 'model': ''}


def test_load_backend_settings_rejects_unknown_backend(env_file):
    with pytest.raises(ValueError):
        load_backend_settings('unknown-backend', env_path=env_file)


def test_load_active_backend(env_file):
    assert load_active_backend(env_path=env_file) == ''
    save_backend_settings('cline', api_key='c-line', env_path=env_file)
    assert load_active_backend(env_path=env_file) == 'cline'
    assert load_active_backend(env_path=env_file.parent / 'nope') == ''


def test_saved_settings_load_back_into_gui_fakes(env_file, monkeypatch):
    """Сквозной сценарий: сохранение -> .env -> автозагрузка при старте GUI."""
    from npazs.compare import gui as compare_gui

    save_backend_settings(
        'gemini',
        api_key='AIza-saved',
        base_url='https://gemini.example/v1',
        model='gemini-2.5-flash',
        env_path=env_file,
    )
    monkeypatch.setattr(compare_gui, 'load_active_backend', lambda: 'gemini')
    monkeypatch.setattr(
        compare_gui, 'load_backend_settings',
        lambda backend: load_backend_settings(backend, env_path=env_file),
    )
    saved = compare_gui._initial_backend_settings()
    assert saved['backend'] == 'gemini'
    assert saved['base_url'] == 'https://gemini.example/v1'
    assert saved['model'] == 'gemini-2.5-flash'


# --- Проверка связки GUI -> .env (без создания Tk-окна) ----------------------


class _FakeVar:
    """Минимальная замена ``tk.StringVar``: нужен только ``get()``."""

    def __init__(self, value: str = ''):
        self._value = value

    def get(self) -> str:
        return self._value


class _FakeCompareApp:
    """Двойник GUI сравнения/пост-анализа с нужными полями."""

    def __init__(
        self,
        backend: str = 'gemini',
        url: str = 'https://example.test/v1',
        model: str = '',
    ):
        self.backend = _FakeVar(backend)
        self.kilo_gateway_url = _FakeVar(url)
        self.model = _FakeVar(model)
        self.log_queue: queue.Queue = queue.Queue()


class _FakeRevisionApp(_FakeCompareApp):
    """Двойник GUI внесения изменений (плюс модель Ollama и журнал)."""

    def __init__(self, *args, model: str = 'gemini-2.0-flash', **kwargs):
        super().__init__(*args, model=model, **kwargs)
        self.ollama_model = _FakeVar(model)
        self.messages: list = []

    def log(self, message: str, tag: str | None = None) -> None:
        self.messages.append((tag, message))


def _install_recorder(monkeypatch, module) -> dict:
    """Подменить ``save_backend_settings`` в модуле GUI и записать аргументы."""
    saved: dict = {}

    def fake(backend, base_url=None, model=None, make_active=True, env_path=None):
        saved.update(
            backend=backend, base_url=base_url, model=model,
            make_active=make_active, env_path=env_path,
        )
        return {ACTIVE_BACKEND_ENV: backend}

    monkeypatch.setattr(module, 'save_backend_settings', fake)
    return saved


def test_revision_gui_saves_backend_url_to_env(monkeypatch):
    from npazs.ui import gui_builder
    from npazs.ui import revision_app

    saved = _install_recorder(monkeypatch, gui_builder)
    app = _FakeRevisionApp(backend='gemini')
    assert revision_app.App.save_env_settings(app) is True
    assert saved['backend'] == 'gemini'
    assert saved['model'] == 'gemini-2.0-flash'
    assert app.messages and '.env' in app.messages[-1][1]


def test_revision_gui_quiet_mode_keeps_journal_clean(monkeypatch):
    from npazs.ui import revision_app

    _install_recorder(monkeypatch, revision_app)
    app = _FakeRevisionApp(backend='cline')
    assert revision_app.App.save_env_settings(app, quiet=True) is True
    assert app.messages == []


def test_save_post_analysis_settings_roundtrip(env_file):
    from npazs.config.env_store import (
        POST_ANALYSIS_BACKEND_ENV,
        POST_ANALYSIS_MODEL_ENV,
        load_post_analysis_backend,
        load_post_analysis_model,
        save_post_analysis_settings,
    )

    written = save_post_analysis_settings(
        backend='gemini', model='gemini-2.5-flash', env_path=env_file)
    assert written[POST_ANALYSIS_BACKEND_ENV] == 'gemini'
    assert written[POST_ANALYSIS_MODEL_ENV] == 'gemini-2.5-flash'
    text = env_file.read_text(encoding='utf-8')
    assert 'GEMINI_API_KEY' not in text
    assert f'{POST_ANALYSIS_BACKEND_ENV}=gemini' in text
    assert f'{POST_ANALYSIS_MODEL_ENV}=gemini-2.5-flash' in text
    assert load_post_analysis_backend(env_path=env_file) == 'gemini'
    assert load_post_analysis_model(env_path=env_file) == 'gemini-2.5-flash'


def test_save_post_analysis_settings_rejects_unknown_backend(env_file):
    from npazs.config.env_store import save_post_analysis_settings

    with pytest.raises(ValueError):
        save_post_analysis_settings(backend='nope', env_path=env_file)


def test_save_post_analysis_settings_writes_own_creds(env_file):
    """Креды пост-анализа пишутся в POST_ANALYSIS_API_KEY/_BASE_URL."""
    from npazs.config.env_store import (
        POST_ANALYSIS_API_KEY_ENV,
        POST_ANALYSIS_BACKEND_ENV,
        POST_ANALYSIS_BASE_URL_ENV,
        POST_ANALYSIS_MODEL_ENV,
        load_post_analysis_api_key,
        load_post_analysis_base_url,
        save_post_analysis_settings,
    )

    written = save_post_analysis_settings(
        backend='free_deepseek', model='deepseek-v4-flash',
        api_key='proxy-secret', base_url='http://127.0.0.1:9656/v1',
        env_path=env_file)
    assert written[POST_ANALYSIS_BACKEND_ENV] == 'free_deepseek'
    assert written[POST_ANALYSIS_MODEL_ENV] == 'deepseek-v4-flash'
    assert written[POST_ANALYSIS_API_KEY_ENV] == 'proxy-secret'
    assert written[POST_ANALYSIS_BASE_URL_ENV] == 'http://127.0.0.1:9656/v1'
    text = env_file.read_text(encoding='utf-8')
    assert 'POST_ANALYSIS_API_KEY=proxy-secret' in text
    assert 'POST_ANALYSIS_BASE_URL=http://127.0.0.1:9656/v1' in text
    # Ключи самого бэкенда не тронуты.
    assert 'FREE_DEEPSEEK_API_KEY' not in text
    assert load_post_analysis_api_key(env_path=env_file) == 'proxy-secret'
    assert load_post_analysis_base_url(env_path=env_file) == 'http://127.0.0.1:9656/v1'


def test_save_post_analysis_settings_skips_empty_creds(env_file):
    """Пустые креды пост-анализа пропускаются (наследуются креды бэкенда)."""
    from npazs.config.env_store import save_post_analysis_settings

    written = save_post_analysis_settings(
        backend='gemini', model='gemini-2.5-flash',
        api_key='', base_url=None, env_path=env_file)
    assert 'POST_ANALYSIS_API_KEY' not in written
    assert 'POST_ANALYSIS_BASE_URL' not in written
    text = env_file.read_text(encoding='utf-8')
    assert 'POST_ANALYSIS_API_KEY' not in text
    assert 'POST_ANALYSIS_BASE_URL' not in text


def test_post_analysis_llm_config_uses_own_backend(monkeypatch):
    from npazs.config.ollama import get_post_analysis_llm_config

    # .env репозитория/окружения не должен влиять: креды пост-бэкенда
    # задаём явно, оверрайды снимаем.
    _check_pa_test_env_clean(monkeypatch)
    monkeypatch.setenv('POST_ANALYSIS_BACKEND', 'gemini')
    monkeypatch.setenv('POST_ANALYSIS_MODEL', 'gemini-2.5-flash')
    monkeypatch.setenv('GEMINI_API_KEY', 'K-pa')
    monkeypatch.setenv('GEMINI_BASE_URL', 'https://pa-url')
    monkeypatch.setenv('GEMINI_DEFAULT_MODEL', 'gemini-2.5-flash')
    config = get_post_analysis_llm_config()
    assert config['backend'] == 'gemini'
    assert config['model'] == 'gemini-2.5-flash'
    assert config['api_key'] == 'K-pa'
    assert config['base_url'] == 'https://pa-url'


def test_post_analysis_llm_config_falls_back_to_main(monkeypatch):
    from npazs.config.ollama import get_post_analysis_llm_config

    _check_pa_test_env_clean(monkeypatch)
    monkeypatch.setenv('LLM_BACKEND', 'openrouter')
    config = get_post_analysis_llm_config()
    assert config['backend'] == 'openrouter'