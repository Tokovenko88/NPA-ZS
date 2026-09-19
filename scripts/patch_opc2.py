#!/usr/bin/env python3
"""ЧАСТЬ 1: Полный патч OPcache (function_exists)."""
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


def run(cmd, t=120):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=t)
    return (stdout.read().decode('utf-8', errors='replace'),
            stderr.read().decode('utf-8', errors='replace'))


PATH_OPC = '/var/www/u0220513/data/www/sevzakon.ru/manager/processors/cache_sync.class.processor.php'

PHP_OPC = r"""<?php
$path = '/var/www/u0220513/data/www/sevzakon.ru/manager/processors/cache_sync.class.processor.php';
if (!file_exists($path)) { die("NOT FOUND\n"); }
echo "File: $path\n";
$c = file_get_contents($path);
$o = $c;

$old = "if (!empty($opcache['opcache_enabled']) && ini_get('opcache.enable')) {
                @opcache_reset();";
$new = "if (!empty($opcache['opcache_enabled']) && ini_get('opcache.enable') && function_exists('opcache_reset')) {
                @opcache_reset();";

if (strpos($c, $old) !== false) {
    $c = str_replace($old, $new, $c);
    echo "PATCHED (full)\n";
} elseif (strpos($c, "function_exists('opcache_reset')") !== false) {
    echo "ALREADY FULLY PATCHED\n";
} else {
    echo "NOT FOUND exact pattern\n";
    $lines = explode("\n", $c);
    foreach ($lines as $i => $ln) {
        if (strpos($ln, 'opcache_reset') !== false) {
            echo "  line " . $i . ": " . $ln . "\n";
            if (isset($lines[$i-1])) echo "  line " . ($i-1) . ": " . $lines[$i-1] . "\n";
            if (isset($lines[$i+1])) echo "  line " . ($i+1) . ": " . $lines[$i+1] . "\n";
        }
    }
    foreach ($lines as $i => $ln) {
        if (strpos($ln, '@opcache_reset()') !== false) {
            for ($j = $i; $j >= max(0, $i-5); $j--) {
                if (strpos($lines[$j], 'opcache_enabled') !== false) {
                    echo "  Found if at line $j: " . $lines[$j] . "\n";
                    $lines[$j] = str_replace('}', ', function_exists(\'opcache_reset\')) {', $lines[$j]);
                    echo "  Patched line $j\n";
                    break;
                }
            }
            break;
        }
    }
    $c = implode("\n", $lines);
}

if ($c !== $o) {
    if (file_put_contents($path, $c)) {
        echo "SAVED\n";
    } else {
        echo "SAVE FAILED\n";
        exit(1);
    }
} else {
    echo "NO CHANGE\n";
}
echo "DONE\n";
"""

print('Writing patch script via SFTP...')
sftp = ssh.open_sftp()
with sftp.file('/tmp/patch_opc2.php', 'w') as f:
    f.write(PHP_OPC)
sftp.close()
print('Written to /tmp/patch_opc2.php')

print('\n=== Running patch ===')
out, err = run('php /tmp/patch_opc2.php')
print('OUTPUT:')
print(out)
if err.strip():
    print('ERRORS:')
    print(err[:500])

print('\n=== Verify after patch ===')
out2, _ = run(f"grep -n -A2 -B1 'opcache_reset' {PATH_OPC}")
print(out2)

ssh.close()
print('\n✅ PART 1 DONE')
