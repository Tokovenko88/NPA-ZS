"""Настройка локального прокси FreeDeepseekAPI для NPA-ZS.

Скрипт:
  1. Клонирует FreeDeepseekAPI (если ещё не развёрнут).
  2. npm install (если нужно).
  3. Авторизация в chat.deepseek.com через Chrome
     (пропускается, если deepseek-auth.json уже есть).
  4. Интерактивное меню: запуск прокси / повторный auth / выход.

Использование::

    python scripts/setup_free_deepseek.py
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_URL = 'https://github.com/dekrezz/FreeDeepseekAPI.git'
DEFAULT_DIR = Path('tools') / 'FreeDeepseekAPI'
AUTH_FILE = 'deepseek-auth.json'


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
    return (target / 'server.js').exists() and (target / 'package.json').exists()


def is_authorized(target: Path) -> bool:
    return (target / AUTH_FILE).exists()


def deploy(target: Path) -> bool:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and any(target.iterdir()):
        print(f'ОШИБКА: каталог {target} не пуст и не похож на FreeDeepseekAPI.', file=sys.stderr)
        return False
    if shutil.which('git') is None:
        print('ОШИБКА: git не найден в PATH.', file=sys.stderr)
        return False
    if _run(['git', 'clone', '--depth', '1', REPO_URL, str(target)]):
        return False
    return True


def install_deps(target: Path, no_install: bool) -> bool:
    if no_install:
        return True
    rc = _run(['npm', 'install'], cwd=target)
    if rc and (os.name != 'nt' or _run(['npm.cmd', 'install'], cwd=target)):
        return False
    return True


def run_auth(target: Path) -> bool:
    print()
    print('=' * 50)
    print('  АВТОРИЗАЦИЯ В chat.deepseek.com')
    print('=' * 50)
    print()
    print('Откроется Chrome (развёрнуто). Войдите в DeepSeek')
    print('и отправьте тестовое сообщение (например: ok).')
    print('После этого вернитесь сюда и нажмите Enter.')
    print()
    input('[Enter, когда залогинились] ')
    rc = _run(['npm', 'run', 'auth'], cwd=target)
    if rc:
        print('ОШИБКА: авторизация не удалась.', file=sys.stderr)
        return False
    if not (target / AUTH_FILE).exists():
        print('ОШИБКА: auth файл не найден после авторизации.', file=sys.stderr)
        return False
    print(f'Авторизация успешна: {target / AUTH_FILE}')
    return True


def start_proxy(target: Path) -> int:
    env = {**os.environ, 'NON_INTERACTIVE': '1'}
    print()
    print('Запускаю прокси на http://127.0.0.1:9655 ...')
    print('(Ctrl+C для остановки)')
    print()
    return _run(['npm', 'start'], cwd=target, env=env)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Настройка FreeDeepseekAPI (клонирование, авторизация, запуск).',
    )
    parser.add_argument('--dir', default=str(DEFAULT_DIR), help='Каталог (по умолчанию tools/FreeDeepseekAPI).')
    parser.add_argument('--no-install', action='store_true', help='Без npm install.')
    parser.add_argument('--no-auth', action='store_true', help='Без авторизации (пропустить шаг 2).')
    parser.add_argument('--start', action='store_true', help='После установки сразу запустить прокси.')
    args = parser.parse_args(argv)

    target = Path(args.dir).resolve()

    if is_deployed(target):
        print(f'FreeDeepseekAPI уже развёрнут: {target}')
    else:
        print('Шаг 1/3: Клонирование FreeDeepseekAPI...')
        if not deploy(target):
            return 2
        print('Клонирование завершено.')

    print('Шаг 2/3: Проверка зависимостей...')
    node = shutil.which('node')
    npm = shutil.which('npm') or shutil.which('npm.cmd')
    print(f'  node: {node or "НЕ НАЙДЕН"}; npm: {npm or "НЕ НАЙДЕН"}')
    if node is None:
        print('Установите Node.js >= 18 (https://nodejs.org).', file=sys.stderr)
        return 2
    if _run(['node', '--version']):
        return 2
    if not install_deps(target, args.no_install):
        return 2

    if args.no_auth:
        print('Авторизация пропущена (--no-auth).')
    elif is_authorized(target):
        print('Авторизация уже выполнена (deepseek-auth.json найден). Пропускаю.')
    else:
        print('Шаг 3/3: Авторизация...')
        if not run_auth(target):
            return 2

    if args.start:
        return start_proxy(target)

    print()
    print('=' * 50)
    print('  Готово! Что дальше?')
    print('=' * 50)
    while True:
        choice = _input(
            '\n  1) Запустить прокси (npm start)\n'
            '  2) Запустить прокси фоново\n'
            '  3) Пропустить — я запущу вручную\n'
            '  4) Повторить авторизацию (заново)\n'
            'Выбор [1/2/3/4]: '
        )
        if choice in ('1', '1) '):
            return start_proxy(target)
        elif choice in ('2', '2) '):
            env = {**os.environ, 'NON_INTERACTIVE': '1'}
            return _run(['npm', 'start'], cwd=target, env=env)
        elif choice in ('3', '3) ', ''):
            print('Настройка завершена. В NPA-ZS выберите бэкенд FreeDeepseek.')
            return 0
        elif choice in ('4', '4) '):
            if is_authorized(target):
                _run(['npm', 'run', 'auth', '--', '--remove'], cwd=target)
            run_auth(target)
        else:
            print('  Неверный выбор.')


if __name__ == '__main__':
    raise SystemExit(main())
