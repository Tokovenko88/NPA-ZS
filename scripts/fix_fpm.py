#!/usr/bin/env python3
"""Диагностика PHP-FPM и Apache — поиск сервиса FPM для запуска."""
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


print('=== Все php-fpm сервисы ===')
out, err = run("find /usr/lib/systemd /etc/systemd -name '*fpm*' -type f 2>/dev/null")
print(out)
print('ERR:', err[:200])

print('\n=== Конфиг Apache + PHP ===')
for f in ['/etc/httpd/conf.d/php.conf', '/etc/httpd/conf.modules.d/00-base.conf', '/etc/httpd/conf/httpd.conf']:
    print(f'--- {f} ---')
    out, err = run(f'head -100 {f} 2>/dev/null')
    if out.strip():
        print(out[:500])
    else:
        print('NOTFOUND')
    if err.strip():
        print('ERR:', err[:200])

print('\n=== Запущенные сокеты/порт PHP ===')
out, err = run("ss -lnp 2>/dev/null | grep -E 'php|9000|9001|9002|9003'")
if out.strip():
    print(out)
else:
    out2, _ = run("netstat -lnp 2>/dev/null | grep -E 'php|9000|9001|9002|9003'")
    print(out2)
print('ERR:', err[:200])

print('\n=== Все службы с php ===')
out, err = run("systemctl list-units --type=service --all 2>/dev/null | grep -i php")
print(out)
print('ERR:', err[:200])

print('\n=== Конфиг сайта в Apache ===')
out, err = run("grep -r 'sevzakon.ru' /etc/httpd/ 2>/dev/null | head -10")
print(out[:500])
if err.strip():
    print('ERR:', err[:200])

print('\n=== Содержимое php-fpm.service ===')
out, err = run('cat /usr/lib/systemd/system/php-fpm.service 2>/dev/null')
print(out[:500])
if err.strip():
    print('ERR:', err[:300])

print('\n=== PHP-FPM pool.d ===')
out, err = run('ls /etc/php-fpm.d/ 2>/dev/null')
print(out)
if err.strip():
    print('ERR:', err[:200])

print('\n=== Apache конфиг: загрузка модулей PHP ===')
out, err = run("grep -i 'php' /etc/httpd/conf.modules.d/*.conf 2>/dev/null")
print(out[:500])
if err.strip():
    print('ERR:', err[:200])

print('\n=== Как Apache обслуживает PHP ===')
out, err = run("grep -rn 'SetHandler\\|ProxyPass\\|SetHandler.*php\\|AddHandler\\|mod_php' /etc/httpd/ 2>/dev/null | head -20")
print(out[:500])
if err.strip():
    print('ERR:', err[:200])

cli.close()
print('\nDONE')
