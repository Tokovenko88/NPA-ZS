<?php
/**
 * NPA-ZS | render/element.php — рекурсивный рендер элементов документа.
 *
 * Функции: getInternalItemId, getElementHtmlById, renderElement, renderSubtree.
 * renderElement — центральный рендерер: типы элементов, утрата силы, таблицы,
 * кнопки/примечания; getElementHtmlById — HTML по внешнему id (ссылки из других НПА).
 * Глобальные: $itemsByIdGlobal (global), $NPA_NO_NAME_IDS (global).
 * Источник: строки 1934-1944, 2045-2180, 3033-3345 монолита snippet.php.
 */

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
                $refChild = $itemsById[$refInternalId];
                // При сравнении редакций утратившие силу дети не должны попадать
                // в текущую колонку — их тело больше не входит в ревизию структурного
                // элемента на выбранную дату.
                if ($forComparison && !empty($refChild['is_expired'])) {
                    // пропускаем
                } else {
                    $html .= renderElement($refChild, $itemsById, $pdo, $viewDate, $npaData, $renderedItems, $skipInteractive, $noNameIds, $forComparison);
                    $html .= '<div class="npa-para-sep"></div>';
                }
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
    // Если родитель устаревший и рендерится в режиме сравнения, его дети уже включены
    // в expired_content_html через getItemRevisionContent — не дублируем их здесь.
    $isExpired = !empty($item['is_expired']);
    if ($item['item_type'] !== 'structured_table' && !($isExpired && $forComparison)) {
        $children = array_filter($itemsById, function($child) use ($item, $key, $forComparison) {
            if (empty($child['parent_id'])) return false;
            if ((string)$child['parent_id'] !== (string)$item['id']
                && (string)$child['parent_id'] !== (string)$key) {
                return false;
            }
            // getItemTree оставляет в режиме сравнения только тех утративших
            // силу детей, на которых ссылается body актуальной редакции
            // родителя. Их необходимо передать в renderElement(): в режиме
            // comparison он выводит последнюю редакцию ребёнка зачёркнутой.
            // Иначе текущая колонка скрывает факт удаления, хотя он был
            // внесён выбранной редакцией НПА.
            return true;
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