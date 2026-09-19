#!/usr/bin/env python3
"""Диагностика PHP-FPM и OPcache — PHP-скрипт через SFTP."""
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

# PHP-скрипт — собирает всю информацию о PHP/OPcache
php = (
    b'<?php' + b'\n'
    + b'ob_start();' + b'\n'
    + b'phpinfo();' + b'\n'
    + b'$info = ob_get_clean();' + b'\n'
    # Фильтруем только то, что нужно
    + b'$lines = explode("\n", $info);' + b'\n'
    + b'foreach($lines as $l) {' + b'\n'
    + b'  if(preg_match("/^(Server API|Loaded Configuration|Configuration File Count|Additional .ini|Scan this dir|opcache.enable|opcache.enable_cli|opcache.memory_consumption|opcache.max_accelerated_files|opcache.revalidate_freq|PHP Version|Loaded Modules|HTTP_SERVER_SOFTWARE)/i", $l)) echo $l."\n";' + b'\n'
    + b'} ' + b'\n'
    + b'echo "\n=== CLI opcache_reset check ===\n";' + b'\n'
    + b'var_dump(function_exists("opcache_reset"));' + b'\n'
    + b'$c = ini_get("opcache.enable"); echo "opcache.enable (CLI) = ".(int)$c."\n";'+ b'\n'
    + b'if(extension_loaded("opcache")) { echo "OPcache extension: LOADED\n"; } else { echo "OPcache extension: NOT LOADED\n"; }' + b'\n'
)

print('Writing diag script via SFTP...')
sftp = ssh.open_sftp()
with sftp.file('/tmp/diag_php_opcache.php', 'wb') as f:
    f.write(php)
sftp.close()

print('Running...')
stdin, stdout, stderr = ssh.exec_command('php /tmp/diag_php_opcache.php')
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
print(out)
if err.strip():
    print('[stderr]', err[:200])

# Читаем конфиг PHP-FPM
print('\n=== PHP-FPM pool.d ===')
stdin2, stdout2, stderr2 = ssh.exec_command('ls -la /etc/php/*/fpm/pool.d/ 2>/dev/null; for f in /etc/php/*/fpm/pool.d/*; do echo "---$f---"; head -80 "$f"; done')
conf_out = stdout2.read().decode('utf-8', errors='replace')
conf_err = stderr2.read().decode('utf-8', errors='replace')
print(conf_out[:3000])
if conf_err.strip():
    print('[stderr]', conf_err[:200])

# Проверяем opcache.ini если есть
print('\n=== opcache ini ===')
stdin3, stdout3, stderr3 = ssh.exec_command('ls -la /etc/php/*/fpm/conf.d/ 2>/dev/null; cat /etc/php/*/fpm/conf.d/*opcache* 2>/dev/null; echo "---END---"')
ini_out = stdout3.read().decode('utf-8', errors='replace')
print(ini_out[:2000])

ssh.close()
print('\nDONE')
