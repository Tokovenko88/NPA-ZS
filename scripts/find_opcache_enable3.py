#!/usr/bin/env python3
"""Поиск кода, который пытается включить OPcache (ini_set('opcache.enable', 1) и т.д.)."""
import os
import base64
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

PHP = """<?php
$root = \"""" + ROOT + """\";
echo "=== SEARCHING for opcache enable/disable attempts ===\n";
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
      if (
        strpos($content, 'ini_set("opcache' ) !== false ||
        strpos($content, "ini_set('opcache" ) !== false ||
        strpos($content, 'opcache.enable' ) !== false ||
        strpos($content, 'opcache.enable_cli' ) !== false ||
        strpos($content, 'opcache_reset' ) !== false ||
        strpos($content, 'opcache_get_status' ) !== false
      ) {
        $files[] = $path;
      }
    }
  }
}

foreach ($files as $f) {
  echo "\n=== FILE: $f\n";
  $c = file_get_contents($f);
  $lines = explode("\n", $c);
  $relevant_lines = [];
  foreach ($lines as $i => $ln) {
    if (
      strpos($ln, 'ini_set("opcache' ) !== false ||
      strpos($ln, "ini_set('opcache' ) !== false ||
      strpos($ln, 'opcache.enable' ) !== false ||
      strpos($ln, 'opcache.enable_cli' ) !== false ||
      strpos($ln, 'opcache_reset' ) !== false ||
      strpos($ln, 'opcache_get_status' ) !== false
    ) {
      $relevant_lines[$i] = $ln;
    }
  }
  foreach ($relevant_lines as $i => $ln) {
    $start = max(0, $i-2);
    $end = min(count($lines), $i+3);
    for ($j = $start; $j < $end; $j++) {
      $marker = ($j == $i) ? ">>>" : "   ";
      echo "$marker L" . ($j+1) . ": " . $lines[$j] . "\n";
    }
    echo "\n";
  }
}

echo "\nTotal files with opcache references: " . count($files) . "\n";
echo "\n=== DONE ===\n";
"""

php_b64 = base64.b64encode(PHP.encode()).decode()
print(f'PHP base64 size: {len(php_b64)} chars')

# Записываем декодер через SFTP
sftp = ssh.open_sftp()
with sftp.file('/tmp/run_b64.php', 'w') as f:
    f.write('<' + '?' + 'php eval(base64_decode($argv[1]));')
sftp.close()
print('Written /tmp/run_b64.php')

print('\n=== Running ===')
stdin, stdout, stderr = ssh.exec_command(f'php /tmp/run_b64.php {php_b64}')
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')

print('--- OUTPUT ---')
print(out)

if err:
    print('\n--- STDERR ---')
    print(err[:1000])

ssh.close()
print('\nDONE')
