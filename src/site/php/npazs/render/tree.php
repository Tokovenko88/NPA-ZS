<?php
/**
 * NPA-ZS | render/tree.php — дерево элементов и оглавление (TOC).
 *
 * Функции: renderTocTree, getItemTree.
 * getItemTree возвращает карту $itemsById — основа всех рендеров.
 * Рекурсия ограничена глубиной 20.
 * Источник: строки 2545-2579, 2915-3032 монолита snippet.php.
 */

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

    // В режиме сравнения includeExpired=true нужен, чтобы текущая колонка могла
    // показать дочерний элемент, утративший силу этой же редакцией. Но наличие
    // такой ревизии в npa_item ещё не означает, что элемент входил в тело
    // текущей редакции родителя: он мог быть удалён из body в более поздней
    // редакции, а сама ревизия ребёнка осталась незакрытой.
    //
    // Одновременно getRevisionForSelectedEdition может вернуть выбранную будущую
    // ревизию ребёнка и пометить её is_expired=false. Если её not_valid ссылается
    // на источник текущей редакции родителя, для diff это всё равно удалённый
    // элемент: он должен быть показан зачёркнутым.
    if ($includeExpired && !empty($itemsById)) {
        $bodyReferencedIds = [];
        $bodyReferenceSources = [];
        foreach ($itemsById as $parentData) {
            // Дочерние элементы должны определяться по body актуального
            // неутратившего силу родителя. Body старой/expired-редакции не даёт
            // права вернуть её детей в текущую колонку.
            if (!empty($parentData['is_expired'])) {
                continue;
            }
            $parentSources = [];
            if (!empty($parentData['item_id']) && $parentData['item_id'] !== 'base') {
                $parentSources[$parentData['item_id']] = true;
            }
            foreach (array_filter(array_map('trim', explode(',', (string)($parentData['modified_by_id'] ?? '')))) as $sourceId) {
                if ($sourceId === 'base') continue;

                // modified_by_id хранит внутренний числовой npa_item.id,
                // not_valid хранит стабильный строковый item_id.
                $parentSources[$sourceId] = true;
                if (ctype_digit($sourceId)) {
                    $stmtSource = $pdo->prepare(
                        'SELECT item_id FROM npa_item WHERE id = ? LIMIT 1'
                    );
                    $stmtSource->execute([(int)$sourceId]);
                    $sourceItemId = $stmtSource->fetchColumn();
                    if ($sourceItemId) {
                        $parentSources[(string)$sourceItemId] = true;
                    }
                }
            }
            foreach (($parentData['paragraphs'] ?? []) as $block) {
                if (($block['block_type'] ?? '') !== 'child_ref') {
                    continue;
                }
                $refId = isset($block['ref_item_internal_id']) ? (int)$block['ref_item_internal_id'] : 0;
                if ($refId > 0) {
                    $bodyReferencedIds[$refId] = true;
                    $bodyReferenceSources[$refId] = $parentSources;
                }
            }
        }

        foreach (array_keys($itemsById) as $internalId) {
            $itemData =& $itemsById[$internalId];
            $isBodyChild = isset($bodyReferencedIds[(int)$internalId]);
            if ($isBodyChild && !empty($bodyReferenceSources[$internalId]) && !empty($itemData['not_valid'])) {
                $notValidIds = array_filter(array_map('trim', explode(',', (string)$itemData['not_valid'])));
                foreach ($notValidIds as $notValidId) {
                    if (isset($bodyReferenceSources[$internalId][$notValidId])) {
                        $itemData['is_expired'] = true;
                        $itemData['expired_valid_to'] = $itemData['valid_to'];
                        break;
                    }
                }
            }
            if (!empty($itemData['is_expired']) && !$isBodyChild) {
                unset($itemsById[$internalId]);
            }
            unset($itemData);
        }
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
