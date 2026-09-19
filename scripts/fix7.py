#!/usr/bin/env python3
"""Загрузка PHP-скрипта исправления на сервер и его запуск."""
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


def run(cmd, t=120):
    _i, o, e = cli.exec_command(cmd, timeout=t)
    return o.read().decode('utf-8', 'replace'), e.read().decode('utf-8', 'replace')


print('=' * 60)
print('Загрузка скрипта исправления на сервер')
print('=' * 60)

# PHP-скрипт, который чинит все 7 сниппетов
php_fix = """<?php
/**
 * Автоматическое исправление 7 повреждённых сниппетов.
 * Проблемы: BOM, отсутствие <?php в начале, short tags.
 */
$pdo = new PDO('mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8',
    'u0220513_modx', 'xP5rX0bA2rgM0cA2');
$pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);

$problem_ids = [125, 150, 167, 173, 182, 239, 240];
$results = [];

foreach ($problem_ids as $sid) {
    $stmt = $pdo->prepare('SELECT name, snippet FROM modx_site_snippets WHERE id = ?');
    $stmt->execute([$sid]);
    $r = $stmt->fetch(PDO::FETCH_ASSOC);
    if (!$r) {
        $results[$sid] = ['status' => 'NOT_FOUND', 'name' => '???'];
        continue;
    }

    $name = $r['name'];
    $body = $r['snippet'];
    $orig_len = strlen($body);
    $actions = [];

    // 1. Удаляем BOM (U+FEFF в начале)
    if (substr($body, 0, 3) === chr(239) . chr(187) . chr(191)) {
        $body = substr($body, 3);
        $actions[] = 'BOM удалён';
    } elseif (substr($body, 0, 1) === "\u{FEFF}") {
        $body = substr($body, 1);
        $actions[] = 'BOM удалён (UTF-8)';
    }

    // 2. Удаляем ведущие пустые строки
    $body = ltrim($body, "\\r\\n");

    // 3. Если начинается с //<?php — заменяем на чистый <?php
    if (substr(ltrim($body), 0, 6) === '//<?php') {
        $body = '<?php' . substr(ltrim($body), 6);
        $actions[] = '//<?php заменён на <?php';
    }

    // 4. Если нет <?php в начале — добавляем перед первым содержимым
    if (strpos($body, '<?php') !== 0) {
        // Определяем, что в начале
        $first_nl = strpos($body, "\\n");
        $first_line = $first_nl !== false ? substr($body, 0, $first_nl) : $body;
        $trimmed = ltrim($first_line);

        if (strpos($trimmed, '//') === 0 || strpos($trimmed, '*') === 0 || strpos($trimmed, '#') === 0) {
            // Комментарий в начале — вставляем <?php перед ним
            $body = '<?php\\n' . $body;
            $actions[] = '<?php добавлен перед комментарием';
        } else {
            $body = '<?php\\n' . $body;
            $actions[] = '<?php добавлен в начало';
        }
    }

    // 5. Удаляем дублирующий <?php если есть несколько
    if (substr_count($body, '<?php') > 1) {
        // Оставляем только первый, остальные удаляем
        $parts = explode('<?php', $body);
        $body = '<?php' . implode('', array_slice($parts, 1));
        $actions[] = 'дублирующие <?php удалены';
    }

    // 6. Сохраняем в БД
    $stmt2 = $pdo->prepare('UPDATE modx_site_snippets SET snippet = ?, editedon = UNIX_TIMESTAMP() WHERE id = ?');
    $stmt2->execute([$body, $sid]);

    $new_len = strlen($body);
    $results[$sid] = [
        'status' => 'DONE',
        'name' => $name,
        'orig_len' => $orig_len,
        'new_len' => $new_len,
        'actions' => $actions,
    ];
}

// Вывод результатов
echo "=== ПОСЛЕ ИСПРАВЛЕНИЯ ===\\n";
foreach ($results as $sid => $info) {
    echo "id={$sid} | {$info['name']}\\n";
    echo "  статус: {$info['status']}\\n";
    if ($info['status'] === 'DONE') {
        echo "  размер: {$info['orig_len']} → {$info['new_len']} байт\\n";
        echo "  действия: " . implode(', ', $info['actions']) . "\\n";
    }
    echo "\\n";
}

// Линт всех исправленных
echo "=== PHP LINT ===\\n";
foreach ($problem_ids as $sid) {
    if (!isset($results[$sid]) || $results[$sid]['status'] !== 'DONE') continue;
    $body = $pdo->query("SELECT snippet FROM modx_site_snippets WHERE id = {$sid}")->fetchColumn();
    $tmpFile = '/tmp/linstest_' . $sid . '.php';
    file_put_contents($tmpFile, $body);
    $out = shell_exec('php -l ' . escapeshellarg($tmpFile) . ' 2>&1');
    $ok = (strpos($out, 'No syntax errors') !== false);
    echo ($ok ? '✅' : '❌') . " id={$sid} {$results[$sid]['name']}: " . trim($out) . "\\n";
}

echo "\\nГотово.\\n";
"""

# Загружаем скрипт через SFTP
sftp = cli.open_sftp()
with sftp.file('/tmp/fix_all_7_snippets.php', 'w') as f:
    f.write(php_fix)
sftp.close()
print('Скрипт загружен на сервер')

# Запускаем
print()
print('=' * 60)
print('Запуск исправления')
print('=' * 60)
out, err = run('php /tmp/fix_all_7_snippets.php 2>&1')
print(out)
if err.strip():
    print('[stderr]', err[:500])

# Финальная проверка — последние 5 записей в логе
print()
print('=' * 60)
print('Последние 5 записей в event_log (должны быть без Parse Error)')
print('=' * 60)
out2, _ = run(
    "php -r \\\""
    "\\$pdo = new PDO('mysql:host=localhost;dbname=u0220513_new_deploy;charset=utf8',"
    "'u0220513_modx','xP5rX0bA2rgM0cA2');"
    "foreach(\\$pdo->query(\\\"SELECT id, FROM_UNIXTIME(createdon) t, source "
    "FROM modx_event_log ORDER BY id DESC LIMIT 5\\\") as \\$r) {"
    "  echo '['.\\$r['id'].'] '.\\$r['t'].' | '.\\$r['source'].\"\\\\n\\\";"
    "}\\\" 2>&1"
)
print(out2)

cli.close()
print()
print('DONE')
