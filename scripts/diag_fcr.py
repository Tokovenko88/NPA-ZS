#!/usr/bin/env python3
"""Диагностика и исправление FirstChildRedirect parse error."""
import os
import time
from dotenv import load_dotenv
import paramiko

load_dotenv('D:/NPA-ZS/.env')
cli = paramiko.SSHClient()
cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
cli.connect(
    os.getenv('MODX_SSH_HOST'),
    port=int(os.getenv('MODX_SSH_PORT', '22')),
    username=os.getenv('MODX_SSH_USERNAME'),
    password=os.getenv('MODX_SSH_PASSWORD'),
    timeout=25,
)


def run(cmd, t=90):
    _i, o, e = cli.exec_command(cmd, timeout=t)
    return o.read().decode('utf-8', 'replace'), e.read().decode('utf-8', 'replace')


print('=' * 60)
print('1. DUMP FirstChildRedirect из БД')
print('=' * 60)

php_dump = (
    "<?php\n"
    "$pdo = new PDO('mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8', "
    "'u0220513_modx', 'xP5rX0bA2rgM0cA2');\n"
    "$s = $pdo->query(\"SELECT snippet FROM modx_site_snippets WHERE name='FirstChildRedirect'\")->fetchColumn();\n"
    "if (empty($s)) { echo 'NOT_FOUND' . \"\\n\"; exit(1); }\n"
    "file_put_contents('/tmp/fcr_dump.php', $s);\n"
    "echo 'len=' . strlen($s) . \"\\n\";\n"
    "echo 'head=' . substr($s, 0, 120) . \"\\n\";\n"
)

sftp = cli.open_sftp()
with sftp.file('/tmp/dump_fcr.php', 'w') as f:
    f.write(php_dump)
sftp.close()

out, err = run('php /tmp/dump_fcr.php 2>&1')
print(out)
if err.strip():
    print('[stderr]', err[:300])

print()
print('=' * 60)
print('2. LINT дампа (php -l)')
print('=' * 60)
out2, err2 = run('php -l /tmp/fcr_dump.php 2>&1')
print(out2)
if err2.strip():
    print('[stderr]', err2[:300])

print()
print('=' * 60)
print('3. Полное содержимое сниппета (первые 3000 символов)')
print('=' * 60)
out3, _ = run('cat /tmp/fcr_dump.php')
print(out3[:3000])

print()
print('=' * 60)
print('4. Поиск возможных проблем (бинарные символы, BOM, <?php дубликат)')
print('=' * 60)
checks = [
    "xxd -l 16 /tmp/fcr_dump.php | head -1",
    "grep -c '<?php' /tmp/fcr_dump.php",
    "grep -c '<?=' /tmp/fcr_dump.php",
    "grep -n '<?php\\|<?=' /tmp/fcr_dump.php",
    "php -r \"echo 'BOM=' . (ord(file_get_contents('/tmp/fcr_dump.php', false, null, 0, 3) === 0xEFBBBF ? 'YES' : 'NO') . \\\"\\n\\\";\"",
]
for cmd in checks:
    out_c, _ = run(cmd)
    print(f'[{cmd}]')
    print(out_c[:500])

cli.close()
print()
print('DIAG COMPLETE')
