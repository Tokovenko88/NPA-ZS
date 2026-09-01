<?php
/**
 * NPA-ZS | ui/buttons.php — кнопки редакций и блок даты вступления в силу.
 *
 * Функции: getElementRevisionButtons, getHeadRevisionButtons,
 *          getItemHeadRevisionButtons, buildRevisionEffectiveDateBlock.
 * Источник: строки 854-1001, 1017-1038 монолита snippet.php.
 */

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

