#!/usr/bin/env python3
"""Глубокая проверка: почему по-прежнему появляется OPcache warning."""
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


def run(cmd, t=90):
    si, so, se = ssh.exec_command(cmd, timeout=t)
    return (so.read().decode('utf-8', errors='replace'),
            se.read().decode('utf-8', errors='replace'))


CS_PATH = '/var/www/u0220513/data/www/sevzakon.ru/manager/processors/cache_sync.class.processor.php'
BASE = '/var/www/u0220513/data/www/sevzakon.ru/'

# 1. Точной проверка: что делает cache_sync.class.processor.php сейчас
print('\n=== 1. Точная симуляция cache_sync ===')
PHP_TEST = (
    '<?php' + '\n'
    + '$base_path = "' + BASE + '";' + '\n'
    + 'define("MODX_BASE_PATH", $base_path);' + '\n'
    + '$config = array();' + '\n'
    + '$opcache = array();' + '\n'
    + 'echo "OPcache available: " . (function_exists("opcache_reset") ? "YES" : "NO") . "\n";' + '\n'
    + 'echo "OPcache enabled in php.ini: " . ini_get("opcache.enable") . "\n";' + '\n'
    + 'echo "OPcache status: " . (function_exists("opcache_get_status") ? "YES" : "NO") . "\n";' + '\n'
    + '$c = file_get_contents("' + CS_PATH + '");' + '\n'
    + '$lines = explode("\n", $c);' + '\n'
    + 'foreach($lines as $i=>$ln) {' + '\n'
    + '  if(strpos($ln,"opcache_reset")!==false) {' + '\n'
    + '    echo "\nFound at line $i:\n";' + '\n'
    + '    for($j=max(0,$i-3);$j<=min(count($lines)-1,$i+3);$j++) echo "  $j: " . $lines[$j] . "\n";' + '\n'
    + '  }' + '\n'
    + '}' + '\n'
)
sftp = ssh.open_sftp()
with sftp.file('/tmp/test_opc.php', 'w') as f:
    f.write(PHP_TEST)
sftp.close()
out, err = run('php /tmp/test_opc.php 2>&1')
print(out[:2000])
if err.strip():
    print('STDERR:', err[:500])

# 2. Проверка: не изменился ли файл после нашего правки
print('\n=== 2. Проверка изменений в cache_sync ===')
out, _ = run('grep -n "function_exists" ' + CS_PATH)
print('function_exists найден:', 'ДА' if out.strip() else 'НЕТ')
print(out[:300] if out.strip() else '')

# 3. Диагностика: проверка виртуального вызова через require
print('\n=== 3. Проверка require snippet.firstchildredirect.php ===')
PHP_FCR = (
    '<?php' + '\n'
    + 'define("MODX_BASE_PATH", "' + BASE + '");' + '\n'
    + '$modx = new stdClass();' + '\n'
    + '$modx->documentIdentifier = 64685;' + '\n'
    + '$modx->makeUrl = function($id) { return "/test/" . $id; };' + '\n'
    + '$modx->sendRedirect = function($url, $count = 0, $mode = "REDIRECT_HEADER", $header = 0) {' + '\n'
    + '  echo "Redirect to: $url\n";' + '\n'
    + '  return true;' + '\n'
    + '};' + '\n'
    + '$modx->getActiveChildren = function($docid, $sortBy = "menuindex", $sortDir = "ASC") {' + '\n'
    + '  return false;' + '\n'
    + '};' + '\n'
    + 'ob_start();' + '\n'
    + '$result = include MODX_BASE_PATH . "assets/snippets/firstchildredirect/snippet.firstchildredirect.php";' + '\n'
    + '$output = ob_get_clean();' + '\n'
    + 'echo "Output: " . $output . "\n";' + '\n'
    + 'echo "Result: " . var_export($result, true) . "\n";' + '\n'
    + 'echo "ERRORS: " . (error_get_last() ? print_r(error_get_last(), true) : "none") . "\n";' + '\n'
    + 'echo "DONE\n";' + '\n'
)
sftp = ssh.open_sftp()
with sftp.file('/tmp/test_fcr.php', 'w') as f:
    f.write(PHP_FCR)
sftp.close()
out, err = run('php /tmp/test_fcr.php 2>&1')
print(out[:2000])
if err.strip():
    print('STDERR:', err[:500])

# 4. Проверка event_log после очистки кеша (5 записей)
print('\n=== 4. event_log (5 записей до и после 23:40) ===')
PHP_LOG = (
    '<?php' + '\n'
    + '$pdo=new PDO("mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8",' + '\n'
    + '"u0220513_modx","xP5rX0bA2rgM0cA2");' + '\n'
    + '$rows=$pdo->query("SELECT id,FROM_UNIXTIME(createdon) t,source,description' + '\n'
    + ' FROM modx_event_log ORDER BY id DESC LIMIT 10")->fetchAll(PDO::FETCH_ASSOC);' + '\n'
    + 'foreach($rows as $r) {' + '\n'
    + '  echo "[" . $r["id"] . "] " . $r["t"] . "\n";' + '\n'
    + '  echo "Source: " . $r["source"] . "\n";' + '\n'
    + '  echo "Description: " . substr(strip_tags($r["description"]), 0, 200) . "\n";' + '\n'
    + '  echo "---\n";' + '\n'
    + '}' + '\n'
)
sftp = ssh.open_sftp()
with sftp.file('/tmp/log_last.php', 'w') as f:
    f.write(PHP_LOG)
sftp.close()
out, err = run('php /tmp/log_last.php 2>&1')
print(out[:3000] if out.strip() else '(пусто)')
if err.strip():
    print('STDERR:', err[:300])

ssh.close()
print('\nDONE')
