#!/usr/bin/env python3
"""Diag final v2: check PHP-FPM config."""
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

# PHP script via SFTP: check PHP ini files for FPM
PHP = (
    b'<?php' + b'\n'
    + b'echo "=== PHP version & SAPI ===\n";' + b'\n'
    + b'echo "PHP Version: ".PHP_VERSION."\n";' + b'\n'
    + b'echo "SAPI: ".php_sapi_name()."\n";' + b'\n'
    + b'echo "\n=== php.ini files ===\n";' + b'\n'
    + b'echo "Loaded Configuration File: ".get_cfg_var("cfg_file_name")."\n";' + b'\n'
    + b'$files = explode(",", get_cfg_var("additional_ini"));' + b'\n'
    + b'if($files && count($files)) { foreach($files as $f) echo "  Additional ini: ".$f."\n"; }' + b'\n'
    + b'echo "\n=== OPcache settings ===\n";' + b'\n'
    + b'$items = array(' + b'\n'
    + b'  "opcache.enable"           => ini_get("opcache.enable"),' + b'\n'
    + b'  "opcache.enable_cli"       => ini_get("opcache.enable_cli"),' + b'\n'
    + b'  "opcache.memory_consumption" => ini_get("opcache.memory_consumption"),' + b'\n'
    + b'  "opcache.max_accelerated_files" => ini_get("opcache.max_accelerated_files"),' + b'\n'
    + b'  "opcache.revalidate_freq"  => ini_get("opcache.revalidate_freq"),' + b'\n'
    + b'  "opcache.fast_shutdown"    => ini_get("opcache.fast_shutdown"),' + b'\n'
    + b');' + b'\n'
    + b'foreach($items as $k=>$v) echo "  $k = ".var_export($v, true)."\n";' + b'\n'
    + b'echo "\n=== Function checks ===\n";' + b'\n'
    + b'echo "  function_exists(opcache_reset): ".var_export(function_exists("opcache_reset"), true)."\n";' + b'\n'
    + b'echo "  extension_loaded(Zend OPcache): ".var_export(extension_loaded("Zend OPcache"), true)."\n";' + b'\n'
    + b'$ht = __DIR__."/.htaccess";' + b'\n'
    + b'echo "\n=== .htaccess opcache test ===\n";' + b'\n'
    + b'if(file_exists($ht)) { echo "  .htaccess FOUND\n";' + b'\n'
    + b'  $htc = file_get_contents($ht);' + b'\n'
    + b'  if(strpos($htc, "opcache.enable") !== false) {' + b'\n'
    + b'    echo "  .htaccess contains opcache.enable directive(s)\n";' + b'\n'
    + b'    $lines = explode("\n", $htc);' + b'\n'
    + b'    foreach($lines as $l) if(strpos($l, "opcache") !== false) echo "    >>> ".$l."\n";' + b'\n'
    + b'  } else { echo "  .htaccess does NOT contain opcache directives\n"; }' + b'\n'
    + b'} else { echo "  .htaccess NOT FOUND\n"; }' + b'\n'
    + b'echo "\nDONE\n";' + b'\n'
)

print('Writing PHP via SFTP: /tmp/diag_final_v2.php')
sftp = ssh.open_sftp()
with sftp.file('/tmp/diag_final_v2.php', 'wb') as f:
    f.write(PHP)
sftp.close()

print('Running...')
stdin, stdout, stderr = ssh.exec_command('php /tmp/diag_final_v2.php')
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
print(out)
if err.strip():
    print('[stderr]', err[:500])

ssh.close()
print('\nDONE')
