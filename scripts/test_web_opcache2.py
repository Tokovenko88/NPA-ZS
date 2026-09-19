#!/usr/bin/env python3
"""Проверка OPcache в веб-контексте через SFTP + curl."""
import os
from dotenv import load_dotenv
import paramiko
import subprocess
import time

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

# PHP-скрипт — только ASCII, без проблемных символов
PHP = """<?php
header('Content-Type: text/plain');
echo "=== OPcache в веб-контексте ===\\n\\n";
echo "extension_loaded(opcache): " . (extension_loaded('opcache') ? 'YES' : 'NO') . "\\n";
echo "function_exists(opcache_reset): " . (function_exists('opcache_reset') ? 'YES' : 'NO') . "\\n";
echo "function_exists(opcache_get_status): " . (function_exists('opcache_get_status') ? 'YES' : 'NO') . "\\n";
echo "ini_get(opcache.enable): [" . ini_get('opcache.enable') . "]\\n";
echo "ini_get(opcache.enable_cli): [" . ini_get('opcache.enable_cli') . "]\\n";
echo "PHP_SAPI: " . PHP_SAPI . "\\n\\n";
if (function_exists('opcache_get_status')) {
    $s = opcache_get_status();
    if ($s === false) echo "opcache_get_status(): FALSE (выключен или недоступен)\\n";
    elseif ($s === null) echo "opcache_get_status(): NULL\\n";
    else echo "opcache_get_status(): OK (включен)\\n";
} else {
    echo "opcache_get_status(): функция не существует\\n";
}
echo "\\nЗагруженные расширения с opcache:\\n";
$ext = get_loaded_extensions();
$found = false;
foreach ($ext as $e) {
    if (stripos($e, 'opcache') !== false || stripos($e, 'Zend OPcache') !== false) {
        echo "  - $e\\n";
        $found = true;
    }
}
if (!$found) echo "  OPcache НЕ найден среди загруженных расширений\\n";
echo "\\nDone.\\n";
"""

WEB_PATH = '/var/www/u0220513/data/www/sevzakon.ru/test_opcache_web.php'
print(f'Запись {WEB_PATH} через SFTP...')
sftp = ssh.open_sftp()
with sftp.file(WEB_PATH, 'w') as f:
    f.write(PHP)
sftp.close()
print('Файл записан')

ssh.exec_command('rm -f /var/www/u0220513/data/www/sevzakon.ru/test_opcache.php 2>/dev/null')
print('Старый файл удалён')

print('\nПроверяем через веб (curl)...')
time.sleep(0.5)

try:
    result = subprocess.run(
        ['curl', '-s', '--max-time', '10', 'http://sevzakon.ru/test_opcache_web.php'],
        capture_output=True, text=True, timeout=15
    )
    print('=== Ответ от сервера (ВЕБ-контекст) ===')
    print(result.stdout[:2000])
    if result.stderr:
        print('STDERR:', result.stderr[:300])
except Exception as e:
    print(f'Ошибка curl: {e}')

print('\n=== Создаём короткий файл в корне ===')
ssh.exec_command(f'cp {WEB_PATH} /var/www/u0220513/data/www/sevzakon.ru/oc.php 2>/dev/null')
print('Скопировано в oc.php')

ssh.close()
print('\nDONE')
