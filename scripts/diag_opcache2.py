#!/usr/bin/env python3
"""Диагностика: где именно вызывается opcache_reset()."""
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


def run(cmd, t=120):
    stdin, stdout, stderr = cli.exec_command(cmd, timeout=t)
    out = stdout.read().decode('utf-8', 'replace')
    err = stderr.read().decode('utf-8', 'replace')
    return out, err

print('=' * 60)
print('1. Патч в cache_sync.class.processor.php')
print('=' * 60)
out, err = run(
    "grep -n 'ini_get\\|opcache_reset\\|@opcache_reset' "
    "/home/u0220513/new_deploy/manager/processors/cache_sync.class.processor.php"
)
print(out)
if err.strip():
    print(f'[stderr] {err[:300]}')

print()
print('=' * 60)
print('2. ВСЕ файлы с opcache_reset на сервере')
print('=' * 60)
out2, err2 = run(
    "find /home/u0220513/new_deploy -name '*.php' "
    "-exec grep -l 'opcache_reset' {} \\; 2>/dev/null | sort"
)
print(out2)
if err2.strip():
    print(f'[stderr] {err2[:300]}')

print()
print('=' * 60)
print('3. PHP opcache.enable')
print('=' * 60)
out3, err3 = run('php -r "echo ini_get(\'opcache.enable\').\'\n\';"')
print(f'opcache.enable = {out3.strip()}')
if err3.strip():
    print(f'[stderr] {err3[:300]}')

print()
print('=' * 60)
print('4. opcache_get_status')
print('=' * 60)
out4, err4 = run(
    "php -r 'print_r(opcache_get_status());' 2>&1 | head -40"
)
print(out4[:2000])
if err4.strip():
    print(f'[stderr] {err4[:300]}')

print()
print('=' * 60)
print('5. Кэш-файлы sevzakon (find) и модель кэша')
print('=' * 60)
out5, err5 = run(
    "ls -la /home/u0220513/new_deploy/assets/cache/ 2>/dev/null | head -10 || "
    "echo 'NO ASSETS CACHE DIRECTORY'"
)
print(out5)

print()
print('=' * 60)
print('6. Ресурс [64685] — какие сниппеты в контенте')
print('=' * 60)
out6, err6 = run(
    "php -r "
    "'\$pdo=new PDO('mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8',"
    "'u0220513_modx','xP5rX0bA2rgM0cA2');"
    "\$r=\$pdo->query(\"SELECT content,template FROM modx_site_content WHERE id=64685\")"
    "->fetch(PDO::FETCH_ASSOC);"
    "echo \"template:\".\$r['template'].\"\n\n\";",
    t=30,
)
print(out6[:500])
if err6.strip():
    print(f'[stderr] {err6[:300]}')

print()
print('=' * 60)
print('7. Content сниппетов page (поиск чанков/сниппетов в контенте)')
print('=' * 60)
out7, err7 = run(
    "php -r "
    "'\$pdo=new PDO('mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8',"
    "'u0220513_modx','xP5rX0bA2rgM0cA2');"
    "\$c=\$pdo->query(\"SELECT content FROM modx_site_content WHERE id=64685\")->fetchColumn();"
    "preg_match_all('/\\\$\\\{([^\\}]+)\\\}/', \$c, \$m);"
    "echo \"tags in content:\\n\";",
    t=30,
)
print(out7[:500])
if err7.strip():
    print(f'[stderr] {err7[:300]}')

cli.close()
print('\nDONE')
