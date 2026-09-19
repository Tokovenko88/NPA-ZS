#!/usr/bin/env python3
"""Диагностика файла snippet.firstchildredirect.php на сервере."""
import os
from dotenv import load_dotenv
import paramiko

load_dotenv('D:/NPA-ZS/.env')
cli = paramiko.SSHClient()
cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
cli.connect(
    os.getenv('MODX_SSH_HOST'),
    port=int(os.getenv('MODX_SSH_PORT', '22')),
    username=os.getenv('MODX_SSH_USERNAME'),
    password=os.getenv('MODX_SSH_PASSWORD'),
    timeout=25,
)


def run(cmd, t=90):
    _i, o, e = cli.exec_command(cmd, timeout=t)
    return o.read().decode('utf-8', 'replace'), e.read().decode('utf-8', 'replace')


base = '/var/www/u0220513/data/www/sevzakon.ru'
fcr_file = f"{base}/assets/snippets/firstchildredirect/snippet.firstchildredirect.php"
fcr_dir = f"{base}/assets/snippets/firstchildredirect/"

print('=' * 60)
print('1. Каталог и файлы')
print('=' * 60)
out, _ = run(f'ls -la {fcr_dir} 2>&1')
print(out)

print()
print('=' * 60)
print('2. Инфо о файле + размер')
print('=' * 60)
out, _ = run(f"file {fcr_file} && wc -c {fcr_file} 2>&1")
print(out)

print()
print('=' * 60)
print('3. PHP LINT')
print('=' * 60)
out, err = run(f'php -l {fcr_file} 2>&1')
print(out)
if err.strip():
    print('[stderr]', err[:500])

print()
print('=' * 60)
print('4. Первые 2000 символов файла')
print('=' * 60)
out, _ = run(f'head -c 2000 {fcr_file} 2>&1')
print(out)

print()
print('=' * 60)
print('5. BOM / бинарные символы в первых 16 байтах')
print('=' * 60)
out, _ = run(f"dd if={fcr_file} bs=1 count=16 2>/dev/null | xxd")
print(out)

print()
print('=' * 60)
print('6. PHP-теги в файле')
print('=' * 60)
out, _ = run(f"grep -n '<?php\\|<?\\\\|<?=' {fcr_file} 2>&1 | head -10")
print(out)

print()
print('=' * 60)
print('7. PHP-тег в конце файла (вдруг он обрывается)')
print('=' * 60)
out, _ = run(f'tail -c 200 {fcr_file} 2>&1')
print(out)

print()
print('=' * 60)
print('8. Поиск parse error в логах Apache')
print('=' * 60)
log_path = f"{base}/../logs/sevzakon.ru.error.log"
out, _ = run(f"grep -i 'firstchildredirect\\|parse error' {log_path} 2>/dev/null | tail -5")
print(out[:1500] if out else '(no matches or no log file)')

print()
print('9. Также проверим access/error логи MODX manager')
print('=' * 60)
out, _ = run(f"grep -ri 'firstchildredirect\\|fcr' {base}/manager/ 2>/dev/null | head -5")
print(out[:500] if out else '(nothing)')

cli.close()
print()
print('DONE')
