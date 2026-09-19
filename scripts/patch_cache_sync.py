#!/usr/bin/env python3
"""Патч cache_sync.class.processor.php — добавление проверки function_exists('opcache_reset')."""
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

SITE_DIR = '/var/www/u0220513/data'
CACHE_SYNC_PATH = f'{SITE_DIR}/www/sevzakon.ru/manager/processors/cache_sync.class.processor.php'

# 1. Создаём PHP-скрипт патча
print('\n=== Создание PHP-скрипта патча ===')
patch_php = """
<?php
/**
 * Патч cache_sync.class.processor.php
 * Добавляет проверку function_exists('opcache_reset') перед вызовом
 */

$path = '/var/www/u0220513/data/www/sevzakon.ru/manager/processors/cache_sync.class.processor.php';

if (!file_exists($path)) {
    die("Файл не найден: $path\\n");
}

echo "Файл найден: $path\\n";

// Читаем файл
$content = file_get_contents($path);
$orig = $content;

// Ищем проблемную строку
$search = "if (!empty(\\$opcache['opcache_enabled']) && ini_get('opcache.enable')) {\n                @opcache_reset();";

// Заменяем на правильный код с проверкой function_exists
$replace = "if (!empty(\\$opcache['opcache_enabled']) && ini_get('opcache.enable') && function_exists('opcache_reset')) {\n                @opcache_reset();";

if (strpos($content, $search) !== false) {
    $content = str_replace($search, $replace, $content);
    echo "Найдено проблемное место - применяем патч\\n";
} else {
    // Проверяем, есть ли уже добавленная проверка
    if (strpos($content, "function_exists('opcache_reset')") !== false) {
        echo "Проверка function_exists уже есть - файл уже пропатчен\\n";
        echo "Текущее состояние:\\n";
        // Показываем строки вокруг opcache_reset
        $lines = explode("\\n", $content);
        foreach ($lines as $i => $line) {
            if (strpos($line, 'opcache_reset') !== false) {
                echo "  Линейка {$i}: {$line}\\n";
                if (isset($lines[$i-1])) echo "  Линейка {$i-1}: {$lines[$i-1]}\\n";
                if (isset($lines[$i+1])) echo "  Линейка {$i+1}: {$lines[$i+1]}\\n";
            }
        }
        $content = $orig; // не меняем
    } else {
        echo "Ожидаемая строка не найдена - возможно, файл уже изменён\\n";
        echo "Ищем другие варианты...\\n";
        // Ищем более общий паттерн
        $search2 = '@opcache_reset()';
        if (strpos($content, $search2) !== false) {
            // Находим строки вокруг и проверяем, есть ли там function_exists
            $lines = explode("\\n", $content);
            foreach ($lines as $i => $line) {
                if (strpos($line, 'opcache_reset') !== false) {
                    echo "  Линейка {$i}: {$line}\\n";
                    if (isset($lines[$i-1])) echo "  Линейка {$i-1}: {$lines[$i-1]}\\n";
                    if (isset($lines[$i+1])) echo "  Линейка {$i+1}: {$lines[$i+1]}\\n";
                }
            }
        }
        $content = $orig;
    }
}

// Сохраняем файл
if ($content !== $orig) {
    if (file_put_contents($path, $content)) {
        echo "Файл успешно обновлён\\n";
    } else {
        echo "ОШИБКА: Не удалось сохранить файл\\n";
        exit(1);
    }
} else {
    echo "Нет изменений\\n";
}

echo "\\n=== Готово ===\\n";
"""

# Записываем PHP-скрипт на сервер через SFTP
print('Запись PHP-скрипта на сервер...')
sftp = ssh.open_sftp()
with sftp.file('/tmp/patch_cache_sync.php', 'w') as f:
    f.write(patch_php)
sftp.close()
print('PHP-скрипт записан')

# 2. Запускаем патч
print('\n=== Запуск патча ===')
stdin, stdout, stderr = ssh.exec_command('php /tmp/patch_cache_sync.php')
output = stdout.read().decode('utf-8', errors='replace')
print(output)
err = stderr.read().decode('utf-8', errors='replace')
if err:
    print('STDERR:', err[:500])

# 3. Проверяем результат
print('\n=== Проверка результата ===')
stdin, stdout, stderr = ssh.exec_command(
    f"grep -n -A3 -B1 'opcache_reset' {CACHE_SYNC_PATH}"
)
result = stdout.read().decode('utf-8', errors='replace')
print(result)
err = stderr.read().decode('utf-8', errors='replace')
if err:
    print('STDERR:', err[:200])

ssh.close()
print('\nDONE')
