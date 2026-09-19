#!/usr/bin/env python3
"""Check web OPcache via curl + antibot structure."""
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

# 1. Copy test file to web root
print('\n=== Copy test file to web root ===')
cmd1 = 'cp /tmp/test_opcache_web.php /var/www/u0220513/data/www/sevzakon.ru/test_opcache_web.php && chmod 644 /var/www/u0220513/data/www/sevzakon.ru/test_opcache_web.php && ls -la /var/www/u0220513/data/www/sevzakon.ru/test_opcache_web.php'
stdin, stdout, stderr = ssh.exec_command(cmd1)
print(stdout.read().decode('utf-8', errors='replace'))

# 2. Curl test
print('\n=== Curl test (localhost) ===')
cmd2 = 'curl -s --max-time 10 http://localhost/test_opcache_web.php 2>&1'
stdin2, stdout2, stderr2 = ssh.exec_command(cmd2)
curl_out = stdout2.read().decode('utf-8', errors='replace')
print(curl_out[:3000])
if stderr2.read().decode('utf-8', errors='replace').strip():
    print('[curl stderr]', stderr2.read().decode('utf-8', errors='replace')[:300])

# 3. Antibot directory structure
print('\n=== Antibot directory structure ===')
cmd3 = 'find /var/www/u0220513/data/www/sevzakon.ru/antibot -type f 2>/dev/null | head -30'
stdin3, stdout3, stderr3 = ssh.exec_command(cmd3)
print(stdout3.read().decode('utf-8', errors='replace'))

print('\n=== Antibot top-level ===')
cmd3b = 'ls -la /var/www/u0220513/data/www/sevzakon.ru/antibot/ 2>/dev/null'
stdin3b, stdout3b, stderr3b = ssh.exec_command(cmd3b)
print(stdout3b.read().decode('utf-8', errors='replace'))

print('\n=== Antibot README/stat ===')
cmd3c = 'stat /var/www/u0220513/data/www/sevzakon.ru/antibot/README 2>/dev/null || echo "README not found"'
stdin3c, stdout3c, stderr3c = ssh.exec_command(cmd3c)
print(stdout3c.read().decode('utf-8', errors='replace'))
if stderr3c.read().decode('utf-8', errors='replace').strip():
    print('[stderr]', stderr3c.read().decode('utf-8', errors='replace')[:300])

# 4. When was antibot created? Check file times
print('\n=== Antibot file ages ===')
cmd4 = 'find /var/www/u0220513/data/www/sevzakon.ru/antibot -type f -printf "%T+ %p\\n" 2>/dev/null | sort | head -10; echo "---"; find /var/www/u0220513/data/www/sevzakon.ru/antibot -type d -printf "%T+ %p\\n" 2>/dev/null | sort | head -10'
stdin4, stdout4, stderr4 = ssh.exec_command(cmd4)
print(stdout4.read().decode('utf-8', errors='replace'))

ssh.close()
print('\nDONE')
