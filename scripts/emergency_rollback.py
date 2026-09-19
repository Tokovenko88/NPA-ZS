#!/usr/bin/env python3
"""СРОЧНЫЙ ОТКАТ: проверка состояния + откат всех изменений."""
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
    timeout=15,
)
print('=== SSH connected ===')

sftp = cli.open_sftp()

def exec_cmd(cmd):
    stdin, stdout, stderr = cli.exec_command(cmd, timeout=10)
    return stdout.read().decode('utf-8', 'replace'), stderr.read().decode('utf-8', 'replace')

def sftp_put(remotepath, content):
    with sftp.file(remotepath, 'w') as f:
        f.write(content)

# 1. Текущее состояние сайта
print('\n=== ТЕКУЩЕЕ СОСТОЯНИЕ САЙТА ===')
code, err = exec_cmd("curl -s -m 15 -o /dev/null -w '%{http_code} %{size_download} bytes %{time_total}s\n' -k https://sevzakon.ru/view/laws/proekty_postanovlenij/2026/pr_post_12_203_ot_18_09_2026/tekst-proekta-postanovleniya132/")
print(f'Страница закона: {code.strip()}')


print('=== PHP-FPM статус ===')
out1, _ = exec_cmd("pgrep -a php-fpm 2>/dev/null | head -5; echo EXIT:$?")
print(out1[:300] if out1.strip() else 'НЕТ ПРОЦЕССОВ')

# 2. Откат .user.ini (удалить или вернуть оригинал)
print('\n=== ОТКАТ .user.ini ===')
path_ini = '/var/www/u0220513/data/www/sevzakon.ru/.user.ini'
try:
    sftp.stat(path_ini)
    content, _ = exec_cmd(f'cat {path_ini}')
    print(f'Текущий .user.ini ({len(content)} байт):')
    print(content[:500])
    
    # Сохраняем резервную копию и удаляем
    exec_cmd(f'cp {path_ini} {path_ini}.bak_$(date +%Y%m%d_%H%M%S) && echo "BACKUP CREATED"')
    exec_cmd(f'rm {path_ini} && echo "REMOVED .user.ini"')
    print('✅ .user.ini удалён')
    
    # Проверяем, что файл удалён
    try:
        sftp.stat(path_ini)
        print('⚠ .user.ini всё ещё существует!')
    except:
        print('✅ .user.ini удалён (подтверждено)')
except Exception as e:
    print(f'.user.ini не найден или ошибка: {e}')

# 3. Откат cache_sync.class.processor.php
print('\n=== ОТКАТ cache_sync.class.processor.php ===')
path_cs = '/var/www/u0220513/data/www/sevzakon.ru/manager/processors/cache_sync.class.processor.php'
try:
    sftp.stat(path_cs)
    out, _ = exec_cmd(f'grep -n "function_exists.*opcache_reset" {path_cs}')
    if 'function_exists' in out:
        print('В файле ЕСТЬ function_exists — нужно откатить')
        # Пытаемся найти бэкап
        import glob
        import datetime
        backups = []
        try:
            batchout, _ = exec_cmd(f'ls -t {path_cs}.bak* 2>/dev/null')
            for line in batchout.strip().split('\n'):
                if line.strip():
                    backups.append(line.strip())
        except:
            pass
        
        if backups:
            backup = backups[0]
            print(f'Найден бэкап: {backup}')
            exec_cmd(f'cp {backup} {path_cs} && echo "RESTORED from {backup}"')
            print('✅ cache_sync.class.processor.php восстановлен из бэкапа')
        else:
            # Откатываем вручную: убираем function_exists из строки 143
            content, _ = exec_cmd(f'cat {path_cs}')
            lines = content.split('\n')
            changed = False
            new_lines = []
            for i, line in enumerate(lines):
                if 'function_exists' in line and 'opcache_reset' in line:
                    # Убираем function_exists проверку
                    fixed = line.replace(' && function_exists(\'opcache_reset\')', '')
                    new_lines.append(fixed)
                    print(f'  Строка {i+1}: удалён function_exists')
                    changed = True
                else:
                    new_lines.append(line)
            
            if changed:
                new_content = '\n'.join(new_lines)
                sftp_put(path_cs, new_content)
                print('✅ cache_sync.class.processor.php откачен (function_exists убран)')
            else:
                print('⚠ Не удалось найти строку для отката')
    else:
        print('function_exists не найден — файл уже в исходном состоянии?')
except Exception as e:
    print(f'Ошибка при работе с cache_sync: {e}')

# 4. Проверяем остальные변화를
print('\n=== ПРОВЕРКА ДРУГИХ ИЗМЕНЕННЫХ ФАЙЛОВ ===')
for f in ['/var/www/u0220513/data/www/sevzakon.ru/.user.ini',
          '/var/www/u0220513/data/www/sevzakon.ru/manager/processors/cache_sync.class.processor.php']:
    try:
        sftp.stat(f)
        print(f'  ✅ ЕСТЬ: {f}')
    except:
        print(f'  ❌ ОТСУТСТВУЕТ: {f}')

# 5. Финальная проверка сайта
print('\n=== ФИНАЛЬНАЯ ПРОВЕРКА САЙТА ===')
code, err = exec_cmd("curl -s -m 20 -o /dev/null -w '%{http_code} %{size_download} bytes %{time_total}s\n' -k https://sevzakon.ru/")
print(f'Главная: {code.strip()}')

code2, err2 = exec_cmd("curl -s -m 20 -o /dev/null -w '%{http_code} %{size_download} bytes %{time_total}s\n' -k -H 'Accept: text/html' https://sevzakon.ru/view/laws/proekty_postanovlenij/2026/pr_post_12_203_ot_18_09_2026/tekst-proekta-postanovleniya132/")
print(f'Страница закона: {code2.strip()}')

cli.close()
print('\n=== ОТКАТ ЗАВЕРШЁН ===')
