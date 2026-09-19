#!/usr/bin/env python3
"""Check FPM config and OPcache ini settings on server."""
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

commands = [
    ('=== /etc/php-fpm.d/www.conf ===', 'cat /etc/php-fpm.d/www.conf 2>/dev/null | head -100'),
    ('=== /etc/pool.conf ===', 'cat /etc/pool.conf 2>/dev/null | head -50'),
    ('=== FPM ini files ===', 'find /etc/php -name "*.ini" -path "*fpm*" 2>/dev/null | head -20; echo "---cli---"; find /etc/php -name "*.ini" -path "*cli*" 2>/dev/null | head -20'),
    ('=== opcache ini content ===', 'for f in $(find /etc/php -name "*opcache*" 2>/dev/null); do echo "--- $f ---"; cat "$f"; done; echo "DONE"'),
    ('=== php.ini opcache section ===', 'grep -n -A5 "^opcache" /etc/php.ini 2>/dev/null; grep -n "opcache" /etc/php.ini 2>/dev/null; echo "---END---"'),
    ('=== PHP version check ===', 'php -v 2>/dev/null'),
]

for label, cmd in commands:
    print(f'\n{label}')
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    print(out[:2000])
    if err.strip():
        print('[stderr]', err[:300])

ssh.close()
print('\nDONE')
