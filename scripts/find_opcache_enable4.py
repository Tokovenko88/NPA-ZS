#!/usr/bin/env python3
"""Поиск кода, который пытается включить OPcache (ini_set('opcache.enable', 1) и т.д.)."""
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

# PHP-скрипт — конструируем через одинарные кавычки Python, чтобы избежать проблем с экранированием
PHP = (
    '<' + '?' + 'php' + '\n'
    + '$root = "' + ROOT + '";' + '\n'
    + 'echo "=== SEARCHING for opcache enable/disable attempts ===' + chr(10) + '";' + '\n'
    + '$files = [];' + '\n'
    + 'scan_dir($root);' + '\n'
    + '' + '\n'
    + 'function scan_dir($dir) {' + '\n'
    + '  global $files;' + '\n'
    + '  $items = scandir($dir);' + '\n'
    + '  if ($items === false) return;' + '\n'
    + '  foreach ($items as $item) {' + '\n'
    + '    if ($item == "." || $item == "..") continue;' + '\n'
    + '    $path = $dir . "/" . $item;' + '\n'
    + '    if (is_dir($path)) scan_dir($path);' + '\n'
    + "    elseif (preg_match('/\.php$/', $item)) {" + '\n'
    + '      $content = file_get_contents($path);' + '\n'
    + '      if (' + '\n'
    + "        strpos($content, 'ini_set(\"opcache' ) !== false ||" + '\n'
    + "        strpos($content, \"ini_set('opcache\" ) !== false ||" + '\n'
    + "        strpos($content, 'opcache.enable' ) !== false ||" + '\n'
    + "        strpos($content, 'opcache.enable_cli' ) !== false ||" + '\n'
    + "        strpos($content, 'opcache_reset' ) !== false ||" + '\n'
    + "        strpos($content, 'opcache_get_status' ) !== false" + '\n'
    + '      ) {' + '\n'
    + '        $files[] = $path;' + '\n'
    + '      }' + '\n'
    + '    }' + '\n'
    + '  }' + '\n'
    + '}' + '\n'
    + '' + '\n'
    + 'foreach ($files as $f) {' + '\n'
    + '  echo "' + chr(10) + '=== FILE: $f' + chr(10) + '";' + '\n'
    + '  $c = file_get_contents($f);' + '\n'
    + '  $lines = explode("' + chr(10) + '", $c);' + '\n'
    + '  $relevant_lines = [];' + '\n'
    + '  foreach ($lines as $i => $ln) {' + '\n'
    + '    if (' + '\n'
    + "      strpos(\$ln, 'ini_set(\"opcache' ) !== false ||" + '\n'
    + "      strpos(\$ln, \"ini_set('opcache\" ) !== false ||" + '\n'
    + "      strpos(\$ln, 'opcache.enable' ) !== false ||" + '\n'
    + "      strpos(\$ln, 'opcache.enable_cli' ) !== false ||" + '\n'
    + "      strpos(\$ln, 'opcache_reset' ) !== false ||" + '\n'
    + "      strpos(\$ln, 'opcache_get_status' ) !== false" + '\n'
    + '    ) {' + '\n'
    + '      $relevant_lines[$i] = $ln;' + '\n'
    + '    }' + '\n'
    + '  }' + '\n'
    + '  foreach ($relevant_lines as $i => $ln) {' + '\n'
    + '    $start = max(0, $i-2);' + '\n'
    + '    $end = min(count($lines), $i+3);' + '\n'
    + '    for ($j = $start; $j < $end; $j++) {' + '\n'
    + '      $marker = ($j == $i) ? ">>>" : "   ";' + '\n'
    + '      echo "$marker L" . ($j+1) . ": " . $lines[$j] . "' + chr(10) + '";' + '\n'
    + '    }' + '\n'
    + '    echo "' + chr(10) + '";' + '\n'
    + '  }' + '\n'
    + '}' + '\n'
    + '' + '\n'
    + 'echo "' + chr(10) + 'Total files with opcache references: " . count($files) . "' + chr(10) + '";' + '\n'
    + 'echo "' + chr(10) + '=== DONE ===' + chr(10) + '";' + '\n'
)

print(f'PHP script size: {len(PHP)} chars')

# Записываем через SFTP
sftp = ssh.open_sftp()
with sftp.file('/tmp/find_opcache_enable.php', 'w') as f:
    f.write(PHP)
sftp.close()
print('Written to /tmp/find_opcache_enable.php')

print('\n=== Running ===')
stdin, stdout, stderr = ssh.exec_command('php /tmp/find_opcache_enable.php')
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')

print('--- OUTPUT ---')
print(out)

if err:
    print('\n--- STDERR ---')
    print(err[:1000])

ssh.close()
print('\nDONE')
