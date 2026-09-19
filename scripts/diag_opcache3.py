#!/usr/bin/env python3
"""Диагностика OPcache: путь к сайту, файл cache_sync, статус PHP OPcache."""
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

# PHP-скрипт: ищет все файлы с opcache_reset, проверяет статус, пишет результат
# Записываем как байты, чтобы избежать проблем с экранированием в Python/PowerShell
PHP_BYTES = (
    b'<?php' + b'\n'
    b'$root = '/var/www/u0220513/data/www/sevzakon.ru';' + b'\n'
    b'echo "=== PHP INFO (web context) ===\n";' + b'\n'
    b'echo "opcache.enable: " . ini_get("opcache.enable") . "\n";' + b'\n'
    b'echo "opcache.enable_cli: " . ini_get("opcache.enable_cli") . "\n";' + b'\n'
    b'echo "function_exists(opcache_reset): " . (function_exists("opcache_reset") ? "YES" : "NO") . "\n";' + b'\n'
    b'echo "extension_loaded(opcache): " . (extension_loaded("opcache") ? "YES" : "NO") . "\n";' + b'\n'
    b'echo "\n=== SEARCHING for opcache_reset in site files ===\n";' + b'\n'
    b'$files = [];' + b'\n'
    b'scan_dir($root);' + b'\n'
    b'function scan_dir($dir) {' + b'\n'
    b'  global $files;' + b'\n'
    b'  $items = scandir($dir);' + b'\n'
    b'  if ($items === false) return;' + b'\n'
    b'  foreach ($items as $item) {' + b'\n'
    b'    if ($item == "." || $item == "..") continue;' + b'\n'
    b'    $path = $dir . "/" . $item;' + b'\n'
    b'    if (is_dir($path)) scan_dir($path);' + b'\n'
    b"    elseif (preg_match('/\.php$/', \$item)) {" + b'\n'
    b'      $content = file_get_contents($path);' + b'\n'
    b'      if (strpos($content, "opcache_reset") !== false) {' + b'\n'
    b'        $files[] = $path;' + b'\n'
    b'      }' + b'\n'
    b'    }' + b'\n'
    b'  }' + b'\n'
    b'}' + b'\n'
    b'foreach ($files as $f) {' + b'\n'
    b'  echo "FILE: $f\n";' + b'\n'
    b'  $c = file_get_contents($f);' + b'\n'
    b'  $lines = explode("\n", $c);' + b'\n'
    b'  foreach ($lines as $i => $ln) {' + b'\n'
    b'    if (strpos($ln, "opcache_reset") !== false) {' + b'\n'
    b'      $start = max(0, $i-3);' + b'\n'
    b'      $end = min(count($lines), $i+4);' + b'\n'
    b'      for ($j = $start; $j < $end; $j++) {' + b'\n'
    b'        $marker = ($j == $i) ? ">>>" : "   ";' + b'\n'
    b'        echo "$marker L" . ($j+1) . ": " . $lines[$j] . "\n";' + b'\n'
    b'      }' + b'\n'
    b'      echo "\n";' + b'\n'
    b'    }' + b'\n'
    b'  }' + b'\n'
    b'}' + b'\n'
    b'echo "Total files with opcache_reset: " . count($files) . "\n";' + b'\n'
    b'echo "\n=== DONE ===\n";' + b'\n'
)

print(f'PHP script size: {len(PHP_BYTES)} bytes')

# Записываем через SFTP
sftp = ssh.open_sftp()
with sftp.file('/tmp/diag_opcache_full.php', 'wb') as f:
    f.write(PHP_BYTES)
sftp.close()
print('Written to /tmp/diag_opcache_full.php')

print('\n=== Running ===')
stdin, stdout, stderr = ssh.exec_command('php /tmp/diag_opcache_full.php')
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')

print('--- OUTPUT ---')
print(out)

if err:
    print('\n--- STDERR ---')
    print(err[:1000])

ssh.close()
print('\nDONE')
