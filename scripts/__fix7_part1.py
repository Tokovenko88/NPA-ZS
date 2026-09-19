#!/usr/bin/env python3
"""Сохранить PHP-скрипт исправления на сервере через SFTP."""
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

# PHP-скрипт бизнеса — максимально компактный
# Используем хитрость: base64-кодируем PHP-код, чтобы избежать любых проблем с экранированием
php_lines = [
    '<' + '?' + 'php',
    ' $pdo=new PDO(\'mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8\',',
    '   \'u0220513_modx\',\'xP5rX0bA2rgM0cA2\');',
    ' $pdo->setAttribute(PDO::ATTR_ERRMODE,PDO::ERRMODE_EXCEPTION);',
    ' $ids=[125,150,167,173,182,239,240];',
    ' $res=[];',
    ' foreach($ids as $sid){',
    '   $s=$pdo->prepare(\'SELECT name,snippet FROM modx_site_snippets WHERE id=?\');',
    '   $s->execute([$sid]);',
    '   $r=$s->fetch(PDO::FETCH_ASSOC);',
    '   if(!$r){$res[$sid]=[\"s\"=>\"NF\"];continue;}',
    '   $name=$r[\"name\"];$body=$r[\"snippet\"];$orig=strlen($body);$act=[];',
    '   if(substr($body,0,3)===chr(239).chr(187).chr(191)){$body=substr($body,3);$act[]=\"BOM\";}',
    '   $body=ltrim($body,\"\\r\\n\");',
    '   if(substr(ltrim($body),0,6)===\'//<?php\'){$body=\'<?php\'.substr(ltrim($body),6);$act[]=\"comm_f\";}',


]

print('Part 1 ready')
