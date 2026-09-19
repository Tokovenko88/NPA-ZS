#!/usr/bin/env python3
"""Аудит FirstChildRedirect — через SFTP."""
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


def run(cmd, t=120):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=t)
    return (stdout.read().decode('utf-8', errors='replace'),
            stderr.read().decode('utf-8', errors='replace'))


FCR_PATH = '/var/www/u0220513/data/www/sevzakon.ru/assets/snippets/firstchildredirect/snippet.firstchildredirect.php'
BASE = '/var/www/u0220513/data/www/sevzakon.ru/'

print('=== FCR Audit ===\n')

# 1
print('1. Файл существует:')
out, _ = run(f'test -f {FCR_PATH} && echo YES || echo NO')
print(out.strip())

# 2
print('\n2. Содержимое файла (через SFTP, первые 6000 байт):')
sftp = ssh.open_sftp()
with sftp.open(FCR_PATH, 'r') as f:
    content = f.read(6500).decode('utf-8', errors='replace')
sftp.close()
print(f'Прочитано {len(content)} байт из файла')
print('---')
print(content)
print('---')

# 3
print('\n3. PHP Lint:')
out, err = run(f'php -l {FCR_PATH} 2>&1')
print(out.strip() + err.strip())

# 4 - сниппет в БД
print('\n4. Сниппет в БД:')
PHP = '<?php' + '\n' + '$pdo=new PDO("mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8","u0220513_modx","xP5rX0bA2rgM0cA2");' + '\n' + '$s=$pdo->query("SELECT id,name,snippet,description,editedon FROM modx_site_snippets WHERE name=\'FirstChildRedirect\'")->fetch(PDO::FETCH_ASSOC);' + '\n' + 'echo "ID:".$s["id']."\n";' + '\n' + 'echo "BODY:\n".$s["snippet"]."\n";' + '\n' + 'echo "\nDESC:\n".$s["description"]."\n";' + '\n'
sftp = ssh.open_sftp()
with sftp.file('/tmp/fcr_q.php', 'w') as f:
    f.write(PHP)
sftp.close()
out, err = run('php /tmp/fcr_q.php 2>&1')
print(out[:2000])
if err.strip():
    print('ERR:', err[:300])

# 5 - require тест
print('\n5. Тест require:')
PHP2 = '<?php' + '\n' + 'define("MODX_BASE_PATH","' + BASE + '");' + '\n' + '$file = MODX_BASE_PATH."assets/snippets/firstchildredirect/snippet.firstchildredirect.php";' + '\n' + 'echo "File: ".$file."\n";' + '\n' + 'echo "Exists: ".(file_exists($file)?"YES":"NO")."\n";' + '\n' + 'if (file_exists($file)) { $r = include $file; echo "Return: ".(is_null($r)?"NULL":(is_bool($r)?($r?"TRUE":"FALSE"):$r))."\n"; }' + '\n'
sftp = ssh.open_sftp()
with sftp.file('/tmp/fcr_t.php', 'w') as f:
    f.write(PHP2)
sftp.close()
out, err = run('php /tmp/fcr_t.php 2>&1')
print('OUT:', out[:2000])
if err.strip():
    print('ERR:', err[:2000])

ssh.close()
print('\nDONE')
