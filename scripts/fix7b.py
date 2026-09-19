#!/usr/bin/env python3
"""Исправление 7 сниппетов: base64-encode PHP и выполнение на сервере."""
import os, base64
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


def run(cmd, t=120):
    _i, o, e = cli.exec_command(cmd, timeout=t)
    return o.read().decode('utf-8', 'replace'), e.read().decode('utf-8', 'replace')


# PHP-код — компактная версия без проблемных символов
php_code = r'''<?php
$pdo=new PDO('mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8','u0220513_modx','xP5rX0bA2rgM0cA2');
$pdo->setAttribute(PDO::ATTR_ERRMODE,PDO::ERRMODE_EXCEPTION);
$ids=[125,150,167,173,182,239,240];
$res=[];
foreach($ids as $sid){
  $s=$pdo->prepare('SELECT name,snippet FROM modx_site_snippets WHERE id=?');
  $s->execute([$sid]);
  $r=$s->fetch(PDO::FETCH_ASSOC);
  if(!$r){$res[$sid]=['st'=>'NF'];continue;}
  $name=$r['name'];
  $body=$r['snippet'];
  $orig=strlen($body);
  $act=[];
  if(substr($body,0,3)===chr(239).chr(187).chr(191)){$body=substr($body,3);$act[]='BOM';}
  $body=ltrim($body,"\r\n");
  if(substr(ltrim($body),0,6)==='//<?php'){$body='<?php'.substr(ltrim($body),6);$act[]='cmm';}
  if(strpos($body,'<?php')!==0){$body='<?php\n'.$body;$act[]='tag';}
  if(substr_count($body,'<?php')>1){$p=explode('<?php',$body);$body='<?php'.implode('',array_slice($p,1));$act[]='dup';}
  $u=$pdo->prepare('UPDATE modx_site_snippets SET snippet=?,editedon=UNIX_TIMESTAMP() WHERE id=?');
  $u->execute([$body,$sid]);
  $res[$sid]=['st'=>'DONE','nm'=>$name,'og'=>$orig,'nw'=>strlen($body),'ac'=>$act];
}
echo "=== RESULTS ===\n";
foreach($res as $sid=>$i){
  echo "id=$sid | {$i['nm']}\n  status: {$i['st']}\n";
  if($i['st']==='DONE')echo "  size: {$i['og']} -> {$i['nw']} bytes\n  actions: ".implode(', ',$i['ac'])."\n\n";
}
echo "=== LINT ===\n";
foreach($ids as $sid){
  if(!isset($res[$sid])|| $res[$sid]['st']!=='DONE')continue;
  $b=$pdo->query("SELECT snippet FROM modx_site_snippets WHERE id=".$sid)->fetchColumn();
  $t='/tmp/ln_'.$sid.'.php';
  file_put_contents($t,$b);
  $o=shell_exec('php -l '.escapeshellarg($t).' 2>&1');
  $ok=(strpos($o,'No syntax errors')!==false);
  echo ($ok?'OK':'FAIL').' id='.$sid.' '.$res[$sid]['nm'].': '.trim($o)."\n";
}
echo "\nDone.\n";
'''

b64 = base64.b64encode(php_code.encode()).decode()
print(f'PHP-скрипт закодирован: {len(b64)} символов base64')

# PHP-деко더가: принимает base64 из аргумента и выполняет
php_decoder = '<?php eval(base64_decode($argv[1]));'

print('Запуск на сервере через php -r + base64...')
out, err = run(f'php -r {php_decoder} {b64} 2>&1')
print('\n=== OUTPUT ===')
print(out)
if err.strip():
    print('\n[stderr]')
    print(err[:500])

print('\n=== event_log (последние 5 записей) ===')
out2, _ = run(
    "php -r '$pdo=new PDO(\"mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8\","
    "\"u0220513_modx\",\"xP5rX0bA2rgM0cA2\");"
    "foreach($pdo->query(\"SELECT id,FROM_UNIXTIME(createdon) t,source "
    "FROM modx_event_log ORDER BY id DESC LIMIT 5\") as $r){"
    "echo \"[\".$r[\"id\"].\"] \".$r[\"t\"].\" | \".$r[\"source\"].\"\\n\";}'"
)
print(out2)

cli.close()
print('\nDONE')
