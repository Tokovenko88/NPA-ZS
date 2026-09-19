#!/usr/bin/env python3
"""Проверка: работает ли OPcache в веб-контексте (PHP-FPM)."""
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

# Путь к сайту
SITE_PATH = '/var/www/u0220513/data/www/sevzakon.ru'

# 1. Проверяем конфиг PHP-FPM
print('\n=== PHP-FPM pool.d конфиг ===')
_, stdout, _ = ssh.exec_command('ls -la /etc/php/8.2/fpm/pool.d/ 2>/dev/null || ls -la /etc/php/*/fpm/pool.d/ 2>/dev/null')
print(stdout.read().decode()[:1000])

# 2. Ищем где opcache.enable настроен
print('\n=== Где настроен opcache.enable ===')
_, stdout, _ = ssh.exec_command(
    "grep -r 'opcache.enable' /etc/php/ 2>/dev/null | head -20 || "
    "grep -r 'opcache.enable' /etc/php/*/ 2>/dev/null | head -20"
)
print(stdout.read().decode()[:2000])

# 3. Проверяем текущий php.ini
print('\n=== Текущий php.ini (отображается в php-cli) ===')
_, stdout, _ = ssh.exec_command('php --ini 2>/dev/null')
print(stdout.read().decode()[:500])

# 4. Создаём PHP-скрипт для проверки OPcache в веб-контексте через curl
# (PHP-FPM может не читать .htaccess с php_value, но читать .user.ini)
print('\n=== Создаём скрипт проверки OPcache в веб-контексте ===')

# PHP-скрипт проверки — пишем через SFTP 
PHP_TEST = b'<?php' + b'\n'
PHP_TEST += b'header("Content-Type: text/plain; charset=utf-8");' + b'\n'
PHP_TEST += b'echo "=== OPcache статус в веб-контексте ===\\n";' + b'\n'
PHP_TEST += b'$status = opcache_get_status();' + b'\n'
PHP_TEST += b'if ($status === false) {' + b'\n'
PHP_TEST += b'    echo "OPcache НЕ ДОСТУПН (возвращает false)\\n";' + b'\n'
PHP_TEST += b'    echo "Вероятная причина: opcache.enable=0 или расширение не загружено в FPM\\n";' + b'\n'
PHP_TEST += b'} else {' + b'\n'
PHP_TEST += b'    echo "OPcache ДОСТУПН\\n";' + b'\n'
PHP_TEST += b'    if (isset($status["opcache_enabled"])) echo "opcache_enabled: " . ($status["opcache_enabled"] ? "1 (ON)" : "0 (OFF)") . "\\n";' + b'\n'
PHP_TEST += b'    if (isset($status["memory_consumption"]["used_memory"])) echo "Использовано памяти: " . round($status["memory_consumption"]["used_memory"]/1024/1024, 2) . " MB\\n";' + b'\n'
PHP_TEST += b'    if (isset($status["memory_consumption"]["max_memory"])) echo "Макс. память: " . round($status["memory_consumption"]["max_memory"]/1024/1024, 2) . " MB\\n";' + b'\n'
PHP_TEST += b'    if (isset($status["opcache_statistics"]["num_cached_scripts"])) echo "Заченные скрипты: " . $status["opcache_statistics"]["num_cached_scripts"] . "\\n";' + b'\n'
PHP_TEST += b'}' + b'\n'
PHP_TEST += b'echo "\\n=== Другие настройки ===\\n";' + b'\n'
PHP_TEST += b'echo "opcache.enable: " . ini_get("opcache.enable") . "\\n";' + b'\n'
PHP_TEST += b'echo "opcache.enable_cli: " . ini_get("opcache.enable_cli") . "\\n";' + b'\n'
PHP_TEST += b'echo "zend_extension: " . (extension_loaded("Zend OPcache") ? "загружен" : "НЕ загружен") . "\\n";' + b'\n'
PHP_TEST += b'echo "SAPI: " . php_sapi_name() . "\\n";' + b'\n'
PHP_TEST += b'echo "\\n=== Файл .user.ini (если есть) ===\\n";' + b'\n'
PHP_TEST += b'$user_ini = __DIR__ . "/.user.ini";' + b'\n'
PHP_TEST += b'if (file_exists($user_ini)) {' + b'\n'
PHP_TEST += b'    echo "Найден .user.ini:\\n";' + b'\n'
PHP_TEST += b'    echo file_get_contents($user_ini);' + b'\n'
PHP_TEST += b'} else {' + b'\n'
PHP_TEST += b'    echo "Не найден\\n";' + b'\n'
PHP_TEST += b'}' + b'\n'

print('Writing test script via SFTP...')
sftp = ssh.open_sftp()
with sftp.file(f'{SITE_PATH}/test_opcache_web.php', 'wb') as f:
    f.write(PHP_TEST)
sftp.close()
print('Written test_opcache_web.php')

# 5. Теперь запускаем curl к этому скрипту
print('\n=== Запуск curl для проверки OPcache в веб-контексте ===')
_, stdout, stderr = ssh.exec_command(
    f'curl -s -m 15 -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" '
    f'http://localhost/test_opcache_web.php 2>&1'
)
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
print('Веб-ответ:')
print(out)
if err:
    print('Ошибки curl:', err[:300])

# 6.Также проверяем .htaccess на наличие проблемных директив
print('\n=== Проверяем .htaccess ===')
_, stdout, _ = ssh.exec_command(f'grep -n "opcache" {SITE_PATH}/.htaccess 2>/dev/null || echo "opcache не найден в .htaccess"')
print(stdout.read().decode()[:500])

# 7. Проверяем есть ли .user.ini
print('\n=== .user.ini ===')
_, stdout, _ = ssh.exec_command(f'cat {SITE_PATH}/.user.ini 2>/dev/null || echo "Нет файла .user.ini"')
print(stdout.read().decode()[:500])

ssh.close()
print('\nDONE')
