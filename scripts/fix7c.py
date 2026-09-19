#!/usr/bin/env python3
"""Исправление 7 сниппетов: PHP через SFTP (без проблем экранирования)."""
import os
from dotenv import load_dotenv
import paramiko

load_dotenv('D:/NPA-ZS/.env')
cli = paramiko.SSHClient()
cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
cli.connect(
    os.getenv('MODX_SSH_HOST'),
    port=int(os.getenv('MODX_SSH_PORT', '22')),
    username=os.getenv('MODX_SSH_USERNAME'),
    password=os.getenv('MODX_SSH_PASSWORD'),
    timeout=25,
)


def remote_run(cmd, t=120):
    stdin, stdout, stderr = cli.exec_command(cmd, timeout=t)
    return stdout.read().decode('utf-8', 'replace'), stderr.read().decode('utf-8', 'replace')


# PHP-код — пишем напрямую через SFTP (без проблем экранирования)
PHP_CODE = (
    '<?php' + '\n'
    '$pdo=new PDO("mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8",'
    '"u0220513_modx","xP5rX0bA2rgM0cA2");' + '\n'
    '$pdo->setAttribute(PDO::ATTR_ERRMODE,PDO::ERRMODE_EXCEPTION);' + '\n'
    '$ids=[125,150,167,173,182,239,240];' + '\n'
    '$res=[];' + '\n'
    'foreach($ids as $sid){' + '\n'
    '  $s=$pdo->prepare("SELECT name,snippet FROM modx_site_snippets WHERE id=?");' + '\n'
    '  $s->execute([$sid]);' + '\n'
    '  $r=$s->fetch(PDO::FETCH_ASSOC);' + '\n'
    '  if(!$r){$res[$sid]=["st"=>"NF"];continue;}' + '\n'
    '  $name=$r["name"];' + '\n'
    '  $body=$r["snippet"];' + '\n'
    '  $orig=strlen($body);$act=[];' + '\n'
    '  if(substr($body,0,3)===chr(239).chr(187).chr(191)){$body=substr($body,3);$act[]="BOM";}' + '\n'
    '  $body=ltrim($body,"\r\n");' + '\n'
    '  if(substr(ltrim($body),0,6)==="//<?php"){$body="<?php".substr(ltrim($body),6);$act[]="cmm";}' + '\n'
    '  if(strpos($body,"<?php")!==0){$body="<?php\n".$body;$act[]="tag";}' + '\n'
    '  if(substr_count($body,"<?php")>1){$p=explode("<?php",$body);$body="<?php".implode("",array_slice($p,1));$act[]="dup";}' + '\n'
    '  $u=$pdo->prepare("UPDATE modx_site_snippets SET snippet=?,editedon=UNIX_TIMESTAMP() WHERE id=?");' + '\n'
    '  $u->execute([$body,$sid]);' + '\n'
    '  $res[$sid]=["st"=>"DONE","nm"=>$name,"og"=>$orig,"nw"=>strlen($body),"ac"=>$act];' + '\n'
    '}' + '\n'
    'echo "=== RESULTS ===\n";' + '\n'
    'foreach($res as $sid=>$i){' + '\n'
    '  echo "id=$sid | {$i["nm"]}\n  status: {$i["st"]}\n";' + '\n'
    '  if($i["st"]==="DONE")echo "  size: {$i["og"]} -> {$i["nw"]} bytes\n  actions: ".implode(", ",$i["ac"])."\n\n";' + '\n'
    '}' + '\n'
    'echo "=== LINT ===\n";' + '\n'
    'foreach($ids as $sid){' + '\n'
    '  if(!isset($res[$sid])|| $res[$sid]["st"]!=="DONE")continue;' + '\n'
    '  $b=$pdo->query("SELECT snippet FROM modx_site_snippets WHERE id=".$sid)->fetchColumn();' + '\n'
    '  $t="/tmp/ln_".$sid.".php";file_put_contents($t,$b);' + '\n'
    '  $o=shell_exec("php -l ".escapeshellarg($t)." 2>&1");' + '\n'
    '  $ok=(strpos($o,"No syntax errors")!==false);' + '\n'
    '  echo ($ok?"OK":"FAIL")." id=$sid ".$res[$sid]["nm"].": ".trim($o)."\n";' + '\n'
    '}' + '\n'
    'echo "\nDone.\n";' + '\n'
)

print(f'PHP-код длиной {len(PHP_CODE)} символов')

# Загружаем на сервер через SFTP
sftp = cli.open_sftp()
with sftp.file('/tmp/fix7_final.php', 'w') as f:
    f.write(PHP_CODE)
sftp.close()
print('✅ Загружено на сервер: /tmp/fix7_final.php')

print()
print('=== Запуск ===')
out, err = remote_run('php /tmp/fix7_final.php 2>&1')
print(out)
if err.strip():
    print(f'[stderr] {err[:300]}')

print()
print('=== event_log — последние 5 записей ===')
out2, _ = remote_run(
    'php -r '
    '$p=new PDO("mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8",'
    '"u0220513_modx","xP5rX0bA2rgM0cA2");'
    'foreach($p->query("SELECT id,FROM_UNIXTIME(createdon) t,source '
    'FROM modx_event_log ORDER BY id DESC LIMIT 5") as $r){'
    'echo "[".$r["id"]."] ".$r["t"]." | ".$r["source"]."\n";}'
)
print(out2)

print()
print('=== Файлы на сервере (tmp) ===')
out3, _ = remote_run('ls -la /tmp/fix7* /tmp/ln_* 2>/dev/null; echo EXIT:$?')
print(out3[:500])

cli.close()
print('\n✅ DONE')
