#!/usr/bin/env python3
"""
Диагностика и исправление OPcache проблемы на sevzakon.ru.
Проверяет cache_sync.class.processor.php и antibot файлы, 
ищет все вызовы opcache_reset() без проверок.
"""
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

SITE_PATH = '/var/www/u0220513/data/www/sevzakon.ru'
CACHE_SYNC_PATH = f'{SITE_PATH}/manager/processors/cache_sync.class.processor.php'

def run(cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    return stdout.read().decode('utf-8', errors='replace'), stderr.read().decode('utf-8', errors='replace')

# 1. Проверяем cache_sync.class.processor.php
print('\n=== 1. cache_sync.class.processor.php ===')
out, err = run(f'grep -n "opcache_reset" {CACHE_SYNC_PATH}')
print(out if out else '  NOT FOUND или пусто')
if err:
    print(f'  stderr: {err[:200]}')

# 2. Ищем ВСЕ вызовы opcache_reset без function_exists
print('\n=== 2. Все opcache_reset() вызовы без function_exists проверки ===')
out, err = run(
    f'cd {SITE_PATH} && grep -rn "opcache_reset" --include="*.php" . | '
    f'grep -v "function_exists" | grep -v "//"'
)
print(out[:2000] if out else '  Нет небезопасных вызовов')
if err:
    print(f'  stderr: {err[:200]}')

# 3. Проверяем antibot файлы
print('\n=== 3. Antibot файлы с opcache_reset ===')
antibot_files = [
    'antibot/adm/backup.php',
    'antibot/adm/beta.php',
    'antibot/adm/beta2.php',
    'antibot/adm/confsave.php',
    'antibot/adm/phpinfo.php',
    'antibot/adm/update.php',
    'antibot/adm/update2.php',
    'antibot/adm/resetcookie.php',
    'antibot/code/ab.php',
    'antibot/code/check.php',
]
for f in antibot_files:
    full_path = f'{SITE_PATH}/{f}'
    out, err = run(f'grep -n "opcache_reset" {full_path} 2>/dev/null')
    if out:
        print(f'  {f}:')
        for line in out.strip().split('\n'):
            print(f'    {line}')

# 4. Проверяем текущее состояние OPcache через PHP
print('\n=== 4. Текущий статус OPcache (через PHP) ===')
php_code = """<?php
echo "opcache.enable = " . ini_get('opcache.enable') . "\\n";
echo "opcache.enable_cli = " . ini_get('opcache.enable_cli') . "\\n";
echo "function_exists('opcache_reset') = " . (function_exists('opcache_reset') ? 'true' : 'false') . "\\n";
echo "extension_loaded('Zend OPcache') = " . (extension_loaded('Zend OPcache') ? 'true' : 'false') . "\\n";
$din = opcache_get_status(false);
if ($din) {
    echo "opcache_statistics: enabled\\n";
    echo "  num_cached_scripts: " . $din['memory_usage']['num_cached_scripts'] . "\\n";
} else {
    echo "opcache_statistics: disabled (opcache_get_status returned null)\\n";
}
"""
out, err = run(f'php -r {repr(php_code)}')
print(out.replace('\\n', '\n'))
if err:
    print(f'  stderr: {err[:200]}')

# 5. Проверяем .htaccess
print('\n=== 5. .htaccess opcache директивы ===')
out, err = run(f'grep -n "opcache" {SITE_PATH}/.htaccess 2>/dev/null')
print(out if out else '  В .htaccess нет opcache директив')
if err:
    print(f'  stderr: {err[:200]}')

ssh.close()
print('\n✅ DONE')
