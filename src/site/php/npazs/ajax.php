<?php
/**
 * NPA-ZS | ajax.php — обработчик AJAX-запросов (fallback для предвычисленных данных).
 *
 * Активируется GET-параметром ajax_action. Клиентский npa-viewer.js обычно НЕ
 * обращается сюда: всё предвычислено в <script id="npa-static-data">.
 * Действия: get_item_history, get_compare, get_item_revision, get_prev_revision_plain.
 * Параметры: npa_id, item_id, rev_id, view_date, context.
 * Отвечает JSON и завершает выполнение (exit). Подключается из HtmlFromNpaZS.php
 * после bootstrap.php и db-блока (при сборке монолита разворачивается в этом же
 * месте); использует $pdo, $GLOBALS['selected_revision_npa_ids'] и все функции.
 * Источник: строки 3395-3842 монолита snippet.php (перенесены дословно).
 */


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
