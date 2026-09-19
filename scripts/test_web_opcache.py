#!/usr/bin/env python3
"""Создать PHP-тест OPcache в веб-контексте на сервере."""
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

# PHP-скрипт для проверки OPcache в ВЕБ-контексте
PHP = b'''<?php
header('Content-Type: text/plain; charset=utf-8');
echo "=== OPcache в веб-контексте ===\n\n";
echo "extension_loaded(opcache): " . (extension_loaded('opcache') ? 'YES' : 'NO') . "\n";
echo "function_exists(opcache_reset): " . (function_exists('opcache_reset') ? 'YES' : 'NO') . "\n";
echo "function_exists(opcache_get_status): " . (function_exists('opcache_get_status') ? 'YES' : 'NO') . "\n";
echo "ini_get(opcache.enable): [" . ini_get('opcache.enable') . "]\n";
echo "ini_get(opcache.enable_cli): [" . ini_get('opcache.enable_cli') . "]\n";
echo "opcache_get_status(): ";
if (function_exists('opcache_get_status')) {
    $s = opcache_get_status();
    if ($s === false) echo "FALSE (OPcache выключен или недоступен)\n";
    elseif ($s === null) echo "NULL\n";
    else echo "OK (включен)\n";
} else {
    echo "недоступна (функция не существует)\n";
}
echo "\n=== Загруженные расширения (только opcache) ===\n";
$ext = get_loaded_extensions();
if (in_array('Zend OPcache', $ext)) echo "Zend OPcache: загружен\n";
elseif (in_array('opcache', $ext)) echo "opcache: загружен\n";
else echo "OPcache НЕ загружен\n";
echo "\n=== SAPI ===\n";
echo "PHP_SAPI: " . PHP_SAPI . "\n";
echo "php_sapi_name(): " . php_sapi_name() . "\n";
echo "\n=== Детальная информация ===\n";
if (function_exists('opcache_get_configuration')) {
    $cfg = opcache_get_configuration();
    if ($cfg && isset($cfg['directives'])) {
        echo "opcache.enable (из конфига): " . ($cfg['directives']['opcache.enable'] ?? 'не задано') . "\n";
    }
}
echo "\nDone.\n";
'''

WEB_PATH = '/var/www/u0220513/data/www/sevzakon.ru/test_opcache_web.php'

print(f'Запись {WEB_PATH} через SFTP...')
sftp = ssh.open_sftp()
with sftp.file(WEB_PATH, 'wb') as f:
    f.write(PHP)
sftp.close()
print('✅ Файл записан')

# Удалим старый файл если есть
try:
    ssh.exec_command(f'rm -f /var/www/u0220513/data/www/sevzakon.ru/test_opcache.php 2>/dev/null')
    print('Старый файл удалён (если был)')
except:
    pass

print('\nТеперь проверим через веб...')
print('(сначала проверяем, что файл доступен)')

import subprocess
import time

# Ждём немного, чтобы файл появился
time.sleep(0.5)

# Пытаемся получить через curl
try:
    result = subprocess.run(
        ['curl', '-s', '--max-time', '10', 
         'http://sevzakon.ru/test_opcache_web.php'],
        capture_output=True, text=True, timeout=15
    )
    print('=== Ответ от сервера (веб-контекст) ===')
    print(result.stdout[:2000])
    if result.stderr:
        print('STDERR:', result.stderr[:200])
    print(f'HTTP код: {result.returncode}')
except Exception as e:
    print(f'Ошибка curl: {e}')

print('\n=== Также создаём файл в корне для удобства ===')
# Копируем в более короткий путь
ssh.exec_command(f'cp {WEB_PATH} /var/www/u0220513/data/www/sevzakon.ru/oc.php 2>/dev/null')
print('Скопировано в oc.php')

ssh.close()
print('\nDONE')
