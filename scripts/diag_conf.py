#!/usr/bin/env python3
"""Диагностика PHP-FPM конфига и OPcache."""
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

for cmd in [
    'echo "=== PHP-FPM pool.d files ==="',
    'ls -la /etc/php/*/fpm/pool.d/ 2>/dev/null || echo "NOT FOUND pool.d"',
    'echo "=== fpm conf files ==="',
    'for f in /etc/php/*/fpm/pool.d/*; do echo "--- $f ---"; cat "$f" 2>/dev/null | head -80; done',
    'echo "=== php.ini locations ==="',
    'php -i 2>/dev/null | grep "Loaded Configuration"',
    'php -i 2>/dev/null | grep "Configuration File"',
    'echo "=== find conf files ==="',
    'ls -la /var/www/u0220513/data/etc/ 2>/dev/null || echo "dir not found"',
    'ls -la /var/www/u0220513/conf/ 2>/dev/null || echo "dir not found"',
]:
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    print(out)
    if err.strip():
        print('[stderr]', err[:200])

ssh.close()
print('\nDONE')
