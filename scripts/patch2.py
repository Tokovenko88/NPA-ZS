#!/usr/bin/env python3
"""Патч cache_sync.class.processor.php — проверка function_exists('opcache_reset')."""
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

PATH = '/var/www/u0220513/data/www/sevzakon.ru/manager/processors/cache_sync.class.processor.php'

# PHP-скрипт патча — пишем как байты для избежания проблем экранирования
PHP = (
    b'<?php' + b'\n'
    + b'$path = ' + repr(PATH).encode() + b';' + b'\n'
    + b'if (!file_exists($path)) { die("NOT FOUND\n"); }' + b'\n'
    + b'echo "Found: $path\n";' + b'\n'
    + b'$c = file_get_contents($path); $o = $c;' + b'\n'
    # Ищем проблемную строку без function_exists
    + b'$s = "if (!empty($opcache[\'opcache_enabled\']) && ini_get(\'opcache.enable\')) {\n                @opcache_reset();";' + b'\n'
    # Заменяем на правильный вариант
    + b'$r = "if (!empty($opcache[\'opcache_enabled\']) && ini_get(\'opcache.enable\') && function_exists(\'opcache_reset\')) {\n                @opcache_reset();";' + b'\n'
    + b'if (strpos($c, $s) !== false) { $c = str_replace($s, $r, $c); echo "PATCHED\n"; }' + b'\n'
    + b'elseif (strpos($c, "function_exists(\'opcache_reset\')") !== false) { echo "ALREADY PATCHED\n"; }' + b'\n'
    + b'else {' + b'\n'
    + b'  echo "NOT FOUND expected pattern\n";' + b'\n'
    + b'  $l = explode("\n", $c);' + b'\n'
    + b'  foreach($l as $i=>$ln) { if(strpos($ln,"opcache_reset")!==false) {' + b'\n'
    + b'    echo "  line $i: $ln\n";' + b'\n'
    + b'    if(isset($l[$i-1])) echo "  line ".($i-1).": ".$l[$i-1]."\n";' + b'\n'
    + b'    if(isset($l[$i+1])) echo "  line ".($i+1).": ".$l[$i+1]."\n";' + b'\n'
    + b'  } }' + b'\n'
    + b'}' + b'\n'
    + b'if ($c !== $o) { if(file_put_contents($path, $c)) echo "SAVED\n"; else { echo "SAVE FAILED\n"; exit(1); } }' + b'\n'
    + b'else echo "NO CHANGE\n";' + b'\n'
    + b'echo "DONE\n";' + b'\n'
)

print('Writing patch script via SFTP...')
sftp = ssh.open_sftp()
with sftp.file('/tmp/patch_cs.php', 'wb') as f:
    f.write(PHP)
sftp.close()
print('Written to /tmp/patch_cs.php')

print('\n=== Running patch ===')
stdin, stdout, stderr = ssh.exec_command('php /tmp/patch_cs.php')
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
print('OUTPUT:')
print(out)
if err:
    print('ERRORS:')
    print(err[:500])

print('\n=== Verify result ===')
stdin, stdout, stderr = ssh.exec_command(f"grep -n -A3 -B1 'opcache_reset' {PATH}")
result = stdout.read().decode('utf-8', errors='replace')
print(result)
err2 = stderr.read().decode('utf-8', errors='replace')
if err2:
    print('ERRORS:', err2[:200])

ssh.close()
print('\nDONE')
