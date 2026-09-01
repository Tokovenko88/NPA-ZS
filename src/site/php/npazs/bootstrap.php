<?php
/**
 * NPA-ZS | bootstrap.php — загрузка конфигурации окружения.
 *
 * Читает .env из каталога уровнем выше корня сайта (dirname(MODX_BASE_PATH)/.env)
 * и объявляет константы NPA_DB_HOST, NPA_DB_NAME, NPA_DB_USER, NPA_DB_PASS,
 * NPA_DB_CHARSET и др. Подключается ПЕРВЫМ из HtmlFromNpaZS.php (require_once).
 * Если .env отсутствует — die() с сообщением для администратора.
 * Источник: строки 1-25 монолита src/site/php/snippet.php (перенесены дословно).
 */

// ========== ЗАГРУЗКА ПЕРЕМЕННЫХ ИЗ .env ==========
$envFile = dirname(MODX_BASE_PATH) . '/.env';  // путь к вашему файлу

if (file_exists($envFile)) {
    $lines = file($envFile, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
    foreach ($lines as $line) {
        $line = trim($line);
        // Пропускаем комментарии (строки, начинающиеся с #)
        if (strpos($line, '#') === 0) continue;
        // Разбиваем по первому знаку "="
        $parts = explode('=', $line, 2);
        if (count($parts) === 2) {
            $key = trim($parts[0]);
            $value = trim($parts[1]);
            // Определяем константу, если её ещё нет
            if (!defined($key)) {
                define($key, $value);
            }
        }
    }
} else {
    // Если файл не найден — остановим выполнение с понятной ошибкой
    die('Ошибка: файл .env не найден. Обратитесь к администратору.');
}
