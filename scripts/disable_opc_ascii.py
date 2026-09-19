#!/usr/bin/env python3
"""Stop OPcache flood - disable opcache_reset via SFTP+PHP."""
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
print('SSH OK', flush=True)

CS_PATH = '/var/www/u0220513/data/www/sevzakon.ru/manager/processors/cache_sync.class.processor.php'

# Build PHP code as bytes (ASCII only)
lines = [
    b'<?php',
    b'$path = ' + repr(CS_PATH).encode() + b';',
    b'if (!file_exists($path)) { die(\'NOT_FOUND\'); }',
    b'$c = file_get_contents($path);',
    b'$o = $c;',
    b'$s = '@opcache_reset();';',
    b'$r = '// @opcache_reset(); /*DISABLED*/';',
    b'$c = str_replace($s, $r, $c);',
    b'if ($c !== $o) { if (file_put_contents($path, $c)) { echo "PATCHED"; } else { echo "SAVE_FAIL"; exit(1); } }',
    b'else { echo "NOTFOUND"; }',
    b'echo "\n---grep---\n";',
    b'$l = explode("\n", $c);',
    b'foreach ($l as $i => $ln) { if (strpos($ln, "opcache_reset") !== false) echo ($i+1).": ".$ln."\n"; }',
    b'echo "\nDONE\n";',
]
php = b'\n'.join(lines) + b'\n'

print(f'PHP len: {len(php)} bytes', flush=True)

sftp = ssh.open_sftp()
with sftp.file('/tmp/patch_opc.php', 'wb') as f:
    f.write(php)
sftp.close()
print('Written /tmp/patch_opc.php', flush=True)

stdin, stdout, stderr = ssh.exec_command('php /tmp/patch_opc.php 2>&1')
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
print(out, flush=True)
if err:
    print('STDERR:', err[:200], flush=True)

# Verify
print('\n=== verify ===', flush=True)
stdin, stdout, stderr = ssh.exec_command(f"sed -n '138,150p' {CS_PATH}")
v = stdout.read().decode('utf-8', errors='replace')
print(v, flush=True)

ssh.close()
print('\nDONE', flush=True)
