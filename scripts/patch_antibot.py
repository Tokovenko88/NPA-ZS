#!/usr/bin/env python3
"""Патч всех файлов антибота: добавляем проверку ini_get('opcache.enable')."""
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
ANTIBOT_DIR = os.path.join(SITE_DIR, 'antibot')

# Файлы с активными вызовами opcache_reset (без // комментария)
files_to_patch = [
    'code/ab.php',
    'adm/confsave.php',
    'adm/beta.php',
    'adm/update.php',
    'adm/resetcookie.php',
    'adm/phpinfo.php',
    'adm/update2.php',
    'adm/beta2.php',
]

# Паттерн поиска и замены
# Было:   if(function_exists('opcache_reset')) {
# Стало:  if(function_exists('opcache_reset') && ini_get('opcache.enable')) {

OLD_PATTERN = "if(function_exists('opcache_reset')) {"
NEW_PATTERN = "if(function_exists('opcache_reset') && ini_get('opcache.enable')) {"

print('=== Патч файлов антибота ===\n')
results = []

for rel_path in files_to_patch:
    full_path = os.path.join(ANTIBOT_DIR, rel_path)
    cmd = f"cat {full_path}"
    stdin, stdout, stderr = ssh.exec_command(cmd)
    content = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')

    if err.strip():
        print(f'❌ {rel_path}: ОШИБКА ЧТЕНИЯ: {err[:100]}')
        results.append((rel_path, 'READ_ERROR'))
        continue

    if OLD_PATTERN not in content:
        print(f'⚠️  {rel_path}: Паттерн не найден (уже исправлен или иной формат)')
        results.append((rel_path, 'NOT_FOUND'))
        continue

    # Считаем вхождения
    count = content.count(OLD_PATTERN)
    new_content = content.replace(OLD_PATTERN, NEW_PATTERN)

    # Проверка: старое содержимое vs новое
    if new_content == content:
        print(f'⚠️  {rel_path}: Без изменений (что-то странное)')
        results.append((rel_path, 'NO_CHANGE'))
        continue

    # Записываем обратно
    put_cmd = f"cat > {full_path}"
    stdin, stdout, stderr = ssh.exec_command(put_cmd)
    stdin.write(new_content)
    stdin.channel.shutdown_write()
    stdout.read()
    err = stderr.read().decode('utf-8', errors='replace')

    if err.strip():
        print(f'❌ {rel_path}: ОШИБКА ЗАПИСИ: {err[:100]}')
        results.append((rel_path, 'WRITE_ERROR'))
        continue

    # PHP lint
    lint_cmd = f"php -l {full_path}"
    stdin, stdout, stderr = ssh.exec_command(lint_cmd)
    lint_out = stdout.read().decode('utf-8', errors='replace')
    lint_err = stderr.read().decode('utf-8', errors='replace')

    lint_ok = 'No syntax errors' in lint_out

    status = '✅ OK' if lint_ok else '❌ LINT FAIL'
    print(f'{status} {rel_path}: {count} замен, lint: {"OK" if lint_ok else "FAIL"}')
    if not lint_ok:
        print(f'   lint output: {lint_out.strip()}')

    results.append((rel_path, 'OK' if lint_ok else 'LINT_FAIL'))

print('\n=== Итог ===')
for path, status in results:
    print(f'  {path}: {status}')

print('\n=== Проверка: войдет ли antbot ab.php в запрос ===')
# Проверим, кто вызывает antibot
cmd = f"grep -rn 'antibot/code/ab.php' {SITE_DIR}/ 2>/dev/null | head -10"
stdin, stdout, stderr = ssh.exec_command(cmd)
out = stdout.read().decode('utf-8', errors='replace')
print(out[:1000] if out.strip() else 'Вызовы не найдены')

print('\n=== Свежий event_log (последние 3 записи) ===')
cmd = "php -r '$pdo=new PDO(\"mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8\",\"u0220513_modx\",\"xP5rX0bA2rgM0cA2\"); foreach($pdo->query(\"SELECT id,FROM_UNIXTIME(createdon) t,source,severity FROM modx_event_log ORDER BY id DESC LIMIT 3\") as $r) echo \"[\".$r[\"id\"].\"]\".$r[\"t\"].\" | \".$r[\"source\"].\" (severity=\" .$r[\"severity\"] .\")\\n\";''"
stdin, stdout, stderr = ssh.exec_command(cmd)
out = stdout.read().decode('utf-8', errors='replace')
print(out)

ssh.close()
print('\nDONE')
