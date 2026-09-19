#!/usr/bin/env python3
"""Включить OPcache через .user.ini для PHP-FPM."""
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

SITE = '/var/www/u0220513/data/www/sevzakon.ru'

# 1. Проверить текущий .user.ini
print('\n=== Текущий .user.ini ===')
stdin, stdout, stderr = ssh.exec_command(f'cat {SITE}/.user.ini')
content = stdout.read().decode(errors='replace')
print(content[:500] if content else 'Файл не найден')

# 2. Добавить настройки OPcache в .user.ini
print('\n=== Добавление OPcache настроек в .user.ini ===')
new_ini = '''display_errors=On
error_reporting=E_ALL
log_errors=On
error_log=/tmp/php_err.log

; OPcache настройки для PHP-FPM
opcache.enable=1
opcache.memory_consumption=128
opcache.max_accelerated_files=4000
opcache.revalidate_freq=60
opcache.fast_shutdown=1
'''

stdin, stdout, stderr = ssh.exec_command(f'echo "{new_ini}" > {SITE}/.user.ini')
print('Записано')

# Проверить
print('\n=== Проверка записанного .user.ini ===')
stdin, stdout, stderr = ssh.exec_command(f'cat {SITE}/.user.ini')
print(stdout.read().decode(errors='replace')[:500])

# 3. Перезапустить PHP-FPM чтобы применить настройки
print('\n=== Перезапуск PHP-FPM ===')
stdin, stdout, stderr = ssh.exec_command('service php8.2-fpm restart 2>&1 || service php-fpm restart 2>&1 || /etc/init.d/php8.2-fpm restart 2>&1 || echo "Нет systemctl"')
out = stdout.read().decode(errors='replace')
err = stderr.read().decode(errors='replace')
print('Вывод:', out[:300])
if err.strip():
    print('Ошибки:', err[:300])

# 4. Проверить статус OPcache через веб
print('\n=== Проверка OPcache через веб ===')
PHP_TEST = '''<?php
header("Content-Type: text/plain; charset=utf-8");
echo "=== OPcache in Web Context ===\\n";
$status = opcache_get_status();
if ($status === false) {
    echo "OPcache NOT AVAILABLE\\n";
} else {
    echo "OPcache AVAILABLE\\n";
    if (isset($status["opcache_enabled"])) {
        echo "opcache_enabled: " . ($status["opcache_enabled"] ? "ON" : "OFF") . "\\n";
    }
    if (isset($status["memory_consumption"]["used_memory"])) {
        echo "Used memory: " . round($status["memory_consumption"]["used_memory"]/1048576, 2) . " MB\\n";
    }
    if (isset($status["opcache_statistics"]["num_cached_scripts"])) {
        echo "Cached scripts: " . $status["opcache_statistics"]["num_cached_scripts"] . "\\n";
    }
}
echo "\\n=== INI ===\\n";
echo "opcache.enable: " . ini_get("opcache.enable") . "\\n";
echo "SAPI: " . php_sapi_name() . "\\n";
'''

with ssh.open_sftp() as sftp:
    sftp.putfo(__import__('io').BytesIO(PHP_TEST.encode()), f'{SITE}/test_oc.php')
print('Скрипт создан')

# Выполнить проверку
stdin, stdout, stderr = ssh.exec_command(f'curl -s -m 15 -k https://{SITE.replace("/var/www/u0220513/data/www/", "")}/test_oc.php')
out = stdout.read().decode(errors='replace')
print('Ответ сервера:')
print(out[:1500])

# Удалить тестовый скрипт
ssh.exec_command(f'rm -f {SITE}/test_oc.php')

ssh.close()
print('\nDONE')
