#!/usr/bin/env python3
"""Полный патч cache_sync.class.processor.php (patch6)."""
import os
from dotenv import load_dotenv
import paramiko

load_dotenv('D:/NPA-ZS/.env')
cli = paramiko.SSHClient()
cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
cli.connect(
    hostname=os.getenv('MODX_SSH_HOST'),
    port=int(os.getenv('MODX_SSH_PORT', 22)),
    username=os.getenv('MODX_SSH_USERNAME'),
    password=os.getenv('MODX_SSH_PASSWORD'),
    timeout=15,
)
print('SSH connected to', os.getenv('MODX_SSH_HOST'))

PATH = '/var/www/u0220513/data/www/sevzakon.ru/manager/processors/cache_sync.class.processor.php'

# PHP-код — используем одинарные кавычки PHP для строк с $opcache
PHP = (
    b'<?php' + b'\n'
    + b'$path = ' + repr(PATH).encode() + b';' + b'\n'
    + b'if (!file_exists($path)) { die(\'NOT FOUND: \' . $path . \'\\n\'); }' + b'\n'
    # Patch 1: add ini_get before opcache_get_status — используем одинарные кавычки PHP
    + b'$old1 = \'if (!$opcache_restrict_api && function_exists(\'opcache_get_status\')) {\';' + b'\n'
    + b'$new1 = \'if (!$opcache_restrict_api && function_exists(\'opcache_get_status\') && ini_get(\'opcache.enable\')) {\';' + b'\n'
    + b'if (strpos($c, $old1) !== false) {' + b'\n'
    + b'    $c = str_replace($old1, $new1, $c);' + b'\n'
    + b'    echo \'PATCH1 applied: ini_get before opcache_get_status\' . "\\n";' + b'\n'
    + b'} else {' + b'\n'
    + b'    echo \'WARNING: PATCH1 NOT found\' . "\\n";' + b'\n'
    + b'}' + b'\n'
    + b'' + b'\n'
    # Patch 2: verify opcache_reset check — тоже одинарные кавычки PHP
    + b'$pat2 = \'if (!empty($opcache[\'opcache_enabled\']) && ini_get(\'opcache.enable\') && function_exists(\'opcache_reset\')) {\';' + b'\n'
    + b'if (strpos($c, $pat2) !== false) {' + b'\n'
    + b'    echo \'PATCH2 OK: opcache_reset check present\' . "\\n";' + b'\n'
    + b'} else {' + b'\n'
    + b'    echo \'WARNING: PATCH2 NOT found\' . "\\n";' + b'\n'
    + b'}' + b'\n'
    + b'' + b'\n'
    # Save
    + b'$c = file_get_contents($path);' + b'\n'
    + b'$orig = $c;' + b'\n'
    + b'if ($c !== $orig) {' + b'\n'
    + b'    if (file_put_contents($path, $c)) {' + b'\n'
    + b'        echo \'SAVED\' . "\\n";' + b'\n'
    + b'    } else {' + b'\n'
    + b'        echo \'SAVE FAILED\' . "\\n";' + b'\n'
    + b'        exit(1);' + b'\n'
    + b'    }' + b'\n'
    + b'} else {' + b'\n'
    + b'    echo \'NO CHANGE\' . "\\n";' + b'\n'
    + b'}' + b'\n'
    + b'' + b'\n'
    + b'echo \'DONE\' . "\\n";' + b'\n'
)

print(f'PHP script size: {len(PHP)} bytes')
print('Writing to /tmp/patch_cs6.php via SFTP...')

sftp = cli.open_sftp()
with sftp.file('/tmp/patch_cs6.php', 'wb') as f:
    f.write(PHP)
sftp.close()
print('Written')

print('\n=== Running PHP ===')
stdin, stdout, stderr = cli.exec_command('php /tmp/patch_cs6.php')
out = stdout.read().decode('utf-8', 'replace')
err = stderr.read().decode('utf-8', 'replace')
print('STDOUT:')
print(out)
if err.strip():
    print('STDERR:')
    print(err[:500])

print('\n=== Verify cache_sync ===')
stdin, stdout, stderr = cli.exec_command(
    "grep -n -A8 'function_exists.*opcache_get_status' " + PATH
)
result = stdout.read().decode('utf-8', 'replace')
print(result[:800])
err2 = stderr.read().decode('utf-8', 'replace')
if err2.strip():
    print('Verify stderr:', err2[:200])

cli.close()
print('\nDONE')
