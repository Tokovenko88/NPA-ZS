#!/usr/bin/env python3
"""Экстренная диагностика состояния сайта."""
import os
from dotenv import load_dotenv
import paramiko
import urllib.request
import ssl

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

def run(cmd, t=120):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=t)
    return stdout.read().decode('utf-8', 'replace'), stderr.read().decode('utf-8', 'replace')


print('=' * 60)
print('1. СОСТОЯНИЕ СЕРВИСОВ')
print('=' * 60)

for svc in ['php-fpm', 'php7.4-fpm', 'php8.1-fpm', 'php8.2-fpm', 'apache2', 'httpd']:
    out, err = run(f'pgrep -x {svc} >/dev/null 2>&1 && echo RUNNING || echo NOT_RUNNING')
    print(f'  {svc:20s}: {out.strip()}')

print()
print('=== Процессы PHP ===')
out, _ = run("ps aux 2>/dev/null | grep -E 'php-fpm|php.*fpm' | grep -v grep | head -20")
print(out[:2000] if out.strip() else '  НЕТ PHP-ПРОЦЕССОВ!')

print()
print('=== systemd/php-fpm ===')
out, err = run('systemctl status php-fpm 2>&1 || service php-fpm status 2>&1 || echo _NEITHER_')
print(out[:800])

print()
print('=== systemd/apache ===')
out, err = run('systemctl status apache2 2>&1 || service apache2 status 2>&1 || systemctl status httpd 2>&1 || service httpd status 2>&1')
print(out[:800])

print()
print('=' * 60)
print('2. LOGS')
print('=' * 60)

print('--- Apache error_log ---')
out, _ = run("tail -30 /var/log/apache2/error.log 2>/dev/null")
print(out[:1500])
out2, _ = run("tail -30 /var/log/httpd/error_log 2>/dev/null")
print(out2[:1500])

print('--- PHP-FPM error_log ---')
for f in ['/var/log/php-fpm.log', '/var/log/php-fpm/www-error.log', '/var/log/php8.1-fpm.log', '/var/log/php8.2-fpm.log']:
    out, _ = run(f"tail -10 {f} 2>/dev/null")
    if out.strip() and 'DONE' not in out:
        print(f'-- {f} --')
        print(out[:500])

print()
print('=' * 60)
print('3. САЙТ ЧЕРЕЗ CURL')
print('=' * 60)

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

for url in [
    'https://sevzakon.ru/',
    'https://sevzakon.ru/view/laws/proekty_postanovlenij/2026/pr_post_12_203_ot_18_09_2026/tekst-proekta-postanovleniya132/',
]:
    print(f'\n--- {url} ---')
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36'
        })
        resp = urllib.request.urlopen(req, timeout=15, context=ctx)
        body = resp.read()
        print(f'  HTTP: {resp.status} | Size: {len(body)} bytes')
        print(f'  First 300 chars: {body[:300]}')
    except Exception as e:
        print(f'  ОШИБКА: {e}')

print()
print('=' * 60)
print('4. OPcache статус через веб')
print('=' * 60)

out, _ = run('php -r "echo json_encode([\\"sapi\\"=>php_sapi_name(),\\"opcache.enable\\"=>ini_get(\\\"opcache.enable\\\"),\\"opcache.version\\"=>function_exists(\\\"opcache_get_status\\\")?opcache_get_status()[\"opcache_version\"]:\\\"N/A\\\",\\"memory\\"=>function_exists(\\\"opcache_get_status\\\")?opcache_get_status()[\"memory_usage\"][\\"used_memory\\\"]:0]);"')
print(out)

print()
print('5. ФАЙЛЫ КОНФИГА В РУКАХ')
print('=' * 60)

# Проверить .user.ini
out, _ = run("cat /var/www/u0220513/data/www/sevzakon.ru/.user.ini 2>/dev/null || echo NO_USER_INI")
print('--- .user.ini ---')
print(out[:500])

# Проверить opcache.ini
out, _ = run("cat /opt/php/7.4/etc/php.d/opcache.ini 2>/dev/null || cat /etc/php/*/fpm/php.d/opcache.ini 2>/dev/null || echo NO_OPCACHE_INI")
print('--- opcache.ini ---')
print(out[:800])

print()
print('6. ПРАВА НА ФАЙЛЫ')
print('=' * 60)

out, _ = run("ls -la /var/www/u0220513/data/www/sevzakon.ru/.user.ini 2>/dev/null")
print('--- .user.ini perms ---')
print(out[:300])

out, _ = run("ls -la /var/www/u0220513/data/www/sevzakon.ru/manager/processors/cache_sync.class.processor.php 2>/dev/null")
print('--- cache_sync perms ---')
print(out[:300])

ssh.close()
print('\nDONE')
