#!/usr/bin/env python3
"""Диагностика 403 ошибки."""
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

print('=== 1. Тело ответа 403 ===')
out, err = run('curl -s -m 20 -k "https://sevzakon.ru/view/laws/proekty_postanovlenij/2026/pr_post_12_203_ot_18_09_2026/tekst-proekta-postanovleniya132/"')
print(out[:2000])
if err.strip():
    print('ERR:', err[:500])

print('\n=== 2. Проверка с User-Agent YandexBot (как в ошибке) ===')
out2, err2 = run('curl -s -m 15 -k -A "Mozilla/5.0 (compatible; YandexBot/3.0; +http://yandex.com/bots)" "https://sevzakon.ru/view/laws/proekty_postanovlenij/2026/pr_post_12_203_ot_18_09_2026/tekst-proekta-postanovleniya132/" -o /dev/null -w "%{http_code}\n"')
print(f'HTTP с YandexBot: {out2.strip()}')
if err2.strip():
    print('ERR:', err2[:200])

print('\n=== 3. Проверка с браузерным UA ===')
out3, err3 = run('curl -s -m 15 -k -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" "https://sevzakon.ru/view/laws/proekty_postanovlenij/2026/pr_post_12_203_ot_18_09_2026/tekst-proekta-postanovleniya132/" -o /dev/null -w "%{http_code}\n"')
print(f'HTTP с браузерным UA: {out3.strip()}')

print('\n=== 4. Проверка с мобильным UA ===')
out4, err4 = run('curl -s -m 15 -k -A "Mozilla/5.0 (Linux; Android 10; SM-G960F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36" "https://sevzakon.ru/view/laws/proekty_postanovlenij/2026/pr_post_12_203_ot_18_09_2026/tekst-proekta-postanovleniya132/" -o /dev/null -w "%{http_code}\n"')
print(f'HTTP с мобильным UA: {out4.strip()}')

print('\n=== 5. Проверка через антибот лог ===')
out5, err5 = run('tail -50 /var/www/u0220513/data/www/sevzakon.ru/antibot/data/*.log 2>/dev/null; echo EXIT:$?')
print(out5 if out5.strip() else '(логи не найдены)' + (err5 if err5 else ''))

print('\n=== 6. Проверка .htaccess на проблемы ===')
out6, err6 = run("head -30 /var/www/u0220513/data/www/sevzakon.ru/.htaccess")
print(out6)
print('\n... (пропущено строчки antibot) ...')
print('Проверка RequireAll блокировки IP:')
out7, err7 = run("sed -n '/\<RequireAll\>/,/\<\/RequireAll\>/p' /var/www/u0220513/data/www/sevzakon.ru/.htaccess")
print(out7)

s.close()
print('\nDONE')
