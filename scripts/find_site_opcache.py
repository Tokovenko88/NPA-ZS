#!/usr/bin/env python3
"""Поиск сайта и opcache_reset на сервере."""
import os
from dotenv import load_dotenv
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

# 1. Пользователь и домашняя директория
print('\n=== Current user ===')
stdin, stdout, stderr = ssh.exec_command('whoami && echo HOME=$HOME')
print(stdout.read().decode('utf-8', errors='replace'))

# 2. Проверка директорий пользователя
print('\n=== Проверка директорий пользователя ===')
dirs = [
    '/home/u0220513',
    '/home/u0220513/www',
    '/home/u0220513/public_html',
    '/home/u0220513/domains',
    '/home/u0220513/sevzakon.ru',
    '/home/u0220513/www',
]
for d in dirs:
    stdin, stdout, stderr = ssh.exec_command(f'test -d {d} && echo FOUND:{d} || echo NOT:{d}')
    print(f'{d}: {stdout.read().decode("utf-8", errors="replace").strip()}')

# 3. Проверка /var/www
print('\n=== /var/www contents ===')
stdin, stdout, stderr = ssh.exec_command('ls -la /var/www 2>/dev/null || echo "NO /var/www"')
print(stdout.read().decode('utf-8', errors='replace')[:2000])

# 4. Поиск사이트를 나타내는 index.php
print('\n=== Поиск index.php ===')
stdin, stdout, stderr = ssh.exec_command(
    "find /home -name 'index.php' -type f 2>/dev/null | head -20"
)
print(stdout.read().decode('utf-8', errors='replace'))

stdin, stdout, stderr = ssh.exec_command(
    "find /var -name 'index.php' -type f 2>/dev/null | head -20"
)
print(stdout.read().decode('utf-8', errors='replace'))

# 5. Поиск MODX manager/
print('\n=== Поиск manager/ директорий ===')
stdin, stdout, stderr = ssh.exec_command(
    "find / -type d -name 'manager' 2>/dev/null | head -10"
)
print(stdout.read().decode('utf-8', errors='replace'))

# 6. Поиск файлов с opcache_reset
print('\n=== Файлы с opcache_reset ===')
stdin, stdout, stderr = ssh.exec_command(
    "grep -r 'opcache_reset' /home 2>/dev/null | head -20"
)
print(stdout.read().decode('utf-8', errors='replace'))

stdin, stdout, stderr = ssh.exec_command(
    "grep -r 'opcache_reset' /var 2>/dev/null | head -20"
)
print(stdout.read().decode('utf-8', errors='replace'))

# 7. info.php для проверки работающего PHP
print('\n=== Создание info.php для проверки ===')
stdin, stdout, stderr = ssh.exec_command(
    "echo '<?php phpinfo(); ?>' > /var/www/info_test.php 2>/dev/null && "
    "echo 'CREATED' || echo 'FAILED - check where site is'"
)
print(stdout.read().decode('utf-8', errors='replace'))

ssh.close()
print('\nDONE')
