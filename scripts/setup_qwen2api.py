"""Настройка локального прокси Qwen2API (Qwen-Proxy) для NPA-ZS.

Скрипт:
  1. Клонирует Qwen2API https://github.com/Rfym21/Qwen2API
     (если ещё не развёрнут) в ``tools/Qwen2API``.
  2. Устанавливает зависимости (bun install / npm install).
  3. Создаёт ``.env`` прокси: SERVICE_PORT=3000 и сгенерированный API_KEY
     (существующие значения не перезаписываются).
  4. Напоминает добавить аккаунт chat.qwen.ai через веб-панель прокси.
  5. Интерактивное меню: запуск прокси / открытие веб-панели / выход.

После установки продублируйте API_KEY прокси в ``QWEN2API_API_KEY`` файла
``.env`` NPA-ZS и выберите бэкенд ``qwen2api`` (или LLM_BACKEND=qwen2api).

Использование::

    python scripts/setup_qwen2api.py
"""

from __future__ import annotations

import argparse
import os
import secrets
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

REPO_URL = 'https://github.com/Rfym21/Qwen2API.git'
DEFAULT_DIR = Path('tools') / 'Qwen2API'
DEFAULT_PORT = 3000
ENV_FILE = '.env'
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CA_BUNDLE_SCRIPT = PROJECT_ROOT / 'scripts' / 'export_system_ca.ps1'
CA_BUNDLE = PROJECT_ROOT / 'data' / 'work_tools' / 'ssl' / 'system-ca-bundle.pem'


def _resolve_cmd(cmd: list[str]) -> list[str]:
    if os.name == 'nt' and cmd:
        found = shutil.which(cmd[0])
        if found is None:
            for suffix in ('.cmd', '.bat', '.exe'):
                found = shutil.which(cmd[0] + suffix)
                if found:
                    break
        if found:
            return [found, *cmd[1:]]
    return cmd


def _run(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> int:
    cmd = _resolve_cmd(cmd)
    print('+', ' '.join(cmd), f'(cwd={cwd})' if cwd else '')
    try:
        proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=env, check=False)
    except FileNotFoundError:
        print(f'ОШИБКА: не найден исполняемый файл: {cmd[0]}', file=sys.stderr)
        return 127
    return proc.returncode


def _input(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        return ''


def is_deployed(target: Path) -> bool:
    return (target / 'src' / 'server.js').exists() and (target / 'package.json').exists()


def deploy(target: Path) -> bool:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and any(target.iterdir()):
        print(f'ОШИБКА: каталог {target} не пуст и не похож на Qwen2API.', file=sys.stderr)
        return False
    if shutil.which('git') is None:
        print('ОШИБКА: git не найден в PATH.', file=sys.stderr)
        return False
    return _run(['git', 'clone', '--depth', '1', REPO_URL, str(target)]) == 0


def _generate_api_key() -> str:
    return f'sk-{secrets.token_hex(24)}'


def _read_env_pairs(env_path: Path) -> dict[str, str]:
    pairs: dict[str, str] = {}
    if not env_path.exists():
        return pairs
    for line in env_path.read_text(encoding='utf-8').splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or '=' not in stripped:
            continue
        key, _, value = stripped.partition('=')
        pairs[key.strip()] = value.strip()
    return pairs


def ensure_env(target: Path, port: int) -> str:
    """Создать/обновить .env прокси; вернуть актуальный API_KEY."""
    env_path = target / ENV_FILE
    pairs = _read_env_pairs(env_path)
    created = not env_path.exists()

    if not pairs.get('API_KEY'):
        pairs['API_KEY'] = _generate_api_key()
        print('Сгенерирован новый API_KEY прокси.')
    if not pairs.get('SERVICE_PORT'):
        pairs['SERVICE_PORT'] = str(port)
    if not pairs.get('LISTEN_ADDRESS'):
        pairs['LISTEN_ADDRESS'] = '127.0.0.1'
    if not pairs.get('DATA_SAVE_MODE'):
        # file-режим сохраняет аккаунты в data/data.json прокси.
        pairs['DATA_SAVE_MODE'] = 'file'

    lines = [
        '# Сгенерировано scripts/setup_qwen2api.py (NPA-ZS)',
        f"LISTEN_ADDRESS={pairs['LISTEN_ADDRESS']}",
        f"SERVICE_PORT={pairs['SERVICE_PORT']}",
        f"API_KEY={pairs['API_KEY']}",
        f"DATA_SAVE_MODE={pairs['DATA_SAVE_MODE']}",
        '# ACCOUNTS=email:pass — необязательно: аккаунты удобнее добавлять',
        f'# через веб-панель прокси (http://127.0.0.1:{port}).',
        '',
    ]
    env_path.write_text('\n'.join(lines), encoding='utf-8')
    if created:
        print(f'Создан {env_path} (порт {pairs["SERVICE_PORT"]}).')
    else:
        print(f'{env_path} обновлён (недостающие поля добавлены).')
    return pairs['API_KEY']


def has_accounts(target: Path) -> bool:
    """Есть ли хотя бы один аккаунт: ACCOUNTS в .env или data/data.json."""
    pairs = _read_env_pairs(target / ENV_FILE)
    if (pairs.get('ACCOUNTS') or '').strip():
        return True
    data_json = target / 'data' / 'data.json'
    if data_json.exists():
        try:
            import json
            payload = json.loads(data_json.read_text(encoding='utf-8'))
            accounts = payload.get('accounts') if isinstance(payload, dict) else None
            return bool(accounts)
        except (OSError, ValueError):
            return False
    return False


def install_deps(target: Path, no_install: bool) -> bool:
    if no_install:
        return True
    if shutil.which('bun'):
        rc = _run(['bun', 'install'], cwd=target)
        if rc == 0:
            return True
        print('Предупреждение: bun install завершился с ошибкой, пробую npm install...', file=sys.stderr)
    # Запуск сервера всё равно требует Bun 1.3.14+ (см. README Qwen2API),
    # но зависимости ставим чем есть, чтобы не блокировать шаг.
    rc = _run(['npm', 'install'], cwd=target)
    if rc == 0:
        return True
    return os.name == 'nt' and _run(['npm.cmd', 'install'], cwd=target) == 0


def ensure_ca_bundle() -> Path | None:
    """Собрать PEM-бандл доверенных корней Windows для Node/bun.

    Антивирусы и корпоративные прокси (Kaspersky, Dr.Web, ESET) с включённой
    проверкой защищённых соединений подменяют TLS-сертификаты своим
    самоподписанным корнем. Node.js и bun не читают хранилище Windows, поэтому
    часть запросов прокси к ``chat.qwen.ai`` падает с ``SELF_SIGNED_CERT_IN_CHAIN``:
    чат не создаётся, и прокси отвечает ``HTTP 500`` — в NPA-ZS это выглядит как
    «qwen2api ошибка (попытка 1/5)».

    Возвращает путь к бандлу или ``None``, если собрать его не удалось.
    """
    if os.name != 'nt':
        return CA_BUNDLE if CA_BUNDLE.exists() else None
    if CA_BUNDLE_SCRIPT.exists():
        _run([
            'powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
            '-File', str(CA_BUNDLE_SCRIPT), '-Quiet',
        ])
    return CA_BUNDLE if CA_BUNDLE.exists() else None


def start_proxy(target: Path, port: int) -> int:
    env = {**os.environ}
    ca_bundle = ensure_ca_bundle()
    if ca_bundle:
        # Переменная читается рантаймом при старте процесса, поэтому задаём её
        # здесь, а не в .env прокси.
        env['NODE_EXTRA_CA_CERTS'] = str(ca_bundle)
        print(f'TLS: доверяем корневым сертификатам Windows ({ca_bundle}).')
    print()
    print(f'Запускаю прокси на http://127.0.0.1:{port} ...')
    print('(Ctrl+C для остановки)')
    print()
    if shutil.which('bun'):
        return _run(['bun', '--no-env-file', 'src/server.js'], cwd=target, env=env)
    print('ОШИБКА: bun не найден — Qwen2API требует Bun >= 1.3.14 '
          '(https://bun.sh). Пробую npm start как fallback...', file=sys.stderr)
    return _run(['npm', 'start'], cwd=target, env=env)


def open_panel(port: int) -> None:
    url = f'http://127.0.0.1:{port}'
    print(f'Открываю веб-панель {url} — добавьте аккаунт chat.qwen.ai.')
    webbrowser.open(url)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Настройка Qwen2API (клонирование, зависимости, .env, запуск).',
    )
    parser.add_argument('--dir', default=str(DEFAULT_DIR), help='Каталог (по умолчанию tools/Qwen2API).')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT, help=f'Порт прокси (по умолчанию {DEFAULT_PORT}).')
    parser.add_argument('--no-install', action='store_true', help='Без bun/npm install.')
    parser.add_argument('--start', action='store_true', help='После установки сразу запустить прокси.')
    args = parser.parse_args(argv)

    target = Path(args.dir).resolve()

    if is_deployed(target):
        print(f'Qwen2API уже развёрнут: {target}')
    else:
        print('Шаг 1/3: Клонирование Qwen2API...')
        if not deploy(target):
            return 2
        print('Клонирование завершено.')

    print('Шаг 2/3: Проверка зависимостей...')
    node = shutil.which('node')
    bun = shutil.which('bun')
    npm = shutil.which('npm') or shutil.which('npm.cmd')
    print(f'  bun: {bun or "НЕ НАЙДЕН"}; node: {node or "НЕ НАЙДЕН"}; npm: {npm or "НЕ НАЙДЕН"}')
    if bun is None:
        print('ВНИМАНИЕ: Bun не найден. Qwen2API запускается через Bun >= 1.3.14:')
        print('  Windows: powershell -c "irm bun.sh/install.ps1 | iex"  (https://bun.sh)')
        print('  Docker-альтернатива: docker run -p 3000:3000 -e API_KEY=... rfym21/qwen2api')
    if node is None and bun is None:
        print('Установите Bun (https://bun.sh) или Node.js (https://nodejs.org).', file=sys.stderr)
        return 2
    if not install_deps(target, args.no_install):
        return 2

    print('Шаг 3/3: Настройка .env прокси...')
    api_key = ensure_env(target, args.port)
    print()
    print('=' * 50)
    print('  API_KEY прокси (скопируйте в NPA-ZS .env):')
    print(f'  QWEN2API_API_KEY={api_key}')
    print('=' * 50)
    if not has_accounts(target):
        print()
        print('Аккаунт chat.qwen.ai ещё не добавлен: запустите прокси и')
        print(f'откройте веб-панель http://127.0.0.1:{args.port} → «Добавить аккаунт».')

    if args.start:
        return start_proxy(target, args.port)

    print()
    print('=' * 50)
    print('  Готово! Что дальше?')
    print('=' * 50)
    while True:
        choice = _input(
            '\n  1) Запустить прокси (bun src/server.js)\n'
            f'  2) Открыть веб-панель аккаунтов (http://127.0.0.1:{args.port})\n'
            '  3) Пропустить — я запущу вручную\n'
            'Выбор [1/2/3]: '
        )
        if choice in ('1', '1) ', ''):
            return start_proxy(target, args.port)
        elif choice in ('2', '2) '):
            open_panel(args.port)
        elif choice in ('3', '3) '):
            print('Настройка завершена. В NPA-ZS выберите бэкенд Qwen2API,')
            print('не забудьте QWEN2API_API_KEY в .env (см. выше).')
            return 0
        else:
            print('  Неверный выбор.')


if __name__ == '__main__':
    raise SystemExit(main())

