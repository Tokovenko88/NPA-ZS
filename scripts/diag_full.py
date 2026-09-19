#!/usr/bin/env python3
"""Диагностика: структура таблицы + последние ошибки + FCR."""
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
    + 'echo "=== Структура modx_event_log ===\\n";' + '\n'
    + 'foreach ($pdo->query("SHOW COLUMNS FROM modx_event_log") as $col) {' + '\n'
    + '    echo "  " . $col["Field"] . " (" . $col["Type"] . ")\\n";' + '\n'
    + '}' + '\n'
    + '\n'
    + 'echo "\\n=== Last 30 errors ===\\n";' + '\n'
    + '$stmt = $pdo->prepare("SELECT id,FROM_UNIXTIME(createdon) t,source FROM modx_event_log' + '\n'
    + '    WHERE (source LIKE :p1 OR source LIKE :p2)' + '\n'
    + '    ORDER BY id DESC LIMIT 30");' + '\n'
    + '$stmt->execute([":p1" => "%Parse%", ":p2" => "%OPcache%"]);' + '\n'
    + 'foreach ($stmt as $r) {' + '\n'
    + '    echo "[" . $r["id"] . "] " . $r["t"] . "\\n";' + '\n'
    + '    echo "  Source: " . $r["source"] . "\\n\\n";' + '\n'
    + '}' + '\n'
    + '\n'
    + 'echo "=== FirstChildRedirect ===\\n";' + '\n'
    + '$body = $pdo->query("SELECT snippet FROM modx_site_snippets WHERE name=\'FirstChildRedirect\'")->fetchColumn();' + '\n'
    + 'echo "Size: " . strlen($body) . " bytes\\n";' + '\n'
    + 'echo "First 300 chars:\\n" . substr($body, 0, 300) . "\\n";' + '\n'
    + 'echo "BOM: " . (substr($body, 0, 3) === chr(239).chr(187).chr(191) ? "YES" : "NO") . "\\n";' + '\n'
    + '$first = substr($body, 0, 20);' + '\n'
    + 'echo "Start: [" . $first . "]\\n";' + '\n'
    + 'echo "Has <?php at start: " . (strpos($body, "<?php") === 0 ? "YES" : "NO") . "\\n";' + '\n'
    + 'echo "Has <?php anywhere: " . (strpos($body, "<?php") !== false ? "YES" : "NO") . "\\n";' + '\n'
    + '\n'
    + 'echo "\\n=== Errors per minute ===\\n";' + '\n'
    + '$cnt = $pdo->query("SELECT COUNT(*) FROM modx_event_log WHERE createdon > UNIX_TIMESTAMP()-60")->fetchColumn();' + '\n'
    + 'echo "Total errors last 60s: " . $cnt . "\\n";' + '\n'
    + '$cnt2 = $pdo->query("SELECT COUNT(*) FROM modx_event_log WHERE createdon > UNIX_TIMESTAMP()-60 AND source LIKE \'%Parse%\'")->fetchColumn();' + '\n'
    + 'echo "Parse errors last 60s: " . $cnt2 . "\\n";' + '\n'
)

print(f'PHP: {len(php)} chars')
print('Writing via SFTP...')
sftp = ssh.open_sftp()
with sftp.file('/tmp/diag_full.php', 'w') as f:
    f.write(php)
sftp.close()
print('Written /tmp/diag_full.php')

print('\n=== Running ===')
stdin, stdout, stderr = ssh.exec_command('php /tmp/diag_full.php', timeout=30)
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
print(out)
if err.strip():
    print('ERRORS:', err[:500])

ssh.close()
print('\nDONE')
