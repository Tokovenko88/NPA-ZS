#!/usr/bin/env python3
"""PHP-скрипт патча антибота — вызываем на сервере напрямую."""
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

# PHP-скрипт патча — чиним антибот, добавляем проверку ini_get('opcache.enable')
PHP_CODE = r"""<?php
$antibot_dir = '/var/www/u0220513/data/www/sevzakon.ru/antibot';
$files = [
    'code/ab.php',
    'adm/confsave.php',
    'adm/beta.php',
    'adm/update.php',
    'adm/resetcookie.php',
    'adm/phpinfo.php',
    'adm/update2.php',
    'adm/beta2.php',
];

$old = "if(function_exists('opcache_reset')) {";
$new = "if(function_exists('opcache_reset') && ini_get('opcache.enable')) {";

echo "=== Патч антибота ===\n";
echo "OLD: $old\n";
echo "NEW: $new\n\n";

$ok = 0;
$total = 0;

foreach ($files as $rel) {
    $path = $antibot_dir . '/' . $rel;
    echo "--- $rel ---\n";
    
    if (!file_exists($path)) {
        echo "  ❌ Файл не найден\n";
        continue;
    }
    
    $content = file_get_contents($path);
    $cnt = substr_count($content, $old);
    
    if ($cnt == 0) {
        echo "  ⚠️  Паттерн не найден (возможно уже исправлен)\n";
        continue;
    }
    
    $new_content = str_replace($old, $new, $content);
    
    if ($new_content === $content) {
        echo "  ⚠️  Без изменений\n";
        continue;
    }
    
    // Бэкап
    $backup = $path . '.bak_' . date('Ymd_His');
    if (!copy($path, $backup)) {
        echo "  ⚠️  Не удалось создать бэкап\n";
    }
    
    // Запись
    if (file_put_contents($path, $new_content) === false) {
        echo "  ❌ Ошибка записи\n";
        continue;
    }
    
    // Lint
    $tmp = '/tmp/lint_' . md5($rel) . '.php';
    file_put_contents($tmp, $new_content);
    $lint_out = shell_exec("php -l $tmp 2>&1");
    $lint_ok = strpos($lint_out, 'No syntax errors') !== false;
    @unlink($tmp);
    
    $status = $lint_ok ? '✅ OK' : '❌ LINT FAIL';
    echo "  $status: $cnt замен, lint: " . ($lint_ok ? 'OK' : 'FAIL') . "\n";
    if (!$lint_ok) echo "    $lint_out\n";
    
    $total += $cnt;
    if ($lint_ok) $ok++;
}

echo "\n=== Итог ===\n";
echo "Исправлено файлов: $ok / " . count($files) . "\n";
echo "Всего замен: $total\n";
echo "=== Конец ===\n";
"""

# Записываем PHP-скрипт на сервер через SFTP
print('Загрузка PHP-скрипта патча на сервер...')
sftp = ssh.open_sftp()
with sftp.file('/tmp/patch_antibot.php', 'w') as f:
    f.write(PHP_CODE)
sftp.close()
print('Загружено: /tmp/patch_antibot.php')

print('\n=== Запуск патча ===')
stdin, stdout, stderr = ssh.exec_command('php /tmp/patch_antibot.php 2>&1')
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
print(out)
if err.strip():
    print('[stderr]', err[:300])

print('\n=== Проверка: войдет ли antibot в запрос ===')
cmd = "grep -rn 'antibot/code/ab.php' /var/www/u0220513/data/www/sevzakon.ru/ 2>/dev/null | head -5"
stdin, stdout, stderr = ssh.exec_command(cmd)
out = stdout.read().decode('utf-8', errors='replace')
print(out if out.strip() else 'Вызовы не найдены')

print('\n=== Свежий event_log ===')
cmd = ("php -r '$pdo=new PDO(\"mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8\","
       "\"u0220513_modx\",\"xP5rX0bA2rgM0cA2\");"
       "foreach($pdo->query(\"SELECT id,FROM_UNIXTIME(createdon) t,source,severity "
       "FROM modx_event_log ORDER BY id DESC LIMIT 5\") as $r) {"
       "echo \"[\".$r[\"id\"].\"]\".$r[\"t\"].\" | \".$r[\"source\"]."
       "\" (severity=\" .$r[\"severity\"] .\")\\n\";}'")
stdin, stdout, stderr = ssh.exec_command(cmd)
out = stdout.read().decode('utf-8', errors='replace')
print(out if out.strip() else 'Лог пуст')

ssh.close()
print('\nDONE')
