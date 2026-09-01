<?php
/**
 * NPA-ZS | document/head.php — редакции наименования документа.
 *
 * Функции: getHeadRevisionsList, getHeadRevisionContent, getDocumentRevisionNote.
 * Списки для модалок истории наименования и примечание о редакции документа.
 * Источник: строки 2181-2288, 2421-2460, 2523-2544 монолита snippet.php.
 */

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

