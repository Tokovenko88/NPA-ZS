<?php
/**
 * NPA-ZS | history/lists.php — таймлайны редакций для модалок истории.
 *
 * Функции: getItemRevisionsList, getItemHeadRevisionsList.
 * Используются AJAX-действием get_item_history и предвычислением в точке входа.
 * Источник: строки 1789-1933, 2289-2420 монолита snippet.php.
 */

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
                $dateForDisplay = formatRusDate(npaRequisiteDate($npaInfo), $npaInfo['date_format']);
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
                    $dateForDisplay = formatRusDate(npaRequisiteDate($expiryNpaInfo), $expiryNpaInfo['date_format']);
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
                $dateForDisplay = formatRusDate(npaRequisiteDate($npaInfo), $npaInfo['date_format']);
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
                    $dateForDisplay = formatRusDate(npaRequisiteDate($expiryNpaInfo), $expiryNpaInfo['date_format']);
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

