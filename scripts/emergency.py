#!/usr/bin/env python3
"""Чрезвычайная диагностика: запуск FPM без systemctl и проверка сайта."""
import os
from dotenv import load_dotenv
import paramiko

load_dotenv('D:/NPA-ZS/.env')
cli = paramiko.SSHClient()
cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
cli.connect(
    hostname=os.getenv('MODX_SSH_HOST'),
    port=int(os.getenv('MODX_SSH_PORT', 22)),
    username=os.getenv('MODX_SSH_USERNAME'),
    password=os.getenv('MODX_SSH_PASSWORD'),
    timeout=10,
)
print('SSH connected')


def run(cmd):
    stdin, stdout, stderr = cli.exec_command(cmd)
    return stdout.read().decode('utf-8', 'replace'), stderr.read().decode('utf-8', 'replace')


print('=== Проверка sudo доступа ===')
out, err = run('sudo -n true 2>&1 && echo "SUDO_OK" || echo "SUDO_FAIL"')
print(f"sudo -n: {out.strip()} | ERR: {err.strip()}")

print('\n=== Пользователь ===')
out, err = run('whoami && id')
print(out.strip())
print(f"ERR: {err.strip()[:200]}")

print('\n=== Прямой запуск php-fpm ===')
out, err = run('sudo /usr/sbin/php-fpm --nodaemonize 2>&1 &')
print(f'out: {out[:300]}')
print(f'err: {err[:300]}')

import time
time.sleep(2)

print('\n=== Статус после запуска ===')
out, err = run('systemctl status php-fpm 2>&1')
print(out[:500])
print(f"ERR: {err[:300]}")

print('\n=== Процессы FPM ===')
out, err = run('ps aux | grep php-fpm | grep -v grep | head -10')
print(out[:500])
print(f"ERR: {err[:200]}")

print('\n=== Сокет FPM ===')
out, err = run('ls -la /run/php-fpm/www.sock 2>/dev/null || ls -la /var/run/php-fpm/www.sock 2>/dev/null || echo "SOCKET_NOT_FOUND"')
print(out[:500])
print(f"ERR: {err[:200]}")

print('\n=== Логи FPM ===')
out, err = run('journalctl -u php-fpm --no-pager -n 30 2>/dev/null')
print(out[:1000])
print(f"ERR: {err[:300]}")

print('\n=== Apache error_log (последние 50 строк) ===')
for log in ['/var/log/httpd/error_log', '/var/log/apache2/error.log', '/var/log/httpd/ssl_error_log']:
    print(f'--- {log} ---')
    out, err = run(f'tail -50 {log} 2>/dev/null | grep -i -E "php|error|parse|warning|fpm|fcgid|opcache"')
    if out.strip():
        print(out[:1500])
    if err.strip():
        print(f'ERR: {err[:300]}')
    print()

print('\n=== mod_fcgid логи ===')
out, err = run('find /var/log /var/run/mod_fcgid -name "*.log" -type f 2>/dev/null')
print(f'log files: {out[:500]}')
for lf in out.strip().split('\n')[:5]:
    if lf:
        print(f'--- {lf} ---')
        out2, _ = run(f'tail -30 {lf} 2>/dev/null')
        if out2.strip():
            print(out2[:800])

print('\n=== Проверка сайта через локальный curl (без значений %{size_download}) ===')
out, err = run('curl -s -m 15 -o /tmp/site_check.html -w "%{http_code}" https://localhost/view/laws/proekty_postanovlenij/2026/pr_post_12_203_ot_18_09_2026/tekst-proekta-postanovleniya132/')
print(f'HTTP code: {out.strip()}')
print(f'ERR: {err[:300]}')
out2, _ = run('wc -c < /tmp/site_check.html')
print(f'Page size: {out2.strip()} bytes')

print('\n=== Ошибки event_log (последние 3) ===')
out, err = run("php -r \"\$p=new PDO('mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8','u0220513_modx','xP5rX0bA2rgM0cA2'); foreach(\$p->query('SELECT id,FROM_UNIXTIME(createdon) t,source,description FROM modx_event_log ORDER BY id DESC LIMIT 3') as \$r) { echo '['.\$r['id'].'] '.\$r['t'].' | '.\$r['source'].\"\\n\"; echo substr(\$r['description'],0,300).\"\\n\\n\"; }\"")
print(out[:1500])
print(f"ERR: {err[:300]}")

print('\n=== Ошибки за ПОСЛЕДНИЕ 30 минут ===')
out, err = run("php -r \"\$p=new PDO('mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8','u0220513_modx','xP5rX0bA2rgM0cA2'); \$c=\$p->query('SELECT COUNT(*) FROM modx_event_log WHERE createdon > UNIX_TIMESTAMP()-1800 AND source LIKE \"%Parse%\"')->fetchColumn(); echo \"Parse errors last 30 min: \".\$c;\"")
print(out.strip())
print(f"ERR: {err[:300]}")

cli.close()
print('\nDONE')
