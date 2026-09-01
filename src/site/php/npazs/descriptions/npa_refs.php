<?php
/**
 * NPA-ZS | descriptions/npa_refs.php — описания НПА-источников изменений.
 *
 * Функции: getNpaInfoByItemId, getShortNpaDescription, getElementHumanPath,
 *          getRevisionDocNoteImproved, getRevisionSourceNote, getIntroducingLawForDate.
 * По modified_by_id находит НПА, внёсший изменение, и строит человекочитаемые
 * описания («Закона города Севастополя № ... от ...») и пути элементов.
 * Источник: строки 639-846, 2772-2785 монолита snippet.php.
 */

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

