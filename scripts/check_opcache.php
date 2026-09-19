#!/usr/bin/env python3
"""Проверка OPcache и FirstChildRedirect на сервере."""
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

# 1. PHP version
print('\n=== PHP Version ===')
stdin, stdout, stderr = ssh.exec_command('php -v')
print(stdout.read().decode('utf-8', errors='replace')[:500])

# 2. php.ini opcache settings
print('\n=== OPcache ini values ===')
stdin, stdout, stderr = ssh.exec_command(
    "php -r '"
    "echo \"opcache.enable=\" . ini_get(\"opcache.enable\") . \"\\n\"; "
    "echo \"opcache.enable_cli=\" . ini_get(\"opcache.enable_cli\") . \"\\n\"; "
    "echo \"opcache.memory_consumption=\" . ini_get(\"opcache.memory_consumption\") . \"\\n\"; "
    "echo \"opcache.interned_strings_buffer=\" . ini_get(\"opcache.interned_strings_buffer\") . \"\\n\"; "
    "echo \"opcache.max_accelerated_files=\" . ini_get(\"opcache.max_accelerated_files\") . \"\\n\"; "
    "echo \"opcache.validate_timestamps=\" . ini_get(\"opcache.validate_timestamps\") . \"\\n\"; "
    "echo \"opcache.revalidate_freq=\" . ini_get(\"opcache.revalidate_freq\") . \"\\n\"; "
    "'"
)
print(stdout.read().decode('utf-8', errors='replace'))

# 3. Список модулей PHP
print('\n=== PHP Modules (opcache-related) ===')
stdin, stdout, stderr = ssh.exec_command('php -m')
modules = stdout.read().decode('utf-8', errors='replace')
print(modules)
print('\nOPcache в модулях:', 'OPcache' in modules)

# 4. Проверка php.ini файл
print('\n=== php.ini location ===')
stdin, stdout, stderr = ssh.exec_command('php --ini')
print(stdout.read().decode('utf-8', errors='replace'))

# 5. Проверить php.ini на наличие opcache directives
print('\n=== grep opcache в php.ini ===')
stdin, stdout, stderr = ssh.exec_command(
    "grep -i 'opcache' /etc/php.ini 2>/dev/null || echo 'NOT FOUND in /etc/php.ini'"
)
print(stdout.read().decode('utf-8', errors='replace'))

# 6. Доступные .ini файлы в php.d
print('\n=== PHP ini files in php.d ===')
stdin, stdout, stderr = ssh.exec_command(
    "ls -la /etc/php.d/ 2>/dev/null || echo 'NO /etc/php.d'"
)
print(stdout.read().decode('utf-8', errors='replace'))

# 7. Проверить наличие opcache.ini
stdin, stdout, stderr = ssh.exec_command(
    "cat /etc/php.d/10-opcache.ini 2>/dev/null || cat /etc/php.d/opcache.ini 2>/dev/null || echo 'No opcache ini found'"
)
print('\n=== opcache.ini ===')
print(stdout.read().decode('utf-8', errors='replace'))

ssh.close()
print('\nDONE')
