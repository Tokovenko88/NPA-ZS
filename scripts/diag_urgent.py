#!/usr/bin/env python3
"""Срочная диагностика сайта — доступность + последние ошибки."""
import os
from dotenv import load_dotenv
import paramiko

load_dotenv('D:/NPA-ZS/.env')
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(
    hostname=os.getenv('MODX_SSH_HOST'),
    port=int(os.getenv('MODX_SSH_PORT', 22)),
    username=os.getenv('MODX_SSH_USERNAME'),
    password=os.getenv('MODX_SSH_PASSWORD'),
    timeout=10,
)

print('=== 1. Check site availability ===')
stdin, stdout, stderr = client.exec_command(
    'curl -s -m 10 -k -o /dev/null'
    ' -w "HTTP_CODE: %{http_code}, SIZE: %{size_download}, TIME: %{time_total}s"'
    ' https://sevzakon.ru/view/laws/proekty_postanovlenij/2026/pr_post_12_203_ot_18_09_2026/tekst-proekta-postanovleniya132/'
)
print('RESPONSE:', stdout.read().decode())
err = stderr.read().decode()
if err:
    print('STDERR:', err[:200])

print()
print('=== 2. Last 10 event_log entries ===')
stdin, stdout, stderr = client.exec_command(
    'php -r "$pdo=new PDO("mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8",'
    '"u0220513_modx","xP5rX0bA2rgM0cA2");'
    'foreach($pdo->query("SELECT id,FROM_UNIXTIME(createdon) t,source,createdby FROM modx_event_log ORDER BY id DESC LIMIT 10") as $r)'
    ' echo "[".$r["id"]."] ".$r["t"]." | ".$r["source"]." | by: ".$r["createdby"]."\\n";"
)
print(stdout.read().decode())

print()
print('=== 3. OPcache status in web context ===')
stdin, stdout, stderr = client.exec_command(
    'curl -s -m 10 -k'
    ' -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"'
    ' https://sevzakon.ru/phpinfo.php 2>/dev/null'
    ' | grep -i "opcache\\.enable[[:space:]]*:" | head -3'
)
print('OPcache enable:', stdout.read().decode().strip())

client.close()
print()
print('DONE')
