#!/usr/bin/env python3
"""Полная защита от OPcache флуда: комментируем opcache_reset + диагностика."""
import os, re
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
print('SSH connected', flush=True)

SITE_PATH = '/var/www/u0220513/data/www/sevzakon.ru'
CS_PATH = SITE_PATH + '/manager/processors/cache_sync.class.processor.php'
print(f'CACHE_SYNC_PATH: {CS_PATH}', flush=True)

# ============================================================
# ЧАСТЬ 1: Полностью отключаем opcache_reset в cache_sync
# ============================================================
print('\n=== ЧАСТЬ 1: Отключение opcache_reset ===', flush=True)

PHP_DISABLE = (
    b'<?php\n'
    b'$path = ' + repr(CS_PATH).encode() + b';\n'
    b'if (!file_exists($path)) { die(\'NOT FOUND\\n\'); }\n'
    b'$c = file_get_contents($path);\n'
    b'$o = $c;\n'
    b'$s = \'@opcache_reset();\';\n'
    b'$r = \'// @opcache_reset();  // ЗАКОММЕНТИРОВАНО - временная защита от зацикливания\';\n'
    b'$c = str_replace($s, $r, $c);\n'
    b'if ($c !== $o) {\n'
    b'    if (file_put_contents($path, $c)) {\n'
    b'        echo "PATCHED\\n";\n'
    b'    } else {\n'
    b'        echo "SAVE FAILED\\n"; exit(1);\n'
    b'    }\n'
    b'} else {\n'
    b'    echo "NOT FOUND target in file\\n";\n'
    b'}\n'
    b'echo "\\n=== Результат (строки с opcache_reset) ===\\n";\n'
    b'$l = explode("\\n", $c);\n'
    b'foreach ($l as $i => $ln) {\n'
    b'    if (strpos($ln, \'opcache_reset\') !== false) {\n'
    b'        echo ($i + 1) . \': \' . $ln . "\\n";\n'
    b'    }\n'
    b'}\n'
    b'echo "DONE\\n";\n'
)

print('Запись PHP-скрипта на сервер...', flush=True)
sftp = ssh.open_sftp()
with sftp.file('/tmp/disable_opcache.php', 'wb') as f:
    f.write(PHP_DISABLE)
sftp.close()
print('Записано /tmp/disable_opcache.php', flush=True)

stdin, stdout, stderr = ssh.exec_command('php /tmp/disable_opcache.php 2>&1')
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
print(out, flush=True)
if err:
    print('STDERR:', err[:300], flush=True)

# ============================================================
# ЧАСТЬ 2: Поиск всех мест в ядре EVO с opcache_reset
# ============================================================
print('\n=== ЧАСТЬ 2: Все opcache_reset в ядре ===', flush=True)
stdin, stdout, stderr = ssh.exec_command(
    f"grep -rn 'opcache_reset' {SITE_PATH}/manager/ 2>/dev/null | head -50"
)
result = stdout.read().decode('utf-8', errors='replace')
print(result[:3000], flush=True)

print('\n=== ЧАСТЬ 3: Проверка файла ===', flush=True)
stdin, stdout, stderr = ssh.exec_command(f"sed -n '135,155p' {CS_PATH}")
lines = stdout.read().decode('utf-8', errors='replace')
print(lines, flush=True)

ssh.close()
print('\nDONE', flush=True)
