#!/usr/bin/env python3
"""Проверка OPcache в веб-контексте (PHP-FPM)."""
import os, base64
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

# 1. PHP-FPM pool.d
print('\n=== PHP-FPM pool.d ===')
_, o, _ = ssh.exec_command('ls -la /etc/php/8.2/fpm/pool.d/ 2>/dev/null || ls -la /etc/php/*/fpm/pool.d/ 2>/dev/null')
content = o.read().decode(errors='replace')
print(content[:800] if content else 'Not found')

# 2. opcache.enable в конфигах
print('\n=== opcache.enable в конфигах ===')
_, o, _ = ssh.exec_command("grep -rn 'opcache.enable' /etc/php/ 2>/dev/null | head -20")
content = o.read().decode(errors='replace')
print(content[:1500] if content else 'Not found')

# 3. php-cli ini
print('\n=== php-cli ini ===')
_, o, _ = ssh.exec_command('php --ini 2>/dev/null')
content = o.read().decode(errors='replace')
print(content[:400] if content else 'Not found')

# 4. PHP-скрипт проверки OPcache — base64
PHP = b'''<?php
header('Content-Type: text/plain; charset=utf-8');
echo '=== OPcache status in web context ===\\n';
$s = opcache_get_status();
if ($s === false) {
    echo 'OPcache NOT AVAILABLE\\n';
} else {
    echo 'OPcache AVAILABLE\\n';
    if (isset($s['opcache_enabled'])) echo 'enabled: ' . ($s['opcache_enabled'] ? 'ON' : 'OFF') . '\\n';
    if (isset($s['memory_consumption']['used_memory'])) echo 'used: ' . round($s['memory_consumption']['used_memory']/1048576,2) . 'MB\\n';
    if (isset($s['memory_consumption']['max_memory'])) echo 'max: ' . round($s['memory_consumption']['max_memory']/1048576,2) . 'MB\\n';
    if (isset($s['opcache_statistics']['num_cached_scripts'])) echo 'cached scripts: ' . $s['opcache_statistics']['num_cached_scripts'] . '\\n';
}
echo '\\n=== Settings ===\\n';
echo 'opcache.enable: ' . ini_get('opcache.enable') . '\\n';
echo 'opcache.enable_cli: ' . ini_get('opcache.enable_cli') . '\\n';
echo 'ext: ' . (extension_loaded('Zend OPcache') ? 'loaded' : 'not') . '\\n';
echo 'SAPI: ' . php_sapi_name() . '\\n';
echo '\\n=== .user.ini ===\\n';
if (file_exists(__DIR__ . '/.user.ini')) echo file_get_contents(__DIR__ . '/.user.ini');
else echo 'not found\\n';
'''

print('\n=== Creating test script via SFTP ===')
b64 = base64.b64encode(PHP).decode()
decoder = b'<?php eval(base64_decode($argv[1])); echo "\\n";'

with ssh.open_sftp() as sftp:
    sftp.putfo(
        __import__('io').BytesIO(decoder + b' ' + b64.encode()),
        f'{SITE}/test_opcache_web.php'
    )
print('Written test_opcache_web.php')

# 5. Curl test
print('\n=== Curl test (web OPcache) ===')
_, o, e = ssh.exec_command('curl -s -m 15 http://localhost/test_opcache_web.php')
out = o.read().decode(errors='replace')
err = e.read().decode(errors='replace')
print('Response:')
print(out)
if err.strip():
    print('curl stderr:', err[:200])

# 6. .htaccess
print('\n=== .htaccess opcache directives ===')
_, o, _ = ssh.exec_command(f'grep -n "opcache" {SITE}/.htaccess 2>/dev/null || echo "Not found"')
print(o.read().decode(errors='replace')[:400])

# 7. .user.ini
print('\n=== .user.ini ===')
_, o, _ = ssh.exec_command(f'cat {SITE}/.user.ini 2>/dev/null || echo "not found"')
print(o.read().decode(errors='replace')[:300])

ssh.close()
print('\nDONE')
