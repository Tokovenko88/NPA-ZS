#!/usr/bin/env python3
"""Проверка файла cache_sync.class.processor.php на сервере."""
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

# PHP-скрипт проверки — пишем через SFTP
PHP = b'''<?php
$path = ''' + repr(PATH).encode() + b''';
if (!file_exists($path)) { echo "NOT FOUND\n"; exit(1); }
echo "EXISTS\n";
$c = file_get_contents($path);
echo "SIZE: " . strlen($c) . " bytes\n";
echo "LINES: " . count(explode("\n", $c)) . "\n";
echo "--- last 30 lines ---\n";
$lines = explode("\n", $c);
for ($i = max(0, count($lines) - 30); $i < count($lines); $i++) {
    echo ($i + 1) . " " . $lines[$i] . "\n";
}
echo "\n--- grep opcache_reset ---\n";
foreach ($lines as $i => $ln) {
    if (strpos($ln, 'opcache_reset') !== false) {
        echo ($i + 1) . ": " . $ln . "\n";
        if (isset($lines[$i - 1])) echo "  " . ($i) . ": " . $lines[$i - 1] . "\n";
        if (isset($lines[$i + 1])) echo "  " . ($i + 2) . ": " . $lines[$i + 1] . "\n";
    }
}
echo "\nDONE\n";
'''

print('Writing PHP checker via SFTP...')
sftp = ssh.open_sftp()
with sftp.file('/tmp/check_cs.php', 'wb') as f:
    f.write(PHP)
sftp.close()
print('Written to /tmp/check_cs.php')

print('\n=== Running checker ===')
stdin, stdout, stderr = ssh.exec_command('php /tmp/check_cs.php 2>&1')
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
print(out)
if err:
    print('STDERR:', err[:300])

ssh.close()
print('\nDONE')
