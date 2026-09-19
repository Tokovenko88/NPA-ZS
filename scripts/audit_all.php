#!/usr/bin/env python3
"""Проверка всех сниппетов MODX на наличие проблемных конструкций."""
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
print('Сниппеты с <?php внутри тела (потенциальная проблема)')
print('=' * 60)

php = (
    "<?php\n"
    "$pdo = new PDO('mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8', "
    "'u0220513_modx', 'xP5rX0bA2rgM0cA2');\n"
    "foreach ($pdo->query(\"SELECT name, LENGTH(snippet) l, LEFT(snippet, 40) h FROM modx_site_snippets "
    "WHERE snippet LIKE '%<?%' OR snippet LIKE '%?>%' ORDER BY name\") as $r) {\n"
    "    echo $r['name'], ' | len=', $r['l'], ' | head=', $r['h'], \"\\n\";\n"
    "}\n"
)

sftp = cli.open_sftp()
with sftp.file('/tmp/check_snippets.php', 'w') as f:
    f.write(php)
sftp.close()

out, err = run('php /tmp/check_snippets.php 2>&1')
print(out)
if err.strip():
    print('[stderr]', err[:500])

print()
print('=' * 60)
print('Все сниппеты (количество)')
print('=' * 60)
out, err = run('php -r "'
    '\$pdo=new PDO(\'mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8\','
    '\'u0220513_modx\',\'xP5rX0bA2rgM0cA2\');'
    '\$r=\$pdo->query(\'SELECT COUNT(*) c FROM modx_site_snippets\')->fetch();'
    'echo \'total=\'.$r[\'c\'].\'\n\';" 2>&1')
print(out)

print()
print('=' * 60)
print('Parse error в event_log за последние 24 часа')
print('=' * 60)
out, _ = run(
    "php -r \""
    "\$pdo=new PDO('mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8',"
    "'u0220513_modx','xP5rX0bA2rgM0cA2');"
    "\$from=time()-86400;"
    "foreach(\$pdo->query(\"SELECT id,FROM_UNIXTIME(createdon) t,source,`description` FROM modx_event_log"
    " WHERE createdon>\$from AND (source LIKE '%Parse Error%' OR source LIKE '%Fatal%')"
    " ORDER BY id DESC LIMIT 10\") as \$row) {"
    "  echo '['.\$row['id'].'] '.\$row['t'].': '.\$row['source'].'|'.substr(strip_tags(\$row['description']),0,200).\"\\n\\n\";"
    "}\" 2>&1"
)
print(out[:2000] if out else '(нет записей за последние 24 часа)')

print()
print('=' * 60)
print('OPcache warning в event_log за последние 24 часа')
print('=' * 60)
out, _ = run(
    "php -r \""
    "\$pdo=new PDO('mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8',"
    "'u0220513_modx','xP5rX0bA2rgM0cA2');"
    "\$from=time()-86400;"
    "foreach(\$pdo->query(\"SELECT id,FROM_UNIXTIME(createdon) t,source,`description` FROM modx_event_log"
    " WHERE createdon>\$from AND source LIKE '%OPcache%'"
    " ORDER BY id DESC LIMIT 5\") as \$row) {"
    "  echo '['.\$row['id'].'] '.\$row['t'].': '.\$row['description'].\"\\n\\n\";"
    "}\" 2>&1"
)
print(out[:1000] if out else '(нет записей — отлично!)')

cli.close()
print()
print('DONE')
