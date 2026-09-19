#!/usr/bin/env python3
"""Проверка opcache.ini на сервере + статус opcache через web PHP."""
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

print('\n=== 1. Содержимое opcache.ini ===')
# Попробуем разные пути
for opcache_ini in [
    '/opt/php/7.4/etc/php.d/opcache.ini',
    '/etc/php.d/opcache.ini',
]:
    stdin, stdout, stderr = ssh.exec_command(f'test -f {opcache_ini} && cat {opcache_ini} || echo NOT_FOUND:{opcache_ini}')
    out = stdout.read().decode('utf-8', errors='replace')
    print(f'--- {opcache_ini} ---')
    print(out[:1000])
    print()

print('\n=== 2. php.ini сервера ===')
stdin, stdout, stderr = ssh.exec_command('cat /var/www/php-bin/u0220513/sevzakon.ru/php.ini 2>/dev/null | head -100')
out = stdout.read().decode('utf-8', errors='replace')
print(out[:2000])
print()

print('\n=== 3. Проверка статуса opcache через web ===')
php_check = b'<?php echo "opcache.enable=" . ini_get("opcache.enable") . "\\n"; echo "opcache.enable_cli=" . ini_get("opcache.enable_cli") . "\\n"; echo "opcache.loaded=" . (extension_loaded("opcache") ? "yes" : "no") . "\\n"; $s = opcache_get_status(false); echo "opcache_status=" . ($s ? "loaded" : "not_loaded") . "\\n"; if ($s) { echo "opcache_enabled=" . ($s["opcache_enabled"] ? "yes" : "no") . "\\n"; echo "memory_free=" . $s["memory_free"] . "\\n"; }'

sftp = ssh.open_sftp()
with sftp.file('/var/www/u0220513/data/www/sevzakon.ru/opcache_check.php', 'wb') as f:
    f.write(php_check)
sftp.close()

import urllib.request
url = 'http://sevzakon.ru/opcache_check.php'
try:
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    resp = urllib.request.urlopen(req, timeout=15)
    print(resp.read().decode('utf-8', errors='replace'))
except Exception as e:
    print(f'HTTP error: {e}')

# Удалить
ssh.exec_command('rm -f /var/www/u0220513/data/www/sevzakon.ru/opcache_check.php')

print('\n=== 4. Поиск ВСЕХ вызовов opcache_reset без function_exists ===')
# Ищем все файлы с opcache_reset, которые НЕ имеют проверки function_exists перед вызовом
stdin, stdout, stderr = ssh.exec_command(
    "cd /var/www/u0220513/data/www/sevzakon.ru && "
    "grep -r 'opcache_reset' --include='*.php' -l | while read f; do "
    "  if ! grep -q 'function_exists.*opcache_reset' \"$f\"; then "
    "    echo \"NO_CHECK: $f\"; "
    "  fi; "
    "done"
)
out = stdout.read().decode('utf-8', errors='replace')
print(out if out.strip() else 'Все файлы с opcache_reset имеют проверку function_exists')

print('\n=== 5. Поиск вызовов opcache_reset в ядре MODX (не в sitiove файлах) ===')
stdin, stdout, stderr = ssh.exec_command(
    "find /var/www/u0220513/data/www/sevzakon.ru -name '*.php' -path '*/manager/*' -exec grep -l 'opcache_reset' {} \\; 2>/dev/null"
)
out = stdout.read().decode('utf-8', errors='replace')
print(out if out.strip() else 'Нет вызовов в manager/')

print('\nDONE')
ssh.close()
