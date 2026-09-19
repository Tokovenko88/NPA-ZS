#!/usr/bin/env python3
"""Проверка: последние записи в event_log и статус патча."""
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

print('=== Последние 10 записей в event_log ===')
stdin, stdout, stderr = ssh.exec_command('''
php -r '
$pdo = new PDO("mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8",
    "u0220513_modx", "xP5rX0bA2rgM0cA2");
foreach ($pdo->query("SELECT id,FROM_UNIXTIME(createdon) t,source FROM modx_event_log ORDER BY id DESC LIMIT 10") as $r) {
    echo "[" . $r["id"] . "] " . $r["t"] . " | " . $r["source"] . "\\n";
}
'
''', timeout=15)
out = stdout.read().decode('utf-8', errors='replace')
print(out)
err = stderr.read().decode('utf-8', errors='replace')
if err.strip():
    print('ERRORS:', err[:300])

print('\n=== Статус патча ===')
stdin, stdout, stderr = ssh.exec_command(
    "grep -n 'function_exists' '/var/www/u0220513/data/www/sevzakon.ru/manager/processors/cache_sync.class.processor.php'",
    timeout=10
)
out2 = stdout.read().decode('utf-8', errors='replace')
print(out2)

print('\n=== Проверка: opcache_enable в php.ini ===')
stdin, stdout, stderr = ssh.exec_command(
    "php -r 'echo \"opcache.enable = \" . ini_get(\"opcache.enable\") . \"\\n\"; echo \"opcache.enable_cli = \" . ini_get(\"opcache.enable_cli\") . \"\\n\";'",
    timeout=10
)
out3 = stdout.read().decode('utf-8', errors='replace')
print(out3)

ssh.close()
print('\nDONE')
