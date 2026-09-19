#!/usr/bin/env python3
"""Поиск ВСЕХ вызовов opcache_reset в сайте + проверка других возможных источников."""
import os
from dotenv import load_dotenv
import paramiko

load_dotenv('D:/NPA-ZS/.env')
cli = paramiko.SSHClient()
cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
cli.connect(
    hostname=os.getenv('MODX_SSH_HOST'),
    port=int(os.getenv('MODX_SSH_PORT', 22)),
    username=os.getenv('MODX_SSH_USERNAME'),
    password=os.getenv('MODX_SSH_PASSWORD'),
    timeout=10,
)
print('SSH connected')

BASE = '/var/www/u0220513/data/www/sevzakon.ru'

# 1. Все вызовы opcache_reset в коде сайта
print('=== 1. Все вызовы opcache_reset в коде ===')
cmd = 'grep -rn "opcache_reset" ' + BASE + ' --include="*.php" 2>/dev/null'
_, out, _ = cli.exec_command(cmd)
text = out.read().decode('utf-8', 'replace')
if text.strip():
    for line in text.split('\n'):
        if line.strip():
            print(line)
else:
    print('(ничего не найдено)')

# 2. Все вызовы opcache_get_status
print('\n=== 2. Все вызовы opcache_get_status ===')
cmd2 = 'grep -rn "opcache_get_status\|opcache_enable\|opcache_disable" ' + BASE + ' --include="*.php" 2>/dev/null'
_, out2, _ = cli.exec_command(cmd2)
text2 = out2.read().decode('utf-8', 'replace')
if text2.strip():
    for line in text2.split('\n'):
        if line.strip():
            print(line)
else:
    print('(ничего не найдено)')

# 3. Полный файл cache_sync вокруг opcache
print('\n=== 3. cache_sync.class.processor.php (строки 130-160) ===')
cs = BASE + '/manager/processors/cache_sync.class.processor.php'
cmd3 = 'sed -n "130,160p" ' + cs
_, out3, _ = cli.exec_command(cmd3)
print(out3.read().decode('utf-8', 'replace'))

# 4. Смотрим главный index.php
print('\n=== 4. Главный index.php (первые 30 строк) ===')
idx = BASE + '/index.php'
cmd4 = 'head -30 ' + idx
_, out4, _ = cli.exec_command(cmd4)
print(out4.read().decode('utf-8', 'replace'))

# 5. Проверяем конфигурацию PHP — opcache включен или нет
print('\n=== 5. Статус OPcache в PHP ===')
cmd5 = 'php -r "print_r(opcache_get_status());" 2>&1'
_, out5, err5 = cli.exec_command(cmd5)
print(out5.read().decode('utf-8', 'replace')[:1500])
if err5.read().decode('utf-8', 'replace').strip():
    print('STDERR:', err5.read().decode('utf-8', 'replace')[:500])

# 6. Проверяем php.ini на предмет opcache
print('\n=== 6. Настройки OPcache из php -i ===')
cmd6 = 'php -r "echo \"opcache.enable: \".ini_get(\"opcache.enable\").\"\\n\"; echo \"opcache.enable_cli: \".ini_get(\"opcache.enable_cli\").\"\\n\"; echo \"opcache.optimization_level: \".ini_get(\"opcache.optimization_level\").\"\\n\";" 2>&1'
_, out6, _ = cli.exec_command(cmd6)
print(out6.read().decode('utf-8', 'replace'))

# 7. Проверяем, есть ли opcache в loaded extensions
print('\n=== 7. Загруженные модули ===')
cmd7 = 'php -m 2>&1 | grep -i opcache'
_, out7, _ = cli.exec_command(cmd7)
print(out7.read().decode('utf-8', 'replace'))

# 8. Ищем любой код, который может вызывать opcache_reset через eval/include
print('\n=== 8. eval/system/exec с opcache ===')
cmd8 = 'grep -rn "opcache" ' + BASE + ' --include="*.php" 2>/dev/null | grep -i "eval\|system\|exec\|passthru" | head -10'
_, out8, _ = cli.exec_command(cmd8)
print((out8.read().decode('utf-8', 'replace').strip() or '(нет)'))[:500]

# 9. Смотрим, какие сниппеты/модули вызывают cache_sync
print('\n=== 9. Кто вызывает cache_sync ===')
cmd9 = 'grep -rn "cache_sync\|modx_cache" ' + BASE + ' --include="*.php" 2>/dev/null | grep -v "cache_sync.class.processor.php" | grep -v "cache_sync" | head -20'
_, out9, _ = cli.exec_command(cmd9)
print((out9.read().decode('utf-8', 'replace').strip() or '(нет)'))[:1000]

# 10. Смотрим custom плагины/модули
print('\n=== 10. Кастомные плагины в manager/ ===')
cmd10 = 'find ' + BASE + '/manager -name "*.php" -newer ' + BASE + '/index.php 2>/dev/null | head -20'
_, out10, _ = cli.exec_command(cmd10)
print((out10.read().decode('utf-8', 'replace').strip() or '(нет)'))[:1000]

cli.close()
print('\nDONE')
