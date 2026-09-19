#!/usr/bin/env python3
"""Полный патч cache_sync.class.processor.php (patch7) — используем b"..." для строк с одинарными кавычками PHP."""
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

# PHP-код — используем b"..." для строк, содержащих одинарные кавычки PHP
# В Python b"..." последовательность \' даёт \ + ' — именно то что нужно для PHP
PHP = (
    b"<?php" + b"\n"
    + b"$path = '" + PATH.encode() + b"';" + b"\n"
    + b"$c = file_get_contents($path);" + b"\n"
    + b"$orig = $c;" + b"\n"
    # Patch 1: add ini_get before opcache_get_status
    # В PHP-коде используем одинарные кавычки PHP, внутри которых \' — экранированная одинарная кавычка
    + b"$old = 'if (!$opcache_restrict_api && function_exists(\'opcache_get_status\')) {';" + b"\n"
    + b"$new = 'if (!$opcache_restrict_api && ini_get(\'opcache.enable\') && function_exists(\'opcache_get_status\')) {';" + b"\n"
    + b"if (strpos($c, $old) !== false) {" + b"\n"
    + b"    $c = str_replace($old, $new, $c);" + b"\n"
    + b"    echo 'PATCH1 applied: ini_get before opcache_get_status' . \"\\n\";" + b"\n"
    + b"} else {" + b"\n"
    + b"    echo 'WARNING: PATCH1 pattern NOT found' . \"\\n\";" + b"\n"
    + b"}" + b"\n"
    + b"" + b"\n"
    # Patch 2: verify opcache_reset check
    + b"$pat2 = 'if (!empty($opcache[\'opcache_enabled\']) && ini_get(\'opcache.enable\') && function_exists(\'opcache_reset\')) {';" + b"\n"
    + b"if (strpos($c, $pat2) !== false) {" + b"\n"
    + b"    echo 'PATCH2 OK: opcache_reset check present' . \"\\n\";" + b"\n"
    + b"} else {" + b"\n"
    + b"    echo 'WARNING: PATCH2 opcache_reset check NOT found' . \"\\n\";" + b"\n"
    + b"}" + b"\n"
    + b"" + b"\n"
    # Save
    + b"if ($c !== $orig) {" + b"\n"
    + b"    if (file_put_contents($path, $c)) {" + b"\n"
    + b"        echo 'SAVED' . \"\\n\";" + b"\n"
    + b"    } else {" + b"\n"
    + b"        echo 'SAVE FAILED' . \"\\n\";" + b"\n"
    + b"        exit(1);" + b"\n"
    + b"    }" + b"\n"
    + b"} else {" + b"\n"
    + b"    echo 'NO CHANGE (already patched?)' . \"\\n\";" + b"\n"
    + b"}" + b"\n"
    + b"\n"
    + b"echo 'DONE' . \"\\n\";" + b"\n"
    + b"" + b"\n"
)

print(f'PHP script size: {len(PHP)} bytes')
print('Writing to /tmp/patch_cs7.php via SFTP...')

sftp = cli.open_sftp()
with sftp.file('/tmp/patch_cs7.php', 'wb') as f:
    f.write(PHP)
sftp.close()
print('Written')

print('\n=== Running PHP ===')
stdin, stdout, stderr = cli.exec_command('php /tmp/patch_cs7.php')
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
