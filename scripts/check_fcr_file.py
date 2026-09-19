#!/usr/bin/env python3
"""Проверка файла snippet.firstchildredirect.php на сервере."""
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

FC_PATH = '/var/www/u0220513/data/www/sevzakon.ru/assets/snippets/firstchildredirect/snippet.firstchildredirect.php'

print(f'\n=== Файл: {FC_PATH} ===')
stdin, stdout, stderr = ssh.exec_command(f'ls -la {FC_PATH}', timeout=10)
print('ls:', stdout.read().decode('utf-8', errors='replace'))

print('\n=== Проверка PHP Lint ===')
stdin, stdout, stderr = ssh.exec_command(f'php -l {FC_PATH}', timeout=10)
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
print('Lint result:', out)
if err.strip():
    print('Errors:', err[:500])

print('\n=== Полное содержимое файла ===')
stdin, stdout, stderr = ssh.exec_command(f'cat {FC_PATH}', timeout=10)
body = stdout.read().decode('utf-8', errors='replace')
print(body)
err2 = stderr.read().decode('utf-8', errors='replace')
if err2.strip():
    print('Errors:', err2[:200])

print('\n=== Поиск синтаксических проблем ===')
# Ищем строки с потенциальными проблемами
stdin, stdout, stderr = ssh.exec_command(f'''php -r '
$body = file_get_contents("''' + FC_PATH + '''");
$lines = explode("\\n", $body);
foreach ($lines as $i => $line) {
    if (strpos($line, "error") !== false || strpos($line, "Error") !== false ||
        strpos($line, "parse") !== false || strpos($line, "die") !== false ||
        strpos($line, "exit") !== false || strpos($line, "?>") !== false) {
        echo "Line " . ($i+1) . ": " . $line . "\\n";
    }
}
echo "\\n=== Проверка require ===\\n";
if (preg_match("/require[^;]+;/", $body, $m)) echo "Require: " . $m[0] . "\\n";
'
''', timeout=15)
out2 = stdout.read().decode('utf-8', errors='replace')
err3 = stderr.read().decode('utf-8', errors='replace')
print(out2)
if err3.strip():
    print('Errors:', err3[:300])

ssh.close()
print('\nDONE')
