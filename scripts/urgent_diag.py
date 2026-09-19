#!/usr/bin/env python3
import os
from dotenv import load_dotenv
import paramiko

load_dotenv('D:/NPA-ZS/.env')

cli = paramiko.SSHClient()
cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
cli.connect(
    hostname=os.getenv('MODX_SSH_HOST'),
    port=int(os.getenv('MODX_SSH_PORT', '22')),
    username=os.getenv('MODX_SSH_USERNAME'),
    password=os.getenv('MODX_SSH_PASSWORD'),
    timeout=15,
)

print('SSH connected')

# PHP-скрипт для диагностики — пишем в файл на сервере через SFTP
php_code = r'''<?php
header('Content-Type: text/plain; charset=utf-8');

echo "=== OPcache статус ===\n";
echo "opcache.enable: " . ini_get('opcache.enable') . "\n";
echo "opcache.enable_cli: " . ini_get('opcache.enable_cli') . "\n";
echo "function_exists('opcache_reset'): " . (function_exists('opcache_reset') ? 'YES' : 'NO') . "\n";
echo "Server API: " . php_sapi_name() . "\n";

echo "\n=== Все файлы с opcache_reset() на сайте ===\n";
$site = '/var/www/u0220513/data/www/sevzakon.ru';
$files = [];
$iterator = new RecursiveIteratorIterator(
    new RecursiveDirectoryIterator($site, RecursiveDirectoryIterator::SKIP_DOTS),
    RecursiveIteratorIterator::SELF_FIRST
);
foreach ($iterator as $file) {
    if ($file->isFile() && $file->getExtension() === 'php') {
        $content = file_get_contents($file->getPathname());
        if (strpos($content, 'opcache_reset') !== false) {
            $files[] = $file->getPathname();
        }
    }
}

foreach ($files as $f) {
    echo "ФАЙЛ: $f\n";
    $lines = file($f);
    foreach ($lines as $i => $line) {
        if (strpos($line, 'opcache_reset') !== false) {
            $prefix = (strpos($line, 'function_exists') !== false) ? '  [ЗАЩИЩЁН] ' : '  [!!! НЕЗАЩИЩЁН !!!] ';
            echo $prefix . "строка " . ($i+1) . ": " . trim($line) . "\n";
        }
    }
    echo "\n";
}

echo "=== КОНФИГ PHP-FPM ===\n";
$poolDir = '/etc/php/*/fpm/pool.d/';
foreach (glob($poolDir . '*.conf') as $conf) {
    echo "ФАЙЛ: $conf\n";
    $content = file_get_contents($conf);
    if (strpos($content, 'opcache') !== false) {
        echo "  ИМЕЕТ настройки opcache\n";
    } else {
        echo "  БЕЗ настроек opcache\n";
    }
}

echo "\n=== PHP.INI ===\n";
foreach (glob('/etc/php/*/fpm/php.ini') as $ini) {
    echo "ФАЙЛ: $ini\n";
    $content = file_get_contents($ini);
    if (strpos($content, 'opcache') !== false) {
        echo "  ИМЕЕТ настройки opcache\n";
        foreach (explode("\n", $content) as $line) {
            if (stripos($line, 'opcache') !== false) {
                echo "    $line\n";
            }
        }
    } else {
        echo "  БЕЗ настроек opcache\n";
    }
}

echo "\n=== .user.ini ===\n";
$userIni = '/var/www/u0220513/data/www/sevzakon.ru/.user.ini';
if (file_exists($userIni)) {
    echo "ФАЙЛ: $userIni (СУЩЕСТВУЕТ)\n";
    echo file_get_contents($userIni);
} else {
    echo "ФАЙЛ: $userIni (ОТСУТСТВУЕТ)\n";
}

echo "\n=== TEST: вызов opcache_reset() сейчас ===\n";
if (function_exists('opcache_reset')) {
    $enable = ini_get('opcache.enable');
    echo "opcache.enable = $enable\n";
    if ($enable) {
        $result = @opcache_reset();
        echo "opcache_reset() = " . var_export($result, true) . " (OK)\n";
    } else {
        echo "OPcache ОТКЛЮЧЁН — вызов opcache_reset() вызовет FATAL ошибку!\n";
        try {
            @opcache_reset();
            echo "РЕЗУЛЬТАТ: нет ошибки (неожиданно)\n";
        } catch (Error $e) {
            echo "РЕЗУЛЬТАТ: " . $e->getMessage() . "\n";
        }
    }
} else {
    echo "function_exists('opcache_reset') = FALSE\n";
}

echo "\nDONE\n";
'''

print('Writing diagnostic script to server...')
sftp = cli.open_sftp()
with sftp.file('/tmp/urgent_diag.php', 'w') as f:
    f.write(php_code)
sftp.close()
print('Written')

print()
print('=== Запуск диагностики ===')
stdin, stdout, stderr = cli.exec_command('php /tmp/urgent_diag.php 2>&1')
out = stdout.read().decode('utf-8', 'replace')
err = stderr.read().decode('utf-8', 'replace')
print(out)
if err.strip():
    print('STDERR:', err[:500])

print()
print('=== Тест страницы ===')
stdin, stdout, stderr = cli.exec_command(
    'curl -s -m 20 -k -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" '
    '"https://sevzakon.ru/view/laws/proekty_postanovlenij/2026/pr_post_12_203_ot_18_09_2026/tekst-proekta-postanovleniya132/" 2>&1 | head -20'
)
page = stdout.read().decode('utf-8', 'replace')
page_err = stderr.read().decode('utf-8', 'replace')
print(page)
if page_err.strip():
    print('CURL STDERR:', page_err[:200])

print()
print('=== Проверка, есть ли Evo Parse Error в выводе страницы ===')
if 'Evo Parse Error' in page or 'Zend OPcache' in page:
    print('!!! КРИТИЧЕСКАЯ ОШИБКА ВЫВОДИТСЯ НА СТРАНИЦЕ !!!')
else:
    print('Страница без Evo Parse Error в выводе')

cli.close()
print('DONE')
