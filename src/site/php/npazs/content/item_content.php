<?php
/**
 * NPA-ZS | content/item_content.php — HTML-контент элементов на дату.
 *
 * Функции: getParagraphsForRevision, getItemHeadRevisionContent,
 *          getItemRevisionContent.
 * getItemRevisionContent — главный (самый тяжёлый) рендерер содержимого элемента:
 * склейка абзацев, вложенные таблицы, префиксы/номера на дату, кнопки и примечания.
 * При $useEditionContext читает $GLOBALS['selected_revision_npa_ids'].
 * Источник: строки 847-853, 1124-1184, 1445-1660 монолита snippet.php.
 */

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
        $itemsById = getItemTree($pdo, $npa_id, $valid_from, null, false, $selRevIds);
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

