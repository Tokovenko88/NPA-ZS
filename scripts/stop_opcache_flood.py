#!/usr/bin/env python3
"""Остановить флуд OPcache — закомментировать opcache_reset в cache_sync."""
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

# PHP-скрипт патча
PHP_PATCH = b'''<?php
$path = ''' + repr(PATH).encode() + b''';
if (!file_exists($path)) { die('NOT FOUND\\n'); }
$c = file_get_contents($path);
$o = $c;

// Заменяем @opcache_reset(); на // @opcache_reset();
$c = str_replace('@opcache_reset();', '// @opcache_reset();', $c);

if ($c !== $o) {
    if (file_put_contents($path, $c)) {
        echo 'PATCHED: opcache_reset закомментирован\\n';
    } else {
        echo 'SAVE FAILED\\n';
        exit(1);
#!/usr/bin/env python3
"""Полная защита от OPcache флуда: комментируем opcache_reset + диагностика."""
import os, re
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

SITE_PATH = '/var/www/u0220513/data/www/sevzakon.ru'
CS_PATH = SITE_PATH + '/manager/processors/cache_sync.class.processor.php'

# ============================================================
# ЧАСТЬ 1: Полностью отключаем opcache_reset в cache_sync
# ============================================================
print('\n=== ЧАСТЬ 1: Отключение opcache_reset ===')

PHP_DISABLE = b'''<?php
$path = ''' + repr(CS_PATH).encode() + b''';
if (!file_exists($path)) { die('NOT FOUND\\n'); }
$c = file_get_contents($path);
$o = $c;
$s = '@opcache_reset();';
$r = '// @opcache_reset();  // ЗАКОММЕНТИРОВАНО - временная защита от зацикливания';
$c = str_replace($s, $r, $c);
if ($c !== $o) {
    if (file_put_contents($path, $c)) {
        echo "PATCHED: $s -> $r\\n";
    } else {
        echo "SAVE FAILED\\n"; exit(1);
    }
} else {
    echo "NOT FOUND $s in file\\n";
}
echo "\\n=== Результат (строки с opcache_reset) ===\\n";
$l = explode("\\n", $c);
foreach ($l as $i => $ln) {
    if (strpos($ln, 'opcache_reset') !== false) {
        echo ($i + 1) . ': ' . $ln . "\\n";
    }
}
echo "DONE\\n";
'''

print('Запись PHP-скрипта на сервер...')
sftp = ssh.open_sftp()
with sftp.file('/tmp/disable_opcache.php', 'wb') as f:
    f.write(PHP_DISABLE)
sftp.close()
print('Записано /tmp/disable_opcache.php')

stdin, stdout, stderr = ssh.exec_command('php /tmp/disable_opcache.php 2>&1')
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
print(out)
if err:
    print('STDERR:', err[:300])

# ============================================================
# ЧАСТЬ 2: Поиск всех мест в ядре EVO с opcache_reset
# ============================================================
print('\n=== ЧАСТЬ 2: Поиск всех opcache_reset в ядре ===')

stdin, stdout, stderr = ssh.exec_command(
    f"grep -rn 'opcache_reset\\|opcache_get_status\\|opcache_enable' {SITE_PATH}/manager/ 2>/dev/null | head -50"
)
result = stdout.read().decode('utf-8', errors='replace')
print(result[:3000])

print('\n=== ЧАСТЬ 3: Проверка файла после патча ===')
stdin, stdout, stderr = ssh.exec_command(f"sed -n '135,155p' {CS_PATH}")
lines = stdout.read().decode('utf-8', errors='replace')
print(lines)

ssh.close()
print('\nDONE')

    }
} else {
    echo 'NO CHANGE (уже закомментирован?)\\n';
}

// Проверяем результат
$l = explode("\\n", $c);
foreach ($l as $i => $ln) {
    if (strpos($ln, 'opcache_reset') !== false) {
        echo ($i + 1) . ': ' . $ln . '\\n';
    }
}
echo "\\nDONE\\n";
'''

print('PHP патч подготовлен')
sftp = ssh.open_sftp()
with sftp.file('/tmp/patch_cs2.php', 'wb') as f:
    f.write(PHP_PATCH)
sftp.close()
print('Записан /tmp/patch_cs2.php')

print('\n=== Запуск патча ===')
stdin, stdout, stderr = ssh.exec_command('php /tmp/patch_cs2.php 2>&1')
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
print(out)
if err:
    print('STDERR:', err[:300])

print('\n=== Проверка результата ===')
stdin, stdout, stderr = ssh.exec_command(f"grep -n -B2 -A2 'opcache_reset' {PATH}")
result = stdout.read().decode('utf-8', errors='replace')
print(result)

ssh.close()
print('\nDONE')
