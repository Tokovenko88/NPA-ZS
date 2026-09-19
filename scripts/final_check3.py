#!/usr/bin/env python3
"""Проверка всех вызовов opcache_reset() и итоговая диагностика."""
import os
from dotenv import load_dotenv
import paramiko

load_dotenv('D:/NPA-ZS/.env')
s = paramiko.SSHClient()
s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
s.connect(
    hostname=os.getenv('MODX_SSH_HOST'),
    port=int(os.getenv('MODX_SSH_PORT', 22)),
    username=os.getenv('MODX_SSH_USERNAME'),
    password=os.getenv('MODX_SSH_PASSWORD'),
    timeout=10,
)

def run(cmd):
    i, o, e = s.exec_command(cmd, timeout=30)
    return o.read().decode('utf-8', errors='replace'), e.read().decode('utf-8', errors='replace')

print('=== 1. Проверка cache_sync.class.processor.php ===')
PATH_CS = '/var/www/u0220513/data/www/sevzakon.ru/manager/processors/cache_sync.class.processor.php'
out, err = run(f'grep -n -B2 -A2 "opcache_reset" {PATH_CS}')
print(out)
if err.strip():
    print('ERR:', err[:200])

print('\n=== 2. Поиск всех вызовов opcache_reset() без function_exists ===')
out2, err2 = run(
    "find /var/www/u0220513/data/www/sevzakon.ru -name '*.php' -type f -exec grep -l 'opcache_reset' {} \\; 2>/dev/null"
)
files = [f for f in out2.strip().split('\n') if f.strip()]
print(f'Найдено файлов с opcache_reset: {len(files)}')
for f in files[:20]:
    print(f'\n--- {f} ---')
    out3, err3 = run(f'grep -n -B3 -A2 "opcache_reset" "{f}"')
    print(out3[:500] if out3.strip() else '(пусто)' + (err3 if err3 else ''))
    if err3.strip():
        print('ERR:', err3[:200])

print('\n=== 3. Проверка antibot файлов на opcache_reset ===')
out4, err4 = run(
    "find /var/www/u0220513/data/www/sevzakon.ru/antibot -name '*.php' -type f -exec grep -l 'opcache_reset' {} \\; 2>/dev/null"
)
ab_files = [f for f in out4.strip().split('\n') if f.strip()]
print(f'Antibot файлов с opcache_reset: {len(ab_files)}')
for f in ab_files:
    print(f'\n--- {f} ---')
    out5, err5 = run(f'grep -n -B3 -A2 "opcache_reset" "{f}"')
    print(out5[:400] if out5.strip() else '(пусто)')

print('\n=== 4. Итоговый тест — эмуляция cache_sync ===')
# Используем только ASCII
test_emul = (
    b'<?php' + b'\n'
    b'header("Content-Type: text/plain; charset=utf-8");' + b'\n'
    b'echo "Test of reset emulation\n";' + b'\n'
    b'$opcache = opcache_get_status();' + b'\n'
    b'echo "OPcache enabled: " . ($opcache["opcache_enabled"] ? "YES" : "NO") . "\n";' + b'\n'
    b'if (!empty($opcache[\'opcache_enabled\']) && ini_get(\'opcache.enable\') && function_exists(\'opcache_reset\')) {' + b'\n'
    b'    @opcache_reset();' + b'\n'
    b'    echo "opcache_reset() called successfully\n";' + b'\n'
    b'} else {' + b'\n'
    b'    echo "opcache_reset() NOT called (condition not met)\n";' + b'\n'
    b'}' + b'\n'
    b'echo "DONE\n";' + b'\n'
)
sftp = s.open_sftp()
with sftp.file('/var/www/u0220513/data/www/sevzakon.ru/test_reset.php', 'wb') as f:
    f.write(test_emul)
sftp.close()
print('Создан test_reset.php')

out6, err6 = run('curl -s -m 15 -k -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" "https://sevzakon.ru/test_reset.php"')
print('\nРезультат теста:')
print(out6)
if err6.strip():
    print('ERR:', err6[:300])

print('\n=== 5. Очистка ===')
run('rm -f /var/www/u0220513/data/www/sevzakon.ru/test_reset.php')

print('\n=== 6. Проверка — нет ли новых ошибок OPcache в логе ===')
out7, err7 = run(
    "php -r '$pdo=new PDO(\"mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8\",\"u0220513_modx\",\"xP5rX0bA2rgM0cA2\");"
    " foreach($pdo->query(\"SELECT id,FROM_UNIXTIME(createdon) t,source FROM modx_event_log ORDER BY id DESC LIMIT 10\") as $r)"
    " echo \"[\".$r[\"id\"].\"]\".$r[\"t\"].\" | \".$r[\"source\"].\"\\n\";'"
)
print('Последние 10 записей в event_log:')
print(out7)
if err7.strip():
    print('ERR:', err7[:300])

s.close()
print('\nDONE')
