#!/usr/bin/env python3
"""Исправление логической ошибки в FirstChildRedirect snippet.firstchildredirect.php"""
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

print('=' * 60)
print('1. БЭКАП исходного файла')
print('=' * 60)
out, err = run(f'cp {fcr_file} /tmp/snippet.firstchildredirect.php.bak && echo "BACKUP_OK"')
print(out.strip())
if err.strip():
    print('[stderr]', err[:300])

print()
print('=' * 60)
print('2. Проверка наличия проблемного кода')
print('=' * 60)
out, _ = run(f"grep -n '!\$children === false' {fcr_file} 2>&1")
print('Найдено строк:', out.count('\n') if out else 0)
if out:
    print('Содержимое:')
    print(out)

print()
print('=' * 60)
print('3. Применяем исправление через sed')
print('=' * 60)
# Заменяем "if (!$children === false)" на "if ($children !== false)"
out, err = run(f"sed -i 's/if (!\\\$children === false)/if (\\\$children !== false)/' {fcr_file} && echo PATCH_OK")
print(out.strip())
if err.strip():
    print('[stderr]', err[:300])

print()
print('=' * 60)
print('4. Верификация: ищем оба варианта')
print('=' * 60)
out_bad, _ = run(f"grep -n '!\$children === false' {fcr_file} 2>&1")
print('Старый код остался:', 'НЕТ (хорошо)' if not out_bad.strip() else 'ДА (плохо)')
out_good, _ = run(f"grep -n '\$children !== false' {fcr_file} 2>&1")
print('Новый код:')
print(out_good)

print()
print('=' * 60)
print('5. PHP LINT после исправления')
print('=' * 60)
out, err = run(f'php -l {fcr_file} 2>&1')
print(out)
if err.strip():
    print('[stderr]', err[:300])

print()
print('=' * 60)
print('6. Отображаем исправный участок кода')
print('=' * 60)
out, _ = run(f"grep -n -A2 -B2 '\$children !== false' {fcr_file} 2>&1")
print(out)

# Очистка кэша MODX (если используется кэширование сниппетов)
print()
print('=' * 60)
print('7. Очистка кэша MODX (site cache)')
print('=' * 60)
cache_dir = f"{base}/assets/cache"
out, err = run(f"rm -f {cache_dir}/siteCache.idx.php {cache_dir}/docid_*.pageCache.php 2>&1 && echo 'CACHE_CLEARED'")
print(out.strip())
if err.strip():
    print('[stderr]', err[:200])

cli.close()
print()
print('FIX COMPLETE')
