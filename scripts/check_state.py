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


fcr_path = '/var/www/u0220513/data/www/sevzakon.ru/assets/snippets/firstchildredirect/snippet.firstchildredirect.php'
cs_path = '/var/www/u0220513/data/www/sevzakon.ru/manager/processors/cache_sync.class.processor.php'

print('\n=== 1. FCR файл ===')
out, _ = run('test -f ' + fcr_path + ' && echo YES || echo NO')
print('Существует:', out.strip())

out, _ = run('php -l ' + fcr_path)
print('PHP Lint:', out.strip())

out, _ = run('grep -n "children === false" ' + fcr_path)
print('Проблемный код (if (!$children === false)):', 'НЕТ' if not out.strip() else 'ДА - ошибка!')
print(out[:300] if out.strip() else '')

out, _ = run('grep -n "children !== false" ' + fcr_path)
print('Правильный код (if ($children !== false)):', out.strip()[:200] if out.strip() else 'НЕТ')

print('\n=== 2. cache_sync.class.processor.php ===')
out, _ = run('grep -n -B1 -A2 "opcache_reset" ' + cs_path)
print('Содержимое вокруг opcache_reset:')
print(out[:500])

print('\n=== 3. Последние ошибки в логе ===')
out, _ = run("php -r '$p=new PDO(\"mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8\",\"u0220513_modx\",\"xP5rX0bA2rgM0cA2\"); foreach($p->query(\"SELECT id,FROM_UNIXTIME(createdon) t,source FROM modx_event_log ORDER BY id DESC LIMIT 5\") as $r) echo \"[\".$r[\"id\"]."] ".$r["t"]." | ".$r["source"]."\\n\";' 2>&1")


print(out[:1500])

ssh.close()
print('\nDONE')
