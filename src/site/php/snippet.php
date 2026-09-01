<?php
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

function parseDate($dateStr) {
    if (empty($dateStr)) return null;
    $dateStr = trim($dateStr);
    $originalTz = date_default_timezone_get();
    date_default_timezone_set('UTC');
    try {
        if (preg_match('/^\d{4}-\d{2}-\d{2}$/', $dateStr)) {
            $dt = DateTime::createFromFormat('Y-m-d', $dateStr);
            if ($dt && $dt->getLastErrors()['warning_count'] === 0) {
                date_default_timezone_set($originalTz);
                return $dt;
            }
        }
        if (preg_match('/^\d{2}\.\d{2}\.\d{4}$/', $dateStr)) {
            $dt = DateTime::createFromFormat('d.m.Y', $dateStr);
            if ($dt && $dt->getLastErrors()['warning_count'] === 0) {
                date_default_timezone_set($originalTz);
                return $dt;
            }
        }
        foreach (['d.m.Y', 'Y-m-d'] as $fmt) {
            try {
                $dt = DateTimeImmutable::createFromFormat($fmt, $dateStr);
                if ($dt && $dt->format($fmt) === $dateStr) {
                    date_default_timezone_set($originalTz);
                    return $dt;
                }
            } catch (Exception $e) {
                continue;
            }
        }
    } finally {
        date_default_timezone_set($originalTz);
    }
    return null;
}

function isRevisionCurrent($isDocExpired, $validToRaw, $validFromRaw, $asOfDate) {
    if ($isDocExpired) return false;
    return (is_null($validToRaw) || $validToRaw >= $asOfDate) && $validFromRaw <= $asOfDate;
}

function formatDateToRus($dateStr) {
    if (empty($dateStr)) return '';
    $dt = parseDate($dateStr);
    return $dt ? $dt->format('d.m.Y') : $dateStr;
}

function formatRusDate($dateStr, $dateFormat) {
    if (empty($dateStr)) return '';
    $dt = parseDate($dateStr);
    if (!$dt) return $dateStr;
    $day = (int)$dt->format('d');
    $month = (int)$dt->format('m');
    $year = $dt->format('Y');
    $months = [1 => 'января', 2 => 'февраля', 3 => 'марта', 4 => 'апреля', 5 => 'мая', 6 => 'июня',7 => 'июля', 8 => 'августа', 9 => 'сентября', 10 => 'октября', 11 => 'ноября', 12 => 'декабря'];
    $monthName = $months[$month] ?? '';
    $dayFormatted = ($dateFormat == 0) ? str_pad($day, 2, '0', STR_PAD_LEFT) : $day;
    return $dayFormatted . ' ' . $monthName . ' ' . $year . ' года';
}

function normalizeHighlightText($text) {
    if (empty($text)) return '';
    $text = str_replace(['–', '—', '‑', '‐'], '-', $text);
    $text = preg_replace('/\s+/', ' ', $text);
    return trim($text);
}

function getDisplayText($item, $isExpired = false, $noNameIds = [], $hideSectionPrefix = false) {
    $type = $item['item_type'];
    $number = $item['display_number'] ?? $item['item_number'] ?? '';
    $head = $item['item_head'];
    $itemId = $item['item_id'] ?? '';
    switch ($type) {
        case 'preamble':    $display = 'Преамбула'; break;
        case 'chapter':     $display = 'Глава ' . $number . ($head ? '. ' . $head : ''); break;
        case 'section':
            if ($hideSectionPrefix) {
                $display = $number . ($head ? '. ' . $head : '');
            } else {
                $display = 'Раздел ' . $number . ($head ? '. ' . $head : '');
            }
            break;
        case 'article':     $display = 'Статья ' . $number . ($head ? '. ' . $head : ''); break;
        case 'part':        $display = 'Часть ' . $number . ($head ? '. ' . $head : ''); break;
        case 'point':       $display = 'Пункт ' . $number . ($head ? '. ' . $head : ''); break;
        case 'subpoint':    $display = 'Подпункт ' . $number . ($head ? '. ' . $head : ''); break;
        case 'appendix':
        case 'nested_appendix': $display = 'Приложение ' . $number . ($head ? '. ' . $head : ''); break;
        case 'structured_table':
            if (!empty($head)) {
                $display = 'Таблица ' . $number . ($head ? '. ' . $head : '');
            } else {
                $display = '';
            }
            break;
        default:            $display = ''; break;
    }
    if ($isExpired && !empty($display)) {
        $suffix = '';
        if ($type === 'article') $suffix = 'а';
        elseif ($type === 'part') $suffix = 'а';
        elseif ($type === 'chapter') $suffix = 'а';
        elseif ($type === 'section') $suffix = 'а';
        elseif ($type === 'appendix' || $type === 'nested_appendix') $suffix = 'о';
        elseif ($type === 'structured_table') $suffix = 'ы';
        $display .= ' (Утратил' . $suffix . ' силу)';
    }
    return $display;
}

function getExpiryGenderSuffix($type) {
     switch ($type) {
            case 'article': return 'а';
            case 'part':    return 'а';
            case 'chapter': return 'а';
            case 'section': return 'а';
            case 'preamble':return 'а';
            case 'appendix':return 'о';
            case 'point':   return '';
            case 'subpoint':return '';
            default:        return '';
        }
}

function getLocalElementGenitive($itemType, $itemNumber) {
        $map = [
            'preamble'  => 'преамбулы',
            'chapter'   => 'главы',
            'section'   => 'раздела',
            'article'   => 'статьи',
            'part'      => 'части',
            'point'     => 'пункта',
            'subpoint'  => 'подпункта',
            'appendix'  => 'приложения',
            'nested_appendix' => 'приложения'
        ];
        $base = $map[$itemType] ?? 'элемента';
        if (in_array($itemType, ['preamble'])) {
            return $base;
        }
                return $base . ' ' . trim($itemNumber, '. ');
}

function normalizeHighlights($highlights) {
    $default = [
        'previous_edition' => ['deletion' => [], 'difference' => []],
        'current_edition'  => ['addition' => [], 'difference' => []]
    ];
    if (empty($highlights)) {
        return $default;
    }
    $toArray = function($data) use (&$toArray) {
        if (is_object($data)) {
            $data = (array) $data;
        }
        if (is_array($data)) {
            foreach ($data as $key => $value) {
                $data[$key] = $toArray($value);
            }
        }
        return $data;
    };
    if (is_string($highlights)) {
        $decoded = json_decode($highlights, true);
        if (is_array($decoded)) {
            $highlights = $decoded;
        } else {
            return $default;
        }
    }
    $highlights = $toArray($highlights);
    if (!is_array($highlights) || empty($highlights)) {
        return $default;
    }
    if (!isset($highlights['previous_edition']) || !is_array($highlights['previous_edition'])) {
        $highlights['previous_edition'] = [];
    }
    if (!isset($highlights['current_edition']) || !is_array($highlights['current_edition'])) {
        $highlights['current_edition'] = [];
    }
    foreach (['deletion', 'difference'] as $key) {
        if (!isset($highlights['previous_edition'][$key]) || !is_array($highlights['previous_edition'][$key])) {
            $highlights['previous_edition'][$key] = [];
        }
    }
    foreach (['addition', 'difference'] as $key) {
        if (!isset($highlights['current_edition'][$key]) || !is_array($highlights['current_edition'][$key])) {
            $highlights['current_edition'][$key] = [];
        }
    }
    return $highlights;
}

function getStaticFilePath($npaData, $viewDateSql, $npa_id) {
    $year = ($npaData['npa_type'] === 'law')
        ? date('Y', strtotime($npaData['date_passed']))
        : date('Y', strtotime($npaData['date_signed'] ?? $npaData['date_passed'] ?? 'now'));
    $typeDir = $npaData['npa_type'] === 'law' ? 'law' : 'regulation';
    $staticBaseDir = MODX_BASE_PATH . 'assets/npa/' . $typeDir . '/' . $year . '/' . $npa_id . '/';
    if (!is_dir($staticBaseDir)) {
        mkdir($staticBaseDir, 0777, true);
    }
    return $staticBaseDir . $npa_id . '_' . $viewDateSql . '_v14.html';
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

function getSelectedRevisionNpaIds(PDO $pdo, $baseNpaId, $viewDate) {
    if (empty($baseNpaId) || empty($viewDate)) {
        return [];
    }

    $stmt = $pdo->prepare("
        SELECT revision_id
        FROM npa_revision_info
        WHERE base_npa_id = ?
          AND revision_date_valid = ?
        ORDER BY revision_number ASC
    ");
    $stmt->execute([$baseNpaId, $viewDate]);

    $ids = [];
    foreach ($stmt->fetchAll() as $row) {
        if (isset($row['revision_id']) && (int)$row['revision_id'] > 0) {
            $ids[] = (int)$row['revision_id'];
        }
    }

    return array_values(array_unique($ids));
}

function buildRevisionNpaIdPlaceholders(array $revisionNpaIds) {
    return implode(',', array_fill(0, count($revisionNpaIds), '?'));
}

function getSelectedEditionRegistrationDate(PDO $pdo, $baseNpaId, array $selectedRevisionNpaIds = []) {
    if (empty($baseNpaId) || empty($selectedRevisionNpaIds)) {
        return null;
    }

    $placeholders = buildRevisionNpaIdPlaceholders($selectedRevisionNpaIds);
    $stmt = $pdo->prepare("
        SELECT MAX(revision_date_reg)
        FROM npa_revision_info
        WHERE base_npa_id = ?
          AND revision_id IN ($placeholders)
    ");
    $stmt->execute(array_merge([$baseNpaId], array_values($selectedRevisionNpaIds)));
    $date = $stmt->fetchColumn();

    return $date ?: null;
}

function getRevisionForSelectedEdition(PDO $pdo, $itemInternalId, $asOfDate, array $selectedRevisionNpaIds = []) {
    $revision = getRevisionForDate($pdo, $itemInternalId, $asOfDate);

    if (empty($selectedRevisionNpaIds)) {
        return $revision;
    }

    $placeholders = buildRevisionNpaIdPlaceholders($selectedRevisionNpaIds);
    $sql = "
        SELECT r.rev_id, r.valid_from, r.valid_to, r.mod_type, r.highlights, r.modified_by_id, r.not_valid
        FROM npa_item_revision r
        WHERE r.item_internal_id = ?
          AND EXISTS (
              SELECT 1
              FROM npa_item changer
              WHERE changer.npa_id IN ($placeholders)
                AND INSTR(
                    BINARY CONCAT(',', REPLACE(COALESCE(r.modified_by_id, ''), ' ', ''), ','),
                    BINARY CONCAT(',', CAST(changer.id AS CHAR), ',')
                ) > 0
          )
          AND EXISTS (
              SELECT 1 FROM npa_paragraph p WHERE p.rev_id = r.rev_id
          )
        ORDER BY r.valid_from DESC, r.rev_id DESC
        LIMIT 1
    ";
    $params = array_merge([$itemInternalId], array_values($selectedRevisionNpaIds));
    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    $selectedRevision = $stmt->fetch();

    if ($selectedRevision) {
        $selectedRevision['is_expired'] = false;
        return $selectedRevision;
    }

    return $revision;
}

function getItemRevisionTimelineForSelectedEdition(PDO $pdo, $itemInternalId, $asOfDate, array $selectedRevisionNpaIds = []) {
    $current = getRevisionForSelectedEdition($pdo, $itemInternalId, $asOfDate, $selectedRevisionNpaIds);
    if (!$current) return [];

    $stmt = $pdo->prepare("
        SELECT r.rev_id, r.valid_from, r.valid_to, r.modified_by_id, r.mod_type, r.not_valid
        FROM npa_item_revision r
        WHERE r.item_internal_id = ?
          AND EXISTS (SELECT 1 FROM npa_paragraph p WHERE p.rev_id = r.rev_id)
          AND (
              r.valid_from < ?
              OR (r.valid_from = ? AND r.rev_id <= ?)
              OR r.valid_from IS NULL
          )
        ORDER BY r.valid_from ASC, r.rev_id ASC
    ");
    $stmt->execute([$itemInternalId, $current['valid_from'], $current['valid_from'], $current['rev_id']]);
    return $stmt->fetchAll();
}

function getItemHeadRevisionTimelineForSelectedEdition(PDO $pdo, $itemInternalId, $asOfDate, array $selectedRevisionNpaIds = []) {
    $current = getItemHeadRevisionForSelectedEdition($pdo, $itemInternalId, $asOfDate, $selectedRevisionNpaIds);
    if (!$current) return [];

    $stmt = $pdo->prepare("
        SELECT id, head_text, valid_from, valid_to, modified_by_id, mod_type, highlights, not_valid
        FROM npa_item_head_revision r
        WHERE r.item_internal_id = ?
          AND (
              r.valid_from < ?
              OR (r.valid_from = ? AND r.id <= ?)
              OR r.valid_from IS NULL
          )
        ORDER BY r.valid_from ASC, r.id ASC
    ");
    $stmt->execute([$itemInternalId, $current['valid_from'], $current['valid_from'], $current['id']]);
    return $stmt->fetchAll();
}

function getItemHeadRevisionForSelectedEdition(PDO $pdo, $itemInternalId, $asOfDate, array $selectedRevisionNpaIds = []) {
    $revision = getItemHeadRevisionForDate($pdo, $itemInternalId, $asOfDate);

    if (empty($selectedRevisionNpaIds)) {
        return $revision;
    }

    $placeholders = buildRevisionNpaIdPlaceholders($selectedRevisionNpaIds);
    $sql = "
        SELECT r.id, r.head_text, r.valid_from, r.valid_to, r.highlights, r.mod_type, r.modified_by_id, r.not_valid
        FROM npa_item_head_revision r
        WHERE r.item_internal_id = ?
          AND EXISTS (
              SELECT 1
              FROM npa_item changer
              WHERE changer.npa_id IN ($placeholders)
                AND INSTR(BINARY CONCAT(',', REPLACE(COALESCE(r.modified_by_id, ''), ' ', ''), ','), BINARY CONCAT(',', CAST(changer.id AS CHAR), ',')) > 0
          )
        ORDER BY r.valid_from DESC, r.id DESC
        LIMIT 1
    ";
    $params = array_merge([$itemInternalId], array_values($selectedRevisionNpaIds));
    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    $selectedRevision = $stmt->fetch();

    if ($selectedRevision) {
        $selectedRevision['is_expired'] = false;
        return $selectedRevision;
    }

    return $revision;
}

function getItemNumberForSelectedEdition(PDO $pdo, $itemInternalId, $asOfDate, array $selectedRevisionNpaIds = []) {
    $number = getItemNumberForDate($pdo, $itemInternalId, $asOfDate);

    if (empty($selectedRevisionNpaIds)) {
        return $number;
    }

    $placeholders = buildRevisionNpaIdPlaceholders($selectedRevisionNpaIds);
    $sql = "
        SELECT r.number_text
        FROM npa_item_number_revision r
        WHERE r.item_internal_id = ?
          AND EXISTS (
              SELECT 1
              FROM npa_item changer
              WHERE changer.npa_id IN ($placeholders)
                AND INSTR(BINARY CONCAT(',', REPLACE(COALESCE(r.modified_by_id, ''), ' ', ''), ','), BINARY CONCAT(',', CAST(changer.id AS CHAR), ',')) > 0
          )
        ORDER BY r.valid_from DESC
        LIMIT 1
    ";
    $params = array_merge([$itemInternalId], array_values($selectedRevisionNpaIds));
    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    $selected = $stmt->fetchColumn();

    return ($selected !== false) ? $selected : $number;
}

function getItemPrefixRevisionForSelectedEdition($itemInternalId, $asOfDate, $pdo, array $selectedRevisionNpaIds = []) {
    $prefix = getItemPrefixRevision($itemInternalId, $asOfDate, $pdo);

    if (empty($selectedRevisionNpaIds)) {
        return $prefix;
    }

    $placeholders = buildRevisionNpaIdPlaceholders($selectedRevisionNpaIds);
    $sql = "
        SELECT r.*
        FROM npa_item_prefix_revision r
        WHERE r.item_internal_id = ?
          AND EXISTS (
              SELECT 1
              FROM npa_item changer
              WHERE changer.npa_id IN ($placeholders)
                AND INSTR(BINARY CONCAT(',', REPLACE(COALESCE(r.modified_by_id, ''), ' ', ''), ','), BINARY CONCAT(',', CAST(changer.id AS CHAR), ',')) > 0
          )
        ORDER BY r.valid_from DESC
        LIMIT 1
    ";
    $params = array_merge([$itemInternalId], array_values($selectedRevisionNpaIds));
    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    $selected = $stmt->fetch();

    if ($selected) {
        $selected['is_expired'] = 0;
        return $selected;
    }

    return $prefix;
}

function isDeferredSelectedEditionRevision($revision, $viewDate, array $selectedRevisionNpaIds = []) {
    if (empty($selectedRevisionNpaIds) || empty($revision['valid_from']) || empty($viewDate)) {
        return false;
    }

    $revisionDate = parseDate($revision['valid_from']);
    $viewDateObj = parseDate($viewDate);

    if (!$revisionDate || !$viewDateObj) {
        return false;
    }

    return $revisionDate->format('Y-m-d') > $viewDateObj->format('Y-m-d');
}

function getPreviousItemRevision(PDO $pdo, $itemInternalId, $currentRevId) {
    $stmt = $pdo->prepare("
        SELECT r.*
        FROM npa_item_revision r
        WHERE r.item_internal_id = ?
          AND (
              r.valid_from < (SELECT c.valid_from FROM npa_item_revision c WHERE c.rev_id = ?)
              OR (
                  r.valid_from = (SELECT c.valid_from FROM npa_item_revision c WHERE c.rev_id = ?)
                  AND r.rev_id < ?
              )
          )
          AND EXISTS (SELECT 1 FROM npa_paragraph p WHERE p.rev_id = r.rev_id)
        ORDER BY r.valid_from DESC, r.rev_id DESC
        LIMIT 1
    ");
    $stmt->execute([$itemInternalId, $currentRevId, $currentRevId, $currentRevId]);
    return $stmt->fetch();
}

function getRevisionForDate(PDO $pdo, $itemInternalId, $asOfDate) {
    $stmt = $pdo->prepare("
        SELECT rev_id, valid_from, valid_to, mod_type, highlights, modified_by_id, not_valid
        FROM npa_item_revision
        WHERE item_internal_id = ?
          AND (valid_from <= ? OR valid_from IS NULL)
          AND (valid_to IS NULL OR valid_to >= ?)
        ORDER BY valid_from DESC
        LIMIT 1
    ");
    $stmt->execute([$itemInternalId, $asOfDate, $asOfDate]);
    $active = $stmt->fetch();
    if ($active) {
        $active['is_expired'] = false;
        return $active;
    }
    $stmt = $pdo->prepare("
        SELECT rev_id, valid_from, valid_to, mod_type, highlights, modified_by_id, not_valid
        FROM npa_item_revision
        WHERE item_internal_id = ?
          AND valid_from <= ?
          AND valid_to < ?
        ORDER BY valid_from DESC
        LIMIT 1
    ");
    $stmt->execute([$itemInternalId, $asOfDate, $asOfDate]);
    $expired = $stmt->fetch();
    if ($expired) {
        $expired['is_expired'] = true;
        return $expired;
    }
    return null;
}

function getActiveRecord(PDO $pdo, $table, $idField, $idValue, $asOfDate) {
    $sql = "SELECT * FROM `$table`
            WHERE `$idField` = ?
              AND (`valid_from` <= ? OR `valid_from` IS NULL)
              AND (`valid_to` IS NULL OR `valid_to` >= ?)
            ORDER BY `valid_from` DESC
            LIMIT 1";
    $stmt = $pdo->prepare($sql);
    $stmt->execute([$idValue, $asOfDate, $asOfDate]);
    $row = $stmt->fetch();
    if ($row) {
        $row['is_expired'] = 0;
        return $row;
    }
    $sql = "SELECT * FROM `$table`
            WHERE `$idField` = ?
              AND `valid_from` <= ?
              AND `valid_to` < ?
            ORDER BY `valid_from` DESC
            LIMIT 1";
    $stmt = $pdo->prepare($sql);
    $stmt->execute([$idValue, $asOfDate, $asOfDate]);
    $expired = $stmt->fetch();
    if ($expired) {
        $expired['is_expired'] = 1;
        return $expired;
    }
    return null;
}

function getLastContentRevision(PDO $pdo, $internal_item_id, $asOfDate = null) {
    if ($asOfDate) {
        $stmt = $pdo->prepare("
            SELECT rev_id, valid_from, valid_to
            FROM npa_item_revision
            WHERE item_internal_id = ?
              AND valid_from <= ?
              AND (valid_to IS NULL OR valid_to >= ?)
              AND EXISTS (SELECT 1 FROM npa_paragraph p WHERE p.rev_id = npa_item_revision.rev_id)
            ORDER BY valid_from DESC
        ");
        $stmt->execute([$internal_item_id, $asOfDate, $asOfDate]);
        $active = $stmt->fetch();
        if ($active) return $active;
        
        $stmt = $pdo->prepare("
            SELECT rev_id, valid_from, valid_to
            FROM npa_item_revision
            WHERE item_internal_id = ?
              AND valid_from <= ?
              AND (valid_to IS NULL OR valid_to >= ?)
              AND EXISTS (SELECT 1 FROM npa_paragraph p WHERE p.rev_id = npa_item_revision.rev_id)
            ORDER BY valid_from DESC
        ");
        $stmt->execute([$internal_item_id, $asOfDate, $asOfDate]);
        return $stmt->fetch();
    } else {
        $stmt = $pdo->prepare("
            SELECT rev_id, valid_from, valid_to
            FROM npa_item_revision
            WHERE item_internal_id = ?
              AND EXISTS (SELECT 1 FROM npa_paragraph p WHERE p.rev_id = npa_item_revision.rev_id)
            ORDER BY valid_from DESC
        ");
        $stmt->execute([$internal_item_id]);
        return $stmt->fetch();
    }
}

function getPreviousItemHeadRevision(PDO $pdo, $itemInternalId, $currentRevId) {
    $stmt = $pdo->prepare("
        SELECT r.*
        FROM npa_item_head_revision r
        WHERE r.item_internal_id = ?
          AND (
              r.valid_from < (SELECT c.valid_from FROM npa_item_head_revision c WHERE c.id = ?)
              OR (
                  r.valid_from = (SELECT c.valid_from FROM npa_item_head_revision c WHERE c.id = ?)
                  AND r.id < ?
              )
          )
        ORDER BY r.valid_from DESC, r.id DESC
        LIMIT 1
    ");
    $stmt->execute([$itemInternalId, $currentRevId, $currentRevId, $currentRevId]);
    return $stmt->fetch();
}

function getItemHeadRevisionForDate(PDO $pdo, $itemInternalId, $asOfDate) {
    $stmt = $pdo->prepare("
        SELECT id, head_text, valid_from, valid_to, highlights, mod_type, modified_by_id, not_valid
        FROM npa_item_head_revision
        WHERE item_internal_id = ?
          AND (valid_from <= ? OR valid_from IS NULL)
          AND (valid_to IS NULL OR valid_to >= ?)
        ORDER BY valid_from DESC
        LIMIT 1
    ");
    $stmt->execute([$itemInternalId, $asOfDate, $asOfDate]);
    $active = $stmt->fetch();
    if ($active) {
        $active['is_expired'] = false;
        return $active;
    }
    $stmt = $pdo->prepare("
        SELECT id, head_text, valid_from, valid_to, highlights, mod_type, modified_by_id, not_valid
        FROM npa_item_head_revision
        WHERE item_internal_id = ?
          AND valid_from <= ?
          AND valid_to < ?
        ORDER BY valid_from DESC
        LIMIT 1
    ");
    $stmt->execute([$itemInternalId, $asOfDate, $asOfDate]);
    $expired = $stmt->fetch();
    if ($expired) {
        $expired['is_expired'] = true;
        return $expired;
    }
    return null;
}

function getHeadRevisionForDate(PDO $pdo, $npa_id, $asOfDate) {
    $stmt = $pdo->prepare("
        SELECT id, npa_title, valid_from, valid_to, highlights, modified_by_id, not_valid
        FROM npa_head_revision
        WHERE npa_id = ?
          AND (valid_from <= ? OR valid_from IS NULL)
          AND (valid_to IS NULL OR valid_to >= ?)
        ORDER BY valid_from DESC
        LIMIT 1
    ");
    $stmt->execute([$npa_id, $asOfDate, $asOfDate]);
    $active = $stmt->fetch();
    if ($active) {
        $active['is_expired'] = false;
        return $active;
    }
    $stmt = $pdo->prepare("
        SELECT id, npa_title, valid_from, valid_to, highlights, modified_by_id, not_valid
        FROM npa_head_revision
        WHERE npa_id = ?
          AND valid_from <= ?
          AND valid_to < ?
        ORDER BY valid_from DESC
        LIMIT 1
    ");
    $stmt->execute([$npa_id, $asOfDate, $asOfDate]);
    $expired = $stmt->fetch();
    if ($expired) {
        $expired['is_expired'] = true;
        return $expired;
    }
    return null;
}

function getItemNumberForDate(PDO $pdo, $itemInternalId, $asOfDate) {
    $stmt = $pdo->prepare("
        SELECT number_text, valid_to
        FROM npa_item_number_revision
        WHERE item_internal_id = ?
          AND (valid_from <= ? OR valid_from IS NULL)
        ORDER BY valid_from DESC
    ");
    $stmt->execute([$itemInternalId, $asOfDate]);
    $revisions = $stmt->fetchAll();
    if (empty($revisions)) {
        return null;
    }
    foreach ($revisions as $rev) {
        if (is_null($rev['valid_to']) || $rev['valid_to'] >= $asOfDate) {
            return $rev['number_text'];
        }
    }
    return $revisions[0]['number_text'];
}
function getItemNumberAtDate(PDO $pdo, $itemInternalId, $asOfDate) {
    $stmt = $pdo->prepare("
        SELECT number_text FROM npa_item_number_revision
        WHERE item_internal_id = ?
          AND (valid_from <= ? OR valid_from IS NULL)
          AND (valid_to IS NULL OR valid_to >= ?)
        ORDER BY valid_from DESC
        LIMIT 1
    ");
    $stmt->execute([$itemInternalId, $asOfDate, $asOfDate]);
    $rev = $stmt->fetch();
    if ($rev) {
        return $rev['number_text'];
    }
    return null;
}

function getItemPrefixRevision($item_internal_id, $asOfDate, $pdo) {
    $sql = "SELECT * FROM npa_item_prefix_revision
            WHERE item_internal_id = ?
              AND (valid_from <= ? OR valid_from IS NULL)
              AND (valid_to IS NULL OR valid_to >= ?)
            ORDER BY valid_from DESC LIMIT 1";
    $stmt = $pdo->prepare($sql);
    $stmt->execute([$item_internal_id, $asOfDate, $asOfDate]);
    $rev = $stmt->fetch();
    if ($rev) {
        $rev['is_expired'] = 0;
        return $rev;
    }
    return null;
}

function getDocMaxDate(PDO $pdo, $npa_id, $asOfDate = null) {
    $stmtMax = $pdo->prepare("
        SELECT MAX(valid_from) as max_date FROM (
            SELECT valid_from FROM npa_base WHERE npa_id = ?
            UNION
            SELECT revision_date_valid FROM npa_revision_info WHERE base_npa_id = ?
        ) AS dates
    ");
    $stmtMax->execute([$npa_id, $npa_id]);
    $maxRow = $stmtMax->fetch();
    $maxDate = $maxRow['max_date'] ?? null;
    if ($asOfDate && ($maxDate === null || $asOfDate > $maxDate)) {
        $maxDate = $asOfDate;
    }
    return $maxDate;
}

function getDocumentStatus(PDO $pdo, $npa_id, $viewDateSql) {
    $stmt = $pdo->prepare("SELECT valid_from, not_valid, not_valid_note, not_valid_npa_id, date_format FROM npa_base WHERE npa_id = ?");
    $stmt->execute([$npa_id]);
    $base = $stmt->fetch();
    if (!$base) {
        return ['status' => 'unknown', 'message' => ''];
    }
    $validFrom = $base['valid_from'];
    $notValid = $base['not_valid'] ?? null;
    $notValidNote = $base['not_valid_note'] ?? '';
    $dateFormat = (int)$base['date_format'];
    if ($validFrom && $viewDateSql < $validFrom) {
        $formattedDate = formatRusDate($validFrom, $dateFormat);
        return [
            'status' => 'future',
            'message' => "Документ вступает в силу с {$formattedDate}"
        ];
    }
    if ($notValid) {
        $dtNotValid = parseDate($notValid);
        if ($dtNotValid) {
            $dtNotValid->modify('+1 day');
            $formattedDate = formatRusDate($dtNotValid->format('Y-m-d'), $dateFormat);
        } else {
            $formattedDate = formatRusDate($notValid, $dateFormat);
        }
        $maxDate = getDocMaxDate($pdo, $npa_id, $viewDateSql);
        $isAlreadyExpired = ($maxDate !== null && $maxDate >= $notValid);
        $msg = $isAlreadyExpired ? "Документ утратил силу с {$formattedDate}" : "Документ утрачивает силу с {$formattedDate}";
        $cancellingNpaId = $base['not_valid_npa_id'] ?? null;
        if ($cancellingNpaId) {
            $stmtCancel = $pdo->prepare("SELECT npa_type, npa_number, npa_url, date_passed FROM npa_base WHERE npa_id = ?");
            $stmtCancel->execute([$cancellingNpaId]);
            $cancellingNpa = $stmtCancel->fetch();
            if ($cancellingNpa) {
                $type = ($cancellingNpa['npa_type'] === 'law') ? 'Закона' : 'Постановления Законодательного Собрания';
                $datePassed = formatRusDate($cancellingNpa['date_passed'], $dateFormat);
                $url = $cancellingNpa['npa_url'] ?? '';
                $cancellingText = $type . ' города Севастополя № ' . $cancellingNpa['npa_number'] . ' от ' . $datePassed;
                if ($url) {
                    $cancellingText = '<a href="' . $url . '" target="_blank" class="npa-revision-link">' . $cancellingText . '</a>';
                }
                $msg .= ' — ' . $cancellingText;
            }
        }
        if (!empty($notValidNote)) {
            $msg .= ' (' . htmlspecialchars($notValidNote) . ')';
        }
        return [
            'status' => $isAlreadyExpired ? 'expired' : 'future_expired',
            'message' => $msg
        ];
    }
    return ['status' => 'active', 'message' => ''];
}

function getActiveRevisionsForDate(PDO $pdo, $npa_id, $date) {
    $stmt = $pdo->prepare("
        SELECT * FROM npa_revision_info
        WHERE base_npa_id = ?
          AND revision_date_valid <= ?
        ORDER BY revision_date_valid ASC, revision_number ASC
    ");
    $stmt->execute([$npa_id, $date]);
    return $stmt->fetchAll();
}

function getExactRevisionsForDate(PDO $pdo, $npa_id, $date) {
    $stmt = $pdo->prepare("
        SELECT * FROM npa_revision_info
        WHERE base_npa_id = ?
          AND revision_date_valid = ?
        ORDER BY revision_number ASC
    ");
    $stmt->execute([$npa_id, $date]);
    return $stmt->fetchAll();
}

function getHeadRevisionsList(PDO $pdo, $npa_id, $asOfDate) {
    $stmtBaseValid = $pdo->prepare("SELECT not_valid FROM npa_base WHERE npa_id = ?");
    $stmtBaseValid->execute([$npa_id]);
    $baseRow = $stmtBaseValid->fetch();
    $notValidDate = $baseRow ? ($baseRow['not_valid'] ?? null) : null;
    $maxDate = getDocMaxDate($pdo, $npa_id, $asOfDate);
    $isDocExpired = $notValidDate && ($maxDate !== null && $maxDate >= $notValidDate);
    $sql = "SELECT id, npa_title, valid_from, valid_to, modified_by_id, not_valid
            FROM npa_head_revision
            WHERE npa_id = ?";
    $params = [$npa_id];
    if ($isDocExpired && $notValidDate) {
        $sql .= " AND valid_from < ?";
        $params[] = $notValidDate;
    }
    $sql .= " ORDER BY valid_from ASC";
    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    $revisions = $stmt->fetchAll();
    $totalRevs = count($revisions);
    $result = [];
    foreach ($revisions as $idx => $rev) {
        $dt = parseDate($rev['valid_from']);
        $validFromDate = $dt ? $dt->format('d.m.Y') : '';
        $validToDate = '';
        if ($rev['valid_to']) {
            $dtTo = parseDate($rev['valid_to']);
            $validToDate = $dtTo ? $dtTo->format('d.m.Y') : '';
        }
        $isLastRev = ($idx === $totalRevs - 1);
        $revValidToDate = !empty($rev['valid_to']) ? substr($rev['valid_to'], 0, 10) : null;
        $isExpiredRev = $isLastRev && ($isDocExpired || ($revValidToDate !== null && $revValidToDate < $asOfDate) || (!empty($rev['not_valid']) && $revValidToDate === null));
        $expirySource = '';
        $expiryUrl = '';
        if ($idx === 0) {
            $displayTitle = 'Исходное наименование';
            $sourceDecode = 'исходная редакция';
            $npaUrl = '';
            $elementPath = 'наименование документа';
        } else {
            $changerElementId = (int)$rev['modified_by_id'];
            $npaInfo = getNpaInfoByItemId($changerElementId, $pdo);
            if ($npaInfo) {
                $typeName = ($npaInfo['npa_type'] === 'law') ? 'Закона' : 'Постановления Законодательного Собрания';
                $dateForDisplay = formatRusDate($npaInfo['date_passed'], $npaInfo['date_format']);
                $displayTitle = $typeName . ' города Севастополя № ' . $npaInfo['npa_number'] . ' от ' . $dateForDisplay;
                $sourceDecode = getElementHumanPath($changerElementId, $pdo);
                $npaUrl = $npaInfo['npa_url'] ?? '';
            } else {
                $displayTitle = 'Неизвестный документ';
                $sourceDecode = '';
                $npaUrl = '';
            }
            $elementPath = 'наименование документа';
        }
        if ($isExpiredRev) {
            $notValidId = $rev['not_valid'] ?? null;
            if ($notValidId && $notValidId !== 'base') {
                $expiryNpaInfo = getNpaInfoByItemId($notValidId, $pdo);
                if ($expiryNpaInfo) {
                    $typeName = ($expiryNpaInfo['npa_type'] === 'law') ? 'Закона' : 'Постановления Законодательного Собрания';
                    $dateForDisplay = formatRusDate($expiryNpaInfo['date_passed'], $expiryNpaInfo['date_format']);
                    $expirySource = $typeName . ' города Севастополя № ' . $expiryNpaInfo['npa_number'] . ' от ' . $dateForDisplay;
                    $expiryUrl = $expiryNpaInfo['npa_url'] ?? '';
                }
            }
            $displayTitle = $expirySource ?: 'последнее действующее наименование';
            $sourceDecode = $expirySource ?: 'последнее действующее наименование';
            $npaUrl = $expiryUrl;
        }
        $result[] = [
            'rev_id'         => $rev['id'],
            'valid_from'     => $validFromDate,
            'valid_to'       => $validToDate,
            'valid_to_raw'   => $rev['valid_to'],
            'valid_from_raw' => $rev['valid_from'],
            'source_decode'  => $sourceDecode,
            'modified_by_id' => $rev['modified_by_id'],
            'display_title'  => $displayTitle,
            'is_original'    => ($idx === 0 && !$isExpiredRev),
            'is_expired'     => $isExpiredRev,
            'expiry_source'  => $expirySource,
            'expiry_url'     => $expiryUrl,
            'element_path'   => $elementPath,
            'npa_title'      => $rev['npa_title'],
            'npa_url'        => $npaUrl
        ];
    }
    $count = count($result);
    if ($count > 0) {
        $maxDate2 = getDocMaxDate($pdo, $npa_id, $asOfDate);
        $isDocExpired = $notValidDate && ($maxDate2 !== null && $maxDate2 >= $notValidDate);
        $currentIndex = -1;
        foreach ($result as $idx => $rev) {
            if ((is_null($rev['valid_to_raw']) || $rev['valid_to_raw'] >= $asOfDate) && $rev['valid_from_raw'] <= $asOfDate) {
                $currentIndex = $idx;
                break;
            }
        }
        if ($currentIndex >= 0 && !$isDocExpired) {
            $result[$currentIndex]['is_current'] = true;
        } elseif ($currentIndex < 0 && !$isDocExpired) {
            $result[$count - 1]['is_current'] = true;
        }
    }
    return $result;
}

function getHeadRevisionContent(PDO $pdo, $rev_id, $npa_id, $asOfDate) {
    $stmt = $pdo->prepare("
        SELECT * FROM npa_head_revision
        WHERE id = ? AND npa_id = ? AND (valid_from <= ? OR valid_from IS NULL) AND (valid_to IS NULL OR valid_to >= ?)
        LIMIT 1
    ");
    $stmt->execute([$rev_id, $npa_id, $asOfDate, $asOfDate]);
    $rev = $stmt->fetch();
    if (!$rev) {
        return null;
    }
    $html = '<div class="npa-head-block">';
    $html .= '<p class="npa-doc-title"><b>' . htmlspecialchars($rev['npa_title']) . '</b></p>';
    $html .= '</div>';
    $sourceInfo = '';
    if ($rev['modified_by_id'] && $rev['modified_by_id'] !== 'base') {
        $sourceInfo = getShortNpaDescription($rev['modified_by_id'], $pdo, true, 'nominative');
        if ($sourceInfo && $sourceInfo !== 'исходная редакция') {
            $sourceInfo = 'Внесено: ' . $sourceInfo;
        } elseif ($sourceInfo === 'исходная редакция') {
            $sourceInfo = 'Исходная редакция';
        }
    } else {
        $sourceInfo = 'Исходная редакция';
    }
    $npaInfo = null;
    if ($rev['modified_by_id'] && $rev['modified_by_id'] !== 'base') {
        $npaInfo = getNpaInfoByItemId((int)$rev['modified_by_id'], $pdo);
    }
    return [
        'html' => $html,
        'modified_by_id' => $rev['modified_by_id'],
        'valid_from' => $rev['valid_from'],
        'valid_to' => $rev['valid_to'],
        'source_info' => $sourceInfo,
        'npa_url' => $npaInfo['npa_url'] ?? '',
        'display_title' => $npaInfo ? ($npaInfo['npa_type'] === 'law' ? 'Закона' : 'Постановления Законодательного Собрания') . ' города Севастополя № ' . $npaInfo['npa_number'] . ' от ' . formatRusDate($npaInfo['date_passed'], $npaInfo['date_format']) : ''
    ];
}

function getDocumentRevisionNote($activeRevInfos, $npaType, $pdo, $baseNpaId) {
    if (empty($activeRevInfos)) return '';
    $typeName   = ($npaType === 'law') ? 'Закона'  : 'Постановления Законодательного Собрания';
    $pluralType = ($npaType === 'law') ? 'Законов' : 'Постановлений Законодательного Собрания';
    $items = [];
    foreach ($activeRevInfos as $rev) {
        $dateReg = formatDateToRus($rev['revision_date_reg']);
        $revisionNumber = $rev['revision_number'];
        $revisionUrl = $rev['revision_url'] ?? '';
        if ($revisionUrl) {
            $items[] = '<a href="' . htmlspecialchars($revisionUrl) . '" target="_blank" class="npa-revision-link">№ ' . htmlspecialchars($revisionNumber) . ' от ' . $dateReg . '</a>';
        } else {
            $items[] = '№ ' . htmlspecialchars($revisionNumber) . ' от ' . $dateReg;
        }
    }
    if (empty($items)) return '';
    $word = (count($items) === 1) ? $typeName : $pluralType;
    return '<div class="document-revision-note" style="margin: 0.5em 0; text-align: center;">'
         . 'В редакции ' . $word . ' города Севастополя ' . implode('; ', $items)
         . '</div>';
}

function getNpaInfoByItemId($itemInternalId, $pdo) {
    $stmt = $pdo->prepare("
        SELECT b.npa_id, b.npa_type, b.npa_number, b.date_passed, b.date_format, b.npa_url,
               l.date_signed AS law_date_signed
        FROM npa_item i
        JOIN npa_base b ON i.npa_id = b.npa_id
        LEFT JOIN npa_law l ON b.npa_id = l.npa_id
        WHERE i.id = ? OR i.item_id = ?
        LIMIT 1
    ");
    $stmt->execute([$itemInternalId, $itemInternalId]);
    $row = $stmt->fetch();
    if (!$row) {
        // Fallback: $itemInternalId может быть npa_base.npa_id (например, revision_id
        // из npa_revision_info, переданный в getShortNpaDescription из fallback-механизма
        // getElementRevisionNotes/getItemHeadRevisionNotes). Прямой поиск по npa_base.npa_id.
        $stmt = $pdo->prepare("
            SELECT b.npa_id, b.npa_type, b.npa_number, b.date_passed, b.date_format, b.npa_url,
                   l.date_signed AS law_date_signed
            FROM npa_base b
            LEFT JOIN npa_law l ON b.npa_id = l.npa_id
            WHERE b.npa_id = ?
            LIMIT 1
        ");
        $stmt->execute([$itemInternalId]);
        $row = $stmt->fetch();
        if (!$row) return null;
    }
    $npaType = $row['npa_type'];
    $datePassed = $row['date_passed'];
    $dateSigned = ($npaType == 'law') ? $row['law_date_signed'] : $datePassed;
    return [
        'npa_id'      => $row['npa_id'],
        'npa_number'  => $row['npa_number'],
        'npa_type'    => $npaType,
        'date_passed' => $datePassed,
        'date_signed' => $dateSigned,
        'date_format' => (int)$row['date_format'],
        'npa_url'     => $row['npa_url'] ?? ''
    ];
}

function getShortNpaDescription($modifiedById, $pdo, $asHtml = false, $case = 'genitive') {
    if (empty($modifiedById) || $modifiedById === 'base') {
        return 'исходная редакция';
    }
    
    $npaInfo = getNpaInfoByItemId($modifiedById, $pdo);
    if (!$npaInfo) {
        if (!preg_match('/\d+/', $modifiedById, $matches)) {
            return $modifiedById;
        }
        $itemInternalId = (int)$matches[0];
        $npaInfo = getNpaInfoByItemId($itemInternalId, $pdo);
        if (!$npaInfo) {
            return $modifiedById;
        }
    }
    
    if ($case === 'nominative') {
        $typeName = ($npaInfo['npa_type'] === 'law')
            ? 'Закон города Севастополя'
            : 'Постановление Законодательного Собрания города Севастополя';
    } else {
        $typeName = ($npaInfo['npa_type'] === 'law')
            ? 'Закона'
            : 'Постановления Законодательного Собрания';
    }
    $dateForDisplay = formatRusDate($npaInfo['date_passed'], $npaInfo['date_format']);
    $text = $typeName . ' № ' . $npaInfo['npa_number'] . ' от ' . $dateForDisplay;
    if ($asHtml && !empty($npaInfo['npa_url'])) {
        return '<a href="' . htmlspecialchars($npaInfo['npa_url']) . '" target="_blank" class="npa-revision-link" style="color:#0066cc;text-decoration:underline;">' . htmlspecialchars($text) . '</a>';
    }
    return $text;
}

function getElementHumanPath($itemInternalId, $pdo, $case = 'nominative') {
    $stmt = $pdo->prepare("SELECT item_type, item_number, parent_id FROM npa_item WHERE id = ? OR item_id = ? LIMIT 1");
    $stmt->execute([$itemInternalId, $itemInternalId]);
    $item = $stmt->fetch(PDO::FETCH_ASSOC);
    if (!$item) return '';
    $stmtHead = $pdo->prepare("SELECT head_text FROM npa_item_head_revision WHERE item_internal_id = ? ORDER BY valid_from DESC LIMIT 1");
    $stmtHead->execute([$item['id']]);
    $head = $stmtHead->fetch();
    $itemHead = $head ? $head['head_text'] : '';
    $typeMap = [
        'preamble' => 'преамбула',
        'chapter'  => 'глава',
        'section'  => 'раздел',
        'article'  => 'статья',
        'part'     => 'часть',
        'point'    => 'пункт',
        'subpoint' => 'подпункт',
        'appendix' => 'приложение',
        'nested_appendix' => 'приложение',
        'structured_table' => 'Таблица'
    ];
    $typeNominative = $typeMap[$item['item_type']] ?? $item['item_type'];
    $number = trim($item['item_number'], '. ');
    if ($item['item_type'] === 'structured_table') {
        if (empty($itemHead)) {
            return '';
        }
        $current = $typeNominative . ' ' . $number . ($itemHead ? '. ' . $itemHead : '');
    } else {
        $current = $typeNominative . ($number ? ' ' . $number : '');
    }
    if ($item['parent_id']) {
        $parentPath = getElementHumanPath($item['parent_id'], $pdo, 'nominative');
        if ($parentPath) {
            $parentWords = explode(' ', $parentPath, 2);
            $parentType = $parentWords[0];
            $parentNumber = $parentWords[1] ?? '';
            $genitiveMap = [
                'преамбула' => 'преамбулы',
                'глава'     => 'главы',
                'раздел'    => 'раздела',
                'статья'    => 'статьи',
                'часть'     => 'части',
                'пункт'     => 'пункта',
                'подпункт'  => 'подпункта',
                'приложение'=> 'приложения',
                'Таблица'   => 'таблицы'
            ];
            $genitiveType = $genitiveMap[$parentType] ?? $parentType;
            $parentGenitive = $genitiveType . ($parentNumber ? ' ' . $parentNumber : '');
            $current .= ' ' . $parentGenitive;
        }
    }
    if ($case === 'genitive') {
        $genMap = [
            'преамбула' => 'преамбулы',
            'глава'     => 'главы',
            'раздел'    => 'раздела',
            'статья'    => 'статьи',
            'часть'     => 'части',
            'пункт'     => 'пункта',
            'подпункт'  => 'подпункта',
            'приложение'=> 'приложения',
            'Таблица'   => 'таблицы'
        ];
        uksort($genMap, function($a, $b) {
            return strlen($b) - strlen($a);
        });
        foreach ($genMap as $nom => $gen) {
            $current = preg_replace('/\b' . preg_quote($nom, '/') . '\b/u', $gen, $current);
        }
    }
    return $current;
}

function getRevisionDocNoteImproved($modifiedBy, $pdo, $case = 'genitive', $asHtml = false) {
    if (empty($modifiedBy) || $modifiedBy === 'base') {
        return 'исходная редакция';
    }
    
    $elementPath = getElementHumanPath($modifiedBy, $pdo, $case);
    if (!$elementPath) {
        return $modifiedBy;
    }
    
    $npaInfo = getNpaInfoByItemId($modifiedBy, $pdo);
    if (!$npaInfo) {
        if (!preg_match('/\d+/', $modifiedBy, $matches)) {
            return $modifiedBy;
        }
        $itemInternalId = (int)$matches[0];
        $npaInfo = getNpaInfoByItemId($itemInternalId, $pdo);
        if (!$npaInfo) {
            return $elementPath;
        }
    }
    
    $dateForDisplay = formatRusDate($npaInfo['date_passed'], $npaInfo['date_format']);
    $typeName = ($npaInfo['npa_type'] === 'law') ? 'Закона' : 'Постановления Законодательного Собрания';
    $npaText = $typeName . ' города Севастополя № ' . $npaInfo['npa_number'] . ' от ' . $dateForDisplay;
    if ($asHtml && !empty($npaInfo['npa_url'])) {
        $npaText = '<a href="' . htmlspecialchars($npaInfo['npa_url']) . '" target="_blank" class="npa-revision-link" style="color:#0066cc;text-decoration:underline;">' . htmlspecialchars($npaText) . '</a>';
    }
    return trim($elementPath . ' ' . $npaText);
}

function getRevisionSourceNote($modifiedById, $pdo, $asHtml = false) {
    if (empty($modifiedById) || $modifiedById === 'base') {
        return 'исходная редакция';
    }
    
    $path = getElementHumanPath($modifiedById, $pdo);
    $npaInfo = getNpaInfoByItemId($modifiedById, $pdo);
    if (!$npaInfo) {
        if (!preg_match('/\d+/', $modifiedById, $matches)) {
            return $path;
        }
        $itemId = (int)$matches[0];
        $npaInfo = getNpaInfoByItemId($itemId, $pdo);
        if (!$npaInfo) return $path;
    }
    
    $typeName = ($npaInfo['npa_type'] === 'law') ? 'Закона' : 'Постановления Законодательного Собрания';
    $dateForDisplay = formatRusDate($npaInfo['date_passed'], $npaInfo['date_format']);
    $text = $path . ' ' . $typeName . ' города Севастополя № ' . $npaInfo['npa_number'] . ' от ' . $dateForDisplay;
    if ($asHtml && !empty($npaInfo['npa_url'])) {
        $npaPart = $typeName . ' города Севастополя № ' . $npaInfo['npa_number'] . ' от ' . $dateForDisplay;
        $text = $path . ' <a href="' . htmlspecialchars($npaInfo['npa_url']) . '" target="_blank" class="npa-revision-link" style="color:#0066cc;text-decoration:underline;">' . htmlspecialchars($npaPart) . '</a>';
    }
    return $text;
}

function getIntroducingLawForDate(PDO $pdo, $baseNpaId, $validFromDate) {
    if (empty($baseNpaId) || empty($validFromDate)) return null;
    $stmt = $pdo->prepare("
        SELECT *
        FROM npa_revision_info
        WHERE base_npa_id = ?
          AND revision_date_valid <= ?
        ORDER BY revision_date_valid DESC, revision_number ASC
        LIMIT 1
    ");
    $stmt->execute([$baseNpaId, $validFromDate]);
    return $stmt->fetch();
}

function getElementRevisionButtons($itemData, $pdo, $npa_id, $viewDate, $pageUrl, $isExpired = false, array $selectedRevisionNpaIds = []) {
    $external_item_id = $itemData['item_id'] ?? '';
    if (empty($external_item_id)) {
        return '';
    }

    $internal_id = (int)($itemData['internal_id'] ?? 0);
    $currentRevId = (int)($itemData['rev_id'] ?? 0);
    if (!$internal_id || !$currentRevId) {
        return '';
    }

    $prev = getPreviousItemRevision($pdo, $internal_id, $currentRevId);
    $prevRevId = $prev ? (int)$prev['rev_id'] : null;

    $selectedContext = htmlspecialchars(json_encode(array_values($selectedRevisionNpaIds), JSON_UNESCAPED_UNICODE), ENT_QUOTES, 'UTF-8');
    $currentRevAttr = htmlspecialchars((string)$currentRevId, ENT_QUOTES, 'UTF-8');

    $stmtOrig = $pdo->prepare("SELECT rev_id FROM npa_item_revision WHERE item_internal_id = ? ORDER BY valid_from ASC, rev_id ASC LIMIT 1");
    $stmtOrig->execute([$internal_id]);
    $origRevId = (int)$stmtOrig->fetchColumn();
    if ($origRevId && $currentRevId === $origRevId && !$isExpired) {
        return '';
    }

    $style = 'display:flex; flex-wrap:wrap; gap:8px; margin:8px 0 12px 0; align-items:center;';
    $buttons = '<div class="npa-item-buttons" style="' . $style . '"'
             . ' data-npa-item-id="' . htmlspecialchars($external_item_id, ENT_QUOTES, 'UTF-8') . '"'
             . ' data-npa-id="' . (int)$npa_id . '"'
             . ' data-current-rev-id="' . $currentRevAttr . '"'
             . ' data-view-date="' . htmlspecialchars($viewDate, ENT_QUOTES, 'UTF-8') . '"'
             . ' data-selected-revision-npa-ids="' . $selectedContext . '">';

    if ($prevRevId) {
        $buttons .= '<button type="button" class="npa-item-btn npa-btn-prev-revision"'
                  . ' data-item-id="' . htmlspecialchars($external_item_id, ENT_QUOTES, 'UTF-8') . '"'
                  . ' data-npa-id="' . (int)$npa_id . '"'
                  . ' data-rev-id="' . $prevRevId . '"'
                  . ' data-current-rev-id="' . $currentRevAttr . '">' .
            '<svg class="npa-btn-icon" viewBox="0 0 16 16" width="12" height="12" style="margin-right:4px"><path d="M10 13L5 8l5-5" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>' .
            'Предыдущая редакция</button>';
    }

    $buttons .= '<button type="button" class="npa-item-btn npa-btn-history"'
              . ' data-item-id="' . htmlspecialchars($external_item_id, ENT_QUOTES, 'UTF-8') . '"'
              . ' data-npa-id="' . (int)$npa_id . '"'
              . ' data-current-rev-id="' . $currentRevAttr . '">'
              . '<svg class="npa-btn-icon" viewBox="0 0 16 16" width="12" height="12" style="margin-right:4px"><path d="M8 3v5l3 2M2 8a6 6 0 1012 0A6 6 0 002 8z" stroke="currentColor" stroke-width="1.4" fill="none"/></svg>'
              . 'История изменений</button>';

    if (!$isExpired) {
        $buttons .= '<button type="button" class="npa-item-btn npa-btn-compare"'
                  . ' data-item-id="' . htmlspecialchars($external_item_id, ENT_QUOTES, 'UTF-8') . '"'
                  . ' data-npa-id="' . (int)$npa_id . '"'
                  . ' data-current-rev-id="' . $currentRevAttr . '">'
                  . '<svg class="npa-btn-icon" viewBox="0 0 16 16" width="16" height="16" fill="none" xmlns="http://www.w3.org/2000/svg">'
                  . '<rect x="2" y="3" width="5" height="10" rx="1" stroke="currentColor" stroke-width="1.2"/>'
                  . '<rect x="9" y="3" width="5" height="10" rx="1" stroke="currentColor" stroke-width="1.2"/>'
                  . '<path d="M4 6h1M11 6h1M4 8h1M11 8h1M4 10h1M11 10h1" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>'
                  . '</svg>Сравнение редакций</button>';
    }

    $buttons .= '</div>';
    return $buttons;
}

function getHeadRevisionButtons($headRevisions, $npa_id, $pdo) {
    if (count($headRevisions) <= 1) return '';
    $currentRev = end($headRevisions);
    $prevRev = null;
    for ($i = count($headRevisions) - 2; $i >= 0; $i--) {
        if ($headRevisions[$i]['valid_from'] < $currentRev['valid_from']) {
            $prevRev = $headRevisions[$i];
            break;
        }
    }
    $buttons = '<div class="npa-item-buttons" data-npa-item-id="head" data-npa-id="' . $npa_id . '">';
    if ($prevRev) {
        $buttons .= '<button class="npa-item-btn npa-btn-prev-revision" data-item-id="head" data-context="head" data-npa-id="' . $npa_id . '" data-rev-id="' . $prevRev['id'] . '">
           <svg class="npa-btn-icon" viewBox="0 0 16 16" width="12" height="12" style="margin-right:4px"><path d="M10 13L5 8l5-5" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>
            Предыдущая редакция
        </button>';
    }
    $buttons .= '<button class="npa-item-btn npa-btn-head-history" data-item-id="head" data-context="head" data-npa-id="' . $npa_id . '">
             <svg class="npa-btn-icon" viewBox="0 0 16 16" width="12" height="12" style="margin-right:4px"><path d="M8 3v5l3 2M2 8a6 6 0 1012 0A6 6 0 002 8z" stroke="currentColor" stroke-width="1.4" fill="none"/></svg>
        История изменений
    </button>';
    $buttons .= '<button class="npa-item-btn npa-btn-head-compare" data-item-id="head" data-context="head" data-npa-id="' . $npa_id . '">
            <svg class="npa-btn-icon" viewBox="0 0 16 16" width="16" height="16" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect x="2" y="3" width="5" height="10" rx="1" stroke="currentColor" stroke-width="1.2"/>
            <rect x="9" y="3" width="5" height="10" rx="1" stroke="currentColor" stroke-width="1.2"/>
            <path d="M4 6h1M11 6h1M4 8h1M11 8h1M4 10h1M11 10h1" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
        </svg>
        Сравнение редакций
    </button>';
    $buttons .= '</div>';
    return $buttons;
}

function getItemHeadRevisionButtons($itemInternalId, $externalItemId, $npa_id, $pdo, $asOfDate, array $selectedRevisionNpaIds = []) {
    $currentRev = getItemHeadRevisionForSelectedEdition($pdo, $itemInternalId, $asOfDate, $selectedRevisionNpaIds);
    if (!$currentRev || empty($currentRev['id'])) {
        return '';
    }
    $currentRevId = (int)$currentRev['id'];

    $prevRev = getPreviousItemHeadRevision($pdo, $itemInternalId, $currentRevId);

    $stmtCount = $pdo->prepare("SELECT COUNT(*) FROM npa_item_head_revision WHERE item_internal_id = ? AND id <> ?");
    $stmtCount->execute([$itemInternalId, $currentRevId]);
    $hasHistory = ((int)$stmtCount->fetchColumn() > 0);

    if (!$prevRev && !$hasHistory) {
        return '';
    }

    $selectedContext = htmlspecialchars(json_encode(array_values($selectedRevisionNpaIds), JSON_UNESCAPED_UNICODE), ENT_QUOTES, 'UTF-8');
    $currentRevAttr = htmlspecialchars((string)$currentRevId, ENT_QUOTES, 'UTF-8');
    $externalAttr = htmlspecialchars($externalItemId, ENT_QUOTES, 'UTF-8');
    $style = 'display:flex; flex-wrap:wrap; gap:8px; margin:8px 0 12px 0; align-items:center;';

    $buttons = '<div class="npa-item-buttons" style="' . $style . '"'
             . ' data-npa-item-id="' . $externalAttr . '"'
             . ' data-npa-id="' . (int)$npa_id . '"'
             . ' data-context="head"'
             . ' data-current-rev-id="' . $currentRevAttr . '"'
             . ' data-view-date="' . htmlspecialchars($asOfDate, ENT_QUOTES, 'UTF-8') . '"'
             . ' data-selected-revision-npa-ids="' . $selectedContext . '">';

    if ($prevRev) {
        $buttons .= '<button type="button" class="npa-item-btn npa-btn-prev-revision"'
                  . ' data-item-id="' . $externalAttr . '" data-context="head" data-npa-id="' . (int)$npa_id . '"'
                  . ' data-rev-id="' . (int)$prevRev['id'] . '" data-current-rev-id="' . $currentRevAttr . '">'
                  . '<svg class="npa-btn-icon" viewBox="0 0 16 16" width="12" height="12" style="margin-right:4px"><path d="M10 13L5 8l5-5" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>'
                  . 'Предыдущая редакция</button>';
    }
    $buttons .= '<button type="button" class="npa-item-btn npa-btn-head-history" data-item-id="' . $externalAttr . '" data-context="head" data-npa-id="' . (int)$npa_id . '" data-current-rev-id="' . $currentRevAttr . '">'
              . '<svg class="npa-btn-icon" viewBox="0 0 16 16" width="12" height="12" style="margin-right:4px"><path d="M8 3v5l3 2M2 8a6 6 0 1012 0A6 6 0 002 8z" stroke="currentColor" stroke-width="1.4" fill="none"/></svg>'
              . 'История изменений</button>';
    $buttons .= '<button type="button" class="npa-item-btn npa-btn-head-compare" data-item-id="' . $externalAttr . '" data-context="head" data-npa-id="' . (int)$npa_id . '" data-current-rev-id="' . $currentRevAttr . '">'
              . '<svg class="npa-btn-icon" viewBox="0 0 16 16" width="16" height="16" fill="none" xmlns="http://www.w3.org/2000/svg">'
              . '<rect x="2" y="3" width="5" height="10" rx="1" stroke="currentColor" stroke-width="1.2"/><rect x="9" y="3" width="5" height="10" rx="1" stroke="currentColor" stroke-width="1.2"/>'
              . '<path d="M4 6h1M11 6h1M4 8h1M11 8h1M4 10h1M11 10h1" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>'
              . 'Сравнение редакций</button>';
    $buttons .= '</div>';
    return $buttons;
}

function buildRevisionEffectiveDateBlock($validFromDate, $isDeferred, $label = 'Изменения вступают в силу с') {
    if (empty($validFromDate)) {
        return '';
    }

    $safeDate = htmlspecialchars($validFromDate, ENT_QUOTES, 'UTF-8');

    if ($isDeferred) {
        return '<div class="element-valid-from element-valid-from-deferred" '
             . 'style="font-size:0.85em; color:#7a5a00; background:#fff8e1; '
             . 'border-left:3px solid #d6a84f; padding:4px 8px; margin:0.35em 0 0.6em 0; '
             . 'border-radius:2px;">'
             . $label . ' ' . $safeDate
             . '</div>';
    }

    return '<div class="element-valid-from" '
         . 'style="font-size:0.85em; color:#666; margin:0.2em 0 0.5em 0;">'
         . 'Последние изменения вступили в силу с ' . $safeDate
         . '</div>';
}

function getItemHeadRevisionNotes($internal_item_id, $pdo, $viewDate, $itemType, array $selectedRevisionNpaIds = [], $baseNpaId = null) {
    $currentRev = getItemHeadRevisionForSelectedEdition($pdo, $internal_item_id, $viewDate, $selectedRevisionNpaIds);
    if (!$currentRev || empty($currentRev['id'])) return '';

    $currentRevId = (int)$currentRev['id'];

    $sql = "SELECT r.* FROM npa_item_head_revision r
            WHERE r.item_internal_id = ?
              AND (r.valid_from IS NULL OR r.valid_from <= ?";
    $params = [$internal_item_id, $currentRev['valid_from']];

    if (!empty($selectedRevisionNpaIds)) {
        $placeholders = buildRevisionNpaIdPlaceholders($selectedRevisionNpaIds);
        $sql .= " OR EXISTS (
            SELECT 1 FROM npa_item changer
            WHERE changer.npa_id IN ($placeholders)
              AND INSTR(BINARY CONCAT(',', REPLACE(COALESCE(r.modified_by_id, ''), ' ', ''), ','), BINARY CONCAT(',', CAST(changer.id AS CHAR), ',')) > 0
        )";
        $params = array_merge($params, array_values($selectedRevisionNpaIds));
    }
    $sql .= ") ORDER BY r.valid_from ASC, r.id ASC";
    
    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    $allRevisions = $stmt->fetchAll();

    $allowedRevisions = [];
    foreach ($allRevisions as $rev) {
        if ((int)$rev['id'] <= $currentRevId) $allowedRevisions[] = $rev;
    }
    if (empty($allowedRevisions)) return '';

    $lastNewRedactionIdx = -1;
    foreach ($allowedRevisions as $idx => $rev) {
        if ($rev['mod_type'] === 'new_redaction') $lastNewRedactionIdx = $idx;
    }
    $revisionsToProcess = ($lastNewRedactionIdx !== -1)
        ? array_slice($allowedRevisions, $lastNewRedactionIdx)
        : $allowedRevisions;

    $addNote = $newRedactionNote = null;
    $changeNotes = [];

    foreach ($revisionsToProcess as $rev) {
        $shortDesc = getShortNpaDescription($rev['modified_by_id'], $pdo, true);
        if ($shortDesc === 'исходная редакция') continue;

        switch ($rev['mod_type']) {
            case 'add': if ($addNote === null) $addNote = $shortDesc; break;
            case 'new_redaction': $newRedactionNote = $shortDesc; break;
            case 'change': if (!in_array($shortDesc, $changeNotes, true)) $changeNotes[] = $shortDesc; break;
        }
    }

    $parts = [];
    if ($addNote) $parts[] = '<span class="revision-note">Заголовок введен — ' . $addNote . '</span>';
    if ($newRedactionNote) $parts[] = '<span class="revision-note">Заголовок в редакции — ' . $newRedactionNote . '</span>';
    if (!empty($changeNotes)) $parts[] = '<span class="revision-note">Заголовок изменен: ' . implode(', ', $changeNotes) . '</span>';

    if (empty($parts) && !empty($baseNpaId) && !empty($selectedRevisionNpaIds)) {
        $allNull = true;
        foreach ($allowedRevisions as $rev) {
            if (!empty($rev['mod_type']) || !empty($rev['modified_by_id'])) $allNull = false;
        }
        if ($allNull && !empty($currentRev['valid_from'])) {
            $law = getIntroducingLawForDate($pdo, $baseNpaId, $currentRev['valid_from']);
            if ($law) {
                $lawShort = getShortNpaDescription($law['revision_id'], $pdo, true);
                if ($lawShort !== 'исходная редакция') $addNote = $lawShort;
            }
        }
        if ($addNote) $parts[] = '<span class="revision-note">Заголовок введен — ' . $addNote . '</span>';
    }

    if (empty($parts)) return '';

    $dt = parseDate($currentRev['valid_from'] ?? null);
    $validFromDate = $dt ? $dt->format('d.m.Y') : '';
    $isDeferred = isDeferredSelectedEditionRevision($currentRev, $viewDate, $selectedRevisionNpaIds);
    $dateBlock = buildRevisionEffectiveDateBlock($validFromDate, $isDeferred);

    return '<div class="element-revision-notes" style="margin: 0.5em 0;">'
         . $dateBlock . implode('<br>', $parts) . '</div>';
}

function getElementRevisionNotes($internal_item_id, $pdo, $baseNpaId, $npaType, $viewDate, $itemType, array $selectedRevisionNpaIds = []) {
    $currentRev = getRevisionForSelectedEdition($pdo, $internal_item_id, $viewDate, $selectedRevisionNpaIds);
    if (!$currentRev || empty($currentRev['rev_id'])) return '';

    $currentRevId = (int)$currentRev['rev_id'];

    $sql = "SELECT r.* FROM npa_item_revision r
            WHERE r.item_internal_id = ?
              AND (r.valid_from IS NULL OR r.valid_from <= ?";
    $params = [$internal_item_id, $currentRev['valid_from']];

    if (!empty($selectedRevisionNpaIds)) {
        $placeholders = buildRevisionNpaIdPlaceholders($selectedRevisionNpaIds);
        $sql .= " OR EXISTS (
            SELECT 1 FROM npa_item changer
            WHERE changer.npa_id IN ($placeholders)
              AND INSTR(BINARY CONCAT(',', REPLACE(COALESCE(r.modified_by_id, ''), ' ', ''), ','), BINARY CONCAT(',', CAST(changer.id AS CHAR), ',')) > 0
        )";
        $params = array_merge($params, array_values($selectedRevisionNpaIds));
    }
    $sql .= ") ORDER BY r.valid_from ASC, r.rev_id ASC";
    
    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    $allRevisions = $stmt->fetchAll();

    $allowedRevisions = [];
    foreach ($allRevisions as $rev) {
        if ((int)$rev['rev_id'] <= $currentRevId) $allowedRevisions[] = $rev;
    }
    if (empty($allowedRevisions)) return '';

    $lastNewRedactionIdx = -1;
    foreach ($allowedRevisions as $idx => $rev) {
        if ($rev['mod_type'] === 'new_redaction') $lastNewRedactionIdx = $idx;
    }
    $revisionsToProcess = ($lastNewRedactionIdx !== -1)
        ? array_slice($allowedRevisions, $lastNewRedactionIdx)
        : $allowedRevisions;

    $addNote = null;
    $newRedactionNote = null;
    $changeNotes = [];

    foreach ($revisionsToProcess as $rev) {
        $shortDesc = getShortNpaDescription($rev['modified_by_id'], $pdo, true);
        if ($shortDesc === 'исходная редакция') continue;

        switch ($rev['mod_type']) {
            case 'add': if ($addNote === null) $addNote = $shortDesc; break;
            case 'new_redaction': $newRedactionNote = $shortDesc; break;
            case 'change': if (!in_array($shortDesc, $changeNotes, true)) $changeNotes[] = $shortDesc; break;
        }
    }

    $genderSuffix = '';
    if ($itemType === 'article' || $itemType === 'part') $genderSuffix = 'а';
    elseif ($itemType === 'appendix') $genderSuffix = 'о';

    $parts = [];
    if ($addNote) $parts[] = '<span class="revision-note">Введен' . $genderSuffix . ' — ' . $addNote . '</span>';
    if ($newRedactionNote) $parts[] = '<span class="revision-note">В редакции — ' . $newRedactionNote . '</span>';
    if (!empty($changeNotes)) $parts[] = '<span class="revision-note">С изменениями: ' . implode(', ', $changeNotes) . '</span>';

    if (empty($parts) && !empty($baseNpaId) && !empty($selectedRevisionNpaIds)) {
        $allNull = true;
        foreach ($allowedRevisions as $rev) {
            if (!empty($rev['mod_type']) || !empty($rev['modified_by_id'])) $allNull = false;
        }
        if ($allNull && !empty($currentRev['valid_from'])) {
            $law = getIntroducingLawForDate($pdo, $baseNpaId, $currentRev['valid_from']);
            if ($law) {
                $lawShort = getShortNpaDescription($law['revision_id'], $pdo, true);
                if ($lawShort !== 'исходная редакция') $addNote = $lawShort;
            }
        }
        if ($addNote) $parts[] = '<span class="revision-note">Введен' . $genderSuffix . ' — ' . $addNote . '</span>';
    }

    if (empty($parts)) return '';

    $dt = parseDate($currentRev['valid_from'] ?? null);
    $validFromDate = $dt ? $dt->format('d.m.Y') : '';
    $isDeferred = isDeferredSelectedEditionRevision($currentRev, $viewDate, $selectedRevisionNpaIds);
    $dateBlock = buildRevisionEffectiveDateBlock($validFromDate, $isDeferred);

    return '<div class="element-revision-notes" style="margin: 0.5em 0;">'
         . $dateBlock . implode('<br>', $parts) . '</div>';
}

/**
 * Фильтрует примечания (npa_note_unified) по правилу отображения
 * (docs/db_schema.md §6.1.4, §6.2, docs/site_output.md §8.4):
 *
 *   Примечание выводится только если его valid_to не задан (бессрочно)
 *   ИЛИ valid_to >= даты вступления в силу выбранной редакции ($editionDate).
 *   Примечание, у которого valid_to меньше даты вступления в силу выбранной
 *   редакции, считается истёкшим и не выводится.
 *
 * $editionDate — дата вступления в силу выбранной редакции (view_date);
 * поддерживаются форматы 'Y-m-d' и 'd.m.Y' (через parseDate()).
 *
 * @param array $notes       Список примечаний (строки npa_note_unified).
 * @param mixed $editionDate Дата вступления в силу выбранной редакции.
 * @return array Отфильтрованный список примечаний.
 */
function filterNotesByValidTo(array $notes, $editionDate) {
    $edition = parseDate($editionDate);
    if (!$edition) {
        // Дата просмотра неизвестна — не принимаем решений, показываем как есть.
        return array_values($notes);
    }
    $editionStr = $edition->format('Y-m-d');
    $filtered = [];
    foreach ($notes as $note) {
        $validTo = parseDate($note['valid_to'] ?? null);
        // Бессрочные примечания (valid_to NULL/'') показываются всегда;
        // истёкшие (valid_to < даты вступления в силу редакции) — скрываются.
        if ($validTo === null || $validTo->format('Y-m-d') >= $editionStr) {
            $filtered[] = $note;
        }
    }
    return $filtered;
}

function getRevisionSelectorOptions(PDO $pdo, $npa_id, $displayDate) {
    $options = [];
    $stmt = $pdo->prepare("SELECT valid_from, not_valid FROM npa_base WHERE npa_id = ?");
    $stmt->execute([$npa_id]);
    $base = $stmt->fetch();

    $baseValidFrom = $base['valid_from'] ?? null;
    $notValidDate = $base['not_valid'] ?? null;
    $isDocExpired = !empty($notValidDate);

    $stmt = $pdo->prepare("
        SELECT revision_date_valid
        FROM npa_revision_info
        WHERE base_npa_id = ?
        ORDER BY revision_date_valid ASC, revision_number ASC
    ");
    $stmt->execute([$npa_id]);

    $dates = [];
    foreach ($stmt->fetchAll() as $row) {
        if (!empty($row['revision_date_valid'])) $dates[$row['revision_date_valid']] = true;
    }
    $dates = array_keys($dates);
    sort($dates);

    $selectedDate = $baseValidFrom;
    foreach ($dates as $dateRaw) {
        if ($isDocExpired && $notValidDate && $dateRaw >= $notValidDate) continue;
        if ($dateRaw <= $displayDate) $selectedDate = $dateRaw;
    }

    $currentDate = $baseValidFrom;
    foreach ($dates as $dateRaw) {
        if ($isDocExpired && $notValidDate && $dateRaw >= $notValidDate) continue;
        $currentDate = $dateRaw;
    }

    if ($baseValidFrom) {
        $baseDateFormatted = formatDateToRus($baseValidFrom);
        $options[] = [
            'date_raw' => $baseValidFrom,
            'date_display' => $baseDateFormatted,
            'label' => 'Первоначальная редакция (вступление в силу ' . $baseDateFormatted . ')',
            'is_original' => true,
            'is_current' => ($baseValidFrom === $currentDate),
            'is_selected' => ($baseValidFrom === $selectedDate)
        ];
    }

    foreach ($dates as $dateRaw) {
        if ($isDocExpired && $notValidDate && $dateRaw >= $notValidDate) continue;

        $stmtRev = $pdo->prepare("
            SELECT revision_number, revision_date_reg
            FROM npa_revision_info
            WHERE base_npa_id = ? AND revision_date_valid = ?
            ORDER BY revision_number ASC
        ");
        $stmtRev->execute([$npa_id, $dateRaw]);

        $items = [];
        foreach ($stmtRev->fetchAll() as $rev) {
            $items[] = '№' . $rev['revision_number'] . ' от ' . formatDateToRus($rev['revision_date_reg']);
        }

        $options[] = [
            'date_raw' => $dateRaw,
            'date_display' => formatDateToRus($dateRaw),
            'label' => 'Редакция — ' . implode('; ', $items),
            'is_original' => false,
            'is_current' => ($dateRaw === $currentDate),
            'is_selected' => ($dateRaw === $selectedDate)
        ];
    }

    return [
        'options' => $options,
        'selected_date' => $selectedDate,
        'current_date' => $currentDate,
        'active_date' => $selectedDate
    ];
}

function renderSignature(PDO $pdo, $npa_id, $dateSigned, $npaNumber, $dateFormat, $includeRequisites = true) {
    $stmt = $pdo->prepare("SELECT s.*, p.fio, pp.name as position_name
                           FROM npa_signatory s
                           JOIN person p ON s.person_id = p.id
                           JOIN person_post pp ON s.person_post_id = pp.id
                           WHERE s.npa_id = ? LIMIT 1");
    $stmt->execute([$npa_id]);
    $signer = $stmt->fetch();
    if (!$signer) return '';
    $signerPost = $signer['position_name'];
    $signerName = $signer['fio'];
    $phrases = ['Законодательного Собрания', 'города Севастополя'];
    foreach ($phrases as $phrase) {
        if (mb_stripos($signerPost, $phrase) !== false) {
            if (!preg_match('/<br\s*\/?>\s*' . preg_quote($phrase, '/') . '/ui', $signerPost)) {
                $signerPost = preg_replace('/(\s*)(' . preg_quote($phrase, '/') . ')/ui', '<br>$1$2', $signerPost, 1);
            }
        }
    }
    $signerPost = htmlspecialchars($signerPost);
    $signerPost = str_replace(['&lt;br&gt;', '&lt;br /&gt;', '&lt;br/&gt;'], '<br>', $signerPost);
    $signerName = htmlspecialchars($signerName);
    $html = '<p class="justifyleft npa-signer">' . $signerPost;
    if ($signerName) $html .= str_repeat('&nbsp;', 5) . $signerName;
    $html .= '</p>';
    if ($includeRequisites) {
        $place = 'Севастополь';
        $formattedDate = formatRusDate($dateSigned, $dateFormat);
        $html .= '<p class="justifyleft npa-requisites">' . $place . '<br>' . $formattedDate . '<br>№&nbsp;' . htmlspecialchars($npaNumber) . '</p>';
    }
    return $html;
}

function getParagraphsForRevision(PDO $pdo, $rev_id) {
    $sql = "SELECT * FROM npa_paragraph WHERE rev_id = ? ORDER BY sort_order";
    $stmt = $pdo->prepare($sql);
    $stmt->execute([$rev_id]);
    return $stmt->fetchAll();
}

function getItemHeadRevisionContent(PDO $pdo, $rev_id, $internal_item_id, $asOfDate) {
    $stmt = $pdo->prepare("SELECT * FROM npa_item_head_revision WHERE id = ? AND item_internal_id = ? LIMIT 1");
    $stmt->execute([$rev_id, $internal_item_id]);
    $rev = $stmt->fetch();
    if (!$rev) return null;
    $stmtItem = $pdo->prepare("SELECT * FROM npa_item WHERE id = ?");
    $stmtItem->execute([$internal_item_id]);
    $item = $stmtItem->fetch();
    $itemType = $item ? $item['item_type'] : '';
    $itemNumber = $item ? ($item['item_number'] ?? '') : '';
    $headText = $rev['head_text'];
    global $NPA_NO_NAME_IDS;
    $skipName = in_array($item['item_id'], $NPA_NO_NAME_IDS);
    $display = '';
    if ($itemType === 'chapter') {
        $display = ($skipName ? '' : 'Глава ') . $itemNumber . ($headText ? '. ' . $headText : '');
    } elseif ($itemType === 'section') {
        $display = ($skipName ? '' : 'Раздел ') . $itemNumber . ($headText ? '. ' . $headText : '');
    } elseif ($itemType === 'article') {
        $display = ($skipName ? '' : 'Статья ') . $itemNumber . ($headText ? '. ' . $headText : '');
    } elseif ($itemType === 'appendix' || $itemType === 'nested_appendix') {
        $display = ($skipName ? '' : 'Приложение ') . $itemNumber . ($headText ? '. ' . $headText : '');
    } elseif ($itemType === 'structured_table') {
        if (!empty($headText)) {
            $display = 'Таблица ' . $itemNumber . ($headText ? '. ' . $headText : '');
        } else {
            $display = '';
        }
    } else {
        $display = $headText;
    }
    $html = '';
    if (!empty($display)) {
        $html = '<div class="npa-item-head-block"><p class="npa-doc-title"><b>' . htmlspecialchars($display) . '</b></p></div>';
    }
    $sourceInfo = '';
    if ($rev['modified_by_id'] && $rev['modified_by_id'] !== 'base') {
        $sourceInfo = getShortNpaDescription($rev['modified_by_id'], $pdo, true, 'nominative');
        if ($sourceInfo && $sourceInfo !== 'исходная редакция') {
            $sourceInfo = 'Внесено: ' . $sourceInfo;
        } elseif ($sourceInfo === 'исходная редакция') {
            $sourceInfo = 'Исходная редакция';
        }
    } else {
        $sourceInfo = 'Исходная редакция';
    }
    $npaInfo = null;
    if ($rev['modified_by_id'] && $rev['modified_by_id'] !== 'base') {
        $npaInfo = getNpaInfoByItemId((int)$rev['modified_by_id'], $pdo);
    }
    return [
        'html' => $html,
        'modified_by_id' => $rev['modified_by_id'],
        'valid_from' => $rev['valid_from'],
        'valid_to' => $rev['valid_to'],
        'source_info' => $sourceInfo,
        'npa_url' => $npaInfo['npa_url'] ?? '',
        'display_title' => $npaInfo ? ($npaInfo['npa_type'] === 'law' ? 'Закона' : 'Постановления Законодательного Собрания') . ' города Севастополя № ' . $npaInfo['npa_number'] . ' от ' . formatRusDate($npaInfo['date_passed'], $npaInfo['date_format']) : ''
    ];
}

function getItemRevisionContent(PDO $pdo, $rev_id, $internal_item_id, $depth = 0, $npa_id = null, $includeHeading = true, $forComparison = false, $asOfDateOverride = null, $paragraphOnly = false, $useEditionContext = true) {
    global $NPA_NO_NAME_IDS, $structured_tree_cache;
    
    if ($depth > 20) return null;
    
    if ($paragraphOnly) {
        $stmtItem = $pdo->prepare("SELECT * FROM npa_item WHERE id = ?");
        $stmtItem->execute([$internal_item_id]);
        $item = $stmtItem->fetch();
        if (!$item) return null;
        
        if ($npa_id === null) {
            $npa_id = $item['npa_id'];
        }
        
        if ($rev_id === null) {
            if ($asOfDateOverride) {
                $stmtRev = $pdo->prepare("
                    SELECT rev_id, mod_type, modified_by_id, valid_from, valid_to
                    FROM npa_item_revision
                    WHERE item_internal_id = ?
                      AND (valid_from <= ? OR valid_from IS NULL)
                      AND (valid_to IS NULL OR valid_to >= ?)
                    ORDER BY valid_from DESC
                    LIMIT 1
                ");
                $stmtRev->execute([$internal_item_id, $asOfDateOverride, $asOfDateOverride]);
            } else {
                $stmtRev = $pdo->prepare("
                    SELECT rev_id, mod_type, modified_by_id, valid_from, valid_to
                    FROM npa_item_revision
                    WHERE item_internal_id = ?
                    ORDER BY valid_from DESC
                    LIMIT 1
                ");
                $stmtRev->execute([$internal_item_id]);
            }
            $rev = $stmtRev->fetch();
            if (!$rev) {
                $lastContentRev = getLastContentRevision($pdo, $internal_item_id, $asOfDateOverride);
                if ($lastContentRev) {
                    $rev_id = $lastContentRev['rev_id'];
                    $stmtRev = $pdo->prepare("SELECT rev_id, mod_type, modified_by_id, valid_from, valid_to FROM npa_item_revision WHERE rev_id = ?");
                    $stmtRev->execute([$rev_id]);
                    $rev = $stmtRev->fetch();
                }
            }
            if (!$rev) return null;
            $rev_id = $rev['rev_id'];
        } else {
            $stmtRev = $pdo->prepare("SELECT * FROM npa_item_revision WHERE rev_id = ? AND item_internal_id = ?");
            $stmtRev->execute([$rev_id, $internal_item_id]);
            $rev = $stmtRev->fetch();
            if (!$rev) return null;
        }
        
        $stmtPara = $pdo->prepare("SELECT * FROM npa_paragraph WHERE rev_id = ? ORDER BY sort_order");
        $stmtPara->execute([$rev_id]);
        $paragraphs = $stmtPara->fetchAll();
        
        if (empty($paragraphs)) {
            $contentRev = getLastContentRevision($pdo, $internal_item_id, $asOfDateOverride ?: $rev['valid_from']);
            if ($contentRev && $contentRev['rev_id'] != $rev_id) {
                $stmtParaContent = $pdo->prepare("SELECT * FROM npa_paragraph WHERE rev_id = ? ORDER BY sort_order");
                $stmtParaContent->execute([$contentRev['rev_id']]);
                $paragraphs = $stmtParaContent->fetchAll();
            }
        }
        
        $html = '';
        $itemType = $item['item_type'];
        $itemNumber = $item['item_number'] ?? '';
        $displayNumber = $itemNumber;
        
        foreach ($paragraphs as $p) {
            $blockType = $p['block_type'];
            if ($blockType === 'paragraph') {
                if (!empty($p['paragraph_note'])) {
                    $html .= '<p align="center">' . htmlspecialchars($p['paragraph_note']) . '</p>';
                }
                $paragraphHtml = $p['html_text'];
                $paragraphHtml = str_replace(['<b><i> &nbsp;</i></b>', '<i><b> &nbsp;</b></i>'], '', $paragraphHtml);
                $html .= $paragraphHtml;
            } elseif ($blockType === 'table' || $blockType === 'table_fragment') {
                $html .= $p['html_text'];
            }
        }
        
        return ['html' => $html];
    }
    
    if ($forComparison) {
        if ($npa_id === null) {
            $stmtItem = $pdo->prepare("SELECT npa_id FROM npa_item WHERE id = ?");
            $stmtItem->execute([$internal_item_id]);
            $item = $stmtItem->fetch();
            if (!$item) return null;
            $npa_id = $item['npa_id'];
        }
        if ($rev_id === null) {
            $stmtRev = $pdo->prepare("SELECT valid_from FROM npa_item_revision WHERE item_internal_id = ? ORDER BY valid_from DESC LIMIT 1");
            $stmtRev->execute([$internal_item_id]);
            $revData = $stmtRev->fetch();
        } else {
            $stmtRev = $pdo->prepare("SELECT valid_from FROM npa_item_revision WHERE rev_id = ? AND item_internal_id = ?");
            $stmtRev->execute([$rev_id, $internal_item_id]);
            $revData = $stmtRev->fetch();
        }
        if (!$revData) return null;
        $valid_from = $asOfDateOverride ?: $revData['valid_from'];
        // При сравнении редакций важно учитывать контекст выбранной редакции документа
        // так же, как это делает основной вывод страницы.
        // ВАЖНО: для предыдущей колонки сравнения ($useEditionContext === false) контекст
        // выбранной редакции применять нельзя — иначе ревизия, внесённая выбранным
        // изменяющим НПА, будет принудительно показана и на дату ДО её вступления в силу,
        // и обе колонки сравнения окажутся текущей редакцией.
        if ($useEditionContext && isset($GLOBALS['selected_revision_npa_ids'])) {
            $selRevIds = $GLOBALS['selected_revision_npa_ids'];
        } else {
            $selRevIds = [];
        }
        $itemsById = getItemTree($pdo, $npa_id, $valid_from, null, true, $selRevIds);
        if (!isset($itemsById[$internal_item_id])) return null;
        $itemData = $itemsById[$internal_item_id];
        $npaData = [
            'npa_id' => $npa_id,
            'pageUrl' => '',
            'no_name_ids' => $NPA_NO_NAME_IDS,
            'npa_type' => 'law',
            'selected_revision_npa_ids' => $selRevIds
        ];
        $renderedItems = [];
        // Рендерим всё поддерево элемента (родитель + рекурсивно все дочерние элементы):
        // при сравнении редакций родительского элемента должны отображаться предыдущая
        // и текущая редакции не только его тела, но и всех вложенных элементов.
        $html = renderSubtree($itemData, $itemsById, $pdo, $valid_from, $npaData, $renderedItems, true, $NPA_NO_NAME_IDS, true);
        return ['html' => $html];
    }
    
    $stmtItem = $pdo->prepare("SELECT * FROM npa_item WHERE id = ?");
    $stmtItem->execute([$internal_item_id]);
    $item = $stmtItem->fetch();
    if (!$item) return null;
    
    if ($npa_id === null) {
        $npa_id = $item['npa_id'];
    }
    
    $asOfDate = $asOfDateOverride;
    if ($asOfDate === null) {
        if ($rev_id === null) {
            $stmtRev = $pdo->prepare("
                SELECT rev_id, mod_type, modified_by_id, valid_from, valid_to
                FROM npa_item_revision
                WHERE item_internal_id = ?
                ORDER BY valid_from DESC
                LIMIT 1
            ");
            $stmtRev->execute([$internal_item_id]);
            $rev = $stmtRev->fetch();
            if (!$rev) return null;
            $rev_id = $rev['rev_id'];
            $asOfDate = $rev['valid_from'];
        } else {
            $stmtRev = $pdo->prepare("SELECT valid_from FROM npa_item_revision WHERE rev_id = ? AND item_internal_id = ?");
            $stmtRev->execute([$rev_id, $internal_item_id]);
            $revData = $stmtRev->fetch();
            if (!$revData) return null;
            $asOfDate = $revData['valid_from'];
        }
    }
    
    $itemsById = getItemTree($pdo, $npa_id, $asOfDate, null, false);
    if (!isset($itemsById[$internal_item_id])) {
        return null;
    }
    
    $itemData = $itemsById[$internal_item_id];
    $npaData = [
        'npa_id' => $npa_id,
        'pageUrl' => '',
        'no_name_ids' => $NPA_NO_NAME_IDS,
        'npa_type' => 'law'
    ];
    $renderedItems = [];
    $html = renderElement($itemData, $itemsById, $pdo, $asOfDate, $npaData, $renderedItems, true, $NPA_NO_NAME_IDS, false);
    
    $sourceInfo = '';
    if ($itemData['modified_by_id'] && $itemData['modified_by_id'] !== 'base') {
        $sourceInfo = getShortNpaDescription($itemData['modified_by_id'], $pdo, true, 'nominative');
        if ($sourceInfo && $sourceInfo !== 'исходная редакция') {
            $sourceInfo = 'Внесено: ' . $sourceInfo;
        } elseif ($sourceInfo === 'исходная редакция') {
            $sourceInfo = 'Исходная редакция';
        }
    } else {
        $sourceInfo = 'Исходная редакция';
    }
    
    $npaInfo = null;
    if ($itemData['modified_by_id'] && $itemData['modified_by_id'] !== 'base') {
        $npaInfo = getNpaInfoByItemId((int)$itemData['modified_by_id'], $pdo);
    }
    
    return [
        'html' => $html,
        'mod_type' => $itemData['mod_type'],
        'modified_by_id' => $itemData['modified_by_id'],
        'valid_from' => $itemData['valid_from'],
        'valid_to' => $itemData['valid_to'],
        'source_info' => $sourceInfo,
        'npa_url' => $npaInfo['npa_url'] ?? '',
        'display_title' => $npaInfo ? ($npaInfo['npa_type'] === 'law' ? 'Закона' : 'Постановления') . ' города Севастополя № ' . $npaInfo['npa_number'] . ' от ' . formatRusDate($npaInfo['date_passed'], $npaInfo['date_format']) : ''
    ];
}

function renderStructuredTable($item, $paragraphs, $pdo, $asOfDate, $itemsById, $skipInteractive = false) {
    $html = '<div class="npa-structured-table">';
    $borderValue = getTableBorderFromContent($paragraphs);
    $borderAttr = ($borderValue !== null && $borderValue === '0') ? ' border="0"' : ' border="1"';
    $tableHtml = '<table class="npa-structured-table-content"' . $borderAttr . ' cellpadding="4" cellspacing="0" style="border-collapse: collapse; width: 100%;">';
    $hasHeader = false;
    $caption = '';
    foreach ($paragraphs as $para) {
        if ($para['block_type'] === 'table_header') {
            $tableHtml .= '<thead>' . $para['html_text'] . '</thead>';
            $hasHeader = true;
        } elseif ($para['block_type'] === 'paragraph') {
            $caption .= $para['html_text'];
        } elseif ($para['block_type'] === 'child_ref') {
            $refId = $para['ref_item_internal_id'];
            if ($refId && isset($itemsById[$refId])) {
                $tableHtml .= renderTableRowWithButtons($refId, $pdo, $asOfDate, $itemsById, $skipInteractive);
            }
        }
    }
    if (!$hasHeader) {
        $tableHtml = '<table class="npa-structured-table-content"' . $borderAttr . ' cellpadding="4" cellspacing="0" style="border-collapse: collapse; width: 100%;">';
    }
    $tableHtml .= '</table>';
    if ($caption) {
        $html .= '<div class="structured-table-caption">' . $caption . '</div>';
    }
    $html .= $tableHtml;
    $html .= '</div>';
    return $html;
}

function getTableBorderFromContent($paragraphs) {
    foreach ($paragraphs as $para) {
        if ($para['block_type'] === 'table' || $para['block_type'] === 'table_fragment' || $para['block_type'] === 'table_header') {
            if (preg_match('/<table[^>]*\bborder\s*=\s*["\']?([0-9]+)["\']?/i', $para['html_text'], $matches)) {
                return $matches[1];
            }
        }
    }
    return null;
}

function renderTableFragment($itemInternalId, $pdo, $asOfDate, $itemsById, $skipInteractive = false) {
    $stmtItem = $pdo->prepare("SELECT id, item_id FROM npa_item WHERE id = ?");
    $stmtItem->execute([$itemInternalId]);
    $item = $stmtItem->fetch();
    if (!$item) return '';
    $stmtRev = $pdo->prepare("
        SELECT rev_id FROM npa_item_revision
        WHERE item_internal_id = ? AND (valid_from <= ? OR valid_from IS NULL) AND (valid_to IS NULL OR valid_to >= ?)
        ORDER BY valid_from DESC LIMIT 1
    ");
    $stmtRev->execute([$itemInternalId, $asOfDate, $asOfDate]);
    $rev = $stmtRev->fetch();
    if (!$rev) return '';
    $stmtPara = $pdo->prepare("SELECT * FROM npa_paragraph WHERE rev_id = ? ORDER BY sort_order");
    $stmtPara->execute([$rev['rev_id']]);
    $paragraphs = $stmtPara->fetchAll();
    $rowsHtml = '';
    foreach ($paragraphs as $para) {
        if ($para['block_type'] === 'table_fragment') {
            $htmlText = $para['html_text'];
            if (!empty($item['item_id']) && preg_match('/<tr/i', $htmlText)) {
                $htmlText = preg_replace('/(<tr)(\s|>)/i', '$1 id="' . htmlspecialchars($item['item_id']) . '"$2', $htmlText, 1);
            }
            $rowsHtml .= $htmlText;
        } elseif ($para['block_type'] === 'child_ref') {
            $refId = $para['ref_item_internal_id'];
            if ($refId) {
                $rowsHtml .= renderTableFragment($refId, $pdo, $asOfDate, $itemsById, $skipInteractive);
            }
        }
    }
    return $rowsHtml;
}

function renderTableRowWithButtons($itemInternalId, $pdo, $asOfDate, $itemsById, $skipInteractive = false) {
    $item = $itemsById[$itemInternalId] ?? null;
    if (!$item) {
        return renderTableFragment($itemInternalId, $pdo, $asOfDate, $itemsById, $skipInteractive);
    }
    $activeRev = getRevisionForDate($pdo, $itemInternalId, $asOfDate);
    if (!$activeRev) return '';
    $stmt = $pdo->prepare("SELECT * FROM npa_paragraph WHERE rev_id = ? AND block_type = 'table_fragment' ORDER BY sort_order");
    $stmt->execute([$activeRev['rev_id']]);
    $fragments = $stmt->fetchAll();
    if (empty($fragments)) return '';
    $buttonsHtml = '';
    if (!$skipInteractive) {
        $buttonsHtml = getElementRevisionButtons($item, $pdo, $item['npa_id'], $asOfDate, '', false, []);
        if ($buttonsHtml) {
            $buttonsHtml = '<div class="npa-table-buttons-wrapper" style="display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px;">' . $buttonsHtml . '</div>';
        }
    }
    $result = '';
    foreach ($fragments as $frag) {
        $rowHtml = $frag['html_text'];
        if (!$skipInteractive && preg_match('/<(td|th)([^>]*)>/i', $rowHtml, $matches, PREG_OFFSET_CAPTURE)) {
            $tagLen = strlen($matches[0][0]);
            $pos = $matches[0][1];
            $insertHtml = $buttonsHtml;
            $rowHtml = substr_replace($rowHtml, $insertHtml, $pos + $tagLen, 0);
        }
        if (!empty($item['item_id']) && preg_match('/<tr/i', $rowHtml)) {
            $rowHtml = preg_replace('/(<tr)(\s|>)/i', '$1 id="' . htmlspecialchars($item['item_id']) . '"$2', $rowHtml, 1);
        }
        $result .= $rowHtml;
    }
    return $result;
}

function renderElementAsTableFragment($itemData, $itemsById, $pdo, $viewDate, $skipInteractive = false) {
    $internal_id = $itemData['internal_id'];
    $html = '';
    foreach ($itemData['paragraphs'] as $para) {
        if ($para['block_type'] === 'table_fragment') {
            $html .= $para['html_text'];
        } elseif ($para['block_type'] === 'child_ref') {
            $refId = $para['ref_item_internal_id'];
            if ($refId && isset($itemsById[$refId])) {
                $html .= renderElementAsTableFragment($itemsById[$refId], $itemsById, $pdo, $viewDate, $skipInteractive);
            }
        }
    }
    return $html;
}

function getItemCompareForSelectedEdition(PDO $pdo, $internal_item_id, $asOfDate, array $selectedRevisionNpaIds = []) {
    $current = getRevisionForSelectedEdition($pdo, $internal_item_id, $asOfDate, $selectedRevisionNpaIds);
    if (!$current) return null;
    $prev = getPreviousItemRevision($pdo, $internal_item_id, $current['rev_id']);
    if (!$prev) {
        return [
            'prev_valid_from' => '',
            'current_valid_from' => formatDateToRus($current['valid_from']),
            'prev_html_raw' => '',
            'current_html_raw' => '',
            'element_human_path' => getElementHumanPath($internal_item_id, $pdo, 'genitive'),
            'changing_elements' => [],
            'highlights' => normalizeHighlights($current['highlights'] ?? null),
            'mod_type' => $current['mod_type'] ?? ''
        ];
    }
    $prevAsOfDate = $current['valid_from'];
    $dtPrev = parseDate($prevAsOfDate);
    if ($dtPrev) {
        $dtPrev->modify('-1 day');
        $prevAsOfDate = $dtPrev->format('Y-m-d');
    } else {
        $prevAsOfDate = $asOfDate;
    }
    $prevContent = getItemRevisionContent($pdo, $prev['rev_id'], $internal_item_id, 0, null, false, true, $prevAsOfDate, false, false);
    // Текущую колонку сравнения рендерим на актуальную дату просмотра ($asOfDate),
    // чтобы изменения, внесённые в дочерние элементы после последней редакции
    // родителя, тоже попадали в сравнение (у родителя отдельная редакция не создаётся).
    $currContent = getItemRevisionContent($pdo, $current['rev_id'], $internal_item_id, 0, null, false, true, $asOfDate);
    $prevHtml = $prevContent ? ensureTableWrapperForComparison($prevContent['html'], $internal_item_id, $pdo, $prevAsOfDate) : '';
    $currHtml = $currContent ? ensureTableWrapperForComparison($currContent['html'], $internal_item_id, $pdo, $asOfDate) : '';
    $changingElements = [];
    $changerIds = [];
    if (!empty($current['modified_by_id']) && $current['modified_by_id'] !== 'base') {
        foreach (array_filter(array_map('trim', explode(',', $current['modified_by_id']))) as $changerStr) {
            if ($changerStr === 'base') continue;
            $changerIds[] = $changerStr;
            $npaInfo = getNpaInfoByItemId($changerStr, $pdo);
            if (!$npaInfo) continue;
            $changerDate = $npaInfo['date_signed'] ?? $npaInfo['date_passed'] ?? $current['valid_from'];
            $changerNpaId = $npaInfo['npa_id'];
            $changerNpaType = $npaInfo['npa_type'];
            $changerHtml = getElementHtmlById($changerStr, $asOfDate, $pdo, $changerNpaId, $changerNpaType);
            $changingElements[] = [
                'note' => getRevisionSourceNote($changerStr, $pdo, true),
                'html' => $changerHtml,
                'date' => formatDateToRus($changerDate)
            ];
        }
    }
        // Дочерние элементы, утратившие силу той же НПА, тоже показываем в «Изменения внесены:».
    $changingElements = array_merge($changingElements, collectExpiredChildChanges($pdo, $internal_item_id, $asOfDate, $changerIds, $selectedRevisionNpaIds));
    $highlightsForClient = null;
    if (!empty($current['highlights'])) {
        $decoded = json_decode($current['highlights'], true);
        if (is_array($decoded)) $highlightsForClient = $decoded;
    }
    return [
        'prev_valid_from' => formatDateToRus($prev['valid_from']),
        'current_valid_from' => formatDateToRus($current['valid_from']),
        'prev_html_raw' => $prevHtml,
        'current_html_raw' => $currHtml,
        'element_human_path' => getElementHumanPath($internal_item_id, $pdo, 'genitive'),
        'changing_elements' => $changingElements,
        'highlights' => normalizeHighlights($highlightsForClient),
        'mod_type' => $current['mod_type']
    ];
}

function getItemHeadCompareForSelectedEdition(PDO $pdo, $internal_item_id, $asOfDate, array $selectedRevisionNpaIds = []) {
    $current = getItemHeadRevisionForSelectedEdition($pdo, $internal_item_id, $asOfDate, $selectedRevisionNpaIds);
    if (!$current) return null;
    $prev = getPreviousItemHeadRevision($pdo, $internal_item_id, $current['id']);
    if (!$prev) {
        return [
            'prev_valid_from' => '',
            'current_valid_from' => formatDateToRus($current['valid_from']),
            'prev_html_raw' => '',
            'current_html_raw' => '',
            'changing_elements' => [],
            'highlights' => normalizeHighlights($current['highlights'] ?? null),
            'mod_type' => $current['mod_type'] ?? ''
        ];
    }
    $prevContent = getItemHeadRevisionContent($pdo, $prev['id'], $internal_item_id, $asOfDate);
        $currContent = getItemHeadRevisionContent($pdo, $current['id'], $internal_item_id, $asOfDate);
    $changingElements = [];
    $changerIds = [];
    if (!empty($current['modified_by_id']) && $current['modified_by_id'] !== 'base') {
        foreach (array_filter(array_map('trim', explode(',', $current['modified_by_id']))) as $changerStr) {
            if ($changerStr === 'base') continue;
            $changerIds[] = $changerStr;
            $npaInfo = getNpaInfoByItemId($changerStr, $pdo);
            if (!$npaInfo) continue;
            $changerDate = $npaInfo['date_signed'] ?? $npaInfo['date_passed'] ?? $current['valid_from'];
            $changingElements[] = [
                'note' => getRevisionSourceNote($changerStr, $pdo, true),
                                'html' => getElementHtmlById($changerStr, $asOfDate, $pdo, $npaInfo['npa_id'], $npaInfo['npa_type']),
                'date' => formatDateToRus($changerDate)
            ];
        }
    }
    // Дочерние элементы, утратившие силу той же НПА, тоже показываем в «Изменения внесены:».
    $changingElements = array_merge($changingElements, collectExpiredChildChanges($pdo, $internal_item_id, $asOfDate, $changerIds, $selectedRevisionNpaIds));
    $highlightsForClient = null;
    if (!empty($current['highlights'])) {
        $decoded = json_decode($current['highlights'], true);
        if (is_array($decoded)) $highlightsForClient = $decoded;
    }
    return [
        'prev_valid_from' => formatDateToRus($prev['valid_from']),
        'current_valid_from' => formatDateToRus($current['valid_from']),
        'prev_html_raw' => $prevContent ? $prevContent['html'] : '',
        'current_html_raw' => $currContent ? $currContent['html'] : '',
        'changing_elements' => $changingElements,
        'highlights' => normalizeHighlights($highlightsForClient),
        'mod_type' => $current['mod_type']
        ];
}

/**
 * Возвращает список дочерних элементов, утративших силу той же редакцией
 * НПА, что и указанные changer-элементы ($changerIds).
 *
 * В БД поле npa_item_revision.not_valid хранит item_id элемента, вызвавшего
 * утрату силы. Если дочерний элемент погиб тем же документом, что и родитель
 * (или один из changer-элементов), его тоже выводим в «Изменения внесены:».
 *
 * Дубли не добавляются (settype к key).
 *
 * @param PDO    $pdo
 * @param mixed  $internal_item_id  Внутренний id родительского элемента (npa_item.id)
 * @param string $asOfDate          Дата просмотра
 * @param array  $changerIds        Список item_id элементов-инициаторов текущей редакции
 * @param array  $selectedRevisionNpaIds
 * @return array Массив записей ['note'=>string, 'html'=>string, 'date'=>string]
 */
function collectExpiredChildChanges(PDO $pdo, $internal_item_id, $asOfDate, array $changerIds, array $selectedRevisionNpaIds = []) {
    if (empty($changerIds)) {
        return [];
    }
    $result = [];
    $seen = [];

    // item_id родительского элемента для сопоставления с not_valid детей.
    $stmt = $pdo->prepare('SELECT item_id FROM npa_item WHERE id = ? LIMIT 1');
    $stmt->execute([$internal_item_id]);
    $parentRow = $stmt->fetch();
    $parentItemId = $parentRow ? $parentRow['item_id'] : null;

    // Все дочерние элементы родителя.
    $stmt = $pdo->prepare('SELECT id, item_id, item_type, item_number FROM npa_item WHERE parent_id = ? ORDER BY sort_order, id');
    $stmt->execute([$internal_item_id]);
    $children = $stmt->fetchAll();

    if (empty($children)) {
        return $result;
    }

    // Список item_id для поиска в not_valid (rtrim на случай "id1,id2").
    $changerItemIdSet = [];
    foreach ($changerIds as $cid) {
        $cids = array_filter(array_map('trim', explode(',', $cid)));
        foreach ($cids as $c) {
            if ($c !== 'base') {
                $changerItemIdSet[$c] = true;
            }
        }
    }
    // Утратившие силу из-за самого родителя тоже считаем.
    if ($parentItemId && $parentItemId !== 'base') {
        $changerItemIdSet[$parentItemId] = true;
    }

    foreach ($children as $child) {
        $childInternalId = $child['id'];
        // Активная ревизия ребёнка — чтобы получить HTML и npa_id.
        $rev = getRevisionForSelectedEdition($pdo, $childInternalId, $asOfDate, $selectedRevisionNpaIds);
        if (!$rev) {
            continue;
        }
        $childNotValid = $rev['not_valid'] ?? null;
        if (!$childNotValid) {
            continue;
        }

        // not_valid хранит item_id элемента, отменившего ребёнка.
        // Проверяем, относится ли он к нашим changer-элементам.
        $notValidIds = array_filter(array_map('trim', explode(',', $childNotValid)));
        $matchedChanger = false;
        foreach ($notValidIds as $nvid) {
            if (isset($changerItemIdSet[$nvid])) {
                $matchedChanger = $nvid;
                break;
            }
        }
        if (!$matchedChanger) {
            continue;
        }
        if (isset($seen[$childInternalId])) {
            continue;
        }
        $seen[$childInternalId] = true;

        $npaInfo = getNpaInfoByItemId($matchedChanger, $pdo);
        $childDate = $npaInfo
            ? ($npaInfo['date_signed'] ?? $npaInfo['date_passed'] ?? $rev['valid_from'])
            : $rev['valid_from'];

                $childHtml = getElementHtmlById(
            $childInternalId, $asOfDate, $pdo,
            $npaInfo['npa_id'] ?? 0, $npaInfo['npa_type'] ?? ''
        );

        $result[] = [
            'note' => getRevisionSourceNote($matchedChanger, $pdo, true),
            'html' => $childHtml,
            'date' => formatDateToRus($childDate)
        ];
    }

    return $result;
}

function getItemHeadCompareHtml(PDO $pdo, $internal_item_id, $asOfDate) {
    $stmt = $pdo->prepare("
        SELECT * FROM npa_item_head_revision
        WHERE item_internal_id = ? AND (valid_from <= ? OR valid_from IS NULL)
        ORDER BY valid_from ASC, id ASC
    ");
    $stmt->execute([$internal_item_id, $asOfDate]);
    $revisions = $stmt->fetchAll();
    if (count($revisions) < 2) {
        return [
            'prev_html_raw' => '',
            'current_html_raw' => '',
            'prev_valid_from' => '',
            'current_valid_from' => '',
            'changing_elements' => [],
            'highlights' => ['previous_edition' => ['deletion' => [], 'difference' => []], 'current_edition' => ['addition' => [], 'difference' => []]],
            'mod_type' => null
        ];
    }
    $prevRev = $revisions[count($revisions)-2];
    $currRev = $revisions[count($revisions)-1];
    $stmtItem = $pdo->prepare("SELECT * FROM npa_item WHERE id = ?");
    $stmtItem->execute([$internal_item_id]);
    $item = $stmtItem->fetch();
    $itemType = $item ? $item['item_type'] : '';
    $itemNumber = $item ? ($item['item_number'] ?? '') : '';
    $oldHead = $prevRev['head_text'];
    $newHead = $currRev['head_text'];
    global $NPA_NO_NAME_IDS;
    $skipName = in_array($item['item_id'], $NPA_NO_NAME_IDS);
    $oldDisplay = '';
    $newDisplay = '';
    if ($itemType === 'chapter') {
        $oldDisplay = ($skipName ? '' : 'Глава ') . $itemNumber . ($oldHead ? '. ' . $oldHead : '');
        $newDisplay = ($skipName ? '' : 'Глава ') . $itemNumber . ($newHead ? '. ' . $newHead : '');
    } elseif ($itemType === 'section') {
        $oldDisplay = ($skipName ? '' : 'Раздел ') . $itemNumber . ($oldHead ? '. ' . $oldHead : '');
        $newDisplay = ($skipName ? '' : 'Раздел ') . $itemNumber . ($newHead ? '. ' . $newHead : '');
    } elseif ($itemType === 'article') {
        $oldDisplay = ($skipName ? '' : 'Статья ') . $itemNumber . ($oldHead ? '. ' . $oldHead : '');
        $newDisplay = ($skipName ? '' : 'Статья ') . $itemNumber . ($newHead ? '. ' . $newHead : '');
    } elseif ($itemType === 'appendix' || $itemType === 'nested_appendix') {
        $oldDisplay = ($skipName ? '' : 'Приложение ') . $itemNumber . ($oldHead ? '. ' . $oldHead : '');
        $newDisplay = ($skipName ? '' : 'Приложение ') . $itemNumber . ($newHead ? '. ' . $newHead : '');
    } elseif ($itemType === 'structured_table') {
        if (!empty($oldHead)) {
            $oldDisplay = 'Таблица ' . $itemNumber . ($oldHead ? '. ' . $oldHead : '');
        } else {
            $oldDisplay = '';
        }
        if (!empty($newHead)) {
            $newDisplay = 'Таблица ' . $itemNumber . ($newHead ? '. ' . $newHead : '');
        } else {
            $newDisplay = '';
        }
    } else {
        $oldDisplay = $oldHead;
        $newDisplay = $newHead;
    }
    $oldTitle = '';
    $newTitle = '';
    if (!empty($oldDisplay)) {
        $oldTitle = '<p class="npa-doc-title"><b>' . htmlspecialchars($oldDisplay) . '</b></p>';
    }
    if (!empty($newDisplay)) {
        $newTitle = '<p class="npa-doc-title"><b>' . htmlspecialchars($newDisplay) . '</b></p>';
    }
    $oldTitle = ensureTableWrapperForComparison($oldTitle, $internal_item_id, $pdo, $asOfDate);
    $newTitle = ensureTableWrapperForComparison($newTitle, $internal_item_id, $pdo, $asOfDate);
    $highlights = null;
    if (!empty($currRev['highlights'])) {
        $highlights = json_decode($currRev['highlights'], true);
        if (!is_array($highlights)) $highlights = null;
    }
    $prevValidFrom = $prevRev['valid_from'] ? formatDateToRus($prevRev['valid_from']) : '';
    $currValidFrom = $currRev['valid_from'] ? formatDateToRus($currRev['valid_from']) : '';
    $changingElements = [];
    if (!empty($currRev['modified_by_id']) && $currRev['modified_by_id'] !== 'base') {
        $changerIds = array_filter(array_map('trim', explode(',', $currRev['modified_by_id'])));
        foreach ($changerIds as $changerStr) {
            if ($changerStr === 'base') continue;
            $npaInfo = getNpaInfoByItemId($changerStr, $pdo);
            if (!$npaInfo) continue;
            $changerDate = $npaInfo['date_signed'] ?? $npaInfo['date_passed'] ?? $currRev['valid_from'];
            $changerNpaId = $npaInfo['npa_id'];
            $changerNpaType = $npaInfo['npa_type'];
            $changerHtml = getElementHtmlById($changerStr, $asOfDate, $pdo, $changerNpaId, $changerNpaType);
            $note = getRevisionSourceNote($changerStr, $pdo, true);
            $changingElements[] = [
                'note' => $note,
                'html' => $changerHtml,
                'date' => formatDateToRus($changerDate)
            ];
        }
    }
    return [
        'prev_html_raw' => $oldTitle,
        'current_html_raw' => $newTitle,
        'prev_valid_from' => $prevValidFrom,
        'current_valid_from' => $currValidFrom,
        'changing_elements' => $changingElements,
        'highlights' => normalizeHighlights($highlights),
        'mod_type' => $currRev['mod_type'] ?? null
    ];
}

function ensureTableWrapperForComparison($html, $itemId, $pdo, $asOfDate) {
    if (stripos($html, '<table') !== false) {
        return $html;
    }
    if (is_numeric($itemId)) {
        $stmt = $pdo->prepare("SELECT item_type, npa_id FROM npa_item WHERE id = ?");
        $stmt->execute([$itemId]);
        $item = $stmt->fetch();
    } else {
        $stmt = $pdo->prepare("SELECT npa_type FROM npa_base WHERE npa_id = ?");
        $stmt->execute([$itemId]);
        $item = $stmt->fetch();
        if ($item) {
            $item['item_type'] = 'base';
        }
    }
    if (!$item) return $html;
    if (isset($item['item_type']) && $item['item_type'] === 'structured_table') {
        $stmtRev = $pdo->prepare("
            SELECT rev_id FROM npa_item_revision
            WHERE item_internal_id = ? AND (valid_from <= ? OR valid_from IS NULL) AND (valid_to IS NULL OR valid_to >= ?)
            LIMIT 1
        ");
        $stmtRev->execute([$itemId, $asOfDate, $asOfDate]);
        $rev = $stmtRev->fetch();
        if ($rev) {
            $stmtPara = $pdo->prepare("SELECT * FROM npa_paragraph WHERE rev_id = ? ORDER BY sort_order");
            $stmtPara->execute([$rev['rev_id']]);
            $paragraphs = $stmtPara->fetchAll();
            $itemsTree = getItemTree($pdo, $item['npa_id'], $asOfDate, [], false);
            $fullTableHtml = renderStructuredTable($item, $paragraphs, $pdo, $asOfDate, $itemsTree, true);
            if ($fullTableHtml) return $fullTableHtml;
        }
    }
    if (stripos($html, '<tr') !== false && stripos($html, '<table') === false) {
        return '<table class="npa-comparison-table" cellpadding="5" cellspacing="0" style="width:100%; border-collapse:collapse;">' .
               '<tbody>' . $html . '</tbody>' .
               '</table>';
    }
    return $html;
}

function getHeadCompareHtml(PDO $pdo, $npa_id, $asOfDate) {
    $stmt = $pdo->prepare("
        SELECT * FROM npa_head_revision
        WHERE npa_id = ?
        ORDER BY valid_from ASC
    ");
    $stmt->execute([$npa_id]);
    $revisions = $stmt->fetchAll();
    if (count($revisions) < 2) {
        return [
            'prev_html_raw' => '',
            'current_html_raw' => '',
            'prev_valid_from' => '',
            'current_valid_from' => '',
            'changing_elements' => [],
            'highlights' => ['previous_edition' => ['deletion' => [], 'difference' => []], 'current_edition' => ['addition' => [], 'difference' => []]],
            'mod_type' => null
        ];
    }
    $prevRev = $revisions[count($revisions)-2];
    $currRev = $revisions[count($revisions)-1];
    $oldTitle = '<p class="npa-doc-title">' . htmlspecialchars($prevRev['npa_title']) . '</p>';
    $newTitle = '<p class="npa-doc-title">' . htmlspecialchars($currRev['npa_title']) . '</p>';
    $oldTitle = ensureTableWrapperForComparison($oldTitle, $npa_id, $pdo, $asOfDate);
    $newTitle = ensureTableWrapperForComparison($newTitle, $npa_id, $pdo, $asOfDate);
    $highlights = null;
    if (!empty($currRev['highlights'])) {
        $highlights = json_decode($currRev['highlights'], true);
        if (!is_array($highlights)) $highlights = null;
    }
    $prevValidFrom = $prevRev['valid_from'] ? formatDateToRus($prevRev['valid_from']) : '';
    $currValidFrom = $currRev['valid_from'] ? formatDateToRus($currRev['valid_from']) : '';
    $changingElements = [];
    if (!empty($currRev['modified_by_id']) && $currRev['modified_by_id'] !== 'base') {
        $changerIds = array_filter(array_map('trim', explode(',', $currRev['modified_by_id'])));
        foreach ($changerIds as $changerStr) {
            if ($changerStr === 'base') continue;
            $npaInfo = getNpaInfoByItemId($changerStr, $pdo);
            if (!$npaInfo) continue;
            $changerDate = $npaInfo['date_signed'] ?? $npaInfo['date_passed'] ?? $currRev['valid_from'];
            $changerNpaId = $npaInfo['npa_id'];
            $changerNpaType = $npaInfo['npa_type'];
            $changerHtml = getElementHtmlById($changerStr, $asOfDate, $pdo, $changerNpaId, $changerNpaType);
            $note = getRevisionSourceNote($changerStr, $pdo, true);
            $changingElements[] = [
                'note' => $note,
                'html' => $changerHtml,
                'date' => formatDateToRus($changerDate)
            ];
        }
    }
    return [
        'prev_html_raw' => $oldTitle,
        'current_html_raw' => $newTitle,
        'prev_valid_from' => $prevValidFrom,
        'current_valid_from' => $currValidFrom,
        'changing_elements' => $changingElements,
        'highlights' => normalizeHighlights($highlights),
        'mod_type' => $currRev['mod_type'] ?? null
    ];
}

function renderTocTree($itemsById, $parentId, $level, $pageUrl, $viewDate, $noNameIds = []) {
    $children = array_filter($itemsById, function($item) use ($parentId) {
        return (string)$item['parent_id'] === (string)$parentId;
    });
    if (empty($children)) return '';
    usort($children, function($a, $b) {
        $sortA = isset($a['sort_order']) ? (float)$a['sort_order'] : 0;
        $sortB = isset($b['sort_order']) ? (float)$b['sort_order'] : 0;
        if ($sortA == $sortB) {
            $idA = isset($a['id']) ? (float)$a['id'] : 0;
            $idB = isset($b['id']) ? (float)$b['id'] : 0;
            return $idA - $idB;
        }
        return $sortA - $sortB;
    });
    $res = '<ul class="toc-list level-' . $level . '">';
    foreach ($children as $item) {
        $isExpired = isset($item['is_expired']) && $item['is_expired'];
        $hideSectionPrefix = !empty($item['hide_section_prefix']);
        $display = getDisplayText($item, $isExpired, $noNameIds, $hideSectionPrefix);
        if (empty($display) || empty($item['item_id'])) continue;

        $res .= '<li class="toc-item level-' . $level . '">';
        $res .= '<a href="' . htmlspecialchars($pageUrl . '#' . $item['item_id']) . '" '
              . 'class="toc-link level-' . $level . '" data-toc-id="' . htmlspecialchars($item['item_id']) . '">'
              . htmlspecialchars($display) . '</a>';
        if (!$isExpired) {
            $res .= renderTocTree($itemsById, $item['id'], $level + 1, $pageUrl, $viewDate, $noNameIds);
        }
        $res .= '</li>';
    }
    $res .= '</ul>';
    return $res;
}

function getItemTree(PDO $pdo, $npa_id, $asOfDate, $npaData = null, $includeExpired = true, array $selectedRevisionNpaIds = []) {
    global $itemsByIdGlobal;
    if ($npaData === null) {
        $npaData = ['no_name_ids' => []];
    }
    $stmt = $pdo->prepare("SELECT * FROM npa_item WHERE npa_id = ? ORDER BY sort_order, id");
    $stmt->execute([$npa_id]);
    $items = $stmt->fetchAll();
    $itemsById = [];
    foreach ($items as $item) {
        $internal_id = $item['id'];
        $revision = getRevisionForSelectedEdition($pdo, $internal_id, $asOfDate, $selectedRevisionNpaIds);
        if (!$revision) {
            continue;
        }
        $isExpired = $revision['is_expired'];
        if (!$includeExpired && $isExpired) {
            continue;
        }
        $rev = $revision;
        $expiredValidTo = null;
        if ($isExpired) {
            $expiredValidTo = $rev['valid_to'];
        }
        $headRev = getItemHeadRevisionForSelectedEdition($pdo, $internal_id, $asOfDate, $selectedRevisionNpaIds);
        $itemHeadText = $headRev ? $headRev['head_text'] : '';
        $stmtPara = $pdo->prepare("SELECT * FROM npa_paragraph WHERE rev_id = ? ORDER BY sort_order");
        $stmtPara->execute([$rev['rev_id']]);
        $paragraphs = $stmtPara->fetchAll();
        if (empty($paragraphs) && !$isExpired) {
            $contentRev = getLastContentRevision($pdo, $internal_id, $rev['valid_from']);
            if ($contentRev && $contentRev['rev_id'] != $rev['rev_id']) {
                $stmtParaContent = $pdo->prepare("SELECT * FROM npa_paragraph WHERE rev_id = ? ORDER BY sort_order");
                $stmtParaContent->execute([$contentRev['rev_id']]);
                $paragraphs = $stmtParaContent->fetchAll();
            }
        }
        $displayNumber = getItemNumberForSelectedEdition($pdo, $internal_id, $asOfDate, $selectedRevisionNpaIds);
        if ($displayNumber === null) {
            $displayNumber = $item['item_number'];
        }
        $itemData = $item;
        $itemData['internal_id']       = $internal_id;
        $itemData['rev_id']            = $rev['rev_id'];
        $itemData['mod_type']          = $rev['mod_type'];
        $itemData['modified_by_id']    = $rev['modified_by_id'];
        $itemData['valid_from']        = $rev['valid_from'];
        $itemData['valid_to']          = $rev['valid_to'];
        $itemData['not_valid']         = $rev['not_valid'];
        $itemData['item_head']         = $itemHeadText;
        $itemData['head_revision']     = $headRev;
        $itemData['paragraphs']        = $paragraphs;
        $itemData['is_expired']        = $isExpired;
        $itemData['expired_valid_to']  = $expiredValidTo;
        $itemData['display_number']    = $displayNumber;
        if ($isExpired) {
            $contentRevId = $rev['rev_id'];
            $stmtCheck = $pdo->prepare("SELECT COUNT(*) FROM npa_paragraph WHERE rev_id = ?");
            $stmtCheck->execute([$contentRevId]);
            $hasContent = $stmtCheck->fetchColumn() > 0;
            if (!$hasContent) {
                $contentRev = getLastContentRevision($pdo, $internal_id, $rev['valid_from']);
                if ($contentRev) {
                    $contentRevId = $contentRev['rev_id'];
                    $stmtContentRev = $pdo->prepare("SELECT * FROM npa_item_revision WHERE rev_id = ?");
                    $stmtContentRev->execute([$contentRevId]);
                    $fullContentRev = $stmtContentRev->fetch();
                    if ($fullContentRev) {
                        $rev = $fullContentRev;
                        $itemData['rev_id'] = $rev['rev_id'];
                        $itemData['mod_type'] = $rev['mod_type'];
                        $itemData['modified_by_id'] = $rev['modified_by_id'];
                        $itemData['valid_from'] = $rev['valid_from'];
                        $itemData['valid_to'] = $rev['valid_to'];
                        $itemData['not_valid'] = $rev['not_valid'];
                        $stmtParaContent = $pdo->prepare("SELECT * FROM npa_paragraph WHERE rev_id = ? ORDER BY sort_order");
                        $stmtParaContent->execute([$contentRevId]);
                        $itemData['paragraphs'] = $stmtParaContent->fetchAll();
                    }
                }
            }
            // Полный рендер последней действующей редакции (номер, заголовок, дочерние элементы),
            // как в истории / «Предыдущая редакция». Вариант «только параграфы» — запасной.
            $expiredContent = getItemRevisionContent($pdo, $itemData['rev_id'], $internal_id, 0, null, true, false, null, false);
            if (!$expiredContent || empty($expiredContent['html'])) {
                $expiredContent = getItemRevisionContent($pdo, $itemData['rev_id'], $internal_id, 0, null, false, false, null, true);
            }
            $itemData['expired_content_html'] = $expiredContent ? $expiredContent['html'] : '';
        } else {
            $itemData['expired_content_html'] = null;
        }
        $itemsById[$internal_id] = $itemData;
    }
    $itemsByIdGlobal = $itemsById;
    $noNameIds = $npaData['no_name_ids'] ?? [];
    $isInsideNoName = function($itemId, $itemsById, $noNameIds) use (&$isInsideNoName) {
        if (in_array($itemId, $noNameIds, true)) {
            return true;
        }
        $item = $itemsById[$itemId] ?? null;
        if ($item && $item['parent_id']) {
            $parentItem = $itemsById[$item['parent_id']] ?? null;
            if ($parentItem && $parentItem['item_id']) {
                return $isInsideNoName($parentItem['item_id'], $itemsById, $noNameIds);
            }
        }
        return false;
    };
    foreach ($itemsById as &$itemData) {
        if ($itemData['item_type'] === 'section') {
            $itemData['hide_section_prefix'] = $isInsideNoName($itemData['item_id'], $itemsById, $noNameIds);
        } else {
            $itemData['hide_section_prefix'] = false;
        }
    }
    return $itemsById;
}

function getInternalItemId(PDO $pdo, $npa_id, $external_item_id) {
    $external_item_id = trim($external_item_id);
    if ($external_item_id === '' || $external_item_id === 'head' || $external_item_id === 'null' || $external_item_id === null) {
        return 0;
    }
    $stmt = $pdo->prepare("SELECT id FROM npa_item WHERE npa_id = ? AND item_id = ?");
    $stmt->execute([$npa_id, $external_item_id]);
    $row = $stmt->fetch();
    return $row ? (int)$row['id'] : 0;
}

function getElementHtmlById($elementId, $asOfDate, $pdo, $npaId, $npaType, $forComparison = false) {
    global $NPA_NO_NAME_IDS;
    $activeRev = getRevisionForDate($pdo, $elementId, $asOfDate);
    if (!$activeRev) {
        return '<i>Элемент не найден на указанную дату</i>';
    }
    $revId = $activeRev['rev_id'];
    $isExpired = !empty($activeRev['is_expired']);
    $stmtItem = $pdo->prepare("SELECT * FROM npa_item WHERE id = ? OR item_id = ? LIMIT 1");
    $stmtItem->execute([$elementId, $elementId]);
    $item = $stmtItem->fetch();
    if (!$item) return '';
    $html = '<div class="npa-item-block' . ($isExpired ? ' npa-expired-block' : '') . '">';
    $itemType = $item['item_type'];
    $itemNumber = $item['item_number'] ?? '';
    $stmtHead = $pdo->prepare("
        SELECT head_text FROM npa_item_head_revision
        WHERE item_internal_id = ?
          AND (valid_from <= ? OR valid_from IS NULL)
          AND (valid_to IS NULL OR valid_to >= ?)
        ORDER BY valid_from DESC LIMIT 1
    ");
    $stmtHead->execute([$item['id'], $asOfDate, $asOfDate]);
    $headRow = $stmtHead->fetch();
    $itemHead = $headRow ? $headRow['head_text'] : '';
    $stmtNpaHead = $pdo->prepare("SELECT npa_title FROM npa_head_revision WHERE npa_id = ? AND (valid_from <= ? OR valid_from IS NULL) ORDER BY valid_from DESC LIMIT 1");
    $stmtNpaHead->execute([$npaId, $asOfDate]);
    $npaHeadRow = $stmtNpaHead->fetch();
    $regulationTitle = $npaHeadRow ? $npaHeadRow['npa_title'] : '';
    $prefixRev = null;
    $hasPrefix = false;
    if ($itemType === 'appendix' || $itemType === 'nested_appendix') {
        $prefixRev = getItemPrefixRevision($item['id'], $asOfDate, $pdo);
        $hasPrefix = !empty($prefixRev['prefix_text']);
    }
    $skipSectionPrefix = false;
    if ($itemType === 'section' && !empty($NPA_NO_NAME_IDS)) {
        $currentId = $item['id'];
        while ($currentId) {
            $stmtParent = $pdo->prepare("SELECT item_id, parent_id, item_type FROM npa_item WHERE id = ?");
            $stmtParent->execute([$currentId]);
            $cur = $stmtParent->fetch();
            if (!$cur) break;
            if (in_array($cur['item_id'], $NPA_NO_NAME_IDS)) {
                $skipSectionPrefix = true;
                break;
            }
            if ($cur['item_type'] === 'appendix' || $cur['item_type'] === 'nested_appendix') break;
            $currentId = $cur['parent_id'];
        }
    }
    if (!in_array($itemType, ['part', 'point', 'subpoint'])) {
        if ($itemType === 'appendix' || $itemType === 'nested_appendix') {
            if ($hasPrefix) {
                $prefixText = $prefixRev['prefix_text'];
                $prefixText = preg_replace('/(к постановлению|к закону)/i', '<br>$1', $prefixText);
                $prefixText = preg_replace('/(«[^»]+»)/u', '<br>$1', $prefixText);
                $html .= '<div class="npa-appendix-prefix" style="margin-left:66.666%; text-align:left; font-weight:bold; color:#1a3d6d; font-family:\'Arial\',sans-serif;">' . $prefixText . '</div>';
                if ($regulationTitle) {
                    $html .= '<p class="npa-regulation-title" style="text-align:center; font-weight:bold; margin:0.5em 0 1em 0;">' . htmlspecialchars($regulationTitle) . '</p>';
                }
            } else {
                $html .= '<p><b>' . htmlspecialchars('Приложение ' . $itemNumber . ($itemHead ? '. ' . $itemHead : '')) . '</b></p>';
            }
        } else {
            $display = '';
            switch ($itemType) {
                case 'chapter': $display = 'Глава ' . $itemNumber . ($itemHead ? '. ' . $itemHead : ''); break;
                case 'section':
                    if ($skipSectionPrefix) {
                        $display = $itemNumber . ($itemHead ? '. ' . $itemHead : '');
                    } else {
                        $display = 'Раздел ' . $itemNumber . ($itemHead ? '. ' . $itemHead : '');
                    }
                    break;
                case 'article': $display = 'Статья ' . $itemNumber . ($itemHead ? '. ' . $itemHead : ''); break;
            }
            if ($display) $html .= '<p><b>' . htmlspecialchars($display) . '</b></p>';
        }
    }
    $stmtPara = $pdo->prepare("SELECT * FROM npa_paragraph WHERE rev_id = ? ORDER BY sort_order");
    $stmtPara->execute([$revId]);
    $paragraphs = $stmtPara->fetchAll();
    if (empty($paragraphs)) {
        $contentRev = getLastContentRevision($pdo, $item['id'], $activeRev['valid_from']);
        if ($contentRev && $contentRev['rev_id'] != $revId) {
            $stmtParaContent = $pdo->prepare("SELECT * FROM npa_paragraph WHERE rev_id = ? ORDER BY sort_order");
            $stmtParaContent->execute([$contentRev['rev_id']]);
            $paragraphs = $stmtParaContent->fetchAll();
        }
    }
    if ($itemType === 'structured_table') {
        global $itemsByIdGlobal;
        if (!isset($itemsByIdGlobal)) $itemsByIdGlobal = [];
        $html .= renderStructuredTable($item, $paragraphs, $pdo, $asOfDate, $itemsByIdGlobal, true);
    } else {
        $isFirstParagraph = true;
        $paragraphBuffer = '';
        $hasTableFragment = false;
        foreach ($paragraphs as $p) {
            $blockType = $p['block_type'];
            if ($blockType === 'paragraph') {
                if (!empty($p['paragraph_note'])) {
                    $paragraphBuffer .= '<p align="center">' . htmlspecialchars($p['paragraph_note']) . '</p>';
                }
                $paragraphHtml = $p['html_text'];
                $paragraphHtml = str_replace(['<b><i> &nbsp;</i></b>', '<i><b> &nbsp;</b></i>'], '', $paragraphHtml);
                if ($isFirstParagraph && in_array($itemType, ['part', 'point', 'subpoint']) && !empty($itemNumber)) {
                    $lastCharItem = substr(trim($itemNumber), -1);
                    $suffixItem = ($lastCharItem !== ')' && $lastCharItem !== '.') ? '.' : '';
                    $paragraphHtml = preg_replace('/<p([^>]*)>/', '<p$1>' . htmlspecialchars($itemNumber . $suffixItem) . ' ', $paragraphHtml, 1);
                    $isFirstParagraph = false;
                }
                $paragraphBuffer .= $paragraphHtml;
            } elseif ($blockType === 'table' || $blockType === 'table_fragment') {
                $paragraphBuffer .= $p['html_text'];
                if ($blockType === 'table_fragment') $hasTableFragment = true;
            } elseif ($blockType === 'child_ref') {
                $refInternalId = $p['ref_item_internal_id'];
                if ($refInternalId) {
                    $childContent = getItemRevisionContent($pdo, null, $refInternalId, 0, $npaId, false, $forComparison, $asOfDate, true);
                    if ($childContent) {
                        $paragraphBuffer .= $childContent['html'];
                    }
                }
            }
        }
        if ($hasTableFragment && strpos($paragraphBuffer, '<table') === false && strpos($paragraphBuffer, '<tr') !== false) {
            $paragraphBuffer = '<table class="npa-comparison-table" cellpadding="5" cellspacing="0" style="width:100%; border-collapse:collapse;"><tbody>' . $paragraphBuffer . '</tbody></table>';
        }
        $html .= $paragraphBuffer;
    }
    $html .= '</div>';
    return $html;
}

function renderElement($itemData, $itemsById, $pdo, $viewDate, $npaData, &$renderedItems = [], $skipInteractive = false, $noNameIds = [], $forComparison = false) {
    $internal_id = $itemData['internal_id'];
    if (isset($renderedItems[$internal_id])) return '';
    $renderedItems[$internal_id] = true;
    $external_item_id = $itemData['item_id'];
    $itemType = $itemData['item_type'];
    $itemNumber = $itemData['item_number'] ?? '';
    $displayNumber = $itemData['display_number'] ?? $itemNumber;
    $isExpired = $itemData['is_expired'] ?? false;
    $expiredValidTo = $itemData['expired_valid_to'] ?? null;
    $showTableButtons = false;
    $parentId = $itemData['parent_id'] ?? null;
    if ($parentId && isset($itemsById[$parentId]) && $itemsById[$parentId]['item_type'] === 'structured_table') {
        $showTableButtons = true;
    }
    if ($isExpired && $forComparison) {
        $expiredHtml = $itemData['expired_content_html'] ?? '';
        if (empty($expiredHtml)) {
            $lastContentRev = getLastContentRevision($pdo, $internal_id, $itemData['valid_from']);
            if ($lastContentRev) {
                $content = getItemRevisionContent($pdo, $lastContentRev['rev_id'], $internal_id, 0, null, false, true);
                $expiredHtml = $content ? $content['html'] : '';
            }
        }
        $html = '<div class="npa-item-block npa-expired-block" data-item-type="' . htmlspecialchars($itemType) . '">';
        $html .= '<div class="npa-diff-delete">' . $expiredHtml . '</div>';
        $html .= '<div class="npa-expired-label" style="color:#999; font-style:italic;">(Утратил силу)</div>';
        $html .= '</div>';
        return $html;
    }
    $modalTitle = '';
    if ($isExpired && !$skipInteractive) {
        if ($itemType === 'article') $lastElementGenitive = 'статьи ' . $displayNumber;
        elseif ($itemType === 'part') $lastElementGenitive = 'части ' . $displayNumber;
        elseif ($itemType === 'point') $lastElementGenitive = 'пункта ' . $displayNumber;
        elseif ($itemType === 'subpoint') $lastElementGenitive = 'подпункта ' . $displayNumber;
        elseif ($itemType === 'chapter') $lastElementGenitive = 'главы ' . $displayNumber;
        elseif ($itemType === 'section') $lastElementGenitive = 'раздела ' . $displayNumber;
        elseif ($itemType === 'appendix' || $itemType === 'nested_appendix') $lastElementGenitive = 'приложения ' . $displayNumber;
        elseif ($itemType === 'preamble') $lastElementGenitive = 'преамбулы';
        else $lastElementGenitive = 'элемента';
        $modalTitle = 'Последняя редакция ' . $lastElementGenitive;
    }
    $html = '<div class="npa-item-block' . ($isExpired ? ' npa-expired-block' : '') . '"'
          . ' data-item-type="' . htmlspecialchars($itemType) . '"'
          . ($modalTitle ? ' data-modal-title="' . htmlspecialchars($modalTitle) . '"' : '')
          . ' data-npa-item-id="' . htmlspecialchars($external_item_id) . '">';
    $html .= '<a name="' . htmlspecialchars($external_item_id) . '" id="' . htmlspecialchars($external_item_id) . '" '
           . 'class="doc-toc-anchor" data-full-url="' . htmlspecialchars($npaData['pageUrl'] . '#' . $external_item_id) . '" '
           . 'style="display:block;position:relative;top:-20px;height:0;width:0;overflow:hidden;margin:0;padding:0;visibility:hidden;"></a>';
    if ($isExpired && !$skipInteractive) {
        $expiryDate = new DateTime($expiredValidTo);
        $expiryDate->modify('+1 day');
        $expiryDateFormatted = $expiryDate->format('d.m.Y');
        $notValidId = $itemData['not_valid'] ?? null;
        if ($notValidId && $notValidId !== 'base') {
            $sourceNote = getShortNpaDescription($notValidId, $pdo, true);
        } else {
            $sourceNote = 'последняя действующая редакция';
        }
        $genderSuffix = getExpiryGenderSuffix($itemType);
        $word = ($genderSuffix === '') ? 'Утратил' : 'Утратил' . $genderSuffix;
        $expiryNote = '<div class="element-revision-notes expired-note" style="margin: 0.5em 0;">';
        $expiryNote .= '<span class="revision-note">' . $word . ' силу с ' . $expiryDateFormatted . ' — ' . $sourceNote . '</span>';
        $expiryNote .= '</div>';
        $html .= $expiryNote;
        if ($itemType === 'chapter') {
            $html .= '<p><b>' . htmlspecialchars('Глава ' . $displayNumber . ($itemData['item_head'] ? '. ' . $itemData['item_head'] : '')) . '</b></p>';
        } elseif ($itemType === 'section') {
            $skipSectionPrefix = false;
            if (!empty($noNameIds)) {
                $currentId = $internal_id;
                while ($currentId) {
                    $cur = $itemsById[$current_id] ?? null;
                    if (!$cur) break;
                    if (in_array($cur['item_id'], $noNameIds)) {
                        $skipSectionPrefix = true;
                        break;
                    }
                    if ($cur['item_type'] === 'appendix' || $cur['item_type'] === 'nested_appendix') break;
                    $currentId = $cur['parent_id'];
                }
            }
            if ($skipSectionPrefix) {
                $html .= '<p><b>' . htmlspecialchars($displayNumber . ($itemData['item_head'] ? '. ' . $itemData['item_head'] : '')) . '</b></p>';
            } else {
                $html .= '<p><b>' . htmlspecialchars('Раздел ' . $displayNumber . ($itemData['item_head'] ? '. ' . $itemData['item_head'] : '')) . '</b></p>';
            }
        } elseif ($itemType === 'article') {
            $html .= '<p><b>' . htmlspecialchars('Статья ' . $displayNumber . ($itemData['item_head'] ? '. ' . $itemData['item_head'] : '')) . '</b></p>';
        } elseif ($itemType === 'appendix' || $itemType === 'nested_appendix') {
            $html .= '<p><b>' . htmlspecialchars('Приложение ' . $displayNumber . ($itemData['item_head'] ? '. ' . $itemData['item_head'] : '')) . '</b></p>';
        }
        $shortGenitive = getLocalElementGenitive($itemType, $displayNumber);
        $viewLink = '<a href="#" class="npa-view-expired" data-item-id="' . htmlspecialchars($external_item_id) . '" data-npa-id="' . $npaData['npa_id'] . '">Посмотреть текст ' . htmlspecialchars($shortGenitive) . '</a>';
        if (in_array($itemType, ['part', 'point', 'subpoint'])) {
            $displayNumberText = $displayNumber;
            $lastChar = substr(trim($displayNumberText), -1);
            if ($lastChar !== ')' && $lastChar !== '.') {
                $displayNumberText .= '.';
            }
            $html .= '<div class="npa-expired-inline">';
            $html .= '<span class="npa-struct-num">' . htmlspecialchars($displayNumberText) . '</span>';
            $html .= '<span class="npa-expired-link">' . $viewLink . '</span>';
            $html .= '</div>';
        } elseif ($itemType === 'preamble') {
            $html .= '<p><b>Преамбула</b></p>';
            $html .= '<p>' . $viewLink . '</p>';
        } elseif (in_array($itemType, ['chapter', 'section', 'article', 'appendix', 'nested_appendix'])) {
            $html .= '<p>' . $viewLink . '</p>';
        }
        if (!$skipInteractive) {
            $buttonsHtml = getElementRevisionButtons($itemData, $pdo, $npaData['npa_id'], $viewDate, $npaData['pageUrl'], true, $npaData['selected_revision_npa_ids'] ?? []);
            if ($buttonsHtml) $html .= $buttonsHtml;
        }
        $expiredHtml = $itemData['expired_content_html'] ?? '';
        if (empty($expiredHtml)) {
            $fallbackContent = getItemRevisionContent($pdo, $itemData['rev_id'], $internal_id, 0, null, true, false, null, false);
            if (!$fallbackContent || empty($fallbackContent['html'])) {
                $fallbackContent = getItemRevisionContent($pdo, $itemData['rev_id'], $internal_id, 0, null, false, false, null, true);
            }
            $expiredHtml = $fallbackContent ? $fallbackContent['html'] : '';
        }
        $html .= '<script type="application/json" class="npa-expired-content" data-item-id="' . htmlspecialchars($external_item_id) . '">'
               . json_encode($expiredHtml, JSON_UNESCAPED_UNICODE | JSON_HEX_TAG)
               . '</script>';
        $html .= '</div>';
        return $html;
    }
    if ($itemType === 'structured_table') {
        $html .= renderStructuredTable($itemData, $itemData['paragraphs'], $pdo, $viewDate, $itemsById, $skipInteractive);
        $html .= '</div>';
        return $html;
    }
    $hasTableFragment = false;
    foreach ($itemData['paragraphs'] as $para) {
        if ($para['block_type'] === 'table_fragment') {
            $hasTableFragment = true;
            break;
        }
        if ($para['block_type'] === 'child_ref') {
            $refId = $para['ref_item_internal_id'];
            if ($refId && isset($itemsById[$refId])) {
                foreach ($itemsById[$refId]['paragraphs'] as $childPara) {
                    if ($childPara['block_type'] === 'table_fragment') {
                        $hasTableFragment = true;
                        break 2;
                    }
                }
            }
        }
    }
    if ($hasTableFragment) {
        $html .= renderElementAsTableFragment($itemData, $itemsById, $pdo, $viewDate, $skipInteractive);
        $html .= '</div>';
        return $html;
    }
    $itemNotes = $npaData['item_notes'] ?? [];
    if (!$skipInteractive) {
        $headNotesHtml = getItemHeadRevisionNotes($internal_id, $pdo, $viewDate, $itemType, $npaData['selected_revision_npa_ids'] ?? [], $npaData['npa_id'] ?? null);
        if ($headNotesHtml) $html .= $headNotesHtml;
        $headButtonsHtml = getItemHeadRevisionButtons($internal_id, $external_item_id, $npaData['npa_id'], $pdo, $viewDate, $npaData['selected_revision_npa_ids'] ?? []);
        if ($headButtonsHtml) $html .= $headButtonsHtml;
    }
    $prefixRev = getItemPrefixRevisionForSelectedEdition($internal_id, $viewDate, $pdo, $npaData['selected_revision_npa_ids'] ?? []);
    $hasPrefix = !empty($prefixRev['prefix_text']);
    $skipSectionPrefix = false;
    if ($itemType === 'section' && !empty($noNameIds)) {
        $currentId = $internal_id;
        while ($currentId) {
            $cur = $itemsById[$current_id] ?? null;
            if (!$cur) break;
            if (in_array($cur['item_id'], $noNameIds)) {
                $skipSectionPrefix = true;
                break;
            }
            if ($cur['item_type'] === 'appendix' || $cur['item_type'] === 'nested_appendix') break;
            $currentId = $cur['parent_id'];
        }
    }
    $buttonsHtml = '';
    if ($showTableButtons && !$skipInteractive && !$isExpired && in_array($itemType, ['section', 'chapter', 'article', 'appendix', 'nested_appendix'])) {
        $buttonsHtml = getElementRevisionButtons($itemData, $pdo, $npaData['npa_id'], $viewDate, $npaData['pageUrl'], false, $npaData['selected_revision_npa_ids'] ?? []);
        if ($buttonsHtml) {
            $buttonsHtml = '<div class="npa-table-buttons-wrapper" style="display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px;">' . $buttonsHtml . '</div>';
        }
    }
    $notes = [];
    if (!$skipInteractive && isset($itemNotes[$external_item_id]) && !empty($itemNotes[$external_item_id])) {
        // Показываем только примечания, действующие на дату вступления в силу выбранной
        // редакции: valid_to не задан ИЛИ valid_to >= даты вступления в силу выбранной
        // редакции. Примечания с истёкшим valid_to не выводятся (docs/db_schema.md §6.1.4).
        $notes = filterNotesByValidTo($itemNotes[$external_item_id], $viewDate);
    }
    if (!empty($notes)) {
        $noteTexts = array_map(function($n) { return htmlspecialchars($n['note_text']); }, $notes);
        $html .= '<div class="npa-item-notes">';
        $html .= '<svg class="npa-item-notes-icon" viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" aria-hidden="true">
                    <circle cx="8" cy="8" r="7" stroke-width="1.2"/>
                    <path d="M8 11V8M8 5h.01" stroke-width="1.5" stroke-linecap="round"/>
                  </svg>';
        $html .= '<span class="npa-item-notes-text">' . implode('; ', $noteTexts) . '</span>';
        $html .= '</div>';
    }
    if (!in_array($itemType, ['part', 'point', 'subpoint'])) {
        if ($itemType === 'appendix' || $itemType === 'nested_appendix') {
            if ($hasPrefix) {
                $html .= $buttonsHtml;
                $prefixText = $prefixRev['prefix_text'];
                $prefixText = preg_replace('/(к постановлению|к закону)/i', '<br>$1', $prefixText);
                $prefixText = preg_replace('/(«[^»]+»)/u', '<br>$1', $prefixText);
                $html .= '<div class="npa-appendix-prefix" style="margin-left:66.666%; text-align:left; font-weight:bold; color:#1a3d6d; font-family:\'Arial\',sans-serif;">' . $prefixText . '</div>';
                $appendixTitle = $itemData['item_head'] ?? '';
                if ($appendixTitle) {
                    $html .= '<p class="npa-appendix-title" style="text-align:center; font-weight:bold; margin:0.5em 0 1em 0;">' . htmlspecialchars($appendixTitle) . '</p>';
                }
            } else {
                $html .= $buttonsHtml;
                $html .= '<p><b>' . htmlspecialchars('Приложение ' . $displayNumber . ($itemData['item_head'] ? '. ' . $itemData['item_head'] : '')) . '</b></p>';
            }
        } else {
            $itemExternalId = $itemData['item_id'] ?? '';
            switch ($itemType) {
                case 'chapter':
                    $html .= $buttonsHtml;
                    $html .= '<p><b>' . htmlspecialchars('Глава ' . $displayNumber . ($itemData['item_head'] ? '. ' . $itemData['item_head'] : '')) . '</b></p>';
                    break;
                case 'section':
                    if ($skipSectionPrefix || !empty($itemData['hide_section_prefix'])) {
                        $sectionHeader = $displayNumber . ($itemData['item_head'] ? '. ' . $itemData['item_head'] : '');
                    } else {
                        $sectionHeader = 'Раздел ' . $displayNumber . ($itemData['item_head'] ? '. ' . $itemData['item_head'] : '');
                    }
                    $html .= $buttonsHtml;
                    $html .= '<p class="npa-section npa-num-processed"><span class="npa-section-num">' . htmlspecialchars($sectionHeader) . '</span></p>';
                    break;
                case 'article':
                    $html .= $buttonsHtml;
                    $html .= '<p><b>' . htmlspecialchars('Статья ' . $displayNumber . ($itemData['item_head'] ? '. ' . $itemData['item_head'] : '')) . '</b></p>';
                    break;
            }
        }
    }
    if (!$skipInteractive) {
        $elementNotesHtml = getElementRevisionNotes($internal_id, $pdo, $npaData['npa_id'], $npaData['npa_type'], $viewDate, $itemType, $npaData['selected_revision_npa_ids'] ?? []);
        if ($elementNotesHtml) $html .= $elementNotesHtml;
        if (!$showTableButtons) {
            $buttonsHtml = getElementRevisionButtons($itemData, $pdo, $npaData['npa_id'], $viewDate, $npaData['pageUrl'], false, $npaData['selected_revision_npa_ids'] ?? []);
            if ($buttonsHtml) $html .= $buttonsHtml;
        }
    }
    $isFirstParagraph = true;
    $isFirstNumbered = false;
    foreach ($itemData['paragraphs'] as $block) {
        $blockType = $block['block_type'];
        if ($blockType === 'paragraph') {
            if (!empty($block['paragraph_note'])) {
                $html .= '<p align="center">' . htmlspecialchars($block['paragraph_note']) . '</p>';
            }
            $paragraphHtml = $block['html_text'];
            $paragraphHtml = str_replace(['<b><i> &nbsp;</i></b>', '<i><b> &nbsp;</b></i>'], '', $paragraphHtml);
            if ($isFirstParagraph && in_array($itemType, ['part', 'point', 'subpoint']) && !empty($displayNumber)) {
                $numberText = $displayNumber;
                $lastChar = substr(trim($numberText), -1);
                if ($lastChar !== ')' && $lastChar !== '.') {
                    $numberText .= '.';
                }
                $paragraphHtml = preg_replace('/<p([^>]*)>/', '<p$1><span class="npa-struct-num">' . htmlspecialchars($numberText) . '</span>', $paragraphHtml, 1);
                $isFirstNumbered = true;
                $isFirstParagraph = false;
            } elseif ($isFirstParagraph) {
                $isFirstParagraph = false;
            } else {
                if ($isFirstNumbered) {
                    $paragraphHtml = preg_replace('/<p([^>]*)>/', '<p$1 class="npa-num-continuation">', $paragraphHtml, 1);
                }
            }
            $html .= $paragraphHtml;
        } elseif ($blockType === 'table') {
            $html .= $block['html_text'];
        } elseif ($blockType === 'child_ref') {
            $refInternalId = $block['ref_item_internal_id'];
            if ($refInternalId && isset($itemsById[$refInternalId])) {
                $html .= renderElement($itemsById[$refInternalId], $itemsById, $pdo, $viewDate, $npaData, $renderedItems, $skipInteractive, $noNameIds, $forComparison);
                $html .= '<div class="npa-para-sep"></div>';
            }
        }
    }
    if ($itemType === 'preamble' && $npaData['npa_type'] === 'regulation') {
        $html .= '<p align="center"><b>П О С Т А Н О В Л Я Е Т:</b></p>';
    }
    $html .= '</div>';
    return $html;
}

function renderSubtree($item, $itemsById, $pdo, $viewDate, $npaData, &$renderedItems, $skipInteractive = true, $noNameIds = [], $forComparison = false) {
    $key = isset($item['internal_id']) ? $item['internal_id'] : (isset($item['id']) ? $item['id'] : 0);
    if (!$key || isset($renderedItems[$key])) {
        return '';
    }
    $html = renderElement($item, $itemsById, $pdo, $viewDate, $npaData, $renderedItems, $skipInteractive, $noNameIds, $forComparison);
    if ($item['item_type'] !== 'structured_table') {
        $children = array_filter($itemsById, function($child) use ($item, $key) {
            if (empty($child['parent_id'])) return false;
            return (string)$child['parent_id'] === (string)$item['id'] || (string)$child['parent_id'] === (string)$key;
        });
        usort($children, function($a, $b) {
            if ($a['sort_order'] != $b['sort_order']) {
                return $a['sort_order'] - $b['sort_order'];
            }
            return $a['id'] - $b['id'];
        });
        foreach ($children as $child) {
            $html .= renderSubtree($child, $itemsById, $pdo, $viewDate, $npaData, $renderedItems, $skipInteractive, $noNameIds, $forComparison);
        }
    }
    return $html;
}

function getItemRevisionsList(PDO $pdo, $internal_item_id, $npa_id, $asOfDate, $baseNpaId, $npaType) {
    $stmtBaseValid = $pdo->prepare("SELECT not_valid FROM npa_base WHERE npa_id = ?");
    $stmtBaseValid->execute([$npa_id]);
    $baseRow = $stmtBaseValid->fetch();
    $notValidDate = $baseRow ? ($baseRow['not_valid'] ?? null) : null;
    $maxDate = getDocMaxDate($pdo, $npa_id, $asOfDate);
    $isDocExpired = $notValidDate && ($maxDate !== null && $maxDate >= $notValidDate);
    $sql = "SELECT r.rev_id, r.valid_from, r.valid_to, r.modified_by_id, r.mod_type, r.not_valid,
                   i.item_id as external_item_id, i.item_type, i.item_number
            FROM npa_item_revision r
            INNER JOIN npa_item i ON r.item_internal_id = i.id
            WHERE r.item_internal_id = ? AND i.npa_id = ?
              AND EXISTS (SELECT 1 FROM npa_paragraph p WHERE p.rev_id = r.rev_id)";
    $params = [$internal_item_id, $npa_id];
    if ($isDocExpired && $notValidDate) {
        $sql .= " AND r.valid_from < ?";
        $params[] = $notValidDate;
    }
    $sql .= " ORDER BY r.valid_from ASC, r.rev_id ASC";
    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    $revisions = $stmt->fetchAll();
    $totalRevs = count($revisions);
    $result = [];
    foreach ($revisions as $idx => $rev) {
        $dt = parseDate($rev['valid_from']);
        $validFromDate = $dt ? $dt->format('d.m.Y') : '';
        $validToDate = '';
        if ($rev['valid_to']) {
            $dtTo = parseDate($rev['valid_to']);
            $validToDate = $dtTo ? $dtTo->format('d.m.Y') : '';
        }
        $isLastRev = ($idx === $totalRevs - 1);
        $revValidToDate = !empty($rev['valid_to']) ? substr($rev['valid_to'], 0, 10) : null;
        $isExpiredRev = $isLastRev && ($isDocExpired || ($revValidToDate !== null && $revValidToDate < $asOfDate) || (!empty($rev['not_valid']) && $revValidToDate === null));
        $expirySource = '';
        $expiryUrl = '';
        $itemType = $rev['item_type'];
        $itemNumber = $rev['item_number'];
        $elementHumanPath = '';
        if ($idx === 0) {
            $npaTitle = '';
            $displayTitle = 'Исходная редакция';
            $sourceDecode = 'исходная редакция';
            $npaUrl = '';
            if ($itemType === 'article') {
                $elementHumanPath = 'статьи ' . $itemNumber;
            } elseif ($itemType === 'section') {
                $elementHumanPath = 'раздела ' . $itemNumber;
            } elseif ($itemType === 'part') {
                $elementHumanPath = 'части ' . $itemNumber;
            } elseif ($itemType === 'point') {
                $elementHumanPath = 'пункта ' . $itemNumber;
            } elseif ($itemType === 'subpoint') {
                $elementHumanPath = 'подпункта ' . $itemNumber;
            } elseif ($itemType === 'chapter') {
                $elementHumanPath = 'главы ' . $itemNumber;
            } elseif ($itemType === 'appendix' || $itemType === 'nested_appendix') {
                $elementHumanPath = 'приложения ' . $itemNumber;
            } elseif ($itemType === 'preamble') {
                $elementHumanPath = 'преамбулы';
            } elseif ($itemType === 'structured_table') {
                $stmtHead = $pdo->prepare("SELECT head_text FROM npa_item_head_revision WHERE item_internal_id = ? ORDER BY valid_from DESC LIMIT 1");
                $stmtHead->execute([$internal_item_id]);
                $head = $stmtHead->fetch();
                $tableHead = $head ? $head['head_text'] : '';
                if (!empty($tableHead)) {
                    $elementHumanPath = 'таблицы ' . $itemNumber . ' (' . $tableHead . ')';
                } else {
                    $elementHumanPath = '';
                }
            } else {
                $elementHumanPath = 'элемента';
            }
        } else {
            $changerElementId = (int)$rev['modified_by_id'];
            $npaInfo = getNpaInfoByItemId($changerElementId, $pdo);
            if ($npaInfo) {
                $typeName = ($npaInfo['npa_type'] === 'law') ? 'Закона' : 'Постановления Законодательного Собрания';
                $dateForDisplay = formatRusDate($npaInfo['date_passed'], $npaInfo['date_format']);
                $npaTitle = $typeName . ' города Севастополя № ' . $npaInfo['npa_number'] . ' от ' . $dateForDisplay;
                $sourceDecode = getElementHumanPath($changerElementId, $pdo);
                $npaUrl = $npaInfo['npa_url'] ?? '';
            } else {
                $npaTitle = 'Неизвестный документ';
                $sourceDecode = '';
                $npaUrl = '';
            }
            $displayTitle = $npaTitle;
            $elementHumanPath = getElementHumanPath($internal_item_id, $pdo);
        }
        if ($isExpiredRev) {
            $notValidId = $rev['not_valid'] ?? null;
            if ($notValidId && $notValidId !== 'base') {
                $expiryNpaInfo = getNpaInfoByItemId($notValidId, $pdo);
                if ($expiryNpaInfo) {
                    $typeName = ($expiryNpaInfo['npa_type'] === 'law') ? 'Закона' : 'Постановления Законодательного Собрания';
                    $dateForDisplay = formatRusDate($expiryNpaInfo['date_passed'], $expiryNpaInfo['date_format']);
                    $expirySource = $typeName . ' города Севастополя № ' . $expiryNpaInfo['npa_number'] . ' от ' . $dateForDisplay;
                    $expiryUrl = $expiryNpaInfo['npa_url'] ?? '';
                }
            }
            $displayTitle = $expirySource ?: 'последняя действующая редакция';
            $sourceDecode = $expirySource ?: 'последняя действующая редакция';
            $npaUrl = $expiryUrl;
        }
        $result[] = [
            'rev_id'         => $rev['rev_id'],
            'valid_from'     => $validFromDate,
            'valid_to'       => $validToDate,
            'valid_to_raw'   => $rev['valid_to'],
            'valid_from_raw' => $rev['valid_from'],
            'source_decode'  => $sourceDecode,
            'modified_by_id' => $rev['modified_by_id'],
            'display_title'  => $displayTitle,
            'is_original'    => ($idx === 0 && !$isExpiredRev),
            'is_expired'     => $isExpiredRev,
            'expiry_source'  => $expirySource,
            'expiry_url'     => $expiryUrl,
            'element_path'   => $elementHumanPath,
            'npa_title'      => $npaTitle,
            'npa_url'        => $npaUrl,
            'external_item_id' => $rev['external_item_id']
        ];
    }
    $count = count($result);
    if ($count > 0) {
        $maxDate2 = getDocMaxDate($pdo, $npa_id, $asOfDate);
        $isDocExpired = $notValidDate && ($maxDate2 !== null && $maxDate2 >= $notValidDate);
        $currentIndex = -1;
        foreach ($result as $idx => $rev) {
            if ((is_null($rev['valid_to_raw']) || $rev['valid_to_raw'] >= $asOfDate) && $rev['valid_from_raw'] <= $asOfDate) {
                $currentIndex = $idx;
                break;
            }
        }
        if ($currentIndex >= 0 && !$isDocExpired) {
            $result[$currentIndex]['is_current'] = true;
        } elseif ($currentIndex < 0 && !$isDocExpired) {
            $result[$count - 1]['is_current'] = true;
        }
    }
    return $result;
}

function getItemHeadRevisionsList(PDO $pdo, $internal_item_id, $npa_id, $asOfDate) {
    $stmtBaseValid = $pdo->prepare("SELECT not_valid FROM npa_base WHERE npa_id = ?");
    $stmtBaseValid->execute([$npa_id]);
    $baseRow = $stmtBaseValid->fetch();
    $notValidDate = $baseRow ? ($baseRow['not_valid'] ?? null) : null;
    $maxDate = getDocMaxDate($pdo, $npa_id, $asOfDate);
    $isDocExpired = $notValidDate && ($maxDate !== null && $maxDate >= $notValidDate);
    $sql = "SELECT id, head_text, valid_from, valid_to, modified_by_id, not_valid
            FROM npa_item_head_revision
            WHERE item_internal_id = ?";
    $params = [$internal_item_id];
    if ($isDocExpired && $notValidDate) {
        $sql .= " AND valid_from < ?";
        $params[] = $notValidDate;
    }
    $sql .= " ORDER BY valid_from ASC";
    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    $revisions = $stmt->fetchAll();
    $totalRevs = count($revisions);
    $result = [];
    $elementHumanPath = getElementHumanPath($internal_item_id, $pdo);
    $stmtItem = $pdo->prepare("SELECT item_type, item_number FROM npa_item WHERE id = ?");
    $stmtItem->execute([$internal_item_id]);
    $item = $stmtItem->fetch();
    $itemType = $item ? $item['item_type'] : '';
    $itemNumber = $item ? ($item['item_number'] ?? '') : '';
    foreach ($revisions as $idx => $rev) {
        $dt = parseDate($rev['valid_from']);
        $validFromDate = $dt ? $dt->format('d.m.Y') : '';
        $validToDate = '';
        if ($rev['valid_to']) {
            $dtTo = parseDate($rev['valid_to']);
            $validToDate = $dtTo ? $dtTo->format('d.m.Y') : '';
        }
        $isLastRev = ($idx === $totalRevs - 1);
        $revValidToDate = !empty($rev['valid_to']) ? substr($rev['valid_to'], 0, 10) : null;
        $isExpiredRev = $isLastRev && ($isDocExpired || ($revValidToDate !== null && $revValidToDate < $asOfDate) || (!empty($rev['not_valid']) && $revValidToDate === null));
        $expirySource = '';
        $expiryUrl = '';
        if ($idx === 0) {
            $displayTitle = 'Исходный заголовок элемента';
            $sourceDecode = 'исходная редакция';
            $npaUrl = '';
            if ($itemType === 'structured_table') {
                $tableHead = $rev['head_text'];
                if (!empty($tableHead)) {
                    $elementPath = 'таблицы ' . $itemNumber . ' (заголовок)';
                } else {
                    $elementPath = '';
                }
            } else {
                $elementPath = $elementHumanPath . ' (заголовок)';
            }
        } else {
            $changerElementId = (int)$rev['modified_by_id'];
            $npaInfo = getNpaInfoByItemId($changerElementId, $pdo);
            if ($npaInfo) {
                $typeName = ($npaInfo['npa_type'] === 'law') ? 'Закона' : 'Постановления Законодательного Собрания';
                $dateForDisplay = formatRusDate($npaInfo['date_passed'], $npaInfo['date_format']);
                $displayTitle = $typeName . ' города Севастополя № ' . $npaInfo['npa_number'] . ' от ' . $dateForDisplay;
                $sourceDecode = getElementHumanPath($changerElementId, $pdo);
                $npaUrl = $npaInfo['npa_url'] ?? '';
            } else {
                $displayTitle = 'Неизвестный документ';
                $sourceDecode = '';
                $npaUrl = '';
            }
            if ($itemType === 'structured_table') {
                $tableHead = $rev['head_text'];
                if (!empty($tableHead)) {
                    $elementPath = 'таблицы ' . $itemNumber . ' (заголовок)';
                } else {
                    $elementPath = '';
                }
            } else {
                $elementPath = $elementHumanPath . ' (заголовок)';
            }
        }
        if ($isExpiredRev) {
            $notValidId = $rev['not_valid'] ?? null;
            if ($notValidId && $notValidId !== 'base') {
                $expiryNpaInfo = getNpaInfoByItemId($notValidId, $pdo);
                if ($expiryNpaInfo) {
                    $typeName = ($expiryNpaInfo['npa_type'] === 'law') ? 'Закона' : 'Постановления Законодательного Собрания';
                    $dateForDisplay = formatRusDate($expiryNpaInfo['date_passed'], $expiryNpaInfo['date_format']);
                    $expirySource = $typeName . ' города Севастополя № ' . $expiryNpaInfo['npa_number'] . ' от ' . $dateForDisplay;
                    $expiryUrl = $expiryNpaInfo['npa_url'] ?? '';
                }
            }
            $displayTitle = $expirySource ?: 'последний действующий заголовок элемента';
            $sourceDecode = $expirySource ?: 'последний действующий заголовок элемента';
            $npaUrl = $expiryUrl;
        }
        $result[] = [
            'rev_id'         => $rev['id'],
            'valid_from'     => $validFromDate,
            'valid_to'       => $validToDate,
            'valid_to_raw'   => $rev['valid_to'],
            'valid_from_raw' => $rev['valid_from'],
            'source_decode'  => $sourceDecode,
            'modified_by_id' => $rev['modified_by_id'],
            'display_title'  => $displayTitle,
            'is_original'    => ($idx === 0 && !$isExpiredRev),
            'is_expired'     => $isExpiredRev,
            'expiry_source'  => $expirySource,
            'expiry_url'     => $expiryUrl,
            'element_path'   => $elementPath,
            'npa_title'      => $rev['head_text'],
            'npa_url'        => $npaUrl
        ];
    }
    $count = count($result);
    if ($count > 0) {
        $maxDate2 = getDocMaxDate($pdo, $npa_id, $asOfDate);
        $isDocExpired = $notValidDate && ($maxDate2 !== null && $maxDate2 >= $notValidDate);
        $currentIndex = -1;
        foreach ($result as $idx => $rev) {
            if ((is_null($rev['valid_to_raw']) || $rev['valid_to_raw'] >= $asOfDate) && $rev['valid_from_raw'] <= $asOfDate) {
                $currentIndex = $idx;
                break;
            }
        }
        if ($currentIndex >= 0 && !$isDocExpired) {
            $result[$currentIndex]['is_current'] = true;
        } elseif ($currentIndex < 0 && !$isDocExpired) {
            $result[$count - 1]['is_current'] = true;
        }
    }
    return $result;
}


/* ================= Контекст запроса (MODX) ================= */

 $structured_tree_cache = [];
 $npa_id = isset($npa_id) ? (int)$npa_id : 0;

if (!$npa_id) {
    $tvValue = $modx->getTemplateVar('npa_id', '*', $modx->documentObject['id']);
    if ($tvValue && isset($tvValue['value'])) {
        $npa_id = (int)$tvValue['value'];
    }
}

if (!$npa_id) {
    return -6;
}

 $tvValue = $modx->getTemplateVar('z-publish','*',$modx->documentObject['id']);
 $z_publish = $tvValue['value'];
 $baseUrl = $modx->config['site_url'];
 $pdfUrl = $baseUrl . ltrim($z_publish, '/');
 $tocTitle = isset($tocTitle) ? $tocTitle : 'Оглавление документа';
 $NPA_NO_NAME_IDS = [];

/* ================= Дата просмотра и подключение к БД ================= */

 $rawDate = isset($_GET['view_date']) ? trim($_GET['view_date']) : null;
 $isCustomDate = ($rawDate !== null);

if ($isCustomDate) {
    $viewDateObj = parseDate($rawDate);
    if (!$viewDateObj) {
        $viewDateObj = new DateTime('today', new DateTimeZone('UTC'));
    }
} else {
    $viewDateObj = null;
}

try {
    $pdo = new PDO(
        "mysql:host=" . NPA_DB_HOST . ";dbname=" . NPA_DB_NAME . ";charset=" . NPA_DB_CHARSET,
        NPA_DB_USER,
        NPA_DB_PASS,
        [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            PDO::ATTR_EMULATE_PREPARES => false,
        ]
    );
} catch (PDOException $e) {
    return -2;
}

if ($viewDateObj === null) {
    $stmtMax = $pdo->prepare("
        SELECT MAX(valid_from) as max_date FROM (
            SELECT valid_from FROM npa_base WHERE npa_id = ?
            UNION
            SELECT revision_date_valid FROM npa_revision_info WHERE base_npa_id = ?
        ) AS dates
    ");
    $stmtMax->execute([$npa_id, $npa_id]);
    $maxRow = $stmtMax->fetch();
    $lastDate = $maxRow['max_date'] ?? null;
    if ($lastDate) {
        $viewDateObj = parseDate($lastDate);
    } else {
        $viewDateObj = new DateTime('today', new DateTimeZone('UTC'));
    }
}

 $viewDateSql = $viewDateObj->format('Y-m-d');


/* ================= AJAX-обработка (может завершить выполнение) ================= */
if (isset($_GET['ajax_action'])) {
    header('Content-Type: application/json');
    $action = $_GET['ajax_action'];
    $ajax_npa_id = isset($_GET['npa_id']) ? (int)$_GET['npa_id'] : 0;
    $external_item_id = isset($_GET['item_id']) ? $_GET['item_id'] : '';
    $context = isset($_GET['context']) ? $_GET['context'] : '';
    $isHeadContext = ($context === 'head');
    $isHeadRevisionOfElement = (strpos($external_item_id, 'head:') === 0);
    $actualItemId = ($isHeadRevisionOfElement || $isHeadContext) ? ($isHeadRevisionOfElement ? substr($external_item_id, 5) : $external_item_id) : $external_item_id;
    $rev_id = isset($_GET['rev_id']) ? (int)$_GET['rev_id'] : 0;
    $rawDateAjax = isset($_GET['view_date']) ? trim($_GET['view_date']) : null;
    $viewDateObjAjax = parseDate($rawDateAjax);
    if (!$viewDateObjAjax) {
        $viewDateObjAjax = new DateTime('today', new DateTimeZone('UTC'));
    }
    $viewDateSqlAjax = $viewDateObjAjax->format('Y-m-d');
    $selectedRevisionNpaIdsAjax = getSelectedRevisionNpaIds($pdo, $ajax_npa_id, $viewDateSqlAjax);
    $GLOBALS['selected_revision_npa_ids'] = $selectedRevisionNpaIdsAjax;
    $stmtBase = $pdo->prepare("SELECT npa_type FROM npa_base WHERE npa_id = ?");
    $stmtBase->execute([$ajax_npa_id]);
    $baseRow = $stmtBase->fetch();
    $npaType = $baseRow ? $baseRow['npa_type'] : 'law';
    if ($action == 'get_item_history') {
        if ($isHeadContext || $isHeadRevisionOfElement) {
            $internal_id = getInternalItemId($pdo, $ajax_npa_id, $actualItemId);
            if (!$internal_id) {
                echo json_encode(['success' => false, 'error' => -6]);
                exit;
            }
            $list = (function() use ($pdo, $internal_id, $ajax_npa_id, $viewDateSqlAjax, $selectedRevisionNpaIdsAjax) {
                $list = getItemHeadRevisionsList($pdo, $internal_id, $ajax_npa_id, $viewDateSqlAjax);
                $current = getItemHeadRevisionForSelectedEdition($pdo, $internal_id, $viewDateSqlAjax, $selectedRevisionNpaIdsAjax);
                if ($current) {
                    $cutoff = $current['valid_from'];
                    $list = array_values(array_filter($list, function($row) use ($cutoff, $current) {
                        $d = $row['valid_from'] ?? null;
                        return $d === null || $d < $cutoff || ($d === $cutoff && (int)$row['rev_id'] <= (int)$current['id']);
                    }));
                }
                return $list;
            })();
            echo json_encode(['success' => true, 'revisions' => $list]);
            exit;
        } elseif (empty($external_item_id) || $external_item_id === 'head' || $external_item_id === 'null') {
            $list = (function() use ($pdo, $ajax_npa_id, $viewDateSqlAjax, $selectedRevisionNpaIdsAjax) {
                $list = getHeadRevisionsList($pdo, $ajax_npa_id, $viewDateSqlAjax);
                $stmt = $pdo->prepare("SELECT * FROM npa_head_revision WHERE npa_id = ? ORDER BY valid_from ASC, id ASC");
                $stmt->execute([$ajax_npa_id]);
                $all = $stmt->fetchAll();
                $current = null;
                foreach ($all as $r) { if (($r['valid_from'] === null || $r['valid_from'] <= $viewDateSqlAjax)) $current = $r; }
                if ($current) {
                    $list = array_values(array_filter($list, function($row) use ($current) { return true; }));
                }
                return $list;
            })();
            echo json_encode(['success' => true, 'revisions' => $list]);
            exit;
        } else {
            $internal_id = getInternalItemId($pdo, $ajax_npa_id, $external_item_id);
            if (!$internal_id) {
                echo json_encode(['success' => false, 'error' => -6]);
                exit;
            }
            $list = (function() use ($pdo, $internal_id, $ajax_npa_id, $viewDateSqlAjax, $npaType, $selectedRevisionNpaIdsAjax) {
                $list = getItemRevisionsList($pdo, $internal_id, $ajax_npa_id, $viewDateSqlAjax, $ajax_npa_id, $npaType);
                $current = getRevisionForSelectedEdition($pdo, $internal_id, $viewDateSqlAjax, $selectedRevisionNpaIdsAjax);
                if ($current) {
                    $cutoff = $current['valid_from'];
                    $currentId = (int)$current['rev_id'];
                    $list = array_values(array_filter($list, function($row) use ($cutoff, $currentId) {
                        $d = $row['valid_from'] ?? null;
                        return $d === null || $d < $cutoff || ($d === $cutoff && (int)$row['rev_id'] <= $currentId);
                    }));
                }
                return $list;
            })();
            echo json_encode(['success' => true, 'revisions' => $list]);
            exit;
        }
    }
    if ($action == 'get_compare') {
        if ($isHeadContext || $isHeadRevisionOfElement) {
            if (empty($actualItemId) || $actualItemId === 'head' || $actualItemId === 'null') {
                $compareData = getHeadCompareHtml($pdo, $ajax_npa_id, $viewDateSqlAjax);
                $scopeName = 'наименования документа';
            } else {
                $internal_id = getInternalItemId($pdo, $ajax_npa_id, $actualItemId);
                if (!$internal_id) {
                    echo json_encode(['success' => false, 'error' => -6]);
                    exit;
                }
                $compareData = getItemHeadCompareForSelectedEdition($pdo, $internal_id, $viewDateSqlAjax, $selectedRevisionNpaIdsAjax);
                $scopeName = 'заголовка элемента';
            }
            echo json_encode([
                'success' => true,
                'changing_elements' => $compareData['changing_elements'] ?? [],
                'prev_html_raw' => $compareData['prev_html_raw'],
                'current_html_raw' => $compareData['current_html_raw'],
                'prev_valid_from' => $compareData['prev_valid_from'],
                'current_valid_from' => $compareData['current_valid_from'],
                'element_human_path' => $scopeName,
                'highlights' => normalizeHighlights($compareData['highlights']),
                'mod_type' => $compareData['mod_type']
            ]);
            exit;
        }
        if (empty($external_item_id) || $external_item_id === 'head' || $external_item_id === 'null') {
            $compareData = getHeadCompareHtml($pdo, $ajax_npa_id, $viewDateSqlAjax);
            echo json_encode([
                'success' => true,
                'changing_elements' => $compareData['changing_elements'] ?? [],
                'prev_html_raw' => $compareData['prev_html_raw'],
                'current_html_raw' => $compareData['current_html_raw'],
                'prev_valid_from' => $compareData['prev_valid_from'],
                'current_valid_from' => $compareData['current_valid_from'],
                'element_human_path' => 'наименования документа',
                'highlights' => normalizeHighlights($compareData['highlights']),
                'mod_type' => $compareData['mod_type']
            ]);
            exit;
        }
        $internal_id = getInternalItemId($pdo, $ajax_npa_id, $external_item_id);
        if (!$internal_id) {
            echo json_encode(['success' => false, 'error' => -6]);
            exit;
        }
        $stmtType = $pdo->prepare("SELECT item_type FROM npa_item WHERE id = ?");
        $stmtType->execute([$internal_id]);
        $itemType = $stmtType->fetchColumn();
        // Текущую ревизию берём с учётом контекста выбранной редакции документа так же,
        // как это делает основной вывод страницы (getRevisionForSelectedEdition):
        // при просмотре редакции изменяющего НПА в AJAX-сравнении должна показываться
        // редакция, внесённая именно этим НПА, даже если её valid_from позже view_date
        // (например, отложенные изменения Закона № 677-ЗС с вступлением в силу 01.01.2023).
        $currentRev = getRevisionForSelectedEdition($pdo, $internal_id, $viewDateSqlAjax, $selectedRevisionNpaIdsAjax);
        if (!$currentRev) {
            echo json_encode(['success' => false, 'error' => -6]);
            exit;
        }
        $changingElements = [];
        $changerIds = [];
        if (!empty($currentRev['modified_by_id']) && $currentRev['modified_by_id'] !== 'base') {
            $changerIds = array_filter(array_map('trim', explode(',', $currentRev['modified_by_id'])));
            foreach ($changerIds as $changerStr) {
                if ($changerStr === 'base') continue;
                $npaInfo = getNpaInfoByItemId($changerStr, $pdo);
                if (!$npaInfo) continue;
                $changerDate = $npaInfo['date_signed'] ?? $npaInfo['date_passed'] ?? $currentRev['valid_from'];
                $changerNpaId = $npaInfo['npa_id'];
                $changerNpaType = $npaInfo['npa_type'];
                $changerHtml = getElementHtmlById($changerStr, $viewDateSqlAjax, $pdo, $changerNpaId, $changerNpaType);
                $note = getRevisionSourceNote($changerStr, $pdo, true);
                $changingElements[] = [
                    'note' => $note,
                    'html' => $changerHtml,
                    'date' => formatDateToRus($changerDate)
                ];
                        }
        }
        // Дочерние элементы, утратившие силу той же НПА, тоже показываем в «Изменения внесены:».
        $changingElements = array_merge($changingElements, collectExpiredChildChanges($pdo, $internal_id, $viewDateSqlAjax, $changerIds, $selectedRevisionNpaIdsAjax));
        $stmtPrev = $pdo->prepare("
            SELECT * FROM npa_item_revision
            WHERE item_internal_id = ?
              AND (valid_from < ? OR (valid_from IS NULL AND ? IS NOT NULL))
              AND EXISTS (SELECT 1 FROM npa_paragraph p WHERE p.rev_id = npa_item_revision.rev_id)
            ORDER BY valid_from DESC
            LIMIT 1
        ");
        $stmtPrev->execute($internal_id, $currentRev['valid_from'], $currentRev['valid_from']);
        $previousRev = $stmtPrev->fetch();
        $prevHtmlRaw = '';
        $currHtmlRaw = '';
        $prevValidFrom = '';
        $currValidFrom = '';
        if ($previousRev) {
            $prevAsOfDate = $currentRev['valid_from'];
            $dtPrev = parseDate($prevAsOfDate);
            if ($dtPrev) {
                $dtPrev->modify('-1 day');
                $prevAsOfDate = $dtPrev->format('Y-m-d');
            } else {
                $prevAsOfDate = $viewDateSqlAjax;
            }
            $prevContent = getItemRevisionContent($pdo, $previousRev['rev_id'], $internal_id, 0, null, false, true, $prevAsOfDate, false, false);
            // Текущую колонку сравнения рендерим на актуальную дату просмотра ($viewDateSqlAjax).
            $currContent = getItemRevisionContent($pdo, $currentRev['rev_id'], $internal_id, 0, null, false, true, $viewDateSqlAjax);
            $prevHtmlRaw = $prevContent ? ensureTableWrapperForComparison($prevContent['html'], $internal_id, $pdo, $prevAsOfDate) : '';
            $currHtmlRaw = $currContent ? ensureTableWrapperForComparison($currContent['html'], $internal_id, $pdo, $viewDateSqlAjax) : '';
            $prevValidFrom = $previousRev['valid_from'] ? formatDateToRus($previousRev['valid_from']) : '';
            $currValidFrom = $currentRev['valid_from'] ? formatDateToRus($currentRev['valid_from']) : '';
        }
        $highlights = null;
        if (!empty($currentRev['highlights'])) {
            $highlights = json_decode($currentRev['highlights'], true);
            if (!is_array($highlights)) $highlights = null;
        }
        $targetScope = getElementHumanPath($internal_id, $pdo, 'genitive');
        echo json_encode([
            'success' => true,
            'changing_elements' => $changingElements,
            'prev_html_raw' => $prevHtmlRaw,
            'current_html_raw' => $currHtmlRaw,
            'prev_valid_from' => $prevValidFrom,
            'current_valid_from' => $currValidFrom,
            'element_human_path' => $targetScope,
            'highlights' => normalizeHighlights($highlights),
            'mod_type' => $currentRev['mod_type']
        ]);
        exit;
    }
    if ($action == 'get_item_revision' && $rev_id && $external_item_id && $ajax_npa_id) {
        if ($isHeadContext || $isHeadRevisionOfElement) {
            $internal_id = getInternalItemId($pdo, $ajax_npa_id, $actualItemId);
            if (!$internal_id) {
                echo json_encode(['success' => false, 'error' => -6]);
                exit;
            }
            $content = getItemHeadRevisionContent($pdo, $rev_id, $internal_id, $viewDateSqlAjax);
            if ($content) {
                $dt = parseDate($content['valid_from']);
                $validFromFormatted = $dt ? $dt->format('d.m.Y') : '';
                $validToFormatted = '';
                if (!empty($content['valid_to'])) {
                    $dtTo = parseDate($content['valid_to']);
                    $validToFormatted = $dtTo ? $dtTo->format('d.m.Y') : '';
                }
                $isCurrent = empty($validToFormatted);
                $stmtOrig = $pdo->prepare("SELECT MIN(valid_from) as first FROM npa_item_head_revision WHERE item_internal_id = ?");
                $stmtOrig->execute([$internal_id]);
                $first = $stmtOrig->fetch();
                $isOriginal = ($first && $first['first'] == $content['valid_from']);
                if ($isOriginal) {
                    $title = 'Заголовок' . ($isCurrent ? ', действующий с ' : ', действовавший с ') . $validFromFormatted;
                    if (!$isCurrent) $title .= ' по ' . $validToFormatted;
                } else {
                    $shortDesc = getShortNpaDescription($content['modified_by_id'], $pdo, false);
                    $title = 'Заголовок' . ($isCurrent ? ', действующий с ' : ', действовавший с ') . $validFromFormatted;
                    if (!$isCurrent) $title .= ' по ' . $validToFormatted;
                    $title = 'В редакции ' . $shortDesc . ' (' . $title . ')';
                }
                echo json_encode([
                    'success' => true,
                    'html' => $content['html'],
                    'title' => $title,
                    'source_info' => $content['source_info'],
                    'valid_from' => $validFromFormatted
                ]);
            } else {
                echo json_encode(['success' => false, 'error' => -6]);
            }
            exit;
        } elseif (empty($external_item_id) || $external_item_id === 'head' || $external_item_id === 'null') {
            $content = getHeadRevisionContent($pdo, $rev_id, $ajax_npa_id, $viewDateSqlAjax);
            if ($content) {
                $dt = parseDate($content['valid_from']);
                $validFromFormatted = $dt ? $dt->format('d.m.Y') : '';
                $validToFormatted = '';
                if (!empty($content['valid_to'])) {
                    $dtTo = parseDate($content['valid_to']);
                    $validToFormatted = $dtTo ? $dtTo->format('d.m.Y') : '';
                }
                $isCurrent = empty($validToFormatted);
                $stmtOrig = $pdo->prepare("SELECT MIN(valid_from) as first FROM npa_head_revision WHERE npa_id = ?");
                $stmtOrig->execute([$ajax_npa_id]);
                $first = $stmtOrig->fetch();
                $isOriginal = ($first && $first['first'] == $content['valid_from']);
                if ($isOriginal) {
                    $title = 'Наименование' . ($isCurrent ? ', действующее с ' : ', действовавшее с ') . $validFromFormatted;
                    if (!$isCurrent) $title .= ' по ' . $validToFormatted;
                } else {
                    $shortDesc = getShortNpaDescription($content['modified_by_id'], $pdo, false);
                    $title = 'Наименование' . ($isCurrent ? ', действующее с ' : ', действовавшее с ') . $validFromFormatted;
                    if (!$isCurrent) $title .= ' по ' . $validToFormatted;
                    $title = 'В редакции ' . $shortDesc . ' (' . $title . ')';
                }
                echo json_encode([
                    'success' => true,
                    'html' => $content['html'],
                    'title' => $title,
                    'source_info' => $content['source_info'],
                    'valid_from' => $validFromFormatted
                ]);
            } else {
                echo json_encode(['success' => false, 'error' => -6]);
            }
            exit;
        } else {
            $internal_id = getInternalItemId($pdo, $ajax_npa_id, $external_item_id);
            if (!$internal_id) {
                echo json_encode(['success' => false, 'error' => -6]);
                exit;
            }
            $stmtRev = $pdo->prepare("SELECT valid_from FROM npa_item_revision WHERE rev_id = ? AND item_internal_id = ?");
            $stmtRev->execute([$rev_id, $internal_id]);
            $revData = $stmtRev->fetch();
            $asOfDateForHistory = $revData ? $revData['valid_from'] : $viewDateSqlAjax;
            
            $content = getItemRevisionContent($pdo, $rev_id, $internal_id, 0, null, true, false, $asOfDateForHistory);
            if ($content) {
                $dt = parseDate($content['valid_from']);
                $validFromFormatted = $dt ? $dt->format('d.m.Y') : '';
                $validToFormatted = '';
                if (!empty($content['valid_to'])) {
                    $dtTo = parseDate($content['valid_to']);
                    $validToFormatted = $dtTo ? $dtTo->format('d.m.Y') : '';
                }
                $isCurrent = empty($validToFormatted);
                $stmtOrig = $pdo->prepare("SELECT MIN(valid_from) as first FROM npa_item_revision WHERE item_internal_id = ?");
                $stmtOrig->execute([$internal_id]);
                $first = $stmtOrig->fetch();
                $isOriginal = ($first && $first['first'] == $content['valid_from']);
                if ($isOriginal) {
                    $title = 'Редакция' . ($isCurrent ? ', действующая с ' : ', действовавшая с ') . $validFromFormatted;
                    if (!$isCurrent) $title .= ' по ' . $validToFormatted;
                } else {
                    $shortDesc = getShortNpaDescription($content['modified_by_id'], $pdo, false);
                    $title = 'Редакция' . ($isCurrent ? ', действующая с ' : ', действовавшая с ') . $validFromFormatted;
                    if (!$isCurrent) $title .= ' по ' . $validToFormatted;
                    $title = 'В редакции ' . $shortDesc . ' (' . $title . ')';
                }
                echo json_encode([
                    'success' => true,
                    'html' => $content['html'],
                    'title' => $title,
                    'mod_type' => $content['mod_type'],
                    'modified_by' => $content['modified_by_id'],
                    'source_info' => $content['source_info'],
                    'valid_from' => $validFromFormatted
                ]);
            } else {
                echo json_encode(['success' => false, 'error' => -6]);
            }
            exit;
        }
    }
    if ($action == 'get_prev_revision_plain' && $rev_id && $external_item_id && $ajax_npa_id) {
        if ($isHeadContext || $isHeadRevisionOfElement) {
            $internal_id = getInternalItemId($pdo, $ajax_npa_id, $actualItemId);
            if (!$internal_id) {
                echo json_encode(['success' => false, 'error' => -6]);
                exit;
            }
            $content = getItemHeadRevisionContent($pdo, $rev_id, $internal_id, $viewDateSqlAjax);
            if ($content) {
                $dt = parseDate($content['valid_from']);
                $validFromFormatted = $dt ? $dt->format('d.m.Y') : '';
                $validToFormatted = '';
                if (!empty($content['valid_to'])) {
                    $dtTo = parseDate($content['valid_to']);
                    $validToFormatted = $dtTo ? $dtTo->format('d.m.Y') : '';
                }
                $isCurrent = empty($validToFormatted);
                $stmtOrig = $pdo->prepare("SELECT MIN(valid_from) as first FROM npa_item_head_revision WHERE item_internal_id = ?");
                $stmtOrig->execute([$internal_id]);
                $first = $stmtOrig->fetch();
                $isOriginal = ($first && $first['first'] == $content['valid_from']);
                if ($isOriginal) {
                    $title = 'Заголовок' . ($isCurrent ? ', действующий с ' : ', действовавший с ') . $validFromFormatted;
                    if (!$isCurrent) $title .= ' по ' . $validToFormatted;
                } else {
                    $shortDesc = getShortNpaDescription($content['modified_by_id'], $pdo, false);
                    $title = 'Заголовок' . ($isCurrent ? ', действующий с ' : ', действовавший с ') . $validFromFormatted;
                    if (!$isCurrent) $title .= ' по ' . $validToFormatted;
                    $title = 'В редакции ' . $shortDesc . ' (' . $title . ')';
                }
                echo json_encode(['success' => true, 'html' => $content['html'], 'title' => $title]);
            } else {
                echo json_encode(['success' => false, 'error' => -6]);
            }
            exit;
        } elseif (empty($external_item_id) || $external_item_id === 'head' || $external_item_id === 'null') {
            $content = getHeadRevisionContent($pdo, $rev_id, $ajax_npa_id, $viewDateSqlAjax);
            if ($content) {
                $dt = parseDate($content['valid_from']);
                $validFromFormatted = $dt ? $dt->format('d.m.Y') : '';
                $validToFormatted = '';
                if (!empty($content['valid_to'])) {
                    $dtTo = parseDate($content['valid_to']);
                    $validToFormatted = $dtTo ? $dtTo->format('d.m.Y') : '';
                }
                $isCurrent = empty($validToFormatted);
                $stmtOrig = $pdo->prepare("SELECT MIN(valid_from) as first FROM npa_head_revision WHERE npa_id = ?");
                $stmtOrig->execute([$ajax_npa_id]);
                $first = $stmtOrig->fetch();
                $isOriginal = ($first && $first['first'] == $content['valid_from']);
                if ($isOriginal) {
                    $title = 'Наименование' . ($isCurrent ? ', действующее с ' : ', действовавшее с ') . $validFromFormatted;
                    if (!$isCurrent) $title .= ' по ' . $validToFormatted;
                } else {
                    $shortDesc = getShortNpaDescription($content['modified_by_id'], $pdo, false);
                    $title = 'Наименование' . ($isCurrent ? ', действующее с ' : ', действовавшее с ') . $validFromFormatted;
                    if (!$isCurrent) $title .= ' по ' . $validToFormatted;
                    $title = 'В редакции ' . $shortDesc . ' (' . $title . ')';
                }
                echo json_encode(['success' => true, 'html' => $content['html'], 'title' => $title]);
            } else {
                echo json_encode(['success' => false, 'error' => -6]);
            }
            exit;
        } else {
            $internal_id = getInternalItemId($pdo, $ajax_npa_id, $external_item_id);
            if (!$internal_id) {
                echo json_encode(['success' => false, 'error' => -6]);
                exit;
            }
            $stmtRev = $pdo->prepare("SELECT valid_from FROM npa_item_revision WHERE rev_id = ? AND item_internal_id = ?");
            $stmtRev->execute([$rev_id, $internal_id]);
            $revData = $stmtRev->fetch();
            $asOfDateForHistory = $revData ? $revData['valid_from'] : $viewDateSqlAjax;
            
            $content = getItemRevisionContent($pdo, $rev_id, $internal_id, 0, null, true, false, $asOfDateForHistory);
            if ($content) {
                $dt = parseDate($content['valid_from']);
                $validFromFormatted = $dt ? $dt->format('d.m.Y') : '';
                $validToFormatted = '';
                if (!empty($content['valid_to'])) {
                    $dtTo = parseDate($content['valid_to']);
                    $validToFormatted = $dtTo ? $dtTo->format('d.m.Y') : '';
                }
                $isCurrent = empty($validToFormatted);
                $stmtOrig = $pdo->prepare("SELECT MIN(valid_from) as first FROM npa_item_revision WHERE item_internal_id = ?");
                $stmtOrig->execute([$internal_id]);
                $first = $stmtOrig->fetch();
                $isOriginal = ($first && $first['first'] == $content['valid_from']);
                if ($isOriginal) {
                    $title = 'Редакция' . ($isCurrent ? ', действующая с ' : ', действовавшая с ') . $validFromFormatted;
                    if (!$isCurrent) $title .= ' по ' . $validToFormatted;
                } else {
                    $shortDesc = getShortNpaDescription($content['modified_by_id'], $pdo, false);
                    $title = 'Редакция' . ($isCurrent ? ', действующая с ' : ', действовавшая с ') . $validFromFormatted;
                    if (!$isCurrent) $title .= ' по ' . $validToFormatted;
                    $title = 'В редакции ' . $shortDesc . ' (' . $title . ')';
                }
                echo json_encode([
                    'success' => true,
                    'html' => $content['html'],
                    'title' => $title
                ]);
            } else {
                echo json_encode(['success' => false, 'error' => -6]);
            }
            exit;
        }
    }
    echo json_encode(['success' => false, 'error' => -1]);
    exit;
}


/* ================= Сборка страницы НПА ================= */

 $stmt = $pdo->prepare("SELECT * FROM npa_base WHERE npa_id = ?");
 $stmt->execute([$npa_id]);
 $npaBase = $stmt->fetch();
if (!$npaBase) {
    return -7;
}

 $npaData = $npaBase;
 $npaData['pageUrl'] = $modx->makeUrl($modx->documentObject['id'], '', '', 'full');
 $npaData['npa_type'] = $npaBase['npa_type'];
 $npaData['no_name_raw'] = $npaBase['no_name'] ?? '';
 $npaData['no_name_ids'] = !empty($npaData['no_name_raw']) ? array_map('trim', explode(',', $npaData['no_name_raw'])) : [];
 $GLOBALS['NPA_NO_NAME_IDS'] = $npaData['no_name_ids'];

if ($viewDateObj === null) {
    $stmtMax = $pdo->prepare("
        SELECT MAX(valid_from) as max_date FROM (
            SELECT valid_from FROM npa_base WHERE npa_id = ?
            UNION
            SELECT revision_date_valid FROM npa_revision_info WHERE base_npa_id = ?
        ) AS dates
    ");
    $stmtMax->execute([$npa_id, $npa_id]);
    $maxRow = $stmtMax->fetch();
    $lastDate = $maxRow['max_date'] ?? null;
    if ($lastDate) {
        $viewDateObj = parseDate($lastDate);
    } else {
        $viewDateObj = new DateTime('today', new DateTimeZone('UTC'));
    }
}

 $viewDateSql = $viewDateObj->format('Y-m-d');
 $selectedRevisionNpaIds = getSelectedRevisionNpaIds($pdo, $npa_id, $viewDateSql);
 $GLOBALS['selected_revision_npa_ids'] = $selectedRevisionNpaIds;
 $npaData['selected_revision_npa_ids'] = $selectedRevisionNpaIds;

 $staticFile = getStaticFilePath($npaData, $viewDateSql, $npa_id);
 $forceRegenerate = isset($_GET['regenerate']) || isset($_GET['force']) || isset($_GET['nocache']);
if (file_exists($staticFile) && !$forceRegenerate) {
    return file_get_contents($staticFile);
}

if ($npaData['npa_type'] === 'law') {
    $stmt = $pdo->prepare("SELECT * FROM npa_law WHERE npa_id = ?");
    $stmt->execute([$npa_id]);
    $law = $stmt->fetch();
    if ($law) {
        $npaData = array_merge($npaData, $law);
    }
    if (!isset($npaData['date_passed'])) {
        $npaData['date_passed'] = $npaBase['date_passed'];
    }
} else {
    $stmt = $pdo->prepare("SELECT * FROM npa_regulation WHERE npa_id = ?");
    $stmt->execute([$npa_id]);
    $reg = $stmt->fetch();
    if ($reg) {
        $npaData = array_merge($npaData, $reg);
    }
    if (!isset($npaData['date_passed'])) {
        $npaData['date_passed'] = $npaBase['date_passed'];
    }
}

 $docStatus = getDocumentStatus($pdo, $npa_id, $viewDateSql);
 $isExpiredDoc = ($docStatus['status'] === 'expired');
 $npaData['doc_status'] = $docStatus;

 $stmtHead = $pdo->prepare("
    SELECT * FROM npa_head_revision
    WHERE npa_id = ? AND (valid_from <= ? OR valid_from IS NULL) AND (valid_to IS NULL OR valid_to >= ?)
    ORDER BY valid_from ASC
");
 $stmtHead->execute([$npa_id, $viewDateSql, $viewDateSql]);
 $headRevisions = $stmtHead->fetchAll();
foreach ($headRevisions as &$hr) {
    if (isset($hr['highlights'])) {
        $hr['highlights'] = normalizeHighlights($hr['highlights']);
    }
}
unset($hr);
 $headNotes = [];
 $currentTitle = '';
foreach ($headRevisions as $hr) {
    $currentTitle = $hr['npa_title'];
    if ($hr['modified_by_id'] && $hr['modified_by_id'] !== 'base') {
        $headNotes[] = getShortNpaDescription($hr['modified_by_id'], $pdo, true);
    }
}
 $npaData['npa_head'] = $currentTitle;
 $npaData['all_head_notes'] = array_unique($headNotes);

 $activeRevisions = getActiveRevisionsForDate($pdo, $npa_id, $viewDateSql);
 $exactRevisions = getExactRevisionsForDate($pdo, $npa_id, $viewDateSql);

 $itemsById = getItemTree($pdo, $npa_id, $viewDateSql, $npaData, true, $selectedRevisionNpaIds);
 $noNameIds = $npaData['no_name_ids'];
foreach ($itemsById as &$item) {
    if (isset($item['highlights'])) {
        $item['highlights'] = normalizeHighlights($item['highlights']);
    }
}
unset($item);

if (empty($itemsById)) {
    return -8;
}

 $ghostTables = [];
foreach ($itemsById as $id => $item) {
    if ($item['item_type'] === 'structured_table') {
        $hasNoName = empty($item['item_head']);
        if ($hasNoName) {
            $ghostTables[$id] = $item['parent_id'];
        }
    }
}
 $tocItems = [];
foreach ($itemsById as $id => $item) {
    if (isset($ghostTables[$id])) {
        continue;
    }
    $tocItem = $item;
    while (isset($ghostTables[$tocItem['parent_id']])) {
        $tocItem['parent_id'] = $ghostTables[$tocItem['parent_id']];
    }
    $tocItems[$id] = $tocItem;
}

 $selectedEditionRegDate = getSelectedEditionRegistrationDate(
    $pdo,
    $npa_id,
    $selectedRevisionNpaIds
);

 $noteSql = "
    SELECT n.target_type, n.target_id, n.note_text, n.valid_from, n.valid_to, n.source_item_id
    FROM npa_note_unified n
    WHERE n.npa_id = ?
      AND (
            (
                n.source_item_id IS NOT NULL
                AND (n.valid_to IS NULL OR n.valid_to >= ?)
                AND (
                    ? IS NOT NULL
                    AND EXISTS (
                        SELECT 1
                        FROM npa_item source_item
                        JOIN npa_revision_info source_revision
                          ON source_revision.revision_id = source_item.npa_id
                        WHERE source_item.id = n.source_item_id
                          AND source_revision.base_npa_id = n.npa_id
                          AND source_revision.revision_date_reg <= ?
                    )
                )
            )
            OR
            (
                n.source_item_id IS NULL
                AND (n.valid_from <= ? OR n.valid_from IS NULL)
                AND (n.valid_to IS NULL OR n.valid_to >= ?)
            )
      )
";
 $stmtNotes = $pdo->prepare($noteSql);
 $stmtNotes->execute([
    $npa_id,
    $viewDateSql,
    $selectedEditionRegDate,
    $selectedEditionRegDate,
    $viewDateSql,
    $viewDateSql
]);
 $allNotes = $stmtNotes->fetchAll();
 $npaNotes = [];
 $itemNotes = [];
foreach ($allNotes as $note) {
    if ($note['target_type'] === 'npa') {
        $npaNotes[] = $note;
    } elseif ($note['target_type'] === 'item' && !empty($note['target_id'])) {
        $itemNotes[$note['target_id']][] = $note;
    }
}
 $npaData['npa_notes'] = $npaNotes;
 $npaData['item_notes'] = $itemNotes;

 $newContent = '';
if ($docStatus['status'] !== 'active') {
    $statusClass = htmlspecialchars($docStatus['status']);
    $newContent .= '<div class="npa-doc-status-banner ' . $statusClass . '">'
                 . $docStatus['message']
                 . '</div>';
}
if ($npaData['npa_type'] === 'law') {
    $newContent .= '<p align="center"><b>ЗАКОН<br />ГОРОДА СЕВАСТОПОЛЯ</b></p>';
    if (!empty($npaData['all_head_notes'])) {
        $notesText = implode('; ', $npaData['all_head_notes']);
        $newContent .= '<div class="document-revision-note" style="margin: 0.5em 0;"><span class="revision-note">Наименование в редакции ' . $notesText . '</span></div>';
    }
    $newContent .= getHeadRevisionButtons($headRevisions, $npa_id, $pdo);
    if ($npaData['npa_head']) {
        $newContent .= '<p class="npa-doc-title" align="center"><b>' . htmlspecialchars($npaData['npa_head']) . '</b></p>';
    }
    if (!empty($npaNotes)) {
        $noteTexts = array_map(function($n) { return htmlspecialchars($n['note_text']); }, $npaNotes);
        $notesHtml = '<div class="npa-doc-notes">';
        $notesHtml .= '<div class="npa-doc-notes-header">';
        $notesHtml .= '<span class="npa-doc-notes-title">Примечания к документу</span>';
        $notesHtml .= '<span class="toggle-buttons-icon closed" data-target="npa-doc-notes-body"></span>';
        $notesHtml .= '</div>';
        $notesHtml .= '<div class="npa-doc-notes-body" id="npa-doc-notes-body" style="display:none;">';
        foreach ($noteTexts as $text) {
            $notesHtml .= '<div class="npa-doc-note">' . $text . '</div>';
        }
        $notesHtml .= '</div>';
        $notesHtml .= '</div>';
        $newContent .= $notesHtml;
    }
    if (!empty($npaData['not_valid_npa_id'])) {
        $stmtCancel = $pdo->prepare("SELECT npa_number FROM npa_base WHERE npa_id = ?");
        $stmtCancel->execute([$npaData['not_valid_npa_id']]);
        $cancelNpa = $stmtCancel->fetch();
        if ($cancelNpa) {
            $cancelNumber = $cancelNpa['npa_number'];
            $activeRevisions = array_filter($activeRevisions, function($rev) use ($cancelNumber) {
                return $rev['revision_number'] != $cancelNumber;
            });
        }
    }
    $docRevisionNote = getDocumentRevisionNote($activeRevisions, $npaData['npa_type'], $pdo, $npaData['npa_id']);
    if ($docRevisionNote) $newContent .= $docRevisionNote;
    $datePassed = $npaData['date_passed'] ?? '';
    $formattedPassed = formatRusDate($datePassed, $npaData['date_format']);
    $newContent .= '<p class="justifyleft npa-date-passed">Принят Законодательным Собранием<br />города Севастополя ' . $formattedPassed . '</p>';
} else {
    $newContent .= '<p align="center"><b>ЗАКОНОДАТЕЛЬНОЕ СОБРАНИЕ<br>ГОРОДА СЕВАСТОПОЛЯ</b></p>';
    if (!empty($npaData['term_number'])) {
        $newContent .= '<p align="center"><b>' . htmlspecialchars($npaData['term_number']) . ' созыва</b></p>';
    }
    $newContent .= '<p align="center"><b>П О С Т А Н О В Л Е Н И Е</b></p>';
    if (!empty($npaData['session_number'])) {
        $newContent .= '<p align="center"><b>' . htmlspecialchars($npaData['session_number']) . ' сессия</b></p>';
    }
    $datePassed = $npaData['date_passed'] ?? '';
    $formattedPassed = formatRusDate($datePassed, $npaData['date_format']);
    $nbsp = '&nbsp;';
    $newContent .= '<p align="center"><b>' . $formattedPassed . str_repeat($nbsp, 5) . '№' . $nbsp . htmlspecialchars($npaData['npa_number']) . str_repeat($nbsp, 5) . 'г. Севастополь</b></p>';
    if (!empty($npaData['all_head_notes'])) {
        $notesText = implode('; ', $npaData['all_head_notes']);
        $newContent .= '<div class="document-revision-note" style="margin: 0.5em 0;"><span class="revision-note">Наименование в редакции ' . $notesText . '</span></div>';
    }
    $newContent .= getHeadRevisionButtons($headRevisions, $npa_id, $pdo);
    if ($npaData['npa_head']) {
        $newContent .= '<p class="npa-doc-title" align="center"><b>' . htmlspecialchars($npaData['npa_head']) . '</b></p>';
    }
    if (!empty($npaNotes)) {
        $noteTexts = array_map(function($n) { return htmlspecialchars($n['note_text']); }, $npaNotes);
        $notesHtml = '<div class="npa-doc-notes">';
        $notesHtml .= '<div class="npa-doc-notes-header">';
        $notesHtml .= '<span class="npa-doc-notes-title">Примечания к документу</span>';
        $notesHtml .= '<span class="toggle-buttons-icon closed" data-target="npa-doc-notes-body"></span>';
        $notesHtml .= '</div>';
        $notesHtml .= '<div class="npa-doc-notes-body" id="npa-doc-notes-body" style="display:none;">';
        foreach ($noteTexts as $text) {
            $notesHtml .= '<div class="npa-doc-note">' . $text . '</div>';
        }
        $notesHtml .= '</div>';
        $notesHtml .= '</div>';
        $newContent .= $notesHtml;
    }
    $docRevisionNote = getDocumentRevisionNote($activeRevisions, 'regulation', $pdo, $npaData['npa_id']);
    if ($docRevisionNote) $newContent .= $docRevisionNote;
}

 $renderedItems = [];
 $rootItems = array_filter($itemsById, function($item) {
    return $item['parent_id'] === null && !in_array($item['item_type'], ['appendix', 'nested_appendix']);
});
usort($rootItems, function($a, $b) {
    if ($a['sort_order'] != $b['sort_order']) return $a['sort_order'] - $b['sort_order'];
    return $a['id'] - $b['id'];
});
foreach ($rootItems as $item) {
    $newContent .= renderElement($item, $itemsById, $pdo, $viewDateSql, $npaData, $renderedItems, false, $noNameIds);
}

if ($npaData['npa_type'] === 'regulation') {
    $dateForSignature = $npaData['date_passed'] ?? '';
    $signatureHtml = renderSignature($pdo, $npa_id, $dateForSignature, $npaData['npa_number'], $npaData['date_format'], false);
    $newContent .= '<div class="npa-doc-footer">' . $signatureHtml . '</div>';
}
if ($npaData['npa_type'] === 'law') {
    $dateForSignature = $npaData['date_signed'] ?? $npaData['date_passed'] ?? '';
    $signatureHtml = renderSignature($pdo, $npa_id, $dateForSignature, $npaData['npa_number'], $npaData['date_format'], true);
    $newContent .= '<div class="npa-doc-footer">' . $signatureHtml . '</div>';
}

 $appendixItems = array_filter($itemsById, function($item) {
    return $item['parent_id'] === null && in_array($item['item_type'], ['appendix', 'nested_appendix']);
});
usort($appendixItems, function($a, $b) {
    if ($a['sort_order'] != $b['sort_order']) return $a['sort_order'] - $b['sort_order'];
    return $a['id'] - $b['id'];
});
foreach ($appendixItems as $item) {
    $newContent .= renderElement($item, $itemsById, $pdo, $viewDateSql, $npaData, $renderedItems, false, $noNameIds);
    if ($npaData['npa_type'] === 'regulation') {
        $dateForSignature = $npaData['date_passed'] ?? '';
        $signatureHtml = renderSignature($pdo, $npa_id, $dateForSignature, $npaData['npa_number'], $npaData['date_format'], false);
        $newContent .= '<div class="npa-doc-footer">' . $signatureHtml . '</div>';
    }
}

 $itemsByIdForToc = getItemTree($pdo, $npa_id, $viewDateSql, $npaData, true, $selectedRevisionNpaIds);
 $treeHtml = '';
if (!empty($itemsByIdForToc)) {
    $typeName = ($npaData['npa_type'] ?? $npaBase['npa_type']) === 'regulation' ? 'Постановление' : 'Закон';
    
    $visibleTocItems = [];
    foreach ($tocItems as $id => $item) {
        if (isset($renderedItems[$id])) {
            $visibleTocItems[$id] = $item;
        }
    }
    
    $treeHtml = '<ul class="toc-list level-0 law-type">' .
              '<li class="toc-item level-0">' .
              '<span class="toc-link level-0">' . htmlspecialchars($typeName) . '</span>' .
              renderTocTree($visibleTocItems, null, 1, $npaData['pageUrl'], $viewDateSql, $noNameIds) .
              '</li></ul>';
}
 $selectorData = getRevisionSelectorOptions($pdo, $npa_id, $viewDateSql);
 $selectorOptions = $selectorData['options'];
 $selectedRevisionDate = $selectorData['selected_date'];
 $currentRevisionDate = $selectorData['current_date'];
 $selectHtml = '';
if (count($selectorOptions) > 1) {
    $optionsHtml = '';
    foreach ($selectorOptions as $opt) {
        $isSelected = ($opt['date_raw'] === $selectedRevisionDate);
        $isCurrent = !empty($opt['is_current']);
        $label = $opt['label'];

        if ($isCurrent) {
            $label .= $isExpiredDoc
                ? ' (последняя действовавшая редакция)'
                : ' (действующая)';
        }

        $optionsHtml .= '<option value="' . htmlspecialchars($opt['date_raw']) . '"'
                      . ' data-date-display="' . htmlspecialchars($opt['date_display']) . '"'
                      . ' data-is-original="' . (!empty($opt['is_original']) ? '1' : '0') . '"'
                      . ' data-is-current="' . ($isCurrent ? '1' : '0') . '"'
                      . ' data-is-last="' . ($isCurrent ? '1' : '0') . '"'
                      . ($isSelected ? ' selected' : '') . '>'
                      . htmlspecialchars($label) . '</option>';
    }

    $selectHtml = '<div class="npa-control-group npa-control-revision">' .
                  '<label class="npa-control-label" for="npa-revision-select">Редакция:</label>' .
                  '<select id="npa-revision-select" class="npa-revision-select" aria-label="Выбор редакции документа" onchange="npaChangeRevision(this.value)">' .
                  $optionsHtml . '</select></div>';
}

 $fullTypeText = ($npaData['npa_type'] ?? 'law') === 'law' ? 'Закон города Севастополя' : 'Постановление Законодательного Собрания города Севастополя';
 $revisionText = '';
if (!empty($exactRevisions)) {
    $typeWord = ($npaData['npa_type'] === 'law') ? 'Закона' : 'Постановления';
    $itemsText = [];
    foreach ($exactRevisions as $rev) {
        $dateReg = formatDateToRus($rev['revision_date_reg']);
        $revisionNumber = $rev['revision_number'];
        $revisionUrl = $rev['revision_url'] ?? '';
        if ($revisionUrl) {
            $itemsText[] = '<a href="' . htmlspecialchars($revisionUrl) . '" target="_blank">№ ' . $revisionNumber . ' от ' . $dateReg . '</a>';
        } else {
            $itemsText[] = '№ ' . $revisionNumber . ' от ' . $dateReg;
        }
    }
    if (!empty($itemsText)) {
        $revisionText = 'в редакции ' . $typeWord . ' города Севастополя ' . implode('; ', $itemsText);
    }
}

 $controlsHtml =
  '<div class="npa-doc-controls"'.
      ' data-npa-number="' . htmlspecialchars($npaData['npa_number']) . '"'.
      ' data-npa-type="' . htmlspecialchars($npaData['npa_type']) . '"'.
      ' data-npa-full-type="' . htmlspecialchars($fullTypeText) . '"'.
      ' data-npa-date="' . htmlspecialchars(($npaData['npa_type'] === 'law' ? ($npaData['date_signed'] ?? '') : ($npaData['date_passed'] ?? ''))) . '"'.
      ' data-npa-title="' . htmlspecialchars($npaData['npa_head'] ?? '') . '"'.
      ' data-npa-url="' . htmlspecialchars($npaData['npa_url'] ?? '') . '"'.
      ' data-download-filename="' . htmlspecialchars(generateFilename($npaData, $exactRevisions)) . '"'.
      ' role="toolbar" aria-label="Управление документом">' .
    '<div class="npa-doc-controls-inner">' .
      $selectHtml .
      '<div class="npa-control-group npa-control-download">' .
        '<div class="npa-download-item npa-download-rtf" onclick="npaDownloadRtf(); return false;">' .
            '<img src="' . MODX_SITE_URL . 'assets/images/icons/svg/rtf.svg" width="48" height="48" alt="" class="npa-download-icon">' .
            '<span class="npa-download-caption" id="rtf-caption">Действующая редакция</span>' .
        '</div>' .
        (!empty($z_publish) ?
          '<a href="' . MODX_SITE_URL . ltrim($z_publish, '/') . '" class="npa-download-item" target="_blank" title="Скачать первоначальную редакцию в PDF">' .
              '<img src="' . MODX_SITE_URL . 'assets/images/icons/svg/pdf.svg" width="48" height="48" alt="" class="npa-download-icon">' .
              '<span class="npa-download-caption">Первоначальная редакция</span>' .
          '</a>'
          : ''
        ) .
      '</div>' .
    '</div>' .
  '</div>';

 $tocOutput =
'<div id="modx-toc-button" class="modx-toc-button">Оглавление</div>' .
'<div id="modx-toc-panel" class="modx-toc-panel">' .
  '<div class="toc-panel-header">' .
    '<span class="toc-panel-title">' . htmlspecialchars($tocTitle) . '</span>' .
    '<button class="toc-panel-close">×</button>' .
  '</div>' .
  '<div class="toc-panel-content">' .
    '<div class="toc-list-container">' . $treeHtml . '</div>' .
  '</div>' .
'</div>';

 $wrapperClass = 'npa-doc-content-wrapper';
if ($docStatus['status'] !== 'active') {
    $wrapperClass .= ' is-' . htmlspecialchars($docStatus['status']);
}

 $output = $tocOutput . $controlsHtml . '<div class="' . $wrapperClass . '"><div class="npa-doc-content">' . $newContent . '</div></div>';
 $output .= '<div id="npa-modal-container" class="npa-modal-container" style="display:none;"></div>';

 $precomputedRevisions = [];
 $precomputedHistories = [];
 $precomputedCompares = [];

foreach ($headRevisions as $hr) {
    $revId = $hr['id'];
    $key = "head_{$revId}";
    $content = getHeadRevisionContent($pdo, $revId, $npa_id, $viewDateSql);
    if ($content) {
        $precomputedRevisions[$key] = [
            'success' => true,
            'html' => $content['html'],
            'valid_from' => formatDateToRus($content['valid_from']),
            'valid_to' => $content['valid_to'] ? formatDateToRus($content['valid_to']) : null,
            'modified_by_id' => $content['modified_by_id'],
            'is_current' => isRevisionCurrent($isExpiredDoc, $hr['valid_to'], $hr['valid_from'], $viewDateSql),
            'title' => null,
            'doc_note' => $content['source_info'] ?? ''
        ];
    }
}

foreach ($itemsById as $item) {
    $internalId = $item['internal_id'];
    $externalId = $item['item_id'];
    $selectedCurrentItemRev = getRevisionForSelectedEdition($pdo, $internalId, $viewDateSql, $selectedRevisionNpaIds);
    $selectedCurrentItemRevId = $selectedCurrentItemRev ? (int)$selectedCurrentItemRev['rev_id'] : 0;
    $allItemRevs = getItemRevisionTimelineForSelectedEdition($pdo, $internalId, $viewDateSql, $selectedRevisionNpaIds);
    $lastItemRevId = !empty($allItemRevs) ? end($allItemRevs)['rev_id'] : null;
    foreach ($allItemRevs as $rev) {
        $revId = $rev['rev_id'];
        $key = "item_{$externalId}_{$revId}";
        $content = getItemRevisionContent($pdo, $revId, $internalId, 0, null, true, false, $rev['valid_from']);
        if ($content) {
            $precomputedRevisions[$key] = [
                'success' => true,
                'html' => $content['html'],
                'valid_from' => formatDateToRus($content['valid_from']),
                'valid_to' => $content['valid_to'] ? formatDateToRus($content['valid_to']) : null,
                'modified_by_id' => $content['modified_by_id'],
                'mod_type' => $content['mod_type'],
                'is_current' => ((int)$rev['rev_id'] === $selectedCurrentItemRevId),
                'doc_note' => $content['source_info'] ?? ''
            ];
        }
    }
    $revisionsData = getItemRevisionTimelineForSelectedEdition($pdo, $internalId, $viewDateSql, $selectedRevisionNpaIds);
    if (!empty($revisionsData)) {
        $historyResult = ['success' => true, 'revisions' => []];
        $firstValidFrom = $revisionsData[0]['valid_from'];
        $elementPathForHistory = getElementHumanPath($internalId, $pdo);
        $lastIdx = count($revisionsData) - 1;
        foreach ($revisionsData as $idx => $rev) {
            $isLastRev = ($idx === $lastIdx);
            $revValidToDate = !empty($rev['valid_to']) ? substr($rev['valid_to'], 0, 10) : null;
            $isExpiredRev = $isLastRev && ($isExpiredDoc || ($revValidToDate !== null && $revValidToDate < $viewDateSql) || (!empty($rev['not_valid']) && $revValidToDate === null));
            $isOriginal = ($idx === 0) && !$isExpiredRev;
            $isCurrent = ((int)$rev['rev_id'] === $selectedCurrentItemRevId) && !$isExpiredRev;
            $expirySource = '';
            $expiryUrl = '';
            $npaUrl = '';
            if ($isExpiredRev) {
                $notValidId = $rev['not_valid'] ?? null;
                if ($notValidId && $notValidId !== 'base') {
                    $expiryNpaInfo = getNpaInfoByItemId($notValidId, $pdo);
                    if ($expiryNpaInfo) {
                        $typeName = ($expiryNpaInfo['npa_type'] === 'law')
                            ? 'Закона'
                            : 'Постановления Законодательного Собрания';
                        $dateForDisplay = formatRusDate($expiryNpaInfo['date_passed'], $expiryNpaInfo['date_format']);
                        $expirySource = $typeName . ' города Севастополя № ' . $expiryNpaInfo['npa_number'] . ' от ' . $dateForDisplay;
                        $expiryUrl = $expiryNpaInfo['npa_url'] ?? '';
                    }
                }
                $displayTitle = $expirySource ?: 'последняя действующая редакция';
                $sourceDecode = $expirySource ?: 'последняя действующая редакция';
                $npaUrl = $expiryUrl;
            } else {
                $displayTitle = $elementPathForHistory ?: 'Элемент';
                $sourceDecode = getShortNpaDescription($rev['modified_by_id'], $pdo, false);
            }
            $historyResult['revisions'][] = [
                'rev_id' => $rev['rev_id'],
                'valid_from' => formatDateToRus($rev['valid_from']),
                'valid_to' => $rev['valid_to'] ? formatDateToRus($rev['valid_to']) : null,
                'modified_by_id' => $rev['modified_by_id'],
                'mod_type' => $rev['mod_type'],
                'display_title' => $displayTitle,
                'source_decode' => $sourceDecode,
                'npa_url' => $npaUrl,
                'is_original' => $isOriginal,
                'is_current' => $isCurrent,
                'is_expired' => $isExpiredRev,
                'expiry_source' => $expirySource,
                'expiry_url' => $expiryUrl,
                'element_path' => $elementPathForHistory
            ];
        }
        $precomputedHistories[$externalId] = $historyResult;
    }
    $current = getRevisionForSelectedEdition($pdo, $internalId, $viewDateSql, $selectedRevisionNpaIds);
    if ($current) {
        $prev = getPreviousItemRevision($pdo, $internalId, $current['rev_id']);
        $prevHtml = '';
        $currHtml = '';
        if ($prev) {
            $prevAsOfDate = $current['valid_from'];
            $dtPrev = parseDate($prevAsOfDate);
            if ($dtPrev) {
                $dtPrev->modify('-1 day');
                $prevAsOfDate = $dtPrev->format('Y-m-d');
            } else {
                $prevAsOfDate = $viewDateSql;
            }
            $prevContent = getItemRevisionContent($pdo, $prev['rev_id'], $internalId, 0, null, false, true, $prevAsOfDate, false, false);
            // Текущую колонку сравнения рендерим на актуальную дату просмотра ($viewDateSql),
            // чтобы изменения, внесённые в дочерние элементы после последней редакции
            // родителя, тоже попадали в сравнение.
            $currContent = getItemRevisionContent($pdo, $current['rev_id'], $internalId, 0, null, false, true, $viewDateSql);
            $prevHtml = $prevContent ? ensureTableWrapperForComparison($prevContent['html'], $internalId, $pdo, $prevAsOfDate) : '';
            $currHtml = $currContent ? ensureTableWrapperForComparison($currContent['html'], $internalId, $pdo, $viewDateSql) : '';
        }
        $changingElements = [];
        $changerIds = [];
        if (!empty($current['modified_by_id']) && $current['modified_by_id'] !== 'base') {
            $changerIds = array_filter(array_map('trim', explode(',', $current['modified_by_id'])));
            foreach ($changerIds as $changerStr) {
                if ($changerStr === 'base') continue;
                $npaInfo = getNpaInfoByItemId($changerStr, $pdo);
                if (!$npaInfo) continue;
                $changerDate = $npaInfo['date_signed'] ?? $npaInfo['date_passed'] ?? $current['valid_from'];
                $changerNpaId = $npaInfo['npa_id'];
                $changerNpaType = $npaInfo['npa_type'];
                $changerHtml = getElementHtmlById($changerStr, $viewDateSql, $pdo, $changerNpaId, $changerNpaType);
                $note = getRevisionSourceNote($changerStr, $pdo, true);
                $changingElements[] = [
                    'note' => $note,
                    'html' => $changerHtml,
                    'date' => formatDateToRus($changerDate)
                ];
                        }
        }
        // Дочерние элементы, утратившие силу той же НПА, тоже показываем в «Изменения внесены:».
        $changingElements = array_merge($changingElements, collectExpiredChildChanges($pdo, $internalId, $viewDateSql, $changerIds, $selectedRevisionNpaIds));
        $highlightsForClient = null;
        if (!empty($current['highlights'])) {
            $decoded = json_decode($current['highlights'], true);
            if (is_array($decoded)) $highlightsForClient = $decoded;
        }
        $precomputedCompares[$externalId] = [
            'success' => true,
            'prev_valid_from' => $prev ? formatDateToRus($prev['valid_from']) : '',
            'current_valid_from' => formatDateToRus($current['valid_from']),
            'prev_html_raw' => $prevHtml,
            'current_html_raw' => $currHtml,
            'element_human_path' => getElementHumanPath($internalId, $pdo, 'genitive'),
            'changing_elements' => $changingElements,
            'highlights' => normalizeHighlights($highlightsForClient),
            'mod_type' => $current['mod_type']
        ];
    }
    $selectedCurrentHeadRev = getItemHeadRevisionForSelectedEdition($pdo, $internalId, $viewDateSql, $selectedRevisionNpaIds);
    $selectedCurrentHeadRevId = $selectedCurrentHeadRev ? (int)$selectedCurrentHeadRev['id'] : 0;
    $headHistoryAll = getItemHeadRevisionTimelineForSelectedEdition($pdo, $internalId, $viewDateSql, $selectedRevisionNpaIds);
    if (!empty($headHistoryAll)) {
        $historyResultHead = ['success' => true, 'revisions' => []];
        $stmtItemType = $pdo->prepare("SELECT item_type, item_number FROM npa_item WHERE id = ?");
        $stmtItemType->execute([$internalId]);
        $itemInfo = $stmtItemType->fetch();
        $itemType = $itemInfo ? $itemInfo['item_type'] : '';
        $itemNumber = $itemInfo ? ($itemInfo['item_number'] ?? '') : '';
        $lastHeadIdx = count($headHistoryAll) - 1;
        foreach ($headHistoryAll as $idx => $rev) {
            $dt = parseDate($rev['valid_from']);
            $validFromDate = $dt ? $dt->format('d.m.Y') : '';
            $isLastHeadRev = ($idx === $lastHeadIdx);
            $revValidToDate = !empty($rev['valid_to']) ? substr($rev['valid_to'], 0, 10) : null;
            $isExpiredHeadRev = $isLastHeadRev && ($isExpiredDoc || ($revValidToDate !== null && $revValidToDate < $viewDateSql) || (!empty($rev['not_valid']) && $revValidToDate === null));
            $isOriginal = ($idx === 0) && !$isExpiredHeadRev;
            $expirySource = '';
            $expiryUrl = '';
            if ($isExpiredHeadRev) {
                $notValidId = $rev['not_valid'] ?? null;
                $expirySources = '';
                $expiryUrls = '';
                if ($notValidId && $notValidId !== 'base') {
                    $expiryNpaInfo = getNpaInfoByItemId($notValidId, $pdo);
                    if ($expiryNpaInfo) {
                        $expiryTypeName = ($expiryNpaInfo['npa_type'] === 'law') ? 'Закона' : 'Постановления Законодательного Собрания';
                        $expiryDateForDisplay = formatRusDate($expiryNpaInfo['date_passed'], $expiryNpaInfo['date_format']);
                        $expirySources = $expiryTypeName . ' города Севастополя № ' . $expiryNpaInfo['npa_number'] . ' от ' . $expiryDateForDisplay;
                        $expiryUrls = $expiryNpaInfo['npa_url'] ?? '';
                    }
                }
                $displayTitle = $expirySources ?: 'последний действующий заголовок элемента';
                $sourceDecode = $expirySources ?: 'последний действующий заголовок элемента';
                $npaUrl = $expiryUrls;
                $expirySource = $expirySources;
                $expiryUrl = $expiryUrls;
                if ($itemType === 'structured_table') {
                    $tableHeadForPath = $rev['head_text'] ?? '';
                    if (!empty($tableHeadForPath)) {
                        $elementPath = 'таблицы ' . $itemNumber . ' (заголовок)';
                    } else {
                        $elementPath = '';
                    }
                } else {
                    $elementPath = getElementHumanPath($internalId, $pdo) . ' (заголовок)';
                }
            } elseif ($isOriginal) {
                $displayTitle = 'Исходный заголовок элемента';
                $sourceDecode = 'исходная редакция';
                $npaUrl = '';
                if ($itemType === 'structured_table') {
                    $tableHead = $rev['head_text'];
                    if (!empty($tableHead)) {
                        $elementPath = 'таблицы ' . $itemNumber . ' (заголовок)';
                    } else {
                        $elementPath = '';
                    }
                } else {
                    $elementPath = getElementHumanPath($internalId, $pdo) . ' (заголовок)';
                }
            } else {
                $changerElementId = (int)$rev['modified_by_id'];
                $npaInfo = getNpaInfoByItemId($changerElementId, $pdo);
                if ($npaInfo) {
                    $typeName = ($npaInfo['npa_type'] === 'law') ? 'Закона' : 'Постановления';
                    $dateForDisplay = formatRusDate($npaInfo['date_passed'], $npaInfo['date_format']);
                    $displayTitle = $typeName . ' города Севастополя № ' . $npaInfo['npa_number'] . ' от ' . $dateForDisplay;
                    $sourceDecode = getElementHumanPath($changerElementId, $pdo);
                    $npaUrl = $npaInfo['npa_url'] ?? '';
                } else {
                    $displayTitle = 'Неизвестный документ';
                    $sourceDecode = '';
                    $npaUrl = '';
                }
                if ($itemType === 'structured_table') {
                    $tableHead = $rev['head_text'];
                    if (!empty($tableHead)) {
                        $elementPath = 'таблицы ' . $itemNumber . ' (заголовок)';
                    } else {
                        $elementPath = '';
                    }
                } else {
                    $elementPath = getElementHumanPath($internalId, $pdo) . ' (заголовок)';
                }
            }
            $isCurrent = ((int)$rev['id'] === $selectedCurrentHeadRevId) && !$isExpiredHeadRev;
            $historyResultHead['revisions'][] = [
                'rev_id' => $rev['id'],
                'valid_from' => $validFromDate,
                'valid_to' => $rev['valid_to'] ? formatDateToRus($rev['valid_to']) : null,
                'source_decode' => $sourceDecode,
                'modified_by_id' => $rev['modified_by_id'],
                'display_title' => $displayTitle,
                'is_original' => $isOriginal,
                'is_current' => $isCurrent,
                'is_expired' => $isExpiredHeadRev,
                'expiry_source' => $expirySource,
                'expiry_url' => $expiryUrl,
                'element_path' => $elementPath,
                'npa_title' => $rev['head_text'],
                'npa_url' => $npaUrl
            ];
        }
        $precomputedHistories["head:{$externalId}"] = $historyResultHead;
        foreach ($headHistoryAll as $rev) {
            $revId = $rev['id'];
            $key = "head_item_{$externalId}_{$revId}";
            $content = getItemHeadRevisionContent($pdo, $revId, $internalId, $viewDateSql);
            if ($content) {
                $precomputedRevisions[$key] = [
                    'success' => true,
                    'html' => $content['html'],
                    'valid_from' => formatDateToRus($content['valid_from']),
                    'valid_to' => $content['valid_to'] ? formatDateToRus($content['valid_to']) : null,
                    'modified_by_id' => $content['modified_by_id'],
                    'is_current' => isRevisionCurrent($isExpiredDoc, $rev['valid_to'], $rev['valid_from'], $viewDateSql),
                    'doc_note' => $content['source_info'] ?? ''
                ];
            }
        }
    }
    $headCompare = getItemHeadCompareForSelectedEdition($pdo, $internalId, $viewDateSql, $selectedRevisionNpaIds);
    $precomputedCompares["head:{$externalId}"] = [
        'success' => true,
        'prev_valid_from' => $headCompare['prev_valid_from'],
        'current_valid_from' => $headCompare['current_valid_from'],
        'prev_html_raw' => $headCompare['prev_html_raw'],
        'current_html_raw' => $headCompare['current_html_raw'],
        'element_human_path' => 'заголовка ' . getElementHumanPath($internalId, $pdo, 'genitive'),
        'changing_elements' => $headCompare['changing_elements'] ?? [],
        'highlights' => normalizeHighlights($headCompare['highlights']),
        'mod_type' => $headCompare['mod_type']
    ];
}

 $stmtHeadAllRevisions = $pdo->prepare("
    SELECT * FROM npa_head_revision
    WHERE npa_id = ?
      AND valid_from <= ?
    ORDER BY valid_from ASC
");
 $stmtHeadAllRevisions->execute([$npa_id, $viewDateSql]);
 $allHeadRevisions = $stmtHeadAllRevisions->fetchAll();
 $headHistoryResult = ['success' => true, 'revisions' => []];
if (!empty($allHeadRevisions)) {
    $lastDocHeadIdx = count($allHeadRevisions) - 1;
    foreach ($allHeadRevisions as $idx => $rev) {
        $dt = parseDate($rev['valid_from']);
        $validFromDate = $dt ? $dt->format('d.m.Y') : '';
        $isLastDocHeadRev = ($idx === $lastDocHeadIdx);
        $revValidToDate = !empty($rev['valid_to']) ? substr($rev['valid_to'], 0, 10) : null;
        $isExpiredDocHeadRev = $isLastDocHeadRev && ($isExpiredDoc || ($revValidToDate !== null && $revValidToDate < $viewDateSql) || (!empty($rev['not_valid']) && $revValidToDate === null));
        $isOriginal = ($idx === 0) && !$isExpiredDocHeadRev;
        $expirySource = '';
        $expiryUrl = '';
        if ($isExpiredDocHeadRev) {
            $notValidId = $rev['not_valid'] ?? null;
            $expirySources = '';
            $expiryUrls = '';
            if ($notValidId && $notValidId !== 'base') {
                $expiryNpaInfo = getNpaInfoByItemId($notValidId, $pdo);
                if ($expiryNpaInfo) {
                    $expiryTypeName = ($expiryNpaInfo['npa_type'] === 'law') ? 'Закона' : 'Постановления Законодательного Собрания';
                    $expiryDateForDisplay = formatRusDate($expiryNpaInfo['date_passed'], $expiryNpaInfo['date_format']);
                    $expirySources = $expiryTypeName . ' города Севастополя № ' . $expiryNpaInfo['npa_number'] . ' от ' . $expiryDateForDisplay;
                    $expiryUrls = $expiryNpaInfo['npa_url'] ?? '';
                }
            }
            $displayTitle = $expirySources ?: 'последнее действующее наименование';
            $sourceDecode = $expirySources ?: 'последнее действующее наименование';
            $npaUrl = $expiryUrls;
            $expirySource = $expirySources;
            $expiryUrl = $expiryUrls;
        } elseif ($isOriginal) {
            $displayTitle = 'Исходное наименование';
            $sourceDecode = 'исходная редакция';
            $npaUrl = '';
        } else {
            $changerElementId = (int)$rev['modified_by_id'];
            $npaInfo = getNpaInfoByItemId($changerElementId, $pdo);
            if ($npaInfo) {
                $typeName = ($npaInfo['npa_type'] === 'law') ? 'Закона' : 'Постановления';
                $dateForDisplay = formatRusDate($npaInfo['date_passed'], $npaInfo['date_format']);
                $displayTitle = $typeName . ' города Севастополя № ' . $npaInfo['npa_number'] . ' от ' . $dateForDisplay;
                $sourceDecode = getElementHumanPath($changerElementId, $pdo);
                $npaUrl = $npaInfo['npa_url'] ?? '';
            } else {
                $displayTitle = 'Неизвестный документ';
                $sourceDecode = '';
                $npaUrl = '';
            }
        }
        $isCurrent = isRevisionCurrent($isExpiredDoc, $rev['valid_to'], $rev['valid_from'], $viewDateSql);
        $headHistoryResult['revisions'][] = [
            'rev_id' => $rev['id'],
            'valid_from' => $validFromDate,
            'valid_to' => $rev['valid_to'] ? formatDateToRus($rev['valid_to']) : null,
            'source_decode' => $sourceDecode,
            'modified_by_id' => $rev['modified_by_id'],
            'display_title' => $displayTitle,
            'is_original' => $isOriginal,
            'is_current' => $isCurrent,
            'is_expired' => $isExpiredDocHeadRev,
            'expiry_source' => $expirySource,
            'expiry_url' => $expiryUrl,
            'element_path' => 'наименование документа',
            'npa_title' => $rev['npa_title'],
            'npa_url' => $npaUrl
        ];
    }
}
 $precomputedHistories['head'] = $headHistoryResult;

 $headCompareData = getHeadCompareHtml($pdo, $npa_id, $viewDateSql);
 $highlightsArray = is_string($headCompareData['highlights'])
    ? json_decode($headCompareData['highlights'], true)
    : $headCompareData['highlights'];
if (!is_array($highlightsArray)) {
    $highlightsArray = ['current_edition' => ['addition' => [], 'difference' => []], 'previous_edition' => ['deletion' => [], 'difference' => []]];
}
 $precomputedCompares['head'] = [
    'success' => true,
    'prev_valid_from' => $headCompareData['prev_valid_from'],
    'current_valid_from' => $headCompareData['current_valid_from'],
    'prev_html_raw' => $headCompareData['prev_html_raw'],
    'current_html_raw' => $headCompareData['current_html_raw'],
    'element_human_path' => 'наименования документа',
    'changing_elements' => $headCompareData['changing_elements'] ?? [],
    'highlights' => $highlightsArray,
    'mod_type' => $headCompareData['mod_type']
];

foreach ($precomputedCompares as $key => &$compare) {
    if (isset($compare['highlights'])) {
        $compare['highlights'] = normalizeHighlights($compare['highlights']);
    } else {
        $compare['highlights'] = normalizeHighlights(null);
    }
}
unset($compare);

 $staticJsData = [
    'npa_id' => $npa_id,
    'view_date' => $viewDateSql,
    'selected_revision_npa_ids' => $selectedRevisionNpaIds,
    'head_revisions' => $headRevisions,
    'items' => $itemsById,
    'revisionContents' => $precomputedRevisions,
    'precomputed' => [
        'histories' => $precomputedHistories,
        'compares' => $precomputedCompares
    ],
    'no_name_ids' => $NPA_NO_NAME_IDS
];

 $json = json_encode($staticJsData, JSON_UNESCAPED_UNICODE | JSON_HEX_TAG);
 $json = str_replace(['[[', ']]'], ['[ [', '] ]'], $json);
 $output .= '<script id="npa-static-data" type="application/json">' . $json . '</script>';

file_put_contents($staticFile, $output);
return $output;
