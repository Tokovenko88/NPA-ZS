#!/usr/bin/env python3
"""Проверка текущего состояния на сервере."""
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


def run(cmd, t=90):
    si, so, se = ssh.exec_command(cmd, timeout=t)
    return (so.read().decode('utf-8', errors='replace'),
            se.read().decode('utf-8', errors='replace'))


FCR = '/var/www/u0220513/data/www/sevzakon.ru/assets/snippets/firstchildredirect/snippet.firstchildredirect.php'
CS = '/var/www/u0220513/data/www/sevzakon.ru/manager/processors/cache_sync.class.processor.php'
CACHE = '/var/www/u0220513/data/www/sevzakon.ru/assets/cache/siteCache.idx.php'

print('\n1. FCR существует:')
out, _ = run('test -f ' + FCR + ' && echo YES || echo NO')
print(out.strip())

print('\n2. FCR PHP Lint:')
out, _ = run('php -l ' + FCR + ' 2>&1')
print(out.strip())

print('\n3. FCR md5:')
out, _ = run('md5sum ' + FCR)
print(out.strip())

print('\n4. FCR содержимое (первые 30 строк):')
out, _ = run('head -30 ' + FCR)
print(out[:2000])

print('\n5. FCR grep children:')
out, _ = run('grep -n children ' + FCR)
print(out[:300] if out.strip() else '(не найдено)')

print('\n6. cache_sync opcache_reset:')
out, _ = run('grep -n -B1 -A2 opcache_reset ' + CS)
print(out[:500] if out.strip() else '(не найдено)')

print('\n7. Очистка MODX cache:')
out, _ = run('rm -f ' + CACHE + ' 2>/dev/null && echo CLEARED || echo NOT_FOUND')
print(out.strip())

print('\n8. Очистка OPcache через файл:')
PHP_OC = '<?php if(function_exists("opcache_invalidate_file")) { $f="'+FCR+'"; opcache_invalidate_file($f); echo "Invalidated: $f\n"; } else { echo "opcache_invalidate_file not available\n"; }'
sftp = ssh.open_sftp()
with sftp.file('/tmp/invalidate_fcr.php', 'w') as f:
    f.write(PHP_OC)
sftp.close()
out, _ = run('php /tmp/invalidate_fcr.php 2>&1')
print(out.strip())

print('\n9. Последние 5 записей event_log через PHP-скрипт на сервере:')
PHP_LOG = (
    '<?php' + '\n'
    + '$pdo=new PDO("mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8",'
    + '"u0220513_modx","xP5rX0bA2rgM0cA2");' + '\n'
    + '$r=$pdo->query("SELECT id,FROM_UNIXTIME(createdon) t,source FROM modx_event_log ORDER BY id DESC LIMIT 5")->fetchAll(PDO::FETCH_ASSOC);' + '\n'
    + 'foreach($r as $row) { echo "[" . $row["id"] . "] " . $row["t"] . " | " . $row["source"] . "\n"; }'
)
sftp = ssh.open_sftp()
with sftp.file('/tmp/log_query.php', 'w') as f:
    f.write(PHP_LOG)
sftp.close()
out, _ = run('php /tmp/log_query.php 2>&1')
print(out[:1500] if out.strip() else '(пусто)')

print('\n10. FCR содержимое (строки 50-75):')
out, _ = run('sed -n "50,75p" ' + FCR)
print(out[:2000] if out.strip() else '(пусто)')

print('\n11. Проверка OPcache статус:')
out, _ = run('php -r "print_r(opcache_get_status());" 2>&1 | head -20')
print(out[:1000] if out.strip() else '(ошибка или OPcache выключен)')

ssh.close()
print('\nDONE')
