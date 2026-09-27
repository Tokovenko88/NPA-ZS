"""Тесты подсказки о перехвате TLS для локального прокси Qwen2API.

``npazs.revision.ai_utils.tls_interception_hint`` помогает в GUI понять, что
``HTTP 500 {"error":"无法创建或续接 Qwen 会话"}`` от прокси — это следствие
MITM-перехвата TLS антивирусом (Kaspersky/Dr.Web/ESET), а не неверного ключа.
"""

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "npazs_bootstrap", _ROOT / "src" / "bootstrap.py"
)
assert _spec is not None and _spec.loader is not None
_bootstrap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bootstrap)
_bootstrap.bootstrap()

from npazs.revision.ai_utils import tls_interception_hint

QWEN500 = 'HTTP 500: {"error":"无法创建或续接 Qwen 会话"}'


def test_hint_for_qwen2api_http_500():
    """qwen2api + HTTP 500 → подсказка про NODE_EXTRA_CA_CERTS."""
    hint = tls_interception_hint('qwen2api', QWEN500)
    assert 'NODE_EXTRA_CA_CERTS' in hint
    assert 'qwen2api' in hint.lower() or 'Qwen2API' in hint


def test_hint_for_qwen2api_chinese_error_without_http_code():
    """Китайский текст ошибки ловится и без «HTTP 500» в сообщении."""
    assert tls_interception_hint('QWEN2API', '无法创建或续接 Qwen 会话') != ''


def test_no_hint_for_other_backends():
    """Прочие бэкенды подсказку не получают — она специфична для прокси."""
    assert tls_interception_hint('free_deepseek', QWEN500) == ''
    assert tls_interception_hint('openrouter', QWEN500) == ''


def test_no_hint_for_unrelated_qwen2api_error():
    """401 (неверный ключ) не маскируется под TLS-проблему."""
    assert tls_interception_hint('qwen2api', 'HTTP 401: {"error":"unauthorized"}') == ''
    assert tls_interception_hint('qwen2api', 'WinError 10061 connection refused') == ''
