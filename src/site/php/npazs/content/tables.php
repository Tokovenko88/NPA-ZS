<?php
/**
 * NPA-ZS | content/tables.php — структурные таблицы (thead/tbody по абзацам).
 *
 * Функции: renderStructuredTable, getTableBorderFromContent, renderTableFragment,
 *          renderTableRowWithButtons, renderElementAsTableFragment.
 * Источник: строки 1661-1788 монолита snippet.php.
 */

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

