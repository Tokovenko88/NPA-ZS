#!/usr/bin/env python3
"""
Поиск всех вызовов opcache_reset в ядре MODX
и применение патча function_exists.
"""
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


def remote_exec(cmd, t=120):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=t)
    return stdout.read().decode('utf-8', 'replace'), stderr.read().decode('utf-8', 'replace')


def write_php(path, code):
    with ssh.open_sftp() as sftp:
        with sftp.file(path, 'w') as f:
            f.write(code)


# ---------- PHP: поиск ----------
FIND_PHP = r"""<?php
$base = '/var/www/u0220513/data/www/sevzakon.ru';
$out = [];
function scan($d, &$out) {
    while ($f = readdir($d)) {
        if ($f == '.' || $f == '..') continue;
        $p = $d . '/' . $f;
        if (is_dir($p)) { $sub = opendir($p); scan($sub, $out); closedir($sub); }
        elseif (preg_match('/\.php$/', $f)) {
            $c = @file_get_contents($p);
            if ($c !== false && strpos($c, 'opcache_reset') !== false) {
                $out[$p] = $c;
            }
        }
    }
    closedir($d);
}
$d = opendir($base);
scan($d, $out);
closedir($d);
echo "Found " . count($out) . " files with opcache_reset\n\n";
foreach ($out as $f => $c) {
    echo "--- $f\n";
    $lines = explode("\n", $c);
    foreach ($lines as $i => $ln) {
        if (strpos($ln, 'opcache_reset') !== false) {
            echo "  line " . ($i+1) . ": " . $ln . "\n";
            if (isset($lines[$i-1])) echo "  prev: " . $lines[$i-1] . "\n";
            if (isset($lines[$i+1])) echo "  next: " . $lines[$i+1] . "\n";
        }
    }
    echo "\n";
}
"""

# ---------- PHP: патч ----------
PATCH_PHP = r"""<?php
$base = '/var/www/u0220513/data/www/sevzakon.ru';
$done = 0; $err = 0;
function patch_file($f) {
    global $done, $err;
    $c = @file_get_contents($f);
    if ($c === false) { echo "  READ ERR: $f\n"; $err++; return; }
    $orig = $c;
    // 1. opcache_reset() -> @opcache_reset()
    $c = str_replace('opcache_reset()', '@opcache_reset()', $c);
    // 2. Добавляем проверку function_exists
    // ищем: if (cond) { \n spaces @opcache_reset();
    $c = preg_replace(
        '/\(\s*!empty\(\$opcache\['\''opcache_enabled'\''\]\)\s*&&\s*ini_get\(\'\''opcache\.enable'\''\) \)\s*\{\s*\n\s*@opcache_reset\(\);/',
        "if (!empty(\$opcache['opcache_enabled']) && ini_get('opcache.enable') && function_exists('opcache_reset')) {\n                @opcache_reset();",
        $c
    );
    // если preg_match не сработал — пробуем простую замену
    if ($c === $orig) {
        // Альтернативный паттерн: может быть без @
        $c = preg_replace(
            '/\(\s*!empty\(\$opcache\['\''opcache_enabled'\''\]\)\s*&&\s*ini_get\(\'\''opcache\.enable'\''\) \)\s*\{\s*\n\s*opcache_reset\(\);/',
            "if (!empty(\$opcache['opcache_enabled']) && ini_get('opcache.enable') && function_exists('opcache_reset')) {\n                @opcache_reset();",
            $c
        );
    }
    if ($c !== $orig) {
        if (@file_put_contents($f, $c)) { echo "  FIXED: $f\n"; $done++; }
        else { echo "  WRITE ERR: $f\n"; $err++; }
    } else {
        echo "  already ok: $f\n";
    }
}
function scan_and_patch($dir) {
    $d = opendir($dir);
    while ($f = readdir($d)) {
        if ($f == '.' || $f == '..') continue;
        $p = $dir . '/' . $f;
        if (is_dir($p)) { $sub = opendir($p); scan_and_patch($p); closedir($sub); }
        elseif (preg_match('/\.php$/', $f)) {
            $c = @file_get_contents($p);
            if ($c !== false && strpos($c, 'opcache_reset') !== false) {
                patch_file($p);
            }
        }
    }
    closedir($d);
}
scan_and_patch($base);
echo "\nRESULT: fixed=$done errors=$err\n";
"""

# ---------- Шаг 1: поиск ----------
print('\n=== Поиск файлов с opcache_reset ===')
write_php('/tmp/find_o.php', FIND_PHP)
out, err = remote_exec('php /tmp/find_o.php 2>&1')
print(out)
if err:
    print('ERR:', err[:300])

# ---------- Шаг 2: патч ----------
print('\n=== Применение патча ===')
write_php('/tmp/patch_o.php', PATCH_PHP)
out, err = remote_exec('php /tmp/patch_o.php 2>&1')
print(out)
if err:
    print('ERR:', err[:300])

# ---------- Шаг 3: проверка после патча ----------
print('\n=== Повторный поиск (после патча) ===')
out, err = remote_exec('php /tmp/find_o.php 2>&1')
print(out)



# ---------- Переписываем PHP-скрипты правильно ----------
# Проблема: $d (resource) передаётся в функцию, но внутри функции используется readdir($d)
# где $d — это КОПИЯ локальной переменной, которая может быть закрыта.
# Решение: передаём full path, а внутри функции открываем/закрываем handle.


FIND_PHP_V2 = """<?php
$base = '/var/www/u0220513/data/www/sevzakon.ru';
$out = [];
function scan($dir_path, &$out) {
    $handle = opendir($dir_path);
    if ($handle === false) return;
    while (($f = readdir($handle)) !== false) {
        if ($f == '.' || $f == '..') continue;
        $p = $dir_path . '/' . $f;
        if (is_dir($p)) {
            scan($p, $out);
        } elseif (preg_match('/\\\\.php$/', $f)) {
            $c = @file_get_contents($p);
            if ($c !== false && strpos($c, 'opcache_reset') !== false) {
                $out[$p] = $c;
            }
        }
    }
    closedir($handle);
}
scan($base, $out);
echo "Found " . count($out) . " files with opcache_reset\\n\\n";
foreach ($out as $f => $c) {
    echo "--- $f\\n";
    $lines = explode("\\n", $c);
    foreach ($lines as $i => $ln) {
        if (strpos($ln, 'opcache_reset') !== false) {
            echo "  line " . ($i+1) . ": " . $ln . "\\n";
            if (isset($lines[$i-1])) echo "  prev: " . $lines[$i-1] . "\\n";
            if (isset($lines[$i+1])) echo "  next: " . $lines[$i+1] . "\\n";
        }
    }
    echo "\\n";
}
"""

# ВАЖНО: в PHP-строках выше:
# - '\\\\.php$' → в Python r-string это \\\\.php$ → в PHP это \\.php$ → regex: \.php$
#   (backslash-dot в regex = буквальная точка)
# - "\\n" → в Python это \n → в PHP это буквальный \n → PHP explode("\n") работает
# - 'opcache_reset' → буквальная строка в PHP

# Проверим, что записанное PHP корректно
print("FIND_PHP_V2 length:", len(FIND_PHP_V2))

# Пишем улучшенную версию
with ssh.open_sftp() as sftp:
    with sftp.file('/tmp/find_o_v2.php', 'w') as f:
        f.write(FIND_PHP_V2)

out, err = remote_exec('php /tmp/find_o_v2.php 2>&1')
print("=== Поиск (v2) ===")
print(out)
if err:
    print("ERR:", err[:300])


# ---------- PHP: патч (упрощённый и надёжный вариант) ----------
# Вместо сложного regex — несколько простых str_replace и проверка
PATCH_PHP_V2 = """<?php
$base = '/var/www/u0220513/data/www/sevzakon.ru';
$done = 0; $err = 0;
function patch_file($f) {
    global $done, $err;
    $c = @file_get_contents($f);
    if ($c === false) { echo "  READ ERR: $f\\n"; $err++; return; }
    $orig = $c;
    // 1. opcache_reset() -> @opcache_reset()
    $c = str_replace('opcache_reset()', '@opcache_reset()', $c);
    // 2. Оборачиваем вызов в проверку function_exists
    // ищем: $opcache = opcache_get_status(); ... $opcache['opcache_enabled'] ...
    //        if (!empty($opcache['opcache_enabled']) && ini_get('opcache.enable')) {
    //            @opcache_reset();
    //        }
    // заменяем на:
    //        if (!empty($opcache['opcache_enabled']) && ini_get('opcache.enable') && function_exists('opcache_reset')) {
    //            @opcache_reset();
    //        }
    $old_block = "if (!empty($opcache['opcache_enabled']) && ini_get('opcache.enable')) {\n                @opcache_reset();";
    $new_block = "if (!empty($opcache['opcache_enabled']) && ini_get('opcache.enable') && function_exists('opcache_reset')) {\n                @opcache_reset();";
    $c = str_replace($old_block, $new_block, $c);
    if ($c !== $orig) {
        if (@file_put_contents($f, $c)) { echo "  FIXED: $f\n"; $done++; }
        else { echo "  WRITE ERR: $f\n"; $err++; }
    } else {
        echo "  already ok: $f\n";
    }
}
function scan_and_patch($dir_path) {
    $handle = opendir($dir_path);
    if ($handle === false) return;
    while (($f = readdir($handle)) !== false) {
        if ($f == '.' || $f == '..') continue;
        $p = $dir_path . '/' . $f;
        if (is_dir($p)) {
            scan_and_patch($p);
        } elseif (preg_match('/\\\\.php$/', $f)) {
            $c = @file_get_contents($p);
            if ($c !== false && strpos($c, 'opcache_reset') !== false) {
                patch_file($p);
            }
        }
    }
    closedir($handle);
}
scan_and_patch($base);
echo "\\nRESULT: fixed=$done errors=$err\\n";
"""

print("\nPATCH_PHP_V2 length:", len(PATCH_PHP_V2))

with ssh.open_sftp() as sftp:
    with sftp.file('/tmp/patch_o_v2.php', 'w') as f:
        f.write(PATCH_PHP_V2)

print("\n=== Применение патча (v2) ===")
out, err = remote_exec('php /tmp/patch_o_v2.php 2>&1')
print(out)
if err:
    print("ERR:", err[:300])

# ---------- Шаг 3: проверка после патча ----------
print("\n=== Повторный поиск (после патча) ===")
out, err = remote_exec('php /tmp/find_o_v2.php 2>&1')
print(out)

ssh.close()
print("\nDONE")

ssh.close()
print('\nDONE')
