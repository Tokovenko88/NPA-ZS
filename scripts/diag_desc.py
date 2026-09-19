#!/usr/bin/env python3
"""Проверка description колонки последних ошибок + поиск источника Parser errors."""
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

php = (
    '<?php' + '\n'
    + '$pdo = new PDO("mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8",' + '\n'
    + '    "u0220513_modx", "xP5rX0bA2rgM0cA2");' + '\n'
    + '$pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);' + '\n'
    + '\n'
    + 'echo "=== Последние 10 ошибок с описанием ===\\n";' + '\n'
    + '$stmt = $pdo->prepare("SELECT id,FROM_UNIXTIME(createdon) t,type,source,description' + '\n'
    + '    FROM modx_event_log WHERE (source LIKE :p1 OR source LIKE :p2)' + '\n'
    + '    ORDER BY id DESC LIMIT 10");' + '\n'
    + '$stmt->execute([":p1" => "%Parse%", ":p2" => "%OPcache%"]);' + '\n'
    + 'foreach ($stmt as $r) {' + '\n'
    + '    echo "ID: " . $r["id"] . " | " . $r["t"] . "\\n";' + '\n'
    + '    echo "Type: " . $r["type"] . " | Source: " . $r["source"] . "\\n";' + '\n'
    + '    echo "Description: " . $r["description"] . "\\n\\n";' + '\n'
    + '}' + '\n'
    + '\n'
    + 'echo "=== Поиск: какие ресурсы вызывают ошибки ===\\n";' + '\n'
    + '$stmt2 = $pdo->prepare("SELECT DISTINCT source, COUNT(*) cnt FROM modx_event_log' + '\n'
    + '    WHERE (source LIKE :p1 OR source LIKE :p2)' + '\n'
    + '    GROUP BY source ORDER BY cnt DESC LIMIT 10");' + '\n'
    + '$stmt2->execute([":p1" => "%Parse%", ":p2" => "%OPcache%"]);' + '\n'
    + 'foreach ($stmt2 as $r) {' + '\n'
    + '    echo "  " . $r["source"] . " : " . $r["cnt"] . " errors\\n";' + '\n'
    + '}' + '\n'
    + '\n'
    + 'echo "\\n=== Хронология за последний час ===\\n";' + '\n'
    + '$stmt3 = $pdo->prepare("SELECT id,FROM_UNIXTIME(createdon) t,source FROM modx_event_log' + '\n'
    + '    WHERE createdon > UNIX_TIMESTAMP()-3600 AND (source LIKE :p1 OR source LIKE :p2)' + '\n'
    + '    ORDER BY id ASC LIMIT 50");' + '\n'
    + '$stmt3->execute([":p1" => "%Parse%", ":p2" => "%OPcache%"]);' + '\n'
    + 'foreach ($stmt3 as $r) {' + '\n'
    + '    echo "[" . $r["id"] . "] " . $r["t"] . " | " . $r["source"] . "\\n";' + '\n'
    + '}' + '\n'
)

print(f'PHP: {len(php)} chars')
print('Writing via SFTP...')
sftp = ssh.open_sftp()
with sftp.file('/tmp/diag_desc.php', 'w') as f:
    f.write(php)
sftp.close()
print('Written /tmp/diag_desc.php')

print('\n=== Running ===')
stdin, stdout, stderr = ssh.exec_command('php /tmp/diag_desc.php', timeout=30)
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
print(out)
if err.strip():
    print('ERRORS:', err[:500])

ssh.close()
print('\nDONE')
