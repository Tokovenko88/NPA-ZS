#!/usr/bin/env python3
"""Полный линт-аудит всех сниппетов MODX + логические проверки."""
import os, re
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


def run(cmd, t=120):
    _i, o, e = cli.exec_command(cmd, timeout=t)
    return o.read().decode('utf-8', 'replace'), e.read().decode('utf-8', 'replace')


print('=' * 60)
print('ШАГ 1. PHP lint для всех сниппетов БД')
print('=' * 60)

# Генерируем PHP-скрипт для линта всех сниппетов
php_lint = (
    "<?php\n"
    "$pdo = new PDO('mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8', "
    "'u0220513_modx', 'xP5rX0bA2rgM0cA2');\n"
    "$pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);\n"
    "$rows = $pdo->query(\"SELECT id, name, snippet FROM modx_site_snippets\")->fetchAll(PDO::FETCH_ASSOC);\n"
    "echo 'Всего сниппетов: ' . count($rows) . \"\\n\\n\";\n"
    "foreach ($rows as $r) {\n"
    "    $tmpFile = '/tmp/snippet_' . $r['id'] . '.php';\n"
    "    file_put_contents($tmpFile, $r['snippet']);\n"
    "    $out = shell_exec('php -l ' . escapeshellarg($tmpFile) . ' 2>&1');\n"
    "    $ok = (strpos($out, 'No syntax errors') !== false);\n"
    "    $mark = $ok ? 'OK' : 'FAIL';\n"
    "    if (!$ok) {\n"
    "        echo '[' . $mark . '] ' . $r['name'] . \" (id={$r['id']})\\n\";\n"
    "        echo '  ' . trim($out) . \"\\n\";\n"
    "    }\n"
    "}\n"
    "echo \"\\nЛинт завершён.\\n\";\n"
)

sftp = cli.open_sftp()
with sftp.file('/tmp/audit_lint_all.php', 'w') as f:
    f.write(php_lint)
sftp.close()

out, err = run('php /tmp/audit_lint_all.php 2>&1')
print(out)
if err.strip():
    print('[stderr]', err[:500])

print()
print('=' * 60)
print('ШАГ 2. Проверка сниппетов с <?php в теле (проблема для MODX eval)')
print('=' * 60)

php_check = (
    "<?php\n"
    "$pdo = new PDO('mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8', "
    "'u0220513_modx', 'xP5rX0bA2rgM0cA2');\n"
    "$rows = $pdo->query(\"SELECT id, name, snippet FROM modx_site_snippets\")->fetchAll(PDO::FETCH_ASSOC);\n"
    "echo 'Сниппеты с <?php внутри тела (потенциальный parse error при eval):\\n\\n';\n"
    "$found = 0;\n"
    "foreach ($rows as $r) {\n"
    "    $body = $r['snippet'];\n"
    "    $has_open = (strpos($body, '<?php') !== false);\n"
    "    $has_open_short = (strpos($body, '<?') !== false && strpos($body, '<?php') === false);\n"
    "    if ($has_open || $has_open_short) {\n"
    "        $found++;\n"
    "        $head = substr($body, 0, 50);\n"
    "        $has_close = (strpos($body, '?>') !== false);\n"
    "        $tag_pos = $has_open ? '<?php@' . (strpos($body, '<?php')+5) : ( $has_open_short ? '<?@' . (strpos($body, '<?')+2) : '' );\n"
    "        echo \"  id={$r['id']} | {$r['name']}\\n\";\n"
    "        echo \"    head: \" . trim($head) . \"\\n\";\n"
    "        echo \"    close_tag: \" . ($has_close ? 'YES' : 'NO') . \"\\n\";\n"
    "        echo \"    tag_pos: {$tag_pos}\\n\\n\";\n"
    "    }\n"
    "}\n"
    "if ($found === 0) echo \"  (нет сниппетов с PHP-тегом в теле — отлично)\\n\";\n"
    "else echo \"  Всего: {$found}\\n\";\n"
)

sftp = cli.open_sftp()
with sftp.file('/tmp/audit_check_tags.php', 'w') as f:
    f.write(php_check)
sftp.close()

out, err = run('php /tmp/audit_check_tags.php 2>&1')
print(out)
if err.strip():
    print('[stderr]', err[:500])

print()
print('=' * 60)
print('ШАГ 3. Логические ошибки типа !$x === false во всех сниппетах')
print('=' * 60)

php_logical = (
    "<?php\n"
    "$pdo = new PDO('mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8', "
    "'u0220513_modx', 'xP5rX0bA2rgM0cA2');\n"
    "$rows = $pdo->query(\"SELECT id, name, snippet FROM modx_site_snippets\")->fetchAll(PDO::FETCH_ASSOC);\n"
    "echo 'Поиск potential логических ошибок (!$x === false / !$x == false):\\n\\n';\n"
    "$pat = '/!\\$[a-zA-Z_][a-zA-Z0-9_]*\\s*===\\s*(true|false)/';\n"
    "foreach ($rows as $r) {\n"
    "    if (preg_match_all($pat, $r['snippet'], $m)) {\n"
    "        foreach ($m[0] as $match) {\n"
    "            echo \"  [!] {$r['name']} (id={$r['id']}): \" . trim($match) . \"\\n\";\n"
    "        }\n"
    "    }\n"
    "}\n"
    "echo \"\\nГотово.\\n\";\n"
)

sftp = cli.open_sftp()
with sftp.file('/tmp/audit_logical.php', 'w') as f:
    f.write(php_logical)
sftp.close()

out, err = run('php /tmp/audit_logical.php 2>&1')
print(out)
if err.strip():
    print('[stderr]', err[:500])

cli.close()
print()
print('AUDIT DONE')
