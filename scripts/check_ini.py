#!/usr/bin/env python3
"""Проверка antibot phpinfo и применение .user.ini."""
import os
from dotenv import load_dotenv
import paramiko

load_dotenv('D:/NPA-ZS/.env')
s = paramiko.SSHClient()
s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
s.connect(
    hostname=os.getenv('MODX_SSH_HOST'),
    port=int(os.getenv('MODX_SSH_PORT', 22)),
    username=os.getenv('MODX_SSH_USERNAME'),
    password=os.getenv('MODX_SSH_PASSWORD'),
    timeout=10,
)

def run(cmd):
    i, o, e = s.exec_command(cmd, timeout=30)
    return o.read().decode('utf-8', errors='replace'), e.read().decode('utf-8', errors='replace')

print('=== 1. Что возвращает antibot phpinfo.php ===')
out, err = run('curl -s -m 15 -k "https://sevzakon.ru/antibot/adm/phpinfo.php" | head -50')
print(out[:2000])
if err.strip():
    print('ERR:', err[:300])

print('\n=== 2. Создание тестового скрипта с phpinfo() прямо в корне ===')
test_php = b'<?php header("Content-Type: text/plain; charset=utf-8"); phpinfo();'
sftp = s.open_sftp()
with sftp.file('/var/www/u0220513/data/www/sevzakon.ru/phpinfo_test.php', 'wb') as f:
    f.write(test_php)
sftp.close()
print('Создан /phpinfo_test.php')

print('\n=== 3. Проверка с браузерным UA ===')
out2, err2 = run('curl -s -m 15 -k -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" "https://sevzakon.ru/phpinfo_test.php" 2>&1 | grep -i "opcache" | head -20')
print(out2 if out2.strip() else '(ничего не найдено)' + (err2 if err2 else ''))

print('\n=== 4. Проверка настроек OPcache через ini_get ===')
# Создаем скрипт с ini_get
test_ini = (
    b'<?php' + b'\n'
    b'header("Content-Type: text/plain; charset=utf-8");' + b'\n'
    b'echo "opcache.enable: " . ini_get("opcache.enable") . "\n";' + b'\n'
    b'echo "opcache.enable_cli: " . ini_get("opcache.enable_cli") . "\n";' + b'\n'
    b'echo "opcache.memory_consumption: " . ini_get("opcache.memory_consumption") . "\n";' + b'\n'
    b'echo "opcache.max_accelerated_files: " . ini_get("opcache.max_accelerated_files") . "\n";' + b'\n'
    b'echo "opcache.revalidate_freq: " . ini_get("opcache.revalidate_freq") . "\n";' + b'\n'
    b'echo "opcache.jit: " . ini_get("opcache.jit") . "\n";' + b'\n'
    b'echo "opcache.jit_buffer_size: " . ini_get("opcache.jit_buffer_size") . "\n";' + b'\n'
    b'echo "Server API: " . php_sapi_name() . "\n";' + b'\n'
    b'echo "DONE\n";' + b'\n'
)
sftp2 = s.open_sftp()
with sftp2.file('/var/www/u0220513/data/www/sevzakon.ru/phpinfo_ini.php', 'wb') as f:
    f.write(test_ini)
sftp2.close()
print('Создан phpinfo_ini.php')

print('\n=== 5. Проверка ini_get ===')
out3, err3 = run('curl -s -m 15 -k -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" "https://sevzakon.ru/phpinfo_ini.php"')
print(out3)
if err3.strip():
    print('ERR:', err3[:300])

print('\n=== 6. Очистка тестовых файлов ===')
run('rm -f /var/www/u0220513/data/www/sevzakon.ru/phpinfo_test.php /var/www/u0220513/data/www/sevzakon.ru/phpinfo_ini.php')
print('Удалено')

print('\n=== 7. Проверка user_ini.cache_ttl ===')
out4, err4 = run('grep -r "user_ini" /etc/php/8.2/fpm/ /etc/php/8.2/ 2>/dev/null; echo EXIT:$?')
print(out4 if out4.strip() else '(не найдено)' + (err4 if err4 else ''))

print('\n=== 8. Проверка процесса php-fpm ===')
out5, err5 = run("ps aux | grep 'php-fpm' | grep -v grep | awk '{print $2, $11, $12, $13}' | head -5")
print(out5[:500])

s.close()
print('\nDONE')
