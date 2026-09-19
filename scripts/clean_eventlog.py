#!/usr/bin/env python3
"""Очистка event_log от старых записей Parse Error / Fatal / OPcache."""
import os
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
print('ОЧИСТКА modx_event_log')
print('=' * 60)

# Сначала покажем, что будем удалять
php_preview = (
    "<?php\n"
    "$pdo = new PDO('mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8', "
    "'u0220513_modx', 'xP5rX0bA2rgM0cA2');\n"
    "echo 'Текущее количество записей в event_log: ';\n"
    "echo $pdo->query('SELECT COUNT(*) FROM modx_event_log')->fetchColumn() . \"\\n\\n\";\n"
    "echo 'Записи за последние 30 дней по категориям:\\n';\n"
    "foreach (['Parse Error', 'Fatal', 'Warning', 'OPcache', 'Error'] as $cat) {\n"
    "    $n = $pdo->query(\"SELECT COUNT(*) FROM modx_event_log WHERE createdon > UNIX_TIMESTAMP(NOW() - INTERVAL 30 DAY) AND source LIKE '%{$cat}%'\")->fetchColumn();\n"
    "    echo \"  {$cat}: {$n}\\n\";\n"
    "}\n"
    "echo \"\\n\";\n"
)

sftp = cli.open_sftp()
with sftp.file('/tmp/preview_eventlog.php', 'w') as f:
    f.write(php_preview)
sftp.close()

out, err = run('php /tmp/preview_eventlog.php 2>&1')
print(out)
if err.strip():
    print('[stderr]', err[:300])

print()
print('=' * 60)
print('Удаление старых записей (старше 30 дней) из event_log')
print('=' * 60)

# Удаляем записи старше 30 дней
php_clean = (
    "<?php\n"
    "$pdo = new PDO('mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8', "
    "'u0220513_modx', 'xP5rX0bA2rgM0cA2');\n"
    "echo 'Было: ' . $pdo->query('SELECT COUNT(*) FROM modx_event_log')->fetchColumn() . \"\\n\";\n"
    "$deleted = $pdo->exec(\"DELETE FROM modx_event_log WHERE createdon < UNIX_TIMESTAMP(NOW() - INTERVAL 30 DAY)\");\n"
    "echo 'Удалено записей: ' . $deleted . \"\\n\";\n"
    "echo 'Стало: ' . $pdo->query('SELECT COUNT(*) FROM modx_event_log')->fetchColumn() . \"\\n\";\n"
)

sftp = cli.open_sftp()
with sftp.file('/tmp/clean_eventlog.php', 'w') as f:
    f.write(php_clean)
sftp.close()

out, err = run('php /tmp/clean_eventlog.php 2>&1')
print(out)
if err.strip():
    print('[stderr]', err[:300])

# Проверяем, что не удалили важные записи (последние 10)
print()
print('=' * 60)
print('Проверка: последние 10 записей после очистки')
print('=' * 60)

php_tail = (
    "<?php\n"
    "$pdo = new PDO('mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8', "
    "'u0220513_modx', 'xP5rX0bA2rgM0cA2');\n"
    "foreach ($pdo->query('SELECT id, FROM_UNIXTIME(createdon) t, source FROM modx_event_log ORDER BY id DESC LIMIT 10') as $r) {\n"
    "    echo '[' . $r['id'] . '] ' . $r['t'] . ' | ' . $r['source'] . \"\\n\";\n"
    "}\n"
)

sftp = cli.open_sftp()
with sftp.file('/tmp/tail_eventlog.php', 'w') as f:
    f.write(php_tail)
sftp.close()

out, err = run('php /tmp/tail_eventlog.php 2>&1')
print(out)

cli.close()
print()
print('CLEAN DONE')
