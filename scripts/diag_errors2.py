#!/usr/bin/env python3
"""Диагностика: полная информация о последних ошибках + проверка FCR."""
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

print('=== Последние 20 ошибок (с текстом) ===')
stdin, stdout, stderr = ssh.exec_command('''
php -r '
$pdo = new PDO("mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8",
    "u0220513_modx", "xP5rX0bA2rgM0cA2");
foreach ($pdo->query("SELECT id,FROM_UNIXTIME(createdon) t,source,error FROM modx_event_log 
    WHERE source LIKE \"%%Parse%%\" OR source LIKE \"%%OPcache%%\" 
    ORDER BY id DESC LIMIT 20") as $r) {
    echo "[" . $r["id"] . "] " . $r["t"] . "\\n";
    echo "  Source: " . $r["source"] . "\\n";
    echo "  Error:  " . $r["error"] . "\\n\\n";
}
'
''', timeout=15)
out = stdout.read().decode('utf-8', errors='replace')
print(out)
err = stderr.read().decode('utf-8', errors='replace')
if err.strip():
    print('ERRORS:', err[:300])

print('\n=== Текущее тело FirstChildRedirect (первые 500 байт) ===')
stdin, stdout, stderr = ssh.exec_command('''
php -r '
$pdo = new PDO("mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8",
    "u0220513_modx", "xP5rX0bA2rgM0cA2");
$body = $pdo->query("SELECT snippet FROM modx_site_snippets WHERE name=\'FirstChildRedirect\'")->fetchColumn();
echo "Размер: " . strlen($body) . " байт\\n";
echo "Первые 500 символов:\\n";
echo substr($body, 0, 500) . "\\n";
echo "\\n--- BOM check ---\\n";
if (substr($body, 0, 3) === chr(239).chr(187).chr(191)) echo "BOM есть\\n";
else echo "BOM нет\\n";
echo "Начинается с: \"\" . substr($body, 0, 20) . \"\"\\n";
echo "Имеет <?php в начале: " . (strpos($body, "<?php") === 0 ? "ДА" : "НЕТ") . "\\n";
'
''', timeout=15)
out2 = stdout.read().decode('utf-8', errors='replace')
print(out2)
err2 = stderr.read().decode('utf-8', errors='replace')
if err2.strip():
    print('ERRORS:', err2[:300])

print('\n=== Проверка: всё ещё ли ошибки появляются ===')
stdin, stdout, stderr = ssh.exec_command('''
php -r '
$pdo = new PDO("mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8",
    "u0220513_modx", "xP5rX0bA2rgM0cA2");
$cnt = $pdo->query("SELECT COUNT(*) FROM modx_event_log WHERE createdon > UNIX_TIMESTAMP()-60 AND source LIKE \'%%Parse%%\'")->fetchColumn();
echo "Parse errors за последнюю минуту: " . $cnt . "\\n";
$cnt2 = $pdo->query("SELECT COUNT(*) FROM modx_event_log WHERE createdon > UNIX_TIMESTAMP()-60 AND source LIKE \'%%OPcache%%\'")->fetchColumn();
echo "OPcache warnings за последнюю минуту: " . $cnt2 . "\\n";
'
''', timeout=15)
out3 = stdout.read().decode('utf-8', errors='replace')
print(out3)

ssh.close()
print('\nDONE')
