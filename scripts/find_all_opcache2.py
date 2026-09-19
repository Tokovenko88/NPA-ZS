#!/usr/bin/env python3
"""Поиск всех вызовов opcache_reset на сервере."""
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

WEBROOT = '/var/www/u0220513/data/www/sevzakon.ru'

# Ищем ВСЕ вызовы opcache_reset на сервере
cmd = f"grep -rn 'opcache_reset' {WEBROOT}/ --include='*.php' 2>/dev/null | head -50"
stdin, stdout, stderr = ssh.exec_command(cmd)
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
print('=== Все вызовы opcache_reset ===')
print(out)
if err:
    print('ERR:', err[:300])

print('\n=== Контекст вокруг каждого вхождения ===')
cmd2 = f"grep -rn -B5 -A5 'opcache_reset' {WEBROOT}/ --include='*.php' 2>/dev/null | head -200"
stdin, stdout, stderr = ssh.exec_command(cmd2)
out2 = stdout.read().decode('utf-8', errors='replace')
print(out2)

ssh.close()
print('\nDONE')
