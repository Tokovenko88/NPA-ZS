#!/usr/bin/env python3
"""Часть 1: Диагностика OPcache на сервере."""
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

SITE = '/var/www/u0220513/data/www/sevzakon.ru'

def run(cmd, t=60):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=t)
    return stdout.read().decode('utf-8', errors='replace'), stderr.read().decode('utf-8', errors='replace')

def header(title):
    print()
    print('=' * 70)
    print(title)
    print('=' * 70)

# 1. PHP SAPI
header('1. PHP Server API (SAPI) и версия')
out, _ = run('php -i 2>/dev/null | grep -E "Server API|PHP Version|Loaded Configuration File|Scan this dir|Additional .ini files"')
print(out)

# 2. OPcache в CLI
header('2. OPcache в CLI-контексте')
out, _ = run('php -r "echo \"extension_loaded: \" . (extension_loaded(\"opcache\") ? \"YES\" : \"NO\") . \"\\n\"; echo \"function_exists(opcache_reset): \" . (function_exists(\"opcache_reset\") ? \"YES\" : \"NO\") . \"\\n\"; echo \"ini_get(enable): [\" . ini_get(\"opcache.enable\") . \"]\\n\"; echo \"SAPI: \" . PHP_SAPI . \"\\n\";"')
print(out)

# 3. Загруженные модули Apache
header('3. Загруженные модули Apache (php-related)')
out, _ = run('apachectl -M 2>/dev/null | grep -i "php\|proxy_fcgi\|proxy_http\|fastcgi" || echo "apachectl недоступен"')
print(out)
if not out.strip() or 'недоступен' in out:
    out, _ = run('php -r "echo \"SAPI: \" . PHP_SAPI . \"\\n\"; echo \"is mod_php: \" . (stripos(PHP_SAPI, \"apache\") !== false ? \"YES\" : \"NO - probably FPM\") . \"\\n\";"')
    print(out)

# 4. Поиск проблемных вызовов opcache_reset (без function_exists)
header('4. Файлы с opcache_reset() БЕЗ function_exists')
out, _ = run(f'''
cd {SITE} && for f in $(grep -rl "opcache_reset" --include="*.php" . 2>/dev/null); do
  if ! grep -q "function_exists.*opcache_reset" "$f" 2>/dev/null; then
    echo "БЕЗ ПРОВЕРКИ: $f"
    grep -n "opcache_reset" "$f" | head -3
    echo "---"
  fi
done
''')
print(out[:3000] if out.strip() else 'Нет проблемных вызовов — все проверены!')

# 5. Правильные вызовы (с проверкой)
header('5. Файлы с opcache_reset() С function_exists')
out, _ = run(f'''
cd {SITE} && for f in $(grep -rl "opcache_reset" --include="*.php" . 2>/dev/null); do
  if grep -q "function_exists.*opcache_reset" "$f" 2>/dev/null; then
    echo "OK: $f"
    grep -n "function_exists.*opcache_reset" "$f"
    echo "---"
  fi
done
''')
print(out[:2000])

# 6. Конфигурация PHP-FPM
header('6. Конфигурация OPcache в php.ini (FPM и CLI)')
out, err = run(f'''
for cfg in /etc/php/*/fpm/php.ini /etc/php.ini /etc/php/*/cli/php.ini; do
  if [ -f "$cfg" ]; then
    echo "--- $cfg ---"
    grep -E "^;? *opcache\.(enable|memory|max_accelerated|revalidate|fast_shutdown)" "$cfg" 2>/dev/null | head -10
  fi
done
echo ""
echo "--- .user.ini в корне сайта ---"
if [ -f "{SITE}/.user.ini" ]; then
  cat "{SITE}/.user.ini"
else
  echo "Нет или пуст"
fi
''')
print(out[:2000])
if err.strip():
    print('stderr:', err[:300])

# 7. .htaccess - настройки OPcache
header('7. Настройки OPcache в .htaccess')
out, _ = run(f'''
echo "--- Весь блок с opcache ---"
grep -n -B2 -A5 "opcache" "{SITE}/.htaccess" 2>/dev/null || echo "Не найдено"
echo ""
echo "--- блок IfModule mod_php ---"
grep -n -A15 "IfModule mod_php" "{SITE}/.htaccess" 2>/dev/null || echo "Не найдено"
''')
print(out[:2000])

# 8. Даты antibot
header('8. Когда появился antibot (даты файлов)')
out, _ = run(f'''
echo "--- Файлы antibot по датам ---"
ls -la --time-style=full-iso {SITE}/antibot/ 2>/dev/null
echo ""
echo "--- Если git ---"
cd {SITE}
if [ -d .git ]; then
  git log --oneline --all -- antibot/ 2>/dev/null | head -5 || echo "git не доступен"
else
  echo "git не инициализирован"
fi
''')
print(out[:2000])

ssh.close()
print('\n✅ Диагностика завершена')

#!/usr/bin/env python3
"""Комплексный поиск и патч opcache_reset на сервере."""
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

SITE_DIR = '/var/www/u0220513/data/www/sevzakon.ru'

print('=== Шаг 1: Полный поиск opcache_reset по сайту ===')
cmd = f"grep -rn 'opcache_reset' {SITE_DIR}/ 2>/dev/null | grep -v '.git' | grep -v 'Binary'"
stdin, stdout, stderr = ssh.exec_command(cmd)
out = stdout.read().decode('utf-8', errors='replace')
print(out[:5000] if out.strip() else 'Ничего не найдено')

print('\n=== Шаг 2: Папка antibot ===')
cmd = f"find {SITE_DIR}/antibot -type f -name '*.php' 2>/dev/null"
stdin, stdout, stderr = ssh.exec_command(cmd)
out = stdout.read().decode('utf-8', errors='replace')
print(out)

print('\n=== Шаг 3: Содержимое antibot/code/ab.php (первые 50 строк) ===')
cmd = f"head -50 {SITE_DIR}/antibot/code/ab.php"
stdin, stdout, stderr = ssh.exec_command(cmd)
out = stdout.read().decode('utf-8', errors='replace')
print(out)

print('\n=== Шаг 4: PHP info — opcache ===')
cmd = "php -r 'echo ini_get(\"opcache.enable\") ? \"ENABLED\" : \"DISABLED\"; echo \"\\n\"; '"
stdin, stdout, stderr = ssh.exec_command(cmd)
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
print('stdout:', out.strip())
if err.strip():
    print('stderr:', err[:300])

ssh.close()
print('\nDONE')
