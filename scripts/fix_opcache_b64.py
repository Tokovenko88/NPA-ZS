#!/usr/bin/env python3
"""Патч cache_sync.class.processor.php через base64 — без проблем экранирования."""
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

PATH = '/var/www/u0220513/data/www/sevzakon.ru/manager/processors/cache_sync.class.processor.php'

# PHP-скрипт патча — пишем как обычную Python-строку (без bytes)
# Кавычки в PHP: используем двойные кавычки PHP для строк с внутренними одинарными кавычками
php = """<?php
$path = '""" + PATH + """';
if (!file_exists($path)) { die('NOT FOUND\\n'); }
echo "Found: $path\\n";
$c = file_get_contents($path);
$o = $c;

if (strpos($c, "function_exists('opcache_reset')") !== false) {
    echo "ALREADY PATCHED\\n";
} else {
    // Оригинальный паттерн (без function_exists)
    $orig = 'if (!empty($opcache[\\'opcache_enabled\\']) && ini_get(\\'opcache.enable\\')) {
                @opcache_reset();';
    // Патченный вариант
    $fixed = 'if (!empty($opcache[\\'opcache_enabled\\']) && ini_get(\\'opcache.enable\\') && function_exists(\\'opcache_reset\\')) {
                @opcache_reset();';
    if (strpos($c, $orig) !== false) {
        $c = str_replace($orig, $fixed, $c);
        echo "PATCHED\\n";
    } else {
        echo "NOT FOUND: expected pattern not found\\n";
        echo "Showing lines with opcache_reset:\\n";
        $lines = explode("\\n", $c);
        foreach ($lines as $i => $line) {
            if (strpos($line, "opcache_reset") !== false) {
                echo "  Line $i: $line\\n";
                if (isset($lines[$i-1])) echo "  Line " . ($i-1) . ": " . $lines[$i-1] . "\\n";
                if (isset($lines[$i+1])) echo "  Line " . ($i+1) . ": " . $lines[$i+1] . "\\n";
            }
        }
    }
}

if ($c !== $o) {
    if (file_put_contents($path, $c)) echo "SAVED\\n";
    else { echo "SAVE FAILED\\n"; exit(1); }
} else {
    echo "NO CHANGE\\n";
}
echo "DONE\\n";
"""

# Кодируем в base64
b64 = base64.b64encode(php.encode()).decode()
print(f'PHP script encoded: {len(b64)} chars base64')
print('Writing to server via SFTP...')

sftp = ssh.open_sftp()
with sftp.file('/tmp/fix_opcache_b64.php', 'w') as f:
    f.write('<?php\n')
    f.write('$b = \'' + b64 + '\';\n')
    f.write('eval(base64_decode($b));\n')
sftp.close()
print('Written /tmp/fix_opcache_b64.php')

print('\n=== Running ===')
stdin, stdout, stderr = ssh.exec_command('php /tmp/fix_opcache_b64.php', timeout=30)
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
print('OUTPUT:')
print(out)
if err.strip():
    print('ERRORS:')
    print(err[:500])

print('\n=== Verify ===')
stdin, stdout, stderr = ssh.exec_command(
    f"grep -n -A3 -B1 'opcache_reset' {PATH}",
    timeout=10
)
result = stdout.read().decode('utf-8', errors='replace')
print(result)
err2 = stderr.read().decode('utf-8', errors='replace')
if err2:
    print('ERRORS:', err2[:200])

ssh.close()
print('\nDONE')
