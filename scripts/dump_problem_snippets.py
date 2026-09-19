#!/usr/bin/env python3
"""Дамп содержимого проблемных сниппетов для анализа."""
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


# ID проблемных сниппетов
problem_ids = [125, 150, 167, 173, 182, 239, 240]

for sid in problem_ids:
    print('=' * 70)
    print(f'Сниппет id={sid}')
    print('=' * 70)
    
    php_dump = (
        "<?php\n"
        "$pdo = new PDO('mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8', "
        "'u0220513_modx', 'xP5rX0bA2rgM0cA2');\n"
        "$r = $pdo->query(\"SELECT name, snippet FROM modx_site_snippets WHERE id={$sid}\")->fetch(PDO::FETCH_ASSOC);\n"
        "echo 'Имя: ' . $r['name'] . \"\\n\\n\";\n"
        "echo '=== СОДЕРЖИМОЕ (первые 3000 символов) ===\\n';\n"
        "echo substr($r['snippet'], 0, 3000) . \"\\n\\n\";\n"
        "echo '=== Размер ===\\n';\n"
        "echo 'Длина: ' . strlen($r['snippet']) . \" байт\\n\";\n"
        "echo 'Первый байт: ' . ord($r['snippet'][0]) . \" (BOM=239 или 60 для <)\\n\";\n"
        "echo 'Последние 100 символов:\\n';\n"
        "echo substr($r['snippet'], -100) . \"\\n\";\n"
    )
    
    sftp = cli.open_sftp()
    with sftp.file(f'/tmp/dump_snippet_{sid}.php', 'w') as f:
        f.write(php_dump)
    sftp.close()
    
    out, err = run(f'php /tmp/dump_snippet_{sid}.php 2>&1')
    print(out[:3000])
    if err.strip():
        print('[stderr]', err[:300])
    print()

cli.close()
print('DUMP DONE')
