#!/usr/bin/env python3
"""Поиск cache_sync и opcache_reset в правильной директории сайта."""
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

SITE_DIR = '/var/www/u0220513/data'

print(f'SITE_DIR = {SITE_DIR}')

# 1. Проверка содержимого корня сайта
print('\n=== Корень сайта ===')
stdin, stdout, stderr = ssh.exec_command(f'ls -la {SITE_DIR}/')
print(stdout.read().decode('utf-8', errors='replace')[:3000])

# 2. Поиск manager/processors/
print('\n=== manager/processors/ ===')
stdin, stdout, stderr = ssh.exec_command(
    f'ls -la {SITE_DIR}/manager/processors/ 2>/dev/null || echo "NO manager/processors/"'
)
print(stdout.read().decode('utf-8', errors='replace')[:2000])

# 3. Поиск cache_sync.class.processor.php
print('\n=== cache_sync.class.processor.php ===')
stdin, stdout, stderr = ssh.exec_command(
    f'find {SITE_DIR} -name "cache_sync.class.processor.php" -type f 2>/dev/null'
)
found = stdout.read().decode('utf-8', errors='replace').strip()
print(f'Найдено: {found or "НЕТ"}')
if found:
    cache_sync_path = found.split()[0]  # берём первый путь

# 4. Проверка наличия opcache_reset в cache_sync
print('\n=== opcache_reset в cache_sync ===')
if found:
    stdin, stdout, stderr = ssh.exec_command(
        f"grep -n 'opcache_reset\\|opcache_enable\\|opcache.enable' {cache_sync_path}"
    )
    print(stdout.read().decode('utf-8', errors='replace'))
    if stderr.read().decode('utf-8', errors='replace').strip():
        print('(stderr):', stderr.read().decode('utf-8', errors='replace'))

# 5. Общий поиск opcache_reset в директории сайта
print('\n=== Все файлы с opcache_reset в сайте ===')
stdin, stdout, stderr = ssh.exec_command(
    f"grep -r 'opcache_reset' {SITE_DIR} 2>/dev/null | head -20"
)
print(stdout.read().decode('utf-8', errors='replace'))

# 6. Бэкап cache_sync перед патчем
print('\n=== Бэкап cache_sync ===')
if found:
    cache_sync_path = found.split()[0]
    stdin, stdout, stderr = ssh.exec_command(
        f"cp {cache_sync_path} {cache_sync_path}.bak_$(date +%Y%m%d_%H%M%S) && echo 'BACKED UP'"
    )
    print(stdout.read().decode('utf-8', errors='replace'))

# 7. Эхо content cache_sync.class.processor.php
print('\n=== Текущее состояние cache_sync (строки с opcache) ===')
if found:
    cache_sync_path = found.split()[0]
    stdin, stdout, stderr = ssh.exec_command(
        f"grep -n -A2 -B2 'opcache' {cache_sync_path}"
    )
    print(stdout.read().decode('utf-8', errors='replace'))

ssh.close()
print('\nDONE')
