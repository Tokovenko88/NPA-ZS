#!/usr/bin/env python3
"""Диагностика PHP-FPM: проверка правильных ini-файлов."""
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

# PHP-скрипт — проверяет ОПРАВДАННЫЕ пути к ini для PHP-FPM
php = b'''<?php
//
// Эталонный скрипт: проверяет, какие ini-файлы загружает PHP-FPM
//
echo "=== PHP version & SAPI ===\\n";
echo "PHP Version: ".PHP_VERSION."\\n";
echo "SAPI: ".php_sapi_name()."\\n";

echo "\\n=== php.ini files ===\\n";
echo "Loaded Configuration File: ".get_cfg_var("cfg_file_name")."\\n";
$files = explode(",", get_cfg_var("additional_ini"));
if($files && count($files)) {
    foreach($files as $f) echo "  Additional ini: ".$f."\\n";
}

echo "\\n=== OPcache settings (from active ini) ===\\n";
$items = [
    "opcache.enable"           => ini_get("opcache.enable"),
    "opcache.enable_cli"       => ini_get("opcache.enable_cli"),
    "opcache.memory_consumption" => ini_get("opcache.memory_consumption"),
    "opcache.max_accelerated_files" => ini_get("opcache.max_accelerated_files"),
    "opcache.revalidate_freq"  => ini_get("opcache.revalidate_freq"),
    "opcache.fast_shutdown"    => ini_get("opcache.fast_shutdown"),
];
foreach($items as $k=>$v) {
    echo "  $k = ".var_export($v, true).("\\n");
}

echo "\\n=== Function checks ===\\n";
echo "  function_exists('opcache_reset'): ".var_export(function_exists('opcache_reset'), true)."\\n";
echo "  extension_loaded('Zend OPcache'): ".var_export(extension_loaded('Zend OPcache'), true)."\\n";

echo "\\n=== htaccess opcache test (if accessible) ===\\n";
$ht = __DIR__."/.htaccess";
if(file_exists($ht)) {
    $htc = file_get_contents($ht);
    if(strpos($htc, "opcache.enable") !== false) {
        echo "  .htaccess contains opcache.enable directive(s)\\n";
        // Extract lines with opcache.enable
        $lines = explode("\\n", $htc);
        foreach($lines as $l) {
            if(strpos($l, "opcache.enable") !== false) echo "    >>> ".$l."\\n";
        }
    } else {
        echo "  .htaccess does NOT contain opcache.enable\\n";
    }
} else {
    echo "  .htaccess NOT FOUND at ".__DIR__."\\n";
}

echo "\\nDONE\\n";
'''

print('Writing final diagnostic PHP via SFTP...')
sftp = ssh.open_sftp()
with sftp.file('/tmp/diag_opcache_final_v2.php', 'wb') as f:
    f.write(php)
sftp.close()

print('Running PHP diagnostic...')
stdin, stdout, stderr = ssh.exec_command('php /tmp/diag_opcache_final_v2.php')
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
print(out)
if err.strip():
    print('[stderr]', err[:500])

ssh.close()
print('\nDONE')
