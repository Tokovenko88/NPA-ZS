#!/usr/bin/env python3
"""Проверка сайта и OPcache через SSH."""
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

print('=== 1. Проверка сайта ===')
code, size = run('curl -s -m 20 -k -o /dev/null -w "%{http_code} %{size_download}" https://sevzakon.ru/view/laws/proekty_postanovlenij/2026/pr_post_12_203_ot_18_09_2026/tekst-proekta-postanovleniya132/')
print(f'HTTP: {code}, size: {size} байт')

print('\n=== 2. Проверка .user.ini ===')
out, err = run("cat /var/www/u0220513/data/www/sevzakon.ru/.user.ini 2>&1; echo EXIT:$?")
print(out if out.strip() else '(файла нет или ошибка)' + (err if err else ''))

print('\n=== 3. Проверка php-fpm.conf на opcache ===')
out2, err2 = run("grep -rn 'opcache' /etc/php/8.2/fpm/php.ini /etc/php/8.2/fpm/conf.d/ /etc/php/8.2/fpm/pool.d/ 2>/dev/null; echo EXIT:$?")
print(out2 if out2.strip() else '(ничего не найдено)' + (err2 if err2 else ''))

print('\n=== 4. Проверка через antibot phpinfo ===')
out3, err3 = run('curl -s -m 10 -k "https://sevzakon.ru/antibot/adm/phpinfo.php" 2>&1 | grep -i "opcache\\|sapi\\|server api" | head -20')
print(out3 if out3.strip() else '(ничего не найдено)' + (err3 if err3 else ''))

print('\n=== 5. Проверка через curl к phpinfo через сайт ===')
# Создаем временный phpinfo.php через antirect
out4, err4 = run('curl -s -m 15 -k "https://sevzakon.ru/index.php?a=88" 2>&1 | grep -i "opcache" | head -10')
print(out4 if out4.strip() else '(не удалось)' + (err4 if err4 else ''))

s.close()
print('\nDONE')
