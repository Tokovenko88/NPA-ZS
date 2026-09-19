#!/usr/bin/env python3
"""Часть 2: Автоматическое исправление OPcache."""
import os
from dotenv import load_dotenv
import paramiko
import subprocess
import time

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

SITE = '/var/www/u0220513/data/www/sevzakon.ru'
SITE_URL = 'sevzakon.ru'

def run(cmd, t=60):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=t)
    return stdout.read().decode('utf-8', errors='replace'), stderr.read().decode('utf-8', errors='replace')

def header(title):
    print()
    print('=' * 70)
    print(title)
    print('=' * 70)

print('=== Если используется PHP-FPM, создаём .user.ini ===')
header('Создание .user.ini в корне сайта')
out, err = run(f'''
echo "opcache.enable=1" > {SITE}/.user.ini
echo "opcache.memory_consumption=128" >> {SITE}/.user.ini
echo "opcache.max_accelerated_files=4000" >> {SITE}/.user.ini
echo "opcache.revalidate_freq=60" >> {SITE}/.user.ini
echo "opcache.fast_shutdown=1" >> {SITE}/.user.ini
echo "opcache.enable_cli=1" >> {SITE}/.user.ini
cat {SITE}/.user.ini
''')
print(out[:1000])
if err.strip():
    print('stderr:', err[:300])

print()
print('=== Перезагрузка PHP-FPM ===')
header('Перезагрузка PHP-FPM сервиса')
out, err = run('''
echo "Пытаемся перезагрузить PHP-FPM..."
for svc in php8.3-fpm php8.2-fpm php8.1-fpm php8.0-fpm php7.4-fpm; do
    if service $svc status >/dev/null 2>&1; then
        echo "Нашли сервис: $svc"
        service $svc restart 2>&1 && echo "Перезагрузка $svc: OK" || echo "Перезагрузка $svc: ОШИБКА"
        break
    fi
done
if ! service php*-fpm status >/dev/null 2>&1; then
    echo "PHP-FPM сервис не найден. Проверяем альтернативы..."
    systemctl restart php*-fpm 2>/dev/null && echo "systemctl restart OK" || echo "systemctl не сработал"
    service --status-all 2>/dev/null | grep -i fpm
fi
''')
print(out[:2000])
if err.strip():
    print('stderr:', err[:300])

print()
print('=== Проверка после перезагрузки ===')
header('Проверка OPcache в CLI после перезагрузки')
out, _ = run('''
php -r "echo \"extension_loaded(opcache): \" . (extension_loaded(\"opcache\") ? \"YES\" : \"NO\") . \"\\n\"; echo \"function_exists(opcache_reset): \" . (function_exists(\"opcache_reset\") ? \"YES\" : \"NO\") . \"\\n\"; echo \"ini_get(enable): [\" . ini_get(\"opcache.enable\") . \"]\\n\"; if (function_exists(\"opcache_get_status\")) { \$s = opcache_get_status(); echo \"opcache_get_status(): \" . (\$s ? \"включен\" : \"выключен\") . \"\\n\"; } else { echo \"opcache_get_status(): нет функции\\n\"; }" 2>&1
''')
print(out)

print()
print('=== Проверка через веб ===')
header('Проверка OPcache через веб-запрос')
try:
    result = subprocess.run(
        ['curl', '-s', '--max-time', '10', f'http://{SITE_URL}/test_opcache_web.php'],
        capture_output=True, text=True, timeout=15
    )
    print('Ответ сервера:')
    print(result.stdout[:1500])
    if result.stderr:
        print('STDERR:', result.stderr[:300])
except Exception as e:
    print(f'Ошибка curl: {e}')

print()
print('=== Проверка .htaccess - php_flag вместо php_value ===')
header('Исправление .htaccess (php_flag вместо php_value)')
out, err = run(f'''
echo "Текущий блок mod_php в .htaccess:"
grep -n -A10 "IfModule mod_php" {SITE}/.htaccess 2>/dev/null
echo ""
echo "--- Создаём исправленную версию (опционально) ---"
echo "Если нужно, заменить php_value на php_flag:"
echo "php_flag opcache.enable On"
echo "php_flag opcache.enable_cli On"
echo ""
echo "Рекомендуется добавить в начало .htaccess (перед остальным):"
echo "<IfModule mod_php7.c>"
echo "  php_flag opcache.enable On"
echo "  php_flag opcache.enable_cli On"
echo "</IfModule>"
''')
print(out[:2000])

print()
print('=== Поиск оставшихся проблемных вызовов ===')
header('Файлы, где opcache_reset() без function_exists (после исправления)')
out, _ = run(f'''
cd {SITE}
echo "=== Все вызовы opcache_reset в ядре MODX ==="
grep -rn "opcache_reset" manager/ processors/ --include="*.php" 2>/dev/null
echo ""
echo "=== Все вызовы в antibot ==="
grep -rn "opcache_reset" antibot/ --include="*.php" 2>/dev/null
echo ""
echo "=== Все вызовы в остальных файлах ==="
grep -rn "opcache_reset" --include="*.php" . 2>/dev/null | grep -v manager/ | grep -v antibot/ | grep -v ".user.ini" | grep -v test_opcache | grep -v "function_exists" | head -20
''')
print(out[:3000])

ssh.close()
print('\n✅ Исправление завершено')

#!/usr/bin/env python3
"""Финальный патч cache_sync.class.processor.php."""
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
    timeout=25,
)
print('SSH connected')

PATH = '/var/www/u0220513/data/www/sevzakon.ru/manager/processors/cache_sync.class.processor.php'

# PHP-скрипт — r-строка: Python не интерпретирует escape-последовательности
PHP_PATCH = r"""<?php
$path = '/var/www/u0220513/data/www/sevzakon.ru/manager/processors/cache_sync.class.processor.php';
if(!file_exists($path)){die("FILE NOT FOUND\n");}
$c = file_get_contents($path);
$o = $c;

$old = "if (!empty(\$opcache['opcache_enabled']) && ini_get('opcache.enable')) {";
$new = "if (!empty(\$opcache['opcache_enabled']) && ini_get('opcache.enable') && function_exists('opcache_reset')) {";

$pos = strpos($c, $old);
if($pos !== false){
  $after = substr($c, $pos + strlen($old));
  if(strpos($after, "opcache_reset") !== false){
    $c = str_replace($old, $new, $c);
    echo "PATCHED\n";
    echo "OLD: ".$old."\n";
    echo "NEW: ".$new."\n";
  } else {
    echo "FOUND but no opcache_reset after\n";
    $lines = explode("\n", $c);
    foreach($lines as $i=>$ln){
      if(strpos($ln,"opcache_reset")!==false) echo "  line $i: $ln\n";
    }
  }
} else {
  echo "PATTERN NOT FOUND\n";
  $lines = explode("\n", $c);
  foreach($lines as $i=>$ln){
    if(strpos($ln,"opcache_reset")!==false) echo "  line $i: $ln\n";
  }
}

if($c !== $o){
  if(file_put_contents($path, $c)){ echo "SAVED\n"; }
  else { echo "SAVE FAILED\n"; exit(1); }
} else { echo "NO CHANGE\n"; }
echo "DONE\n";
"""

print('PHP script size:', len(PHP_PATCH), 'bytes')

# Записываем через SFTP
sftp = ssh.open_sftp()
with sftp.file('/tmp/patch_cs_final.php', 'w') as f:
    f.write(PHP_PATCH)
sftp.close()
print('Written to /tmp/patch_cs_final.php')

# Запускаем
print('\n=== RUNNING PATCH ===')
stdin, stdout, stderr = ssh.exec_command('php /tmp/patch_cs_final.php')
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
print('OUTPUT:')
print(out)
if err: print('STDERR:', err[:300])

# Проверяем результат
print('\n=== VERIFICATION: opcache_reset lines ===')
stdin, stdout, stderr = ssh.exec_command(f"grep -n -B1 -A2 'function_exists.*opcache_reset\|opcache_enable.*opcache_reset\|opcache_reset()' {PATH}")
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
print(out)
if err: print('STDERR:', err[:300])

ssh.close()
print('\nDONE')
