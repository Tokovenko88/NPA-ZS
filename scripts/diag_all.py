#!/usr/bin/env python3
"""Проверка OPcache через веб-скрипт и просмотр antibot-файлов."""
import os
from dotenv import load_dotenv
import paramiko
import requests

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

# === Часть 1: Fetch OPcache web test ===
print('\n=== Часть 1: OPcache веб-проверка ===')
try:
    r = requests.get('https://sevzakon.ru/test_opcache_web.php',
                     timeout=10,
                     headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
    print(f'Status: {r.status_code}')
    print(f'Content: {r.text[:1000]}')
except Exception as e:
    print(f'Error: {e}')

# === Часть 2: Antibot opcache lines (detailed) ===
print('\n=== Часть 2: Antibot — все строки с opcache ===')
WORKDIR = '/var/www/u0220513/data/www/sevzakon.ru'
ANTIBOT_FILES = [
    'antibot/code/ab.php',
    'antibot/code/check.php',
    'antibot/code/cron.php',
    'antibot/adm/backup.php',
    'antibot/adm/beta.php',
    'antibot/adm/beta2.php',
    'antibot/adm/confsave.php',
    'antibot/adm/phpinfo.php',
    'antibot/adm/update.php',
    'antibot/adm/update2.php',
    'antibot/adm/resetcookie.php',
]

stdin, stdout, stderr = ssh.exec_command(
    'cd ' + WORKDIR + ' && grep -n -C2 "opcache" ' +
    ' '.join(ANTIBOT_FILES)
)
result = stdout.read().decode('utf-8', errors='replace')
print(result[:2000])

# === Часть 3: Все вызовы opcache_reset без function_exists ===
print('\n=== Часть 3: Все opcache_reset вызовы (без function_exists) ===')
stdin, stdout, stderr = ssh.exec_command(
    'cd ' + WORKDIR + ' && grep -rn "opcache_reset" --include="*.php" . | '
    'grep -v "function_exists" | grep -v "//" | head -30'
)
result2 = stdout.read().decode('utf-8', errors='replace')
print(result2[:1000])

# === Часть 4: php.ini / fpm config ===
print('\n=== Часть 4: PHP-FPM / php.ini конфиг ===')
stdin, stdout, stderr = ssh.exec_command(
    'cat /etc/php-fpm.d/www.conf | grep -E "opcache|php_admin_value|php_flag|php_value" | head -20'
)
result3 = stdout.read().decode('utf-8', errors='replace')
print(result3[:500])

stdin, stdout, stderr = ssh.exec_command(
    'php -i 2>/dev/null | grep -E "opcache.enable|opcache.memory|opcache.max|opcache.revalidate|opcache.fast|opcache.enable_cli" | head -10'
)
result4 = stdout.read().decode('utf-8', errors='replace')
print('\nCLI opcache settings:')
print(result4[:500])

ssh.close()
print('\nDONE')
