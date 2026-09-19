#!/usr/bin/env python3
"""Поиск реального пути к MODX и проверка OPCache."""
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


def run(cmd, t=120):
    stdin, stdout, stderr = cli.exec_command(cmd, timeout=t)
    return (stdout.read().decode('utf-8', 'replace'),
            stderr.read().decode('utf-8', 'replace'))


def find_files(base_dir, pattern, t=180):
    """Find files matching pattern under base_dir."""
    cmd = (f"find {base_dir} -name '{pattern}' "
           f"-type f 2>/dev/null | head -30")
    out, err = run(cmd, t)
    return out


print('=' * 60)
print('1. Поиск папки с сайтом')
print('=' * 60)

# Попробуем разные пути
paths_to_check = [
    '/home/u0220513/new_deploy',
    '/home/u0220513/public_html',
    '/home/u0220513/www',
    '/home/u0220513/sevzakon',
    '/var/www',
    '/var/www/sevzakon',
    '/home/sevzakon',
    '/home/sevzakon/www',
    '/home/u0220513/domains/sevzakon.ru',
    '/home/u0220513/sevzakon.ru',
]

for p in paths_to_check:
    out, err = run(f'test -d {p} && echo FOUND:{p} || echo NOT:{p}', t=30)
    result = out.strip()
    print(f'  {p}: {result}')

print()
print('=' * 60)
print('2. Поиск manager/processors/ на сервере')
print('=' * 60)
cmd = ("find / -type d -name 'processors' 2>/dev/null | "
       "grep -i manager | head -10")
out, err = run(cmd, t=60)
print(out[:1500])

print()
print('=' * 60)
print('3. Поиск файлов modx_site_snippets (ядро БД)')
print('=' * 60)
out2, err2 = run(
    "find / -name 'modx_site_snippets' -type f 2>/dev/null | head -5"
)
print(out2[:500])

print()
print('=' * 60)
print('4. PHP версия и загруженные модули')
print('=' * 60)
out3, err3 = run('php -v 2>&1')
print(out3[:500])
out3b, err3b = run('php -m 2>&1 | grep -i opcache')
print(f'Опции OPCache в php -m: {out3b.strip() or "НЕТ"}')
if err3b.strip():
    print(f'[stderr] {err3b[:200]}')

print()
print('=' * 60)
print('5. php.ini файл(ы)')
print('=' * 60)
out4, err4 = run('php --ini 2>&1')
print(out4[:500])
if err4.strip():
    print(f'[stderr] {err4[:200]}')

print()
print('=' * 60)
print('6. Везде поиск opcache_reset и opcache_enable')
print('=' * 60)
# Поиск в возможно найденных директориях
for dir_found in ['/home/u0220513', '/var/www', '/home/sevzakon']:
    out5, err5 = run(
        f"grep -r 'opcache_reset\\|opcache_enable\\|opcache.interned' "
        f"{dir_found} 2>/dev/null | head -20"
    )
    if out5.strip():
        print(f'В {dir_found}:')
        print(out5[:800])
    else:
        print(f'В {dir_found}: ничего не найдено')

print()
print('=' * 60)
print('7. Документация по MODX Evo и opcache')
print('=' * 60)
# Проверяем, есть ли core или manager в найденных каталогах
for base in ['/home/u0220513', '/var/www', '/home/sevzakon']:
    out6, err6 = run(f'test -f {base}/index.php && echo YES:{base}/index.php || echo NO', t=30)
    print(f'{base}/index.php: {out6.strip()}')
    out7, err7 = run(f'test -d {base}/manager && echo YES_MANAGER || echo NO_MANAGER', t=30)
    print(f'{base}/manager/: {out7.strip()}')

cli.close()
print('\nDONE')
