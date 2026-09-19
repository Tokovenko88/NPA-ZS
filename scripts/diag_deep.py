#!/usr/bin/env python3
"""Глубокая диагностика OPcache и PHP-FPM на сервере."""
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

# 1. Найти правильный PHP-FPM pool.d
print('\n=== Ищем PHP-FPM pool.d ===')
_, o, _ = ssh.exec_command(
    'ls -la /etc/php-fpm.d/ 2>/dev/null || '
    'ls -la /etc/php/*/fpm/pool.d/ 2>/dev/null || '
    'ls -la /etc/php-fpm/ 2>/dev/null || '
    'find /etc -name "pool.d" -type d 2>/dev/null || '
    'echo "pool.d не найден"'
)
print(o.read().decode(errors='replace')[:1000])

# 2. Найти главный php.ini и opcache.ini
print('\n=== Ищем opcache.ini / opcache настройки ===')
_, o, _ = ssh.exec_command(
    'find /etc -name "*opcache*" 2>/dev/null | head -10 || '
    'echo "opcache файлы не найдены"'
)
print(o.read().decode(errors='replace')[:500])

# 3. Проверить, работает ли PHP-FPM
print('\n=== PHP-FPM процессы ===')
_, o, _ = ssh.exec_command('ps aux | grep -E "php-fpm|php.*fpm" | grep -v grep | head -10 || echo "нет процессов"')
print(o.read().decode(errors='replace')[:800])

# 4. Проверить nginx конфиг для этого домена
print('\n=== Nginx конфиг для домена ===')
_, o, _ = ssh.exec_command(
    'grep -rn "sevzakon.ru" /etc/nginx/ 2>/dev/null | head -20 || '
    'grep -rn "sevzakon" /etc/nginx/ 2>/dev/null | head -20 || '
    'echo "nginx конфиг не найден"'
)
print(o.read().decode(errors='replace')[:1000])

# 5. Проверить, какой SAPI используется (apache module или FPM)
print('\n=== PHP SAPI (через CLI) ===')
_, o, _ = ssh.exec_command('php -r "echo php_sapi_name() . \"\\n\";"')
print(o.read().decode(errors='replace')[:200])

# 6. Проверить opcache в CLI
print('\n=== OPcache статус в CLI ===')
_, o, _ = ssh.exec_command(
    'php -r '
    "'$s=opcache_get_status(); "
    "if($s===false){echo \"CLI OPcache NOT AVAILABLE\\n\";}"
    "else{echo \"CLI OPcache AVAILABLE\\n\"; "
    "if(isset($s['opcache_enabled']))echo \"enabled: \".($s['opcache_enabled']?'ON':'OFF').\"\\n\"; "
    "if(isset($s['memory_consumption']['used_memory']))echo \"used: \".round($s['memory_consumption']['used_memory']/1048576,2).\"MB\\n\";}"
)
print(o.read().decode(errors='replace')[:400])

# 7. Проверить созданный скрипт
print('\n=== Файл test_opcache_web.php ===')
_, o, _ = ssh.exec_command(f'ls -la {SITE}/test_opcache_web.php 2>/dev/null && head -5 {SITE}/test_opcache_web.php')
print(o.read().decode(errors='replace')[:400])

# 8. Проверить через домен (а не localhost)
print('\n=== Проверка через домен (https) ===')
_, o, e = ssh.exec_command(
    f'curl -s -m 20 -k -H "User-Agent: Mozilla/5.0" '
    f'https://{DOMAIN}/test_opcache_web.php 2>&1'
)
out = o.read().decode(errors='replace')
err = e.read().decode(errors='replace')
print('Ответ от https://' + DOMAIN + '/test_opcache_web.php:')
print(out[:1500])
if err.strip():
    print('curl stderr:', err[:300])

# 9. Если 404 — проверить, как nginx роутит запросы
print('\n=== Nginx default.conf / site config ===')
_, o, _ = ssh.exec_command(
    'cat /etc/nginx/sites-enabled/*.conf 2>/dev/null | head -40 || '
    'cat /etc/nginx/conf.d/*.conf 2>/dev/null | head -40 || '
    'ls -la /etc/nginx/sites-enabled/ 2>/dev/null || '
    'echo "не найдено"'
)
print(o.read().decode(errors='replace')[:1500])

ssh.close()
print('\nDONE')
