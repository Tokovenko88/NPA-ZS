#!/usr/bin/env python3
"""Верификация исправления FirstChildRedirect + ручной фикс если нужно."""
import os
from dotenv import dotenv_values
import paramiko

env = dotenv_values('D:/NPA-ZS/.env')
cli = paramiko.SSHClient()
cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
cli.connect(
    env['MODX_SSH_HOST'],
    port=int(env.get('MODX_SSH_PORT', '22')),
    username=env['MODX_SSH_USERNAME'],
    password=env['MODX_SSH_PASSWORD'],
    timeout=25,
)


def run(cmd, t=90):
    _i, o, e = cli.exec_command(cmd, timeout=t)
    return o.read().decode('utf-8', 'replace'), e.read().decode('utf-8', 'replace')


base = '/var/www/u0220513/data/www/sevzakon.ru'
fcr = base + '/assets/snippets/firstchildredirect/snippet.firstchildredirect.php'

print('=' * 60)
print('1. Текущее состояние строк 50-65')
print('=' * 60)
out, _ = run("sed -n '50,65p' " + fcr)
print(out)

print()
print('=' * 60)
print('2. Поиск проблемного кода')
print('=' * 60)
out, _ = run("grep -n 'children === false' " + fcr)
print("Результат grep:", repr(out))
if '!$' in out or '!$' in out:
    print('>>> Проблемный код всё ещё присутствует — нужно чинить')

print()
print('=' * 60)
print('3. Если проблемный код есть — применяем правильный фикс')
print('=' * 60)

# Читаем полный файл
out_full, _ = run("cat " + fcr)
content = out_full

if '!$children === false' in content:
    print('Применяем исправление...')
    # Загружаем исправленный файл через SFTP
    fixed = content.replace('if (!$children === false)', 'if ($children !== false)')
    sftp = cli.open_sftp()
    with sftp.file(fcr, 'w') as f:
        f.write(fixed)
    sftp.close()
    print('Файл перезаписан.')
else:
    print('Проблемный код уже отсутствует — фикс не требуется.')

print()
print('=' * 60)
print('4. PHP LINT после исправления')
print('=' * 60)
out, err = run('php -l ' + fcr + ' 2>&1')
print(out)
if err.strip():
    print('[stderr]', err[:300])

print()
print('=' * 60)
print('5. Проверка: содержимое исправного участка')
print('=' * 60)
out, _ = run("grep -n -A3 -B3 'children !== false' " + fcr)
print(out)

print()
print('=' * 60)
print('6. Полная проверка на наличие ошибок')
print('=' * 60)
out, _ = run("grep -n '!\$children === false' " + fcr)
if out.strip():
    print('WARNING: проблемный код всё ещё есть!')
    print(out)
else:
    print('OK — проблемный код отсутствует')

# Очистка кэша
cache_idx = base + '/assets/cache/siteCache.idx.php'
out, err = run('rm -f ' + cache_idx + ' && echo CLEARED')
print()
print('Кэш:', out.strip())

cli.close()
print()
print('DONE')
