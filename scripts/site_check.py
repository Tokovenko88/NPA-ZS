#!/usr/bin/env python3
"""Проверка сайта через SSH curl с правильным User-Agent."""
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

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36'
URL = 'https://sevzakon.ru/view/laws/proekty_postanovlenij/2026/pr_post_12_203_ot_18_09_2026/tekst-proekta-postanovleniya132/'

print('=== ПРОВЕРКА САЙТА ===')
cmd = f"curl -s -m 20 -w '\\nHTTP:%{{http_code}} SIZE:%{{size_download}} TIME:%{{time_total}}s\\n' -k -H 'User-Agent: {UA}' '{URL}'"
stdin, stdout, stderr = cli.exec_command(cmd, timeout=25)
out = stdout.read().decode('utf-8', 'replace')
err = stderr.read().decode('utf-8', 'replace')

# Парсим ответ
lines = out.strip().split('\n')
http_line = lines[-1] if lines else ''
size = 0
http_code = 0
for line in lines:
    if line.startswith('HTTP:'):
        http_code = line.split('HTTP:')[1].split()[0]
    if line.startswith('SIZE:'):
        size = int(line.split('SIZE:')[1].split()[0])

print(f'HTTP: {http_code} | Size: {size} bytes')
if http_code == 200:
    print('✅ Страница отдаёт 200 OK')
    # Проверяем контент
    body = '\n'.join(lines[:-1]) if len(lines) > 1 else ''
    if 'opcache' in body.lower() or 'parse error' in body.lower() or ' Evo Parse Error ' in body:
        print('⚠ В контенте ЕСТЬ упоминание ошибки!')
        # Ищем контекст
        idx = body.lower().find('opcache')
        if idx == -1:
            idx = body.lower().find('parse error')
        if idx >= 0:
            print(f'Контекст: ...{body[max(0,idx-50):idx+100]}...')
    else:
        print('✅ В контенте нет ошибок')
        # Проверяем, что контент реальный (не ошибка сервера)
        if '<html' in body.lower() or '<!doctype' in body.lower():
            print('✅ HTML-контент присутствует')
        else:
            print('⚠ Контент не выглядит как HTML')
else:
    print(f'⚠ HTTP {http_code} — сайт НЕ работает!')

if err.strip():
    print(f'[stderr] {err[:300]}')

print('\n=== PHP ОШИБКИ (последние 20 строк) ===')
cmd2 = "tail -20 /tmp/php_err.log 2>/dev/null || tail -20 /var/log/php/error.log 2>/dev/null || echo 'Файл не найден'"
stdin2, stdout2, stderr2 = cli.exec_command(cmd2, timeout=10)
out2 = stdout2.read().decode('utf-8', 'replace')
print(out2[:1500] if out2.strip() else 'Лог ошибок не найден или пуст')

print('\n=== Проверка .user.ini (должен быть удалён) ===')
cmd3 = "ls -la /var/www/u0220513/data/www/sevzakon.ru/.user.ini 2>&1"
stdin3, stdout3, stderr3 = cli.exec_command(cmd3, timeout=10)
out3 = stdout3.read().decode('utf-8', 'replace')
if 'No such file' in out3 or 'not found' in out3.lower():
    print('✅ .user.ini удалён (как и было задумано)')
else:
    print(f'⚠ .user.ini всё ещё есть: {out3.strip()}')

print('\n=== Проверка cache_sync.class.processor.php ===')
cmd4 = "grep -n 'opcache_reset' /var/www/u0220513/data/www/sevzakon.ru/manager/processors/cache_sync.class.processor.php 2>/dev/null"
stdin4, stdout4, stderr4 = cli.exec_command(cmd4, timeout=10)
out4 = stdout4.read().decode('utf-8', 'replace')
if out4.strip():
    print('Строки с opcache_reset:')
    print(out4[:500])
else:
    print('opcache_reset не найден в cache_sync')

cli.close()
print('\n✅ ПРОВЕРКА ЗАВЕРШЕНА')
