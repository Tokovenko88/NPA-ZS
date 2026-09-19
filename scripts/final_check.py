#!/usr/bin/env python3
"""Финальная проверка: патч антибота применён, ошибок нет."""
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

ANTIBOT_DIR = '/var/www/u0220513/data/www/sevzakon.ru/antibot'

print('=== Шаг 1: Проверка патча в antibot файлах ===')
files = [
    'code/ab.php',
    'adm/confsave.php',
    'adm/beta.php',
    'adm/update.php',
    'adm/resetcookie.php',
    'adm/phpinfo.php',
    'adm/update2.php',
    'adm/beta2.php',
]
for rel in files:
    path = ANTIBOT_DIR + '/' + rel
    cmd = "grep -n 'opcache_enable' " + path
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode('utf-8', errors='replace')
    if out.strip():
        print('✅ ' + rel + ': ' + out.strip().replace('\n', ' | '))
    else:
        print('❌ ' + rel + ': патч не найден!')

print('\n=== Шаг 2: Все opcache_reset на сайте (должны быть с проверкой) ===')
cmd = "grep -rn 'opcache_reset' /var/www/u0220513/data/www/sevzakon.ru/ 2>/dev/null | grep -v '.bak_' | grep -v '.git'"
stdin, stdout, stderr = ssh.exec_command(cmd)
out = stdout.read().decode('utf-8', errors='replace')
print(out[:2000] if out.strip() else 'Ничего не найдено')

print('\n=== Шаг 3: PHP lint для всех исправленных файлов ===')
for rel in files:
    path = ANTIBOT_DIR + '/' + rel
    cmd = "php -l " + path
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode('utf-8', errors='replace')
    ok = 'No syntax errors' in out
    print(('✅' if ok else '❌') + ' ' + rel)

print('\n=== Шаг 4: Свежие ошибки в event_log ===')
cmd = ("php -r '$pdo=new PDO(\"mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8\","
       "\"u0220513_modx\",\"xP5rX0bA2rgM0cA2\");"
       "foreach($pdo->query(\"SELECT id,FROM_UNIXTIME(createdon) t,source,severity "
       "FROM modx_event_log ORDER BY id DESC LIMIT 10\") as $r) {"
       "echo \"[\".$r[\"id\"].\"]\".$r[\"t\"].\" | \".$r[\"source\"]."
       "\" (severity=\" .$r[\"severity\"] .\")\\n\";}'")
stdin, stdout, stderr = ssh.exec_command(cmd)
out = stdout.read().decode('utf-8', errors='replace')
print(out if out.strip() else '❌ Лог пуст - проблем нет!')

print('\n=== Шаг 5: Счётчик ошибок Parse Error за последние 2 часа ===')
cmd = ("php -r '$pdo=new PDO(\"mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8\","
       "\"u0220513_modx\",\"xP5rX0bA2rgM0cA2\");"
       "$cut = time() - 7200;"
       "$n = $pdo->query(\"SELECT COUNT(*) FROM modx_event_log "
       "WHERE source LIKE \"%Parse Error%\" AND createdon > $cut\")->fetchColumn();"
       "echo \"Parse Error за последние 2 часа: $n\\n\";')")
stdin, stdout, stderr = ssh.exec_command(cmd)
out = stdout.read().decode('utf-8', errors='replace')
print(out.strip())

ssh.close()
print('\nDONE')
