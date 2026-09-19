#!/usr/bin/env python3
"""Поиск причины OPcache warning и проверка правильности URL."""
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

SITE = '/var/www/u0220513/data/www/sevzakon.ru'
DOMAIN = 'sevzakon.ru'

# 1. Проверить различные варианты URL
print('\n=== Проверка вариантов URL ===')
urls = [
    f'https://{DOMAIN}/view/laws/proekty_postanovlenij/2026/pr_post_12_203_ot_18_09_2026/tekst-proekta-postanovleniya132/',
    f'https://{DOMAIN}/view/laws/proekty_postanovlenij/2026/pr_post_12_203_ot_18_09_2026/',
    f'https://{DOMAIN}/view/laws/proekty_postanovlenij/2026/',
]
for url in urls:
    stdin, stdout, stderr = ssh.exec_command(f'curl -s -o /dev/null -w "%{{http_code}}" -m 15 -k -H "User-Agent: Mozilla/5.0" {url}')
    code = stdout.read().decode(errors='replace').strip()
    print(f'{code} - {url}')

# 2. Найти ВСЕ вызовы opcache_reset в коде сайта
print('\n=== Все вызовы opcache_reset в коде сайта ===')
stdin, stdout, stderr = ssh.exec_command(
    f"grep -rn 'opcache_reset' {SITE}/ "
    f"--include='*.php' 2>/dev/null | "
    f"grep -v 'function_exists' | "
    f"grep -v '//' | "
    f"grep -v 'test_opcache'"
)
content = stdout.read().decode(errors='replace')
print(content[:3000] if content else 'Не найдено проблемных вызовов')
print(f'Всего строк: {len(content.splitlines())}')

# 3. Проверить конкретные файлы antibot
print('\n=== Antibot файлы с opcache_reset ===')
stdin, stdout, stderr = ssh.exec_command(
    f"grep -rn 'opcache_reset' {SITE}/antibot/ "
    f"--include='*.php' 2>/dev/null"
)
content = stdout.read().decode(errors='replace')
for line in content.splitlines():
    if line.strip():
        print(line)

# 4. Проверить .user.ini - можно ли добавить opcache настройки
print('\n=== Текущий .user.ini ===')
stdin, stdout, stderr = ssh.exec_command(f'cat {SITE}/.user.ini 2>/dev/null || echo "не найден"')
print(stdout.read().decode(errors='replace')[:500])

# 5. Проверить, где именно генерируется предупреждение
print('\n=== Поиск в логах WHERE происходит opcache_warning ===')
stdin, stdout, stderr = ssh.exec_command('tail -100 /tmp/php_err.log 2>/dev/null | grep -i "opcache" | head -20')
content = stdout.read().decode(errors='replace')
print(content[:2000] if content else 'Нет записей')

# 6. Проверить, работает ли OPcache в FPM (через правильный скрипт)
print('\n=== Создаём правильный скрипт проверки OPcache ===')
PHP_TEST = '''<?php
header("Content-Type: text/plain; charset=utf-8");
echo "=== OPcache in Web Context ===\\n";
$status = opcache_get_status();
if ($status === false) {
    echo "OPcache NOT AVAILABLE\\n";
    echo "Reason: opcache.enable=0 or extension not loaded in FPM\\n";
} else {
    echo "OPcache AVAILABLE\\n";
    if (isset($status["opcache_enabled"])) {
        echo "opcache_enabled: " . ($status["opcache_enabled"] ? "ON" : "OFF") . "\\n";
    }
    if (isset($status["memory_consumption"]["used_memory"])) {
        echo "Used memory: " . round($status["memory_consumption"]["used_memory"]/1048576, 2) . " MB\\n";
    }
    if (isset($status["memory_consumption"]["max_memory"])) {
        echo "Max memory: " . round($status["memory_consumption"]["max_memory"]/1048576, 2) . " MB\\n";
    }
    if (isset($status["opcache_statistics"]["num_cached_scripts"])) {
        echo "Cached scripts: " . $status["opcache_statistics"]["num_cached_scripts"] . "\\n";
    }
}
echo "\\n=== INI Settings ===\\n";
echo "opcache.enable: " . ini_get("opcache.enable") . "\\n";
echo "opcache.enable_cli: " . ini_get("opcache.enable_cli") . "\\n";
echo "Extension loaded: " . (extension_loaded("Zend OPcache") ? "YES" : "NO") . "\\n";
echo "SAPI: " . php_sapi_name() . "\\n";
echo "\\n=== .user.ini contents ===\\n";
$userIni = __DIR__ . "/.user.ini";
if (file_exists($userIni)) {
    echo file_get_contents($userIni);
} else {
    echo "Not found\\n";
}
'''

with ssh.open_sftp() as sftp:
    sftp.putfo(
        __import__('io').BytesIO(PHP_TEST.encode()),
        f'{SITE}/test_opcache.php'
    )
print('Скрипт создан')

# Проверить через curl
stdin, stdout, stderr = ssh.exec_command(f'curl -s -m 15 -k https://{DOMAIN}/test_opcache.php')
out = stdout.read().decode(errors='replace')
err = stderr.read().decode(errors='replace')
print('Ответ сервера:')
print(out[:2000])
if err.strip():
    print('stderr:', err[:300])

# Удалить тестовый скрипт
ssh.exec_command(f'rm -f {SITE}/test_opcache.php')

ssh.close()
print('\nDONE')
