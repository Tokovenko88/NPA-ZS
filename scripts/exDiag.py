#!/usr/bin/env python3
"""Экстренная диагностика и откат изменений на сервере."""
import os
from dotenv import load_dotenv
import paramiko
import urllib.request
import ssl

load_dotenv('D:/NPA-ZS/.env')
cli = paramiko.SSHClient()
cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
cli.connect(os.getenv('MODX_SSH_HOST'), port=int(os.getenv('MODX_SSH_PORT','22')), 
            username=os.getenv('MODX_SSH_USERNAME'), password=os.getenv('MODX_SSH_PASSWORD'), 
            timeout=10)

def run(cmd, t=120):
    _i, o, e = cli.exec_command(cmd, timeout=t)
    return o.read().decode('utf-8','replace'), e.read().decode('utf-8','replace')

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

ua = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36'}

# =========================================
# 1. САЙТ В ДЕЙСТВИИ
# =========================================
print('=== САЙТ ЧЕРЕЗ CURL ===')
for url in ['https://sevzakon.ru/', 
            'https://sevzakon.ru/view/laws/proekty_postanovlenij/2026/pr_post_12_203_ot_18_09_2026/tekst-proekta-postanovleniya132/']:
    print(f'\n>>> {url}')
    try:
        req = urllib.request.Request(url, headers=ua)
        r = urllib.request.urlopen(req, timeout=15, context=ctx)
        body = r.read()
        txt = body.decode('utf-8', errors='replace')
        print(f'  HTTP: {r.status} | Size: {len(body)} bytes')
        if 'Zend OPcache' in txt or 'Evo Parse Error' in txt or 'Parse error' in txt:
            i = txt.find('Zend OPcache')
            if i < 0: i = txt.find('Evo Parse Error')
            if i < 0: i = txt.find('Parse error')
            if i >= 0:
                print(f'  *** OBНИК В HTML ***')
                print(f'  Context: ...{txt[max(0,i-100):i+200]}...')
        else:
            print(f'  OK, первый фрагмент: {txt[:150]}')
    except Exception as ex:
        print(f'  ОШИБКА: {ex}')

# =========================================
# 2. СОСТОЯНИЕ СЕРВИСОВ
# =========================================
print('\n=== СОСТОЯНИЕ СЕРВИСОВ ===')
for svc in ['php-fpm', 'php7.4-fpm', 'php8.1-fpm', 'php8.2-fpm', 'apache2', 'httpd']:
    out, _ = run(f'pgrep -x {svc} >/dev/null 2>&1 && echo RUNNING || echo NOT_RUNNING')
    print(f'  {svc:20s}: {out.strip()}')

print()
print('=== php-fpm systemd ===')
out, _ = run('systemctl status php-fpm 2>&1 || echo _NO_SYSTEMD_')
print(out[:500])

print()
print('=== httpd systemd ===')
out, _ = run('systemctl status httpd 2>&1 || echo _NO_SYSTEMD_')
print(out[:400])

print()
print('=== PHP процессы ===')
out, _ = run("ps aux 2>/dev/null | grep -E 'php[-_]fpm|mod_php' | grep -v grep | head -5")
print(out if out.strip() else '  НЕТ PHP-ПРОЦЕССОВ')

# =========================================
# 3. PHP-FPM — МОЖНО ЛИ ЗАПУСТИТЬ
# =========================================
print('\n=== PHP-FPM ПУТИ ===')
out, _ = run('which php-fpm 2>/dev/null; find /usr -name php-fpm -type f 2>/dev/null | head -5')
print(out[:300])

out, _ = run('ls -la /usr/sbin/php-fpm 2>/dev/null || echo _NO_USR_SBIN_FPM_')
print(out[:200])

out, _ = run('ls -la /etc/php-fpm.d/ 2>/dev/null || echo _NO_PHP_FPM_D_')
print(out[:300])

# =========================================
# 4. ОПКЭШ СТАТУС
# =========================================
print('\n=== OPcache СТАТУС (CLI) ===')
out, _ = run('php -v 2>&1 | head -3')
print(out[:200])

out, _ = run('php -m 2>&1 | grep -i opcache || echo _OPcache_OТКЛЮЧЕН_')
print(out[:200])

# =========================================
# 5. ПРАВА
# =========================================
print('\n=== ПРАВА ===')
out, _ = run('id')
print(f'  {out.strip()}')
out, _ = run('groups')
print(f'  группы: {out.strip()}')
out, _ = run('sudo -n echo YES 2>&1 || echo _БЕЗ_SUDO_')
print(f'  sudo: {out.strip()}')

# =========================================
# 6. ИЗМЕНЁННЫЕ ФАЙЛЫ — ДАТЫ
# =========================================
print('\n=== ИЗМЕНЁННЫЕ ФАЙЛЫ ===')
out, _ = run('stat /var/www/u0220513/data/www/sevzakon.ru/manager/processors/cache_sync.class.processor.php 2>/dev/null')
print('  cache_sync:')
print(out[:300])
out, _ = run('stat /var/www/u0220513/data/www/sevzakon.ru/.user.ini 2>/dev/null')
print('  .user.ini:')
print(out[:300])

# =========================================
# 7. .user.ini — ЧТО Я НАПИСАЛ
# =========================================
print('\n=== .user.ini ===')
out, _ = run('cat /var/www/u0220513/data/www/sevzakon.ru/.user.ini 2>/dev/null || echo _НЕТ_')
print(out[:500])

# =========================================
# 8. opcache.ini
# =========================================
print('\n=== opcache.ini (из php.d) ===')
out, _ = run('cat /opt/php/7.4/etc/php.d/opcache.ini 2>/dev/null || echo _НЕТ_')
print(out[:500])

cli.close()
print('\nDONE')
