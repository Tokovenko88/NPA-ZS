#!/usr/bin/env python3
"""Проверка сайта после удаления тестовых файлов."""
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

# Удалить тестовые файлы
print('\n=== Удаление тестовых файлов ===')
ssh.exec_command(f'rm -f {SITE}/test_opcache_web.php {SITE}/test_opcache.php')
print('Удалено')

# Проверить сайт — страница законов
print('\n=== Проверка страницы законов ===')
stdin, stdout, stderr = ssh.exec_command(
    f'curl -s -m 20 -k -H "User-Agent: Mozilla/5.0" '
    f'https://{DOMAIN}/view/laws/proekty_postanovlenij/2026/pr_post_12_203_ot_18_09_2026/tekst-proekta-postanovleniya132/'
)
out = stdout.read().decode(errors='replace')
print(f'Длина ответа: {len(out)} байт')
print('Первые 1500 символов:')
print(out[:1500])

# Проверить главную
print('\n=== Проверка главной ===')
stdin, stdout, stderr = ssh.exec_command(
    f'curl -s -m 20 -k -H "User-Agent: Mozilla/5.0" '
    f'https://{DOMAIN}/'
)
out = stdout.read().decode(errors='replace')
print(f'Длина ответа: {len(out)} байт')

# Проверяем ошибки в логе
print('\n=== PHP ошибки за последние 5 минут ===')
stdin, stdout, stderr = ssh.exec_command('tail -50 /tmp/php_err.log 2>/dev/null')
out = stdout.read().decode(errors='replace')
print(out[:2000] if out else 'Лог пуст или не найден')

ssh.close()
print('\nDONE')
