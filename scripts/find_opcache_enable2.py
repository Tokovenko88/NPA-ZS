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

# PHP-скрипт: ищет все файлы, которые делают ini_set('opcache...', ...) или opcache.enable...
PHP = (
    '<' + '?' + 'php' + chr(10)
    + '$root = "' + ROOT + '";' + chr(10)
    + 'echo "=== SEARCHING for opcache enable/disable attempts ===' + chr(10) + '";' + chr(10)
    + '$files = [];' + chr(10)
    + 'scan_dir($root);' + chr(10)
    + '' + chr(10)
    + 'function scan_dir($dir) {' + chr(10)
    + '  global $files;' + chr(10)
    + '  $items = scandir($dir);' + chr(10)
    + '  if ($items === false) return;' + chr(10)
    + '  foreach ($items as $item) {' + chr(10)
    + '    if ($item == "." || $item == "..") continue;' + chr(10)
    + '    $path = $dir . "/" . $item;' + chr(10)
    + '    if (is_dir($path)) scan_dir($path);' + chr(10)
    + '    elseif (preg_match(' + chr(39) + '/\.php$/' + chr(39) + ', $item)) {' + chr(10)
    + '      $content = file_get_contents($path);' + chr(10)
    + '      // Ищем попытки включить opcache через ini_set или similar' + chr(10)
    + '      if (' + chr(10)
    + '        strpos($content, \'ini_set("opcache\' ) !== false ||' + chr(10)
    + '        strpos($content, "ini_set(\'opcache" ) !== false ||' + chr(10)
    + "        strpos(\$content, 'opcache.enable' ) !== false ||" + chr(10)
    + "        strpos(\$content, 'opcache.enable_cli' ) !== false ||" + chr(10)
    + '        strpos($content, '"' + 'opcache_reset' + '"' + ' ) !== false ||' + chr(10)
    + '        strpos($content, '"' + 'opcache_get_status' + '"' + ' ) !== false' + chr(10)
    + '      ) {' + chr(10)
    + '        $files[] = $path;' + chr(10)
    + '      }' + chr(10)
    + '    }' + chr(10)
    + '  }' + chr(10)
    + '}' + chr(10)
    + '' + chr(10)
    + 'foreach ($files as $f) {' + chr(10)
    + '  echo "' + 'chr(10) + "=== FILE: $f' + 'chr(10) + '";' + chr(10)
    + '  $c = file_get_contents($f);' + chr(10)
    + '  $lines = explode("' + 'chr(10)' + '", $c);' + chr(10)
    + '  $relevant_lines = [];' + chr(10)
    + '  foreach ($lines as $i => $ln) {' + chr(10)
    + '    if (' + chr(10)
    + "      strpos(\$ln, 'ini_set(\"opcache' ) !== false ||" + chr(10)
    + '      strpos($ln, "ini_set(\'opcache" ) !== false ||' + chr(10)
    + "      strpos(\$ln, 'opcache.enable' ) !== false ||" + chr(10)
    + "      strpos(\$ln, 'opcache.enable_cli' ) !== false ||" + chr(10)
    + '      strpos($ln, '"opcache_reset" ) !== false ||' + chr(10)
    + '      strpos($ln, '"' + 'opcache_get_status' + '"' + ' ) !== false' + chr(10)
    + '    ) {' + chr(10)
    + '      $relevant_lines[$i] = $ln;' + chr(10)
    + '    }' + chr(10)
    + '  }' + chr(10)
    + '  foreach ($relevant_lines as $i => $ln) {' + chr(10)
    + '    $start = max(0, $i-2);' + chr(10)
    + '    $end = min(count($lines), $i+3);' + chr(10)
    + '    for ($j = $start; $j < $end; $j++) {' + chr(10)
    + '      $marker = ($j == $i) ? ">>>" : "   ";' + chr(10)
    + '      echo "$marker L" . ($j+1) . ": " . $lines[$j] . "' + 'chr(10);' + chr(10)
    + '    }' + chr(10)
    + '    echo "' + 'chr(10);' + chr(10)
    + '  }' + chr(10)
    + '}' + chr(10)
    + '' + chr(10)
    + 'echo "' + 'chr(10) + "Total files with opcache references: " . count($files) . "' + 'chr(10);' + chr(10)
    + 'echo "' + 'chr(10) + "=== DONE ===' + 'chr(10) + '";' + chr(10)
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
