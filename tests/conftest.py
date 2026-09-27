"""Pytest-фикстуры защиты реального ``.env``.

Autouse-фикстура ``protect_real_env``: на каждый тест снимает снимок боевого
``.env`` (если файл есть) и после теста сравнивает. Если тест изменил файл —
восстанавливает исходное содержимое и валит тест с сообщением, какой именно
тест испортил ``.env``. Так ни один тест (включая будущие) не сможет
затирать URL/ключи провайдеров (история с ``https://example.test/v1``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_REAL_ENV = _ROOT / '.env'


@pytest.fixture(autouse=True)
def protect_real_env():
    """Запретить тестам менять боевой ``.env`` (восстановить + завалить тест)."""
    snapshot = _REAL_ENV.read_bytes() if _REAL_ENV.exists() else None
    yield
    if snapshot is None:
        if _REAL_ENV.exists():
            current = _REAL_ENV.read_bytes()
            if current.strip():
                _REAL_ENV.unlink()
                pytest.fail(
                    f'Тест создал боевой {_REAL_ENV} — файл удалён. '
                    'Пишите в tmp_path, а не в репозиторийный .env.'
                )
        return
    current = _REAL_ENV.read_bytes() if _REAL_ENV.exists() else None
    if current != snapshot:
        _REAL_ENV.write_bytes(snapshot)
        pytest.fail(
            f'Тест изменил боевой {_REAL_ENV} — файл восстановлен из снимка. '
            'Такие записи запрещены: передавайте env_path=tmp_path или '
            'подменяйте save_* в модуле GUI (см. tests/test_env_store.py).'
        )
