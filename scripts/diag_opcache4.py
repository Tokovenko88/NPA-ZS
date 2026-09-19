#!/usr/bin/env python3
"""Диагностика OPcache: ищет все файлы с opcache_reset и показывает статус."""
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

ROOT = '/var/www/u0220513/data/www/sevzakon.ru'

# PHP-скрипт: ищет все файлы с opcache_reset, проверяет статус
PHP = """<?php
$root = \"""" + ROOT + """\";
echo "=== PHP INFO (web context) ===\n";
echo "opcache.enable: " . ini_get("opcache.enable") . "\n";
echo "opcache.enable_cli: " . ini_get("opcache.enable_cli") . "\n";
echo "function_exists(opcache_reset): " . (function_exists("opcache_reset") ? "YES" : "NO") . "\n";
echo "extension_loaded(opcache): " . (extension_loaded("opcache") ? "YES" : "NO") . "\n";
echo "\n=== SEARCHING for opcache_reset in site files ===\n";
$files = [];
scan_dir($root);
function scan_dir($dir) {
  global $files;
  $items = scandir($dir);
  if ($items === false) return;
  foreach ($items as $item) {
    if ($item == "." || $item == "..") continue;
    $path = $dir . "/" . $item;
    if (is_dir($path)) scan_dir($path);
    elseif (preg_match('/\.php$/', $item)) {
      $content = file_get_contents($path);
      if (strpos($content, "opcache_reset") !== false) {
        $files[] = $path;
      }
    }
  }
}
foreach ($files as $f) {
  echo "FILE: $f\n";
  $c = file_get_contents($f);
  $lines = explode("\n", $c);
  foreach ($lines as $i => $ln) {
    if (strpos($ln, "opcache_reset") !== false) {
      $start = max(0, $i-3);
      $end = min(count($lines), $i+4);
      for ($j = $start; $j < $end; $j++) {
        $marker = ($j == $i) ? ">>>" : "   ";
        echo "$marker L" . ($j+1) . ": " . $lines[$j] . "\n";
      }
      echo "\n";
    }
  }
}
echo "Total files with opcache_reset: " . count($files) . "\n";
echo "\n=== DONE ===\n";
"""

print(f'PHP script size: {len(PHP)} chars')

# Записываем через SFTP
sftp = ssh.open_sftp()
with sftp.file('/tmp/diag_opcache_full.php', 'w') as f:
    f.write(PHP)
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
