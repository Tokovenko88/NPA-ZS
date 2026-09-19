#!/usr/bin/env python3
"""Поиск ВСЕХ вызовов opcache_reset в ядре MODX и применение патча."""
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

BASE = '/var/www/u0220513/data/www/sevzakon.ru'

# Поиск всех вызовов opcache_reset через PHP-скрипт
PHP = (
    b'<?php' + b'\n'
    + b'$base = ' + repr(BASE).encode() + b';' + b'\n'
    + b'$files = [];' + b'\n'
    + b'recursive:for($d = new DirectoryIterator($base); $d->valid(); $d->next()) {' + b'\n'
    + b'  if ($d->isDot()) continue;' + b'\n'
    + b'  $f = $d->getPathname() . "/" . $d->getFilename();' + b'\n'
    + b'  if ($d->isDir()) { $d = new DirectoryIterator($f); goto recursive; }' + b'\n'
    + b'  if (!preg_match("/\.php$/", $d->getFilename())) continue;' + b'\n'
    + b'  $c = file_get_contents($f);' + b'\n'
    + b'  if (strpos($c, "opcache_reset") !== false) $files[$f] = $c;' + b'\n'
    + b'}' + b'\n'
    + b'echo "=== Найдено файлов с opcache_reset: " . count($files) . " ===\n\n";' + b'\n'
    + b'foreach($files as $f => $c) {' + b'\n'
    + b'  echo "--- $f\n";' + b'\n'
    + b'  $lines = explode("\n", $c);' + b'\n'
    + b'  foreach($lines as $i=>$ln) {' + b'\n'
    + b'    if (strpos($ln, "opcache_reset") !== false) {' + b'\n'
    + b'      echo "  line " . ($i+1) . ": $ln\n";' + b'\n'
    + b'      if (isset($lines[$i-1])) echo "  prev: " . $lines[$i-1] . "\n";' + b'\n'
    + b'      if (isset($lines[$i+1])) echo "  next: " . $lines[$i+1] . "\n";' + b'\n'
    + b'    }' + b'\n'
    + b'  }' + b'\n'
    + b'  echo "\n";' + b'\n'
    + b'}' + b'\n'
)

print('PHP script size:', len(PHP))
sftp = ssh.open_sftp()
with sftp.file('/tmp/find_opcache.php', 'wb') as f:
    f.write(PHP)
sftp.close()
print('Written /tmp/find_opcache.php')

stdin, stdout, stderr = ssh.exec_command('php /tmp/find_opcache.php 2>&1')
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
print('\n=== Результат поиска ===')
print(out)
if err:
    print('ERRORS:', err[:300])

# Теперь патчем все найденные файлы
print('\n=== Патч ===')
PHP2 = (
    b'<?php' + b'\n'
    + b'$base = ' + repr(BASE).encode() + b';' + b'\n'
    + b'$patched = 0;' + b'\n'
    + b'$errors = 0;' + b'\n'
    + b'recursive:for($d = new DirectoryIterator($base); $d->valid(); $d->next()) {' + b'\n'
    + b'  if ($d->isDot()) continue;' + b'\n'
    + b'  $f = $d->getPathname() . "/" . $d->getFilename();' + b'\n'
    + b'  if ($d->isDir()) { $d = new DirectoryIterator($f); goto recursive; }' + b'\n'
    + b'  if (!preg_match("/\.php$/", $d->getFilename())) continue;' + b'\n'
    + b'  $c = file_get_contents($f);' + b'\n'
    + b'  if (strpos($c, "opcache_reset") === false) continue;' + b'\n'
    + b'  echo "Проверка: $f\n";' + b'\n'
    + b'  $old = $c;' + b'\n'
    + b'  $c = preg_replace(' + b"'/" + b'\\'' + b'opcache_reset\\()/' + b'\\'' + b', b"@opcache_reset()", $c);' + b'\n'
    + b'  $c = preg_replace(' + b"'/" + b'\\'' + b'(!empty\\(\\$\opcache\\[\'opcache_enabled\'\]\\) && ini_get\(\'opcache.enable\'\)\) \{[\n\s]*@opcache_reset\(\)\;/' + b'\\'' + b', b"if (!empty(\$opcache['opcache_enabled']) && ini_get('opcache.enable') && function_exists('opcache_reset')) {\n                @opcache_reset();", $c);' + b'\n'
    + b'  if ($c !== $old) {' + b'\n'
    + b'    if (file_put_contents($f, $c)) { echo "  ПОЧИНЕНО\n"; $patched++; }' + b'\n'
    + b'    else { echo "  ОШИБКА записи\n"; $errors++; }' + b'\n'
    + b'  } else {' + b'\n'
    + b'    echo "  УЖЕ ПОЧИНЕНО (или не требует)\n";' + b'\n'
    + b'  }' + b'\n'
    + b'}' + b'\n'
    + b'echo "\nИТОГ: исправлено=$patched, ошибок=$errors\n";' + b'\n'
)

print('PHP2 script size:', len(PHP2))
with sftp.file('/tmp/patch_all_opcache.php', 'wb') as f:
    f.write(PHP2)
sftp.close()

stdin, stdout, stderr = ssh.exec_command('php /tmp/patch_all_opcache.php 2>&1')
out2 = stdout.read().decode('utf-8', errors='replace')
err2 = stderr.read().decode('utf-8', errors='replace')
print(out2)
if err2:
    print('ERRORS:', err2[:500])

# Финальная проверка
print('\n=== Финальная проверка (после патча) ===')
stdin, stdout, stderr = ssh.exec_command('php /tmp/find_opcache.php 2>&1')
print(stdout.read().decode('utf-8', errors='replace'))

ssh.close()
print('\nDONE')
