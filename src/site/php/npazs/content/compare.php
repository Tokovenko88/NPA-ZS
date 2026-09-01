<?php
/**
 * NPA-ZS | content/compare.php — сравнение редакций (diff-колонки).
 *
 * Функции: getItemCompareForSelectedEdition, getItemHeadCompareForSelectedEdition,
 *          getItemHeadCompareHtml, ensureTableWrapperForComparison, getHeadCompareHtml.
 * Источник: строки 1185-1444, 2461-2522 монолита snippet.php.
 */

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
        // Ревизия ребёнка НА ДАТУ ПРОСМОТРА — чтобы not_valid был заполнен,
        // если ребёнок утратил силу к этой дате.
        $rev = getRevisionForDate($pdo, $childInternalId, $asOfDate);
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

