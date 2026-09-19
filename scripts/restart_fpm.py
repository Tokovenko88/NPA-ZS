#!/usr/bin/env python3
"""Поиск способа перезагрузки PHP-FPM и проверка OPcache."""
import os
from dotenv import load_dotenv
import paramiko

load_dotenv('D:/NPA-ZS/.env')
s = paramiko.SSHClient()
s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
s.connect(
    hostname=os.getenv('MODX_SSH_HOST'),
    port=int(os.getenv('MODX_SSH_PORT', 22)),
    username=os.getenv('MODX_SSH_USERNAME'),
    password=os.getenv('MODX_SSH_PASSWORD'),
    timeout=10,
)

def run(cmd):
    i, o, e = s.exec_command(cmd, timeout=30)
    return o.read().decode('utf-8', errors='replace'), e.read().decode('utf-8', errors='replace')

print('=== Поиск PHP-FPM ===')
out, err = run("ps aux | grep -E 'php-fpm|php.*fpm' | grep -v grep | head -5")
print(out[:500])
if err.strip():
    print('ERR:', err[:200])

print('\n=== Найти init-скрипты для php ===')
out2, err2 = run("ls -la /etc/init.d/php* /etc/init.d/php*-fpm 2>/dev/null; echo EXIT:$?")
print(out2 if out2.strip() else '(не найдены)' + (err2 if err2 else ''))

print('\n=== Найти systemctl для php ===')
out3, err3 = run("systemctl list-units --type=service 2>/dev/null | grep -i php | head -5; echo EXIT:$?")
print(out3 if out3.strip() else '(не найдены или нет systemctl)' + (err3 if err3 else ''))

print('\n=== Проверить php-fpm master PID ===')
out4, err4 = run("cat /var/run/php-fpm.pid 2>/dev/null || cat /run/php-fpm.pid 2>/dev/null || pgrep -f 'php-fpm: master' 2>/dev/null; echo EXIT:$?")
print(out4 if out4.strip() else '(PID не найден)' + (err4 if err4 else ''))

print('\n=== Попытка перезагрузки через kill -USR2 (graceful reload) ===')
# Сначала находим PID
pid_out, pid_err = run("pgrep -f 'php-fpm: master' | head -1")
pid = pid_out.strip()
print(f'PID php-fpm master: {pid}')
if pid and pid.isdigit():
    out5, err5 = run(f'kill -USR2 {pid} 2>&1; echo "kill exit: $?"')
    print('kill -USR2 результат:', out5 if out5.strip() else '(пусто)' + (err5 if err5 else ''))
else:
    print('PID не найден, пробуем перезапуск через find')
    out5, err5 = run("find /etc/init.d /etc/rc.d /usr/local/etc/rc.d -name 'php*' -type f 2>/dev/null | head -5")
    print('Найдено:', out5 if out5.strip() else '(ничего)' + (err5 if err5 else ''))

print('\n=== Проверка OPcache через antibot phpinfo.php ===')
# antibot/phpinfo.php — правильный User-Agent не требуется, так как antibot сам разрешает
out6, err6 = run('curl -s -m 15 -k "https://sevzakon.ru/antibot/adm/phpinfo.php" 2>&1 | grep -i "opcache" | head -20')
print(out6 if out6.strip() else '(ничего не найдено)' + (err6 if err6 else ''))

print('\n=== Проверка текущих настроек PHP через antibot phpinfo ===')
out7, err7 = run('curl -s -m 15 -k "https://sevzakon.ru/antibot/adm/phpinfo.php" 2>&1 | grep -E "opcache.enable|opcache.memory|opcache.max_accelerated|opcache.revalidate" | head -10')
print(out7 if out7.strip() else '(ничего не найдено)' + (err7 if err7 else ''))

print('\n=== Проверка .user.ini эффекта через antibot phpinfo ===')
# Смотрим ini_get для opcache
out8, err8 = run('curl -s -m 15 -k "https://sevzakon.ru/antibot/adm/phpinfo.php" 2>&1 | grep -B2 -A2 "opcache" | head -30')
print(out8 if out8.strip() else '(ничего)' + (err8 if err8 else ''))

s.close()
print('\nDONE')
