<?php
/**
 * NPA-ZS | cache/static.php — статический HTML-кеш страниц НПА.
 *
 * Функции: getStaticFilePath, generateFilename, getRenderedCacheHtml.
 * Путь кеша: /assets/npa/{тип}/{год}/{npa_id}/{npa_id}_{дата}.html
 * Инвалидация: GET-параметры regenerate | force | nocache.
 * Источник: строки 530-541, 2023-2044 монолита snippet.php.
 */

function getStaticFilePath($npaData, $viewDateSql, $npa_id) {
    $year = ($npaData['npa_type'] === 'law')
        ? date('Y', strtotime($npaData['date_passed']))
        : date('Y', strtotime($npaData['date_signed'] ?? $npaData['date_passed'] ?? 'now'));
    $typeDir = $npaData['npa_type'] === 'law' ? 'law' : 'regulation';
    $staticBaseDir = MODX_BASE_PATH . 'assets/npa/' . $typeDir . '/' . $year . '/' . $npa_id . '/';
    if (!is_dir($staticBaseDir)) {
        mkdir($staticBaseDir, 0777, true);
    }
    return $staticBaseDir . $npa_id . '_' . $viewDateSql . '_v15.html';
}

/**
 * Резервный слой кеша: готовый HTML из npa_rendered_cache.
 * Таблица заполняется Python-импортёром (npazs.db.html_renderer) сразу после
 * импорта НПА — для каждой уникальной даты valid_from ревизий элементов.
 * Возвращает HTML или null (нет записи / таблица ещё не создана на хостинге —
 * тогда сайт тихо переходит к обычной генерации «на лету»).
 */
function getRenderedCacheHtml($pdo, $npa_id, $viewDateSql) {
    try {
        $stmt = $pdo->prepare(
            "SELECT html_full FROM npa_rendered_cache
             WHERE npa_id = ? AND as_of_date = ?
             LIMIT 1"
        );
        $stmt->execute([$npa_id, $viewDateSql]);
        $row = $stmt->fetch();
        if ($row && $row['html_full'] !== null && $row['html_full'] !== '') {
            return $row['html_full'];
        }
    } catch (PDOException $e) {
        // Таблицы нет / БД недоступна — fallback на генерацию.
    }
    return null;
}

function generateFilename($npaData, $revisions = []) {
    $isLaw = ($npaData['npa_type'] === 'law');
    $prefix = $isLaw ? 'zakon' : 'postanovlenie';
    $npaNumForFile = str_replace('ЗС', 'ZS', $npaData['npa_number']);
    $dateField = $isLaw ? 'date_passed' : 'date_passed';
    $baseDate = $npaData[$dateField] ?? $npaData['date_passed'] ?? '';
    $dt = parseDate($baseDate);
    $dateStr = $dt ? $dt->format('d_m_Y') : 'unknown';
    $filename = $prefix . '_' . $npaNumForFile . '_ot_' . $dateStr;
    if (!empty($revisions)) {
        $parts = [];
        foreach ($revisions as $rev) {
            $revNumForFile = str_replace('ЗС', 'ZS', $rev['revision_number']);
            $revDt = parseDate($rev['revision_date_reg']);
            $revDateStr = $revDt ? $revDt->format('d_m_Y') : 'unknown';
            $parts[] = $revNumForFile . '_ot_' . $revDateStr;
        }
        $filename .= '_redakciya_' . implode('_i_', $parts);
    }
    return $filename . '.rtf';
}

