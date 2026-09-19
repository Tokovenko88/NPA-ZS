#!/usr/bin/env python3
"""Комплексный поиск всех opcache-вызовов и проблемных мест на сервере."""
import os
from dotenv import load_dotdotenv
import paramiko

load_dotenv('D:/NPA-ZS/.env')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(
    hostname=os.getenv('MODX_SSH_HOST'),
    port=int(os.getenv('MODX_SSH_PORT', 22)),
    username=os.getenv('MODX_SSH_USERNAME'),
    password=os.getenv('MODX_SSH_PASSWORD'),
    timeout=10,
)
print('SSH connected')

SITE = '/var/www/u0220513/data/www/sevzakon.ru'

print('\n=== 1. ВСЕ файлы с любой функцией opcache ===')
stdin, stdout, stderr = ssh.exec_command(
    f"cd {SITE} && grep -r -l 'opcache_' --include='*.php' . 2>/dev/null"
)
out = stdout.read().decode('utf-8', errors='replace')
files = [f.strip() for f in out.split('\n') if f.strip()]
print(f'Найдено {len(files)} файлов:')
for f in files:
    print(f'  {f}')
print()

print('\n=== 2. Для каждого файла — контекст вызова (3 строки до и после) ===')
for f in files:
    stdin, stdout, stderr = ssh.exec_command(
        f"grep -n -B2 -A2 'opcache_' '{f}' 2>/dev/null"
    )
    out = stdout.read().decode('utf-8', errors='replace')
    if out.strip():
        print(f'--- {f} ---')
        print(out)
        print()
print()

print('\n=== 3. Поиск в плагинах MODX ===')
stdin, stdout, stderr = ssh.exec_command(
    f"cd {SITE} && find . -path '*/elements/plugins/*' -name '*.php' -exec grep -l 'opcache' {{}} \\; 2>/dev/null"
)
out = stdout.read().decode('utf-8', errors='replace')
print('Плагины с opcache:', out.strip() if out.strip() else 'Нет')
print()

print('\n=== 4. Поиск в модулях MODX ===')
stdin, stdout, stderr = ssh.exec_command(
    f"cd {SITE} && find . -path '*/elements/modules/*' -name '*.php' -exec grep -l 'opcache' {{}} \\; 2>/dev/null"
)
out = stdout.read().decode('utf-8', errors='replace')
print('Модули с opcache:', out.strip() if out.strip() else 'Нет')
print()

print('\n=== 5. Поиск в сниппетах (кроме FCR) ===')
stdin, stdout, stderr = ssh.exec_command(
    f"cd {SITE} && find . -path '*/elements/snippets/*' -name '*.php' -exec grep -l 'opcache' {{}} \\; 2>/dev/null"
)
out = stdout.read().decode('utf-8', errors='replace')
print('Сниппеты с opcache:', out.strip() if out.strip() else 'Нет')
print()

print('\n=== 6. Поиск в ядре MODX (manager/core) ===')
stdin, stdout, stderr = ssh.exec_command(
    f"cd {SITE}/manager && find . -name '*.php' -exec grep -l 'opcache' {{}} \\; 2>/dev/null"
)
out = stdout.read().decode('utf-8', errors='replace')
core_files = [f.strip() for f in out.split('\n') if f.strip()]
print(f'Ядро MODX с opcache ({len(core_files)} файлов):')
for f in core_files:
    print(f'  {f}')
print()

print('\n=== 7. Контекст в ядре MODX ===')
for f in core_files:
    stdin, stdout, stderr = ssh.exec_command(
        f"grep -n -B3 -A3 'opcache' '{SITE}/manager/{f}' 2>/dev/null"
    )
    out = stdout.read().decode('utf-8', errors='replace')
    if out.strip():
        print(f'--- manager/{f} ---')
        print(out)
        print()
print()

print('\n=== 8. Проверка: какие именно opcache-функции вызываются ===')
stdin, stdout, stderr = ssh.exec_command(
    f"cd {SITE} && grep -r -o 'opcache_[a-z_]*' --include='*.php' . 2>/dev/null | sort | uniq -c | sort -rn"
)
out = stdout.read().decode('utf-8', errors='replace')
print(out)
print()

print('\n=== 9. Проверка .htaccess и .user.ini ===')
for config_file in ['.htaccess', '.user.ini']:
    path = f'{SITE}/{config_file}'
    stdin, stdout, stderr = ssh.exec_command(f'test -f {path} && cat {path} || echo NOT_FOUND')
    out = stdout.read().decode('utf-8', errors='replace')
    if 'opcache' in out.lower():
        print(f'{config_file} имеет opcache-настройки:')
        print(out[:1000])
print()

print('\n=== 10. Полный список всех php.ini и .ini файлов, влияющих на opcache ===')
stdin, stdout, stderr = ssh.exec_command(
    "find /var/www/php-bin/u0220513/sevzakon.ru -name '*.ini' -exec echo '=== {} ===' \\; -exec cat {} \\; 2>/dev/null"
)
out = stdout.read().decode('utf-8', errors='replace')
print(out[:2000])
print()

print('DONE')
ssh.close()
