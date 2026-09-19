#!/usr/bin/env python3
"""Проверка OPcache через веб-скрипт (base64 для обхода экранирования)"""
import os, base64, time
from dotenv import load_dotenv
import paramiko
import urllib.request, ssl

load_dotenv('D:/NPA-ZS/.env')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(hostname=os.getenv('MODX_SSH_HOST'), port=int(os.getenv('MODX_SSH_PORT',22)),
           username=os.getenv('MODX_SSH_USERNAME'), password=os.getenv('MODX_SSH_PASSWORD'), timeout=10)
print('SSH connected')

SITE_PATH = '/var/www/u0220513/data/www/sevzakon.ru'
TEST_FILE = SITE_PATH + '/test_opcache_web.php'

# PHP-код как bytes — без проблем экранирования
php_bytes = (
    b'<?php' + b'\n'
    + b'header("Content-Type: text/plain; charset=utf-8");' + b'\n'
    + b'echo "=== PHP Version ===' + b'\n';' + b'\n'
    + b'echo "PHP Version: " . phpversion() . "\n";' + b'\n'
    + b'echo "SAPI: " . php_sapi_name() . "\n";' + b'\n'
    + b'echo "\n\n";' + b'\n'
    + b'echo "=== php.ini files ===' + b'\n';' + b'\n'
    + b'$inifile = php_ini_loaded_file();' + b'\n'
    + b'echo "Loaded Configuration File: " . ($inifile ?: "none") . "\n";' + b'\n'
    + b'echo "Additional .ini files: " . (php_ini_scanned_files() ?: "none") . "\n";' + b'\n'
    + b'echo "\n\n";' + b'\n'
    + b'echo "=== OPcache settings ===' + b'\n';' + b'\n'
    + b'echo "  opcache.enable = '"'"' " . ini_get("opcache.enable") . " '"'"'\n";' + b'\n'
    + b'echo "  opcache.enable_cli = '"'"' " . ini_get("opcache.enable_cli") . " '"'"'\n";' + b'\n'
    + b'echo "  opcache.memory_consumption = '"'"' " . ini_get("opcache.memory_consumption") . " '"'"'\n";' + b'\n'
    + b'echo "  opcache.max_accelerated_files = '"'"' " . ini_get("opcache.max_accelerated_files") . " '"'"'\n";' + b'\n'
    + b'echo "  opcache.revalidate_freq = '"'"' " . ini_get("opcache.revalidate_freq") . " '"'"'\n";' + b'\n'
    + b'echo "  opcache.fast_shutdown = " . (ini_get("opcache.fast_shutdown") ? "true" : "false") . "\n";' + b'\n'
    + b'echo "\n\n";' + b'\n'
    + b'echo "=== Function checks ===' + b'\n';' + b'\n'
    + b'echo "  function_exists(opcache_reset): " . (function_exists("opcache_reset") ? "true" : "false") . "\n";' + b'\n'
    + b'echo "  extension_loaded(Zend OPcache): " . (extension_loaded("Zend OPcache") ? "true" : "false") . "\n";' + b'\n'
    + b'echo "\n\n";' + b'\n'
    + b'echo "=== OPcache status ===' + b'\n';' + b'\n'
    + b'$status = opcache_get_status(false);' + b'\n'
    + b'if ($status === false) { echo "  OPcache status: DISABLED\n"; }' + b'\n'
    + b'elseif ($status === null) { echo "  OPcache status: NOT AVAILABLE\n"; }' + b'\n'
    + b'else { echo "  OPcache status: ENABLED\n"; echo "  opcache_statistics: " . ($status["opcache_statistics"]["enabled"] ? "yes" : "no") . "\n"; }' + b'\n'
    + b'echo "\n\n";' + b'\n'
    + b'echo "=== .htaccess test ===' + b'\n';' + b'\n'
    + b'$htaccess = __DIR__ . "/.htaccess";' + b'\n'
    + b'if (file_exists($htaccess)) { echo "  .htaccess EXISTS\n"; $content = file_get_contents($htaccess);' + b'\n'
    + b'if (strpos($content, "opcache.enable") !== false) { echo "  .htaccess contains opcache.enable directive(s)\n";' + b'\n'
    + b'preg_match_all("/php_value\\s+opcache\\.\\w+\\s+\\w+/i", $content, $m); foreach ($m[0] as $x) echo "    >>> " . $x . "\n"; }' + b'\n'
    + b'else { echo "  .htaccess does NOT contain opcache.enable\n"; } }' + b'\n'
    + b'else { echo "  .htaccess NOT FOUND\n"; }' + b'\n'
    + b'echo "\nDone.\n";' + b'\n'
)

print(f'PHP code: {len(php_bytes)} bytes')

# Запись через SFTP
sftp = ssh.open_sftp()
with sftp.file(TEST_FILE, 'wb') as f:
    f.write(php_bytes)
sftp.close()
print(f'Written to {TEST_FILE}')

stdin, stdout, stderr = ssh.exec_command('chmod 644 ' + TEST_FILE)
print('chmod done')

time.sleep(1)

# HTTP check
print('\n=== HTTP check ===')
host = os.getenv('MODX_SSH_HOST')
url = f'https://{host}/test_opcache_web.php'
print(f'URL: {url}')

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

try:
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
        print(f'Status: {resp.status}')
        print('--- Response ---')
        print(resp.read().decode('utf-8'))
except Exception as e:
    print(f'ERROR: {e}')

# Cleanup
stdin, stdout, stderr = ssh.exec_command('rm -f ' + TEST_FILE)
print('\nCleaned up')

ssh.close()
print('\nDONE')
