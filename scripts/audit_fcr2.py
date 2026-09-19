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
print('SSH connected')


def run(cmd, t=120):
    si, so, se = ssh.exec_command(cmd, timeout=t)
    return (so.read().decode('utf-8', errors='replace'),
            se.read().decode('utf-8', errors='replace'))


FCR_PATH = '/var/www/u0220513/data/www/sevzakon.ru/assets/snippets/firstchildredirect/snippet.firstchildredirect.php'
BASE = '/var/www/u0220513/data/www/sevzakon.ru/'

# 1. Существование
print('\n1. Файл существует:')
out, _ = run('test -f ' + FCR_PATH + ' && echo YES || echo NO')
print(out.strip())

# 2. Содержимое файла через SFTP
print('\n2. Содержимое файла (первые 6000 байт):')
sftp = ssh.open_sftp()
with sftp.open(FCR_PATH, 'r') as f:
    content = f.read(6000).decode('utf-8', errors='replace')
sftp.close()
print('Прочитано', len(content), 'байт')
print('--- СОДЕРЖИМОЕ ---')
print(content)
print('--- КОНЕЦ ---')

# 3. PHP Lint
print('\n3. PHP Lint:')
out, err = run('php -l ' + FCR_PATH + ' 2>&1')
print(out.strip() + err.strip())

# 4. Сниппет в БД
print('\n4. Сниппет в БД (wrapper):')
PHP_Q = (
    '<?php' + '\n'
    + '$p=new PDO("mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8",'
    + '"u0220513_modx","xP5rX0bA2rgM0cA2");' + '\n'
    + '$s=$p->query("SELECT id,name,snippet,description,editedon'
    + ' FROM modx_site_snippets WHERE name=\'FirstChildRedirect\'"
    + '")->fetch(PDO::FETCH_ASSOC);' + '\n'
    + 'echo "ID:".$s["id']."\n";' + '\n'
    + 'echo "NAME:".$s["name']."\n";' + '\n'
    + 'echo "\nSNIPPET BODY:\n".$s["snippet"]."\n";' + '\n'
    + 'echo "\nDESCRIPTION:\n".$s["description"]."\n";' + '\n'
    + 'echo "\neditedon:".date("Y-m-d H:i:s",$s["editedon"])."\n";'
)
with ssh.open_sftp() as sftp2:
    with sftp2.file('/tmp/fcr_q.php', 'w') as f:
        f.write(PHP_Q)
out, err = run('php /tmp/fcr_q.php 2>&1')
print(out[:2000])
if err.strip():
    print('ERR:', err[:300])

# 5. Тест require
print('\n5. Тест require файла:')
PHP_T = (
    '<?php' + '\n'
    + 'define("MODX_BASE_PATH","' + BASE + '");' + '\n'
    + '$file = MODX_BASE_PATH . "assets/snippets/firstchildredirect/snippet.firstchildredirect.php";'
    + '\n'
    + 'echo "File: ".$file."\n";'
    + '\n'
    + 'echo "Exists: ".(file_exists($file) ? "YES" : "NO")."\n";'
    + '\n'
    + 'if (file_exists($file)) {'
    + '\n'
    + '  $r = include $file;'
    + '\n'
    + '  echo "Return type: ".gettype($r)."\n";'
    + '\n'
    + '  echo "Return value: ".(is_null($r) ? "NULL" : (is_bool($r) ? ($r ? "TRUE" : "FALSE") : $r))."\n";'
    + '\n'
    + '} else {'
    + '\n'
    + '  echo "FILE NOT FOUND\n";'
    + '\n'
    + '}'
)
with ssh.open_sftp() as sftp3:
    with sftp3.file('/tmp/fcr_t.php', 'w') as f:
        f.write(PHP_T)
out, err = run('php /tmp/fcr_t.php 2>&1')
print('OUT:', out[:2000])
if err.strip():
    print('ERR:', err[:2000])

ssh.close()
print('\nDONE')
