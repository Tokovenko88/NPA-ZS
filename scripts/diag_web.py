#!/usr/bin/env python3
"""Diag: check OPcache in web context + find FPM pool.d."""
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

# Part 1: find FPM pool.d correctly
find_cmd = (
    'find /etc -name "www.conf" -o -name "sevzakon.conf" -o -name "pool.conf" 2>/dev/null | '
    'head -5; '
    'echo "---"; '
    'ls /etc/php/*/fpm/pool.d/ 2>/dev/null | head -10; '
    'echo "---"; '
    'ls -la /var/www/u0220513/data/etc/ 2>/dev/null | head -20; '
    'echo "---DONE---"'
)

stdin, stdout, stderr = ssh.exec_command(find_cmd)
print('=== FPM pool find ===')
print(stdout.read().decode('utf-8', errors='replace')[:2000])

# Part 2: создаём PHP тест на сервере для проверки OPcache в веб-контексте
PHP_WEB_TEST = (
    b'<?php' + b'\n'
    + b'header("Content-Type: text/plain");' + b'\n'
    + b'echo "=== PHP version & SAPI ===\n";' + b'\n'
    + b'echo "PHP Version: ".PHP_VERSION."\n";' + b'\n'
    + b'echo "SAPI: ".php_sapi_name()."\n";' + b'\n'
    + b'echo "\n=== php.ini files ===\n";' + b'\n'
    + b'echo "Loaded Configuration File: ".get_cfg_var("cfg_file_name")."\n";' + b'\n'
    + b'$files = explode(",", get_cfg_var("additional_ini"));' + b'\n'
    + b'if($files && count($files)) { foreach($files as $f) echo "  Additional ini: ".$f."\n"; }' + b'\n'
    + b'echo "\n=== OPcache settings (from active ini) ===\n";' + b'\n'
    + b'$items = array(' + b'\n'
    + b'  "opcache.enable"           => ini_get("opcache.enable"),' + b'\n'
    + b'  "opcache.enable_cli"       => ini_get("opcache.enable_cli"),' + b'\n'
    + b'  "opcache.memory_consumption" => ini_get("opcache.memory_consumption"),' + b'\n'
    + b'  "opcache.max_accelerated_files" => ini_get("opcache.max_accelerated_files"),' + b'\n'
    + b'  "opcache.revalidate_freq"  => ini_get("opcache.revalidate_freq"),' + b'\n'
    + b'  "opcache.fast_shutdown"    => ini_get("opcache.fast_shutdown"),' + b'\n'
    + b');' + b'\n'
    + b'foreach($items as $k=>$v) echo "  $k = ".var_export($v, true)."\n";' + b'\n'
    + b'echo "\n=== Function checks ===\n";' + b'\n'
    + b'echo "  function_exists(opcache_reset): ".var_export(function_exists("opcache_reset"), true)."\n";' + b'\n'
    + b'echo "  extension_loaded(Zend OPcache): ".var_export(extension_loaded("Zend OPcache"), true)."\n";' + b'\n'
    + b'echo "\n=== .htaccess opcache test ===\n";' + b'\n'
    + b'$ht = __DIR__."/.htaccess";' + b'\n'
    + b'if(file_exists($ht)) { echo "  .htaccess FOUND\n";' + b'\n'
    + b'  $htc = file_get_contents($ht);' + b'\n'
    + b'  if(strpos($htc, "opcache.enable") !== false) {' + b'\n'
    + b'    echo "  .htaccess contains opcache.enable directive(s)\n";' + b'\n'
    + b'    $lines = explode("\n", $htc);' + b'\n'
    + b'    foreach($lines as $l) if(strpos($l, "opcache") !== false) echo "    >>> ".$l."\n";' + b'\n'
    + b'  } else { echo "  .htaccess does NOT contain opcache directives\n"; }' + b'\n'
    + b'} else { echo "  .htaccess NOT FOUND\n"; }' + b'\n'
    + b'echo "\nDONE\n";' + b'\n'
)

print('\nWriting web test script via SFTP...')
sftp = ssh.open_sftp()
with sftp.file('/tmp/test_opcache_web.php', 'wb') as f:
    f.write(PHP_WEB_TEST)
sftp.close()

print('Copied to web dir: /tmp/test_opcache_web.php')
print('(файл доступен по URL: http://sevzakon.ru:443/test_opcache_web.php)')

ssh.close()
print('\nDONE')
