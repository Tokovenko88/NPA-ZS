#!/usr/bin/env python3
"""Читаем содержимое проблемных файлов антибота с opcache_reset."""
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

ANTIBOT_DIR = '/var/www/u0220513/data/www/sevzakon.ru/antibot'

# Файлы для проверки
files_to_check = [
    'code/ab.php',
    'code/check.php',
    'adm/confsave.php',
    'adm/tpl.php',
    'adm/beta.php',
    'adm/update.php',
    'adm/resetcookie.php',
    'adm/phpinfo.php',
]

print('=== Содержимое файлов антибота (строки с opcache) ===\n')
for f in files_to_check:
    path = os.path.join(ANTIBOT_DIR, f)
    cmd = f"grep -n -B2 -A2 'opcache_reset' {path} 2>/dev/null || echo 'NO_MATCH'"
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode('utf-8', errors='replace')
    print(f'--- {f} ---')
    print(out.strip())
    print()

ssh.close()
print('DONE')
