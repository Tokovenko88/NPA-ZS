<?php
/**
 * NPA-ZS | HtmlFromNpaZS.php — точка входа модульной версии и «рецепт сборки» монолита.
 *
 * На сайт этот файл НЕ попадает. Сайт получает ЕДИНЫЙ скрипт
 * src/site/php/snippet.php, собираемый из модулей этого каталога:
 *     make build-snippet   |   python data/work_tools/build_snippet.py
 * Собранный код вставляется в сниппет HtmlFromNpaZS в БД MODX Evolution.
 * Цепочка вызова на сайте: шаблон -> ConditionalNpaContent
 *   -> $modx->runSnippet('HtmlFromNpaZS', array('npa_id' => $parent)) -> [этот код].
 *
 * Сборка читает этот файл и заменяет каждый require на содержимое модуля
 * (без <?php и докблока); секции переносятся в монолит дословно и в том же
 * порядке. Блоки контекста/БД оставлены в этом файле (а не в include), потому
 * что содержат return -6/-2, завершающий ВЕСЬ сниппет.
 *
 * Возвращает HTML страницы НПА или код ошибки:
 *   -6 — не определён npa_id (нет параметра и TV);  -2 — нет соединения с БД;
 *   -7 — документ не найден в npa_base;             -1 — неизвестное ajax_action.
 * Кеш: попадание -> return file_get_contents(...); регенерация: GET
 * regenerate | force | nocache; дата просмотра: GET view_date.
 * Глобальное состояние: $structured_tree_cache, $NPA_NO_NAME_IDS, $itemsByIdGlobal,
 * $GLOBALS['selected_revision_npa_ids'], $GLOBALS['NPA_NO_NAME_IDS'].
 * Карта модулей и правила для агентов: README.md в этом каталоге.
 */

require_once __DIR__ . '/bootstrap.php';
require_once __DIR__ . '/helpers/dates.php';
require_once __DIR__ . '/helpers/text.php';
require_once __DIR__ . '/cache/static.php';
require_once __DIR__ . '/revisions/edition.php';
require_once __DIR__ . '/revisions/item.php';
require_once __DIR__ . '/revisions/head.php';
require_once __DIR__ . '/revisions/number_prefix.php';
require_once __DIR__ . '/document/status.php';
require_once __DIR__ . '/document/head.php';
require_once __DIR__ . '/descriptions/npa_refs.php';
require_once __DIR__ . '/ui/buttons.php';
require_once __DIR__ . '/ui/notes.php';
require_once __DIR__ . '/ui/selector.php';
require_once __DIR__ . '/ui/signature.php';
require_once __DIR__ . '/content/item_content.php';
require_once __DIR__ . '/content/tables.php';
require_once __DIR__ . '/content/compare.php';
require_once __DIR__ . '/render/tree.php';
require_once __DIR__ . '/render/element.php';
require_once __DIR__ . '/history/lists.php';

/* ================= Контекст запроса (MODX) ================= */

 $structured_tree_cache = [];
 $npa_id = isset($npa_id) ? (int)$npa_id : 0;

if (!$npa_id) {
    $tvValue = $modx->getTemplateVar('npa_id', '*', $modx->documentObject['id']);
    if ($tvValue && isset($tvValue['value'])) {
        $npa_id = (int)$tvValue['value'];
    }
}

if (!$npa_id) {
    return -6;
}

 $tvValue = $modx->getTemplateVar('z-publish','*',$modx->documentObject['id']);
 $z_publish = $tvValue['value'];
 $baseUrl = $modx->config['site_url'];
 $pdfUrl = $baseUrl . ltrim($z_publish, '/');
 $tocTitle = isset($tocTitle) ? $tocTitle : 'Оглавление документа';
 $NPA_NO_NAME_IDS = [];

/* ================= Дата просмотра и подключение к БД ================= */

 $rawDate = isset($_GET['view_date']) ? trim($_GET['view_date']) : null;
 $isCustomDate = ($rawDate !== null);

if ($isCustomDate) {
    $viewDateObj = parseDate($rawDate);
    if (!$viewDateObj) {
        $viewDateObj = new DateTime('today', new DateTimeZone('UTC'));
    }
} else {
    $viewDateObj = null;
}

try {
    $pdo = new PDO(
        "mysql:host=" . NPA_DB_HOST . ";dbname=" . NPA_DB_NAME . ";charset=" . NPA_DB_CHARSET,
        NPA_DB_USER,
        NPA_DB_PASS,
        [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            PDO::ATTR_EMULATE_PREPARES => false,
        ]
    );
} catch (PDOException $e) {
    return -2;
}

if ($viewDateObj === null) {
    $stmtMax = $pdo->prepare("
        SELECT MAX(valid_from) as max_date FROM (
            SELECT valid_from FROM npa_base WHERE npa_id = ?
            UNION
            SELECT revision_date_valid FROM npa_revision_info WHERE base_npa_id = ?
        ) AS dates
    ");
    $stmtMax->execute([$npa_id, $npa_id]);
    $maxRow = $stmtMax->fetch();
    $lastDate = $maxRow['max_date'] ?? null;
    if ($lastDate) {
        $viewDateObj = parseDate($lastDate);
    } else {
        $viewDateObj = new DateTime('today', new DateTimeZone('UTC'));
    }
}

 $viewDateSql = $viewDateObj->format('Y-m-d');


/* ================= AJAX-обработка (может завершить выполнение) ================= */
require __DIR__ . '/ajax.php';

/* ================= Сборка страницы НПА ================= */

 $stmt = $pdo->prepare("SELECT * FROM npa_base WHERE npa_id = ?");
 $stmt->execute([$npa_id]);
 $npaBase = $stmt->fetch();
if (!$npaBase) {
    return -7;
}

 $npaData = $npaBase;
 $npaData['pageUrl'] = $modx->makeUrl($modx->documentObject['id'], '', '', 'full');
 $npaData['npa_type'] = $npaBase['npa_type'];
 $npaData['no_name_raw'] = $npaBase['no_name'] ?? '';
 $npaData['no_name_ids'] = !empty($npaData['no_name_raw']) ? array_map('trim', explode(',', $npaData['no_name_raw'])) : [];
 $GLOBALS['NPA_NO_NAME_IDS'] = $npaData['no_name_ids'];

if ($viewDateObj === null) {
    $stmtMax = $pdo->prepare("
        SELECT MAX(valid_from) as max_date FROM (
            SELECT valid_from FROM npa_base WHERE npa_id = ?
            UNION
            SELECT revision_date_valid FROM npa_revision_info WHERE base_npa_id = ?
        ) AS dates
    ");
    $stmtMax->execute([$npa_id, $npa_id]);
    $maxRow = $stmtMax->fetch();
    $lastDate = $maxRow['max_date'] ?? null;
    if ($lastDate) {
        $viewDateObj = parseDate($lastDate);
    } else {
        $viewDateObj = new DateTime('today', new DateTimeZone('UTC'));
    }
}

 $viewDateSql = $viewDateObj->format('Y-m-d');
 $selectedRevisionNpaIds = getSelectedRevisionNpaIds($pdo, $npa_id, $viewDateSql);
 $GLOBALS['selected_revision_npa_ids'] = $selectedRevisionNpaIds;
 $npaData['selected_revision_npa_ids'] = $selectedRevisionNpaIds;

 $staticFile = getStaticFilePath($npaData, $viewDateSql, $npa_id);
 $forceRegenerate = isset($_GET['regenerate']) || isset($_GET['force']) || isset($_GET['nocache']);
if (file_exists($staticFile) && !$forceRegenerate) {
    return file_get_contents($staticFile);
}

if ($npaData['npa_type'] === 'law') {
    $stmt = $pdo->prepare("SELECT * FROM npa_law WHERE npa_id = ?");
    $stmt->execute([$npa_id]);
    $law = $stmt->fetch();
    if ($law) {
        $npaData = array_merge($npaData, $law);
    }
    if (!isset($npaData['date_passed'])) {
        $npaData['date_passed'] = $npaBase['date_passed'];
    }
} else {
    $stmt = $pdo->prepare("SELECT * FROM npa_regulation WHERE npa_id = ?");
    $stmt->execute([$npa_id]);
    $reg = $stmt->fetch();
    if ($reg) {
        $npaData = array_merge($npaData, $reg);
    }
    if (!isset($npaData['date_passed'])) {
        $npaData['date_passed'] = $npaBase['date_passed'];
    }
}

 $docStatus = getDocumentStatus($pdo, $npa_id, $viewDateSql);
 $isExpiredDoc = ($docStatus['status'] === 'expired');
 $npaData['doc_status'] = $docStatus;

 $stmtHead = $pdo->prepare("
    SELECT * FROM npa_head_revision
    WHERE npa_id = ? AND (valid_from <= ? OR valid_from IS NULL) AND (valid_to IS NULL OR valid_to >= ?)
    ORDER BY valid_from ASC
");
 $stmtHead->execute([$npa_id, $viewDateSql, $viewDateSql]);
 $headRevisions = $stmtHead->fetchAll();
foreach ($headRevisions as &$hr) {
    if (isset($hr['highlights'])) {
        $hr['highlights'] = normalizeHighlights($hr['highlights']);
    }
}
unset($hr);
 $headNotes = [];
 $currentTitle = '';
foreach ($headRevisions as $hr) {
    $currentTitle = $hr['npa_title'];
    if ($hr['modified_by_id'] && $hr['modified_by_id'] !== 'base') {
        $headNotes[] = getShortNpaDescription($hr['modified_by_id'], $pdo, true);
    }
}
 $npaData['npa_head'] = $currentTitle;
 $npaData['all_head_notes'] = array_unique($headNotes);

 $activeRevisions = getActiveRevisionsForDate($pdo, $npa_id, $viewDateSql);
 $exactRevisions = getExactRevisionsForDate($pdo, $npa_id, $viewDateSql);

 $itemsById = getItemTree($pdo, $npa_id, $viewDateSql, $npaData, true, $selectedRevisionNpaIds);
 $noNameIds = $npaData['no_name_ids'];
foreach ($itemsById as &$item) {
    if (isset($item['highlights'])) {
        $item['highlights'] = normalizeHighlights($item['highlights']);
    }
}
unset($item);

if (empty($itemsById)) {
    return -8;
}

 $ghostTables = [];
foreach ($itemsById as $id => $item) {
    if ($item['item_type'] === 'structured_table') {
        $hasNoName = empty($item['item_head']);
        if ($hasNoName) {
            $ghostTables[$id] = $item['parent_id'];
        }
    }
}
 $tocItems = [];
foreach ($itemsById as $id => $item) {
    if (isset($ghostTables[$id])) {
        continue;
    }
    $tocItem = $item;
    while (isset($ghostTables[$tocItem['parent_id']])) {
        $tocItem['parent_id'] = $ghostTables[$tocItem['parent_id']];
    }
    $tocItems[$id] = $tocItem;
}

 $selectedEditionRegDate = getSelectedEditionRegistrationDate(
    $pdo,
    $npa_id,
    $selectedRevisionNpaIds
);

 $noteSql = "
    SELECT n.target_type, n.target_id, n.note_text, n.valid_from, n.valid_to, n.source_item_id
    FROM npa_note_unified n
    WHERE n.npa_id = ?
      AND (
            (
                n.source_item_id IS NOT NULL
                AND (n.valid_to IS NULL OR n.valid_to >= ?)
                AND (
                    ? IS NOT NULL
                    AND EXISTS (
                        SELECT 1
                        FROM npa_item source_item
                        JOIN npa_revision_info source_revision
                          ON source_revision.revision_id = source_item.npa_id
                        WHERE source_item.id = n.source_item_id
                          AND source_revision.base_npa_id = n.npa_id
                          AND source_revision.revision_date_reg <= ?
                    )
                )
            )
            OR
            (
                n.source_item_id IS NULL
                AND (n.valid_from <= ? OR n.valid_from IS NULL)
                AND (n.valid_to IS NULL OR n.valid_to >= ?)
            )
      )
";
 $stmtNotes = $pdo->prepare($noteSql);
 $stmtNotes->execute([
    $npa_id,
    $viewDateSql,
    $selectedEditionRegDate,
    $selectedEditionRegDate,
    $viewDateSql,
    $viewDateSql
]);
 $allNotes = $stmtNotes->fetchAll();
 $npaNotes = [];
 $itemNotes = [];
foreach ($allNotes as $note) {
    if ($note['target_type'] === 'npa') {
        $npaNotes[] = $note;
    } elseif ($note['target_type'] === 'item' && !empty($note['target_id'])) {
        $itemNotes[$note['target_id']][] = $note;
    }
}
 $npaData['npa_notes'] = $npaNotes;
 $npaData['item_notes'] = $itemNotes;

 $newContent = '';
if ($docStatus['status'] !== 'active') {
    $statusClass = htmlspecialchars($docStatus['status']);
    $newContent .= '<div class="npa-doc-status-banner ' . $statusClass . '">'
                 . $docStatus['message']
                 . '</div>';
}
if ($npaData['npa_type'] === 'law') {
    $newContent .= '<p align="center"><b>ЗАКОН<br />ГОРОДА СЕВАСТОПОЛЯ</b></p>';
    if (!empty($npaData['all_head_notes'])) {
        $notesText = implode('; ', $npaData['all_head_notes']);
        $newContent .= '<div class="document-revision-note" style="margin: 0.5em 0;"><span class="revision-note">Наименование в редакции ' . $notesText . '</span></div>';
    }
    $newContent .= getHeadRevisionButtons($headRevisions, $npa_id, $pdo);
    if ($npaData['npa_head']) {
        $newContent .= '<p class="npa-doc-title" align="center"><b>' . htmlspecialchars($npaData['npa_head']) . '</b></p>';
    }
    if (!empty($npaNotes)) {
        $noteTexts = array_map(function($n) { return htmlspecialchars($n['note_text']); }, $npaNotes);
        $notesHtml = '<div class="npa-doc-notes">';
        $notesHtml .= '<div class="npa-doc-notes-header">';
        $notesHtml .= '<span class="npa-doc-notes-title">Примечания к документу</span>';
        $notesHtml .= '<span class="toggle-buttons-icon closed" data-target="npa-doc-notes-body"></span>';
        $notesHtml .= '</div>';
        $notesHtml .= '<div class="npa-doc-notes-body" id="npa-doc-notes-body" style="display:none;">';
        foreach ($noteTexts as $text) {
            $notesHtml .= '<div class="npa-doc-note">' . $text . '</div>';
        }
        $notesHtml .= '</div>';
        $notesHtml .= '</div>';
        $newContent .= $notesHtml;
    }
    if (!empty($npaData['not_valid_npa_id'])) {
        $stmtCancel = $pdo->prepare("SELECT npa_number FROM npa_base WHERE npa_id = ?");
        $stmtCancel->execute([$npaData['not_valid_npa_id']]);
        $cancelNpa = $stmtCancel->fetch();
        if ($cancelNpa) {
            $cancelNumber = $cancelNpa['npa_number'];
            $activeRevisions = array_filter($activeRevisions, function($rev) use ($cancelNumber) {
                return $rev['revision_number'] != $cancelNumber;
            });
        }
    }
    $docRevisionNote = getDocumentRevisionNote($activeRevisions, $npaData['npa_type'], $pdo, $npaData['npa_id']);
    if ($docRevisionNote) $newContent .= $docRevisionNote;
    $datePassed = $npaData['date_passed'] ?? '';
    $formattedPassed = formatRusDate($datePassed, $npaData['date_format']);
    $newContent .= '<p class="justifyleft npa-date-passed">Принят Законодательным Собранием<br />города Севастополя ' . $formattedPassed . '</p>';
} else {
    $newContent .= '<p align="center"><b>ЗАКОНОДАТЕЛЬНОЕ СОБРАНИЕ<br>ГОРОДА СЕВАСТОПОЛЯ</b></p>';
    if (!empty($npaData['term_number'])) {
        $newContent .= '<p align="center"><b>' . htmlspecialchars($npaData['term_number']) . ' созыва</b></p>';
    }
    $newContent .= '<p align="center"><b>П О С Т А Н О В Л Е Н И Е</b></p>';
    if (!empty($npaData['session_number'])) {
        $newContent .= '<p align="center"><b>' . htmlspecialchars($npaData['session_number']) . ' сессия</b></p>';
    }
    $datePassed = $npaData['date_passed'] ?? '';
    $formattedPassed = formatRusDate($datePassed, $npaData['date_format']);
    $nbsp = '&nbsp;';
    $newContent .= '<p align="center"><b>' . $formattedPassed . str_repeat($nbsp, 5) . '№' . $nbsp . htmlspecialchars($npaData['npa_number']) . str_repeat($nbsp, 5) . 'г. Севастополь</b></p>';
    if (!empty($npaData['all_head_notes'])) {
        $notesText = implode('; ', $npaData['all_head_notes']);
        $newContent .= '<div class="document-revision-note" style="margin: 0.5em 0;"><span class="revision-note">Наименование в редакции ' . $notesText . '</span></div>';
    }
    $newContent .= getHeadRevisionButtons($headRevisions, $npa_id, $pdo);
    if ($npaData['npa_head']) {
        $newContent .= '<p class="npa-doc-title" align="center"><b>' . htmlspecialchars($npaData['npa_head']) . '</b></p>';
    }
    if (!empty($npaNotes)) {
        $noteTexts = array_map(function($n) { return htmlspecialchars($n['note_text']); }, $npaNotes);
        $notesHtml = '<div class="npa-doc-notes">';
        $notesHtml .= '<div class="npa-doc-notes-header">';
        $notesHtml .= '<span class="npa-doc-notes-title">Примечания к документу</span>';
        $notesHtml .= '<span class="toggle-buttons-icon closed" data-target="npa-doc-notes-body"></span>';
        $notesHtml .= '</div>';
        $notesHtml .= '<div class="npa-doc-notes-body" id="npa-doc-notes-body" style="display:none;">';
        foreach ($noteTexts as $text) {
            $notesHtml .= '<div class="npa-doc-note">' . $text . '</div>';
        }
        $notesHtml .= '</div>';
        $notesHtml .= '</div>';
        $newContent .= $notesHtml;
    }
    $docRevisionNote = getDocumentRevisionNote($activeRevisions, 'regulation', $pdo, $npaData['npa_id']);
    if ($docRevisionNote) $newContent .= $docRevisionNote;
}

 $renderedItems = [];
 $rootItems = array_filter($itemsById, function($item) {
    return $item['parent_id'] === null && !in_array($item['item_type'], ['appendix', 'nested_appendix']);
});
usort($rootItems, function($a, $b) {
    if ($a['sort_order'] != $b['sort_order']) return $a['sort_order'] - $b['sort_order'];
    return $a['id'] - $b['id'];
});
foreach ($rootItems as $item) {
    $newContent .= renderElement($item, $itemsById, $pdo, $viewDateSql, $npaData, $renderedItems, false, $noNameIds);
}

if ($npaData['npa_type'] === 'regulation') {
    $dateForSignature = $npaData['date_passed'] ?? '';
    $signatureHtml = renderSignature($pdo, $npa_id, $dateForSignature, $npaData['npa_number'], $npaData['date_format'], false);
    $newContent .= '<div class="npa-doc-footer">' . $signatureHtml . '</div>';
}
if ($npaData['npa_type'] === 'law') {
    $dateForSignature = $npaData['date_signed'] ?? $npaData['date_passed'] ?? '';
    $signatureHtml = renderSignature($pdo, $npa_id, $dateForSignature, $npaData['npa_number'], $npaData['date_format'], true);
    $newContent .= '<div class="npa-doc-footer">' . $signatureHtml . '</div>';
}

 $appendixItems = array_filter($itemsById, function($item) {
    return $item['parent_id'] === null && in_array($item['item_type'], ['appendix', 'nested_appendix']);
});
usort($appendixItems, function($a, $b) {
    if ($a['sort_order'] != $b['sort_order']) return $a['sort_order'] - $b['sort_order'];
    return $a['id'] - $b['id'];
});
foreach ($appendixItems as $item) {
    $newContent .= renderElement($item, $itemsById, $pdo, $viewDateSql, $npaData, $renderedItems, false, $noNameIds);
    if ($npaData['npa_type'] === 'regulation') {
        $dateForSignature = $npaData['date_passed'] ?? '';
        $signatureHtml = renderSignature($pdo, $npa_id, $dateForSignature, $npaData['npa_number'], $npaData['date_format'], false);
        $newContent .= '<div class="npa-doc-footer">' . $signatureHtml . '</div>';
    }
}

 $itemsByIdForToc = getItemTree($pdo, $npa_id, $viewDateSql, $npaData, true, $selectedRevisionNpaIds);
 $treeHtml = '';
if (!empty($itemsByIdForToc)) {
    $typeName = ($npaData['npa_type'] ?? $npaBase['npa_type']) === 'regulation' ? 'Постановление' : 'Закон';
    
    $visibleTocItems = [];
    foreach ($tocItems as $id => $item) {
        if (isset($renderedItems[$id])) {
            $visibleTocItems[$id] = $item;
        }
    }
    
    $treeHtml = '<ul class="toc-list level-0 law-type">' .
              '<li class="toc-item level-0">' .
              '<span class="toc-link level-0">' . htmlspecialchars($typeName) . '</span>' .
              renderTocTree($visibleTocItems, null, 1, $npaData['pageUrl'], $viewDateSql, $noNameIds) .
              '</li></ul>';
}
 $selectorData = getRevisionSelectorOptions($pdo, $npa_id, $viewDateSql);
 $selectorOptions = $selectorData['options'];
 $selectedRevisionDate = $selectorData['selected_date'];
 $currentRevisionDate = $selectorData['current_date'];
 $selectHtml = '';
if (count($selectorOptions) > 1) {
    $optionsHtml = '';
    foreach ($selectorOptions as $opt) {
        $isSelected = ($opt['date_raw'] === $selectedRevisionDate);
        $isCurrent = !empty($opt['is_current']);
        $label = $opt['label'];

        if ($isCurrent) {
            $label .= $isExpiredDoc
                ? ' (последняя действовавшая редакция)'
                : ' (действующая)';
        }

        $optionsHtml .= '<option value="' . htmlspecialchars($opt['date_raw']) . '"'
                      . ' data-date-display="' . htmlspecialchars($opt['date_display']) . '"'
                      . ' data-is-original="' . (!empty($opt['is_original']) ? '1' : '0') . '"'
                      . ' data-is-current="' . ($isCurrent ? '1' : '0') . '"'
                      . ' data-is-last="' . ($isCurrent ? '1' : '0') . '"'
                      . ($isSelected ? ' selected' : '') . '>'
                      . htmlspecialchars($label) . '</option>';
    }

    $selectHtml = '<div class="npa-control-group npa-control-revision">' .
                  '<label class="npa-control-label" for="npa-revision-select">Редакция:</label>' .
                  '<select id="npa-revision-select" class="npa-revision-select" aria-label="Выбор редакции документа" onchange="npaChangeRevision(this.value)">' .
                  $optionsHtml . '</select></div>';
}

 $fullTypeText = ($npaData['npa_type'] ?? 'law') === 'law' ? 'Закон города Севастополя' : 'Постановление Законодательного Собрания города Севастополя';
 $revisionText = '';
if (!empty($exactRevisions)) {
    $typeWord = ($npaData['npa_type'] === 'law') ? 'Закона' : 'Постановления';
    $itemsText = [];
    foreach ($exactRevisions as $rev) {
        $dateReg = formatDateToRus($rev['revision_date_reg']);
        $revisionNumber = $rev['revision_number'];
        $revisionUrl = $rev['revision_url'] ?? '';
        if ($revisionUrl) {
            $itemsText[] = '<a href="' . htmlspecialchars($revisionUrl) . '" target="_blank">№ ' . $revisionNumber . ' от ' . $dateReg . '</a>';
        } else {
            $itemsText[] = '№ ' . $revisionNumber . ' от ' . $dateReg;
        }
    }
    if (!empty($itemsText)) {
        $revisionText = 'в редакции ' . $typeWord . ' города Севастополя ' . implode('; ', $itemsText);
    }
}

 $controlsHtml =
  '<div class="npa-doc-controls"'.
      ' data-npa-number="' . htmlspecialchars($npaData['npa_number']) . '"'.
      ' data-npa-type="' . htmlspecialchars($npaData['npa_type']) . '"'.
      ' data-npa-full-type="' . htmlspecialchars($fullTypeText) . '"'.
      ' data-npa-date="' . htmlspecialchars(($npaData['npa_type'] === 'law' ? ($npaData['date_signed'] ?? '') : ($npaData['date_passed'] ?? ''))) . '"'.
      ' data-npa-title="' . htmlspecialchars($npaData['npa_head'] ?? '') . '"'.
      ' data-npa-url="' . htmlspecialchars($npaData['npa_url'] ?? '') . '"'.
      ' data-download-filename="' . htmlspecialchars(generateFilename($npaData, $exactRevisions)) . '"'.
      ' role="toolbar" aria-label="Управление документом">' .
    '<div class="npa-doc-controls-inner">' .
      $selectHtml .
      '<div class="npa-control-group npa-control-download">' .
        '<div class="npa-download-item npa-download-rtf" onclick="npaDownloadRtf(); return false;">' .
            '<img src="' . MODX_SITE_URL . 'assets/images/icons/svg/rtf.svg" width="48" height="48" alt="" class="npa-download-icon">' .
            '<span class="npa-download-caption" id="rtf-caption">Действующая редакция</span>' .
        '</div>' .
        (!empty($z_publish) ?
          '<a href="' . MODX_SITE_URL . ltrim($z_publish, '/') . '" class="npa-download-item" target="_blank" title="Скачать первоначальную редакцию в PDF">' .
              '<img src="' . MODX_SITE_URL . 'assets/images/icons/svg/pdf.svg" width="48" height="48" alt="" class="npa-download-icon">' .
              '<span class="npa-download-caption">Первоначальная редакция</span>' .
          '</a>'
          : ''
        ) .
      '</div>' .
    '</div>' .
  '</div>';

 $tocOutput =
'<div id="modx-toc-button" class="modx-toc-button">Оглавление</div>' .
'<div id="modx-toc-panel" class="modx-toc-panel">' .
  '<div class="toc-panel-header">' .
    '<span class="toc-panel-title">' . htmlspecialchars($tocTitle) . '</span>' .
    '<button class="toc-panel-close">×</button>' .
  '</div>' .
  '<div class="toc-panel-content">' .
    '<div class="toc-list-container">' . $treeHtml . '</div>' .
  '</div>' .
'</div>';

 $wrapperClass = 'npa-doc-content-wrapper';
if ($docStatus['status'] !== 'active') {
    $wrapperClass .= ' is-' . htmlspecialchars($docStatus['status']);
}

 $output = $tocOutput . $controlsHtml . '<div class="' . $wrapperClass . '"><div class="npa-doc-content">' . $newContent . '</div></div>';
 $output .= '<div id="npa-modal-container" class="npa-modal-container" style="display:none;"></div>';

 $precomputedRevisions = [];
 $precomputedHistories = [];
 $precomputedCompares = [];

foreach ($headRevisions as $hr) {
    $revId = $hr['id'];
    $key = "head_{$revId}";
    $content = getHeadRevisionContent($pdo, $revId, $npa_id, $viewDateSql);
    if ($content) {
        $precomputedRevisions[$key] = [
            'success' => true,
            'html' => $content['html'],
            'valid_from' => formatDateToRus($content['valid_from']),
            'valid_to' => $content['valid_to'] ? formatDateToRus($content['valid_to']) : null,
            'modified_by_id' => $content['modified_by_id'],
            'is_current' => isRevisionCurrent($isExpiredDoc, $hr['valid_to'], $hr['valid_from'], $viewDateSql),
            'title' => null,
            'doc_note' => $content['source_info'] ?? ''
        ];
    }
}

foreach ($itemsById as $item) {
    $internalId = $item['internal_id'];
    $externalId = $item['item_id'];
    $selectedCurrentItemRev = getRevisionForSelectedEdition($pdo, $internalId, $viewDateSql, $selectedRevisionNpaIds);
    $selectedCurrentItemRevId = $selectedCurrentItemRev ? (int)$selectedCurrentItemRev['rev_id'] : 0;
    $allItemRevs = getItemRevisionTimelineForSelectedEdition($pdo, $internalId, $viewDateSql, $selectedRevisionNpaIds);
    $lastItemRevId = !empty($allItemRevs) ? end($allItemRevs)['rev_id'] : null;
    foreach ($allItemRevs as $rev) {
        $revId = $rev['rev_id'];
        $key = "item_{$externalId}_{$revId}";
        $content = getItemRevisionContent($pdo, $revId, $internalId, 0, null, true, false, $rev['valid_from']);
        if ($content) {
            $precomputedRevisions[$key] = [
                'success' => true,
                'html' => $content['html'],
                'valid_from' => formatDateToRus($content['valid_from']),
                'valid_to' => $content['valid_to'] ? formatDateToRus($content['valid_to']) : null,
                'modified_by_id' => $content['modified_by_id'],
                'mod_type' => $content['mod_type'],
                'is_current' => ((int)$rev['rev_id'] === $selectedCurrentItemRevId),
                'doc_note' => $content['source_info'] ?? ''
            ];
        }
    }
    $revisionsData = getItemRevisionTimelineForSelectedEdition($pdo, $internalId, $viewDateSql, $selectedRevisionNpaIds);
    if (!empty($revisionsData)) {
        $historyResult = ['success' => true, 'revisions' => []];
        $firstValidFrom = $revisionsData[0]['valid_from'];
        $elementPathForHistory = getElementHumanPath($internalId, $pdo);
        $lastIdx = count($revisionsData) - 1;
        foreach ($revisionsData as $idx => $rev) {
            $isLastRev = ($idx === $lastIdx);
            $revValidToDate = !empty($rev['valid_to']) ? substr($rev['valid_to'], 0, 10) : null;
            $isExpiredRev = $isLastRev && ($isExpiredDoc || ($revValidToDate !== null && $revValidToDate < $viewDateSql) || (!empty($rev['not_valid']) && $revValidToDate === null));
            $isOriginal = ($idx === 0) && !$isExpiredRev;
            $isCurrent = ((int)$rev['rev_id'] === $selectedCurrentItemRevId) && !$isExpiredRev;
            $expirySource = '';
            $expiryUrl = '';
            $npaUrl = '';
            if ($isExpiredRev) {
                $notValidId = $rev['not_valid'] ?? null;
                if ($notValidId && $notValidId !== 'base') {
                    $expiryNpaInfo = getNpaInfoByItemId($notValidId, $pdo);
                    if ($expiryNpaInfo) {
                        $typeName = ($expiryNpaInfo['npa_type'] === 'law')
                            ? 'Закона'
                            : 'Постановления Законодательного Собрания';
                        $dateForDisplay = formatRusDate($expiryNpaInfo['date_passed'], $expiryNpaInfo['date_format']);
                        $expirySource = $typeName . ' города Севастополя № ' . $expiryNpaInfo['npa_number'] . ' от ' . $dateForDisplay;
                        $expiryUrl = $expiryNpaInfo['npa_url'] ?? '';
                    }
                }
                $displayTitle = $expirySource ?: 'последняя действующая редакция';
                $sourceDecode = $expirySource ?: 'последняя действующая редакция';
                $npaUrl = $expiryUrl;
            } else {
                $displayTitle = $elementPathForHistory ?: 'Элемент';
                $sourceDecode = getShortNpaDescription($rev['modified_by_id'], $pdo, false);
            }
            $historyResult['revisions'][] = [
                'rev_id' => $rev['rev_id'],
                'valid_from' => formatDateToRus($rev['valid_from']),
                'valid_to' => $rev['valid_to'] ? formatDateToRus($rev['valid_to']) : null,
                'modified_by_id' => $rev['modified_by_id'],
                'mod_type' => $rev['mod_type'],
                'display_title' => $displayTitle,
                'source_decode' => $sourceDecode,
                'npa_url' => $npaUrl,
                'is_original' => $isOriginal,
                'is_current' => $isCurrent,
                'is_expired' => $isExpiredRev,
                'expiry_source' => $expirySource,
                'expiry_url' => $expiryUrl,
                'element_path' => $elementPathForHistory
            ];
        }
        $precomputedHistories[$externalId] = $historyResult;
    }
    $current = getRevisionForSelectedEdition($pdo, $internalId, $viewDateSql, $selectedRevisionNpaIds);
    if ($current) {
        $prev = getPreviousItemRevision($pdo, $internalId, $current['rev_id']);
        $prevHtml = '';
        $currHtml = '';
        if ($prev) {
            $prevAsOfDate = $current['valid_from'];
            $dtPrev = parseDate($prevAsOfDate);
            if ($dtPrev) {
                $dtPrev->modify('-1 day');
                $prevAsOfDate = $dtPrev->format('Y-m-d');
            } else {
                $prevAsOfDate = $viewDateSql;
            }
            $prevContent = getItemRevisionContent($pdo, $prev['rev_id'], $internalId, 0, null, false, true, $prevAsOfDate, false, false);
            // Текущую колонку сравнения рендерим на актуальную дату просмотра ($viewDateSql),
            // чтобы изменения, внесённые в дочерние элементы после последней редакции
            // родителя, тоже попадали в сравнение.
            $currContent = getItemRevisionContent($pdo, $current['rev_id'], $internalId, 0, null, false, true, $viewDateSql);
            $prevHtml = $prevContent ? ensureTableWrapperForComparison($prevContent['html'], $internalId, $pdo, $prevAsOfDate) : '';
            $currHtml = $currContent ? ensureTableWrapperForComparison($currContent['html'], $internalId, $pdo, $viewDateSql) : '';
        }
        $changingElements = [];
        $changerIds = [];
        if (!empty($current['modified_by_id']) && $current['modified_by_id'] !== 'base') {
            $changerIds = array_filter(array_map('trim', explode(',', $current['modified_by_id'])));
            foreach ($changerIds as $changerStr) {
                if ($changerStr === 'base') continue;
                $npaInfo = getNpaInfoByItemId($changerStr, $pdo);
                if (!$npaInfo) continue;
                $changerDate = $npaInfo['date_signed'] ?? $npaInfo['date_passed'] ?? $current['valid_from'];
                $changerNpaId = $npaInfo['npa_id'];
                $changerNpaType = $npaInfo['npa_type'];
                $changerHtml = getElementHtmlById($changerStr, $viewDateSql, $pdo, $changerNpaId, $changerNpaType);
                $note = getRevisionSourceNote($changerStr, $pdo, true);
                $changingElements[] = [
                    'note' => $note,
                    'html' => $changerHtml,
                    'date' => formatDateToRus($changerDate)
                ];
                        }
        }
        // Дочерние элементы, утратившие силу той же НПА, тоже показываем в «Изменения внесены:».
        $changingElements = array_merge($changingElements, collectExpiredChildChanges($pdo, $internalId, $viewDateSql, $changerIds, $selectedRevisionNpaIds));
        $highlightsForClient = null;
        if (!empty($current['highlights'])) {
            $decoded = json_decode($current['highlights'], true);
            if (is_array($decoded)) $highlightsForClient = $decoded;
        }
        $precomputedCompares[$externalId] = [
            'success' => true,
            'prev_valid_from' => $prev ? formatDateToRus($prev['valid_from']) : '',
            'current_valid_from' => formatDateToRus($current['valid_from']),
            'prev_html_raw' => $prevHtml,
            'current_html_raw' => $currHtml,
            'element_human_path' => getElementHumanPath($internalId, $pdo, 'genitive'),
            'changing_elements' => $changingElements,
            'highlights' => normalizeHighlights($highlightsForClient),
            'mod_type' => $current['mod_type']
        ];
    }
    $selectedCurrentHeadRev = getItemHeadRevisionForSelectedEdition($pdo, $internalId, $viewDateSql, $selectedRevisionNpaIds);
    $selectedCurrentHeadRevId = $selectedCurrentHeadRev ? (int)$selectedCurrentHeadRev['id'] : 0;
    $headHistoryAll = getItemHeadRevisionTimelineForSelectedEdition($pdo, $internalId, $viewDateSql, $selectedRevisionNpaIds);
    if (!empty($headHistoryAll)) {
        $historyResultHead = ['success' => true, 'revisions' => []];
        $stmtItemType = $pdo->prepare("SELECT item_type, item_number FROM npa_item WHERE id = ?");
        $stmtItemType->execute([$internalId]);
        $itemInfo = $stmtItemType->fetch();
        $itemType = $itemInfo ? $itemInfo['item_type'] : '';
        $itemNumber = $itemInfo ? ($itemInfo['item_number'] ?? '') : '';
        $lastHeadIdx = count($headHistoryAll) - 1;
        foreach ($headHistoryAll as $idx => $rev) {
            $dt = parseDate($rev['valid_from']);
            $validFromDate = $dt ? $dt->format('d.m.Y') : '';
            $isLastHeadRev = ($idx === $lastHeadIdx);
            $revValidToDate = !empty($rev['valid_to']) ? substr($rev['valid_to'], 0, 10) : null;
            $isExpiredHeadRev = $isLastHeadRev && ($isExpiredDoc || ($revValidToDate !== null && $revValidToDate < $viewDateSql) || (!empty($rev['not_valid']) && $revValidToDate === null));
            $isOriginal = ($idx === 0) && !$isExpiredHeadRev;
            $expirySource = '';
            $expiryUrl = '';
            if ($isExpiredHeadRev) {
                $notValidId = $rev['not_valid'] ?? null;
                $expirySources = '';
                $expiryUrls = '';
                if ($notValidId && $notValidId !== 'base') {
                    $expiryNpaInfo = getNpaInfoByItemId($notValidId, $pdo);
                    if ($expiryNpaInfo) {
                        $expiryTypeName = ($expiryNpaInfo['npa_type'] === 'law') ? 'Закона' : 'Постановления Законодательного Собрания';
                        $expiryDateForDisplay = formatRusDate($expiryNpaInfo['date_passed'], $expiryNpaInfo['date_format']);
                        $expirySources = $expiryTypeName . ' города Севастополя № ' . $expiryNpaInfo['npa_number'] . ' от ' . $expiryDateForDisplay;
                        $expiryUrls = $expiryNpaInfo['npa_url'] ?? '';
                    }
                }
                $displayTitle = $expirySources ?: 'последний действующий заголовок элемента';
                $sourceDecode = $expirySources ?: 'последний действующий заголовок элемента';
                $npaUrl = $expiryUrls;
                $expirySource = $expirySources;
                $expiryUrl = $expiryUrls;
                if ($itemType === 'structured_table') {
                    $tableHeadForPath = $rev['head_text'] ?? '';
                    if (!empty($tableHeadForPath)) {
                        $elementPath = 'таблицы ' . $itemNumber . ' (заголовок)';
                    } else {
                        $elementPath = '';
                    }
                } else {
                    $elementPath = getElementHumanPath($internalId, $pdo) . ' (заголовок)';
                }
            } elseif ($isOriginal) {
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
                    $elementPath = getElementHumanPath($internalId, $pdo) . ' (заголовок)';
                }
            } else {
                $changerElementId = (int)$rev['modified_by_id'];
                $npaInfo = getNpaInfoByItemId($changerElementId, $pdo);
                if ($npaInfo) {
                    $typeName = ($npaInfo['npa_type'] === 'law') ? 'Закона' : 'Постановления';
                    $dateForDisplay = formatRusDate($npaInfo['date_passed'], $npaInfo['date_format']);
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
                    $elementPath = getElementHumanPath($internalId, $pdo) . ' (заголовок)';
                }
            }
            $isCurrent = ((int)$rev['id'] === $selectedCurrentHeadRevId) && !$isExpiredHeadRev;
            $historyResultHead['revisions'][] = [
                'rev_id' => $rev['id'],
                'valid_from' => $validFromDate,
                'valid_to' => $rev['valid_to'] ? formatDateToRus($rev['valid_to']) : null,
                'source_decode' => $sourceDecode,
                'modified_by_id' => $rev['modified_by_id'],
                'display_title' => $displayTitle,
                'is_original' => $isOriginal,
                'is_current' => $isCurrent,
                'is_expired' => $isExpiredHeadRev,
                'expiry_source' => $expirySource,
                'expiry_url' => $expiryUrl,
                'element_path' => $elementPath,
                'npa_title' => $rev['head_text'],
                'npa_url' => $npaUrl
            ];
        }
        $precomputedHistories["head:{$externalId}"] = $historyResultHead;
        foreach ($headHistoryAll as $rev) {
            $revId = $rev['id'];
            $key = "head_item_{$externalId}_{$revId}";
            $content = getItemHeadRevisionContent($pdo, $revId, $internalId, $viewDateSql);
            if ($content) {
                $precomputedRevisions[$key] = [
                    'success' => true,
                    'html' => $content['html'],
                    'valid_from' => formatDateToRus($content['valid_from']),
                    'valid_to' => $content['valid_to'] ? formatDateToRus($content['valid_to']) : null,
                    'modified_by_id' => $content['modified_by_id'],
                    'is_current' => isRevisionCurrent($isExpiredDoc, $rev['valid_to'], $rev['valid_from'], $viewDateSql),
                    'doc_note' => $content['source_info'] ?? ''
                ];
            }
        }
    }
    $headCompare = getItemHeadCompareForSelectedEdition($pdo, $internalId, $viewDateSql, $selectedRevisionNpaIds);
    $precomputedCompares["head:{$externalId}"] = [
        'success' => true,
        'prev_valid_from' => $headCompare['prev_valid_from'],
        'current_valid_from' => $headCompare['current_valid_from'],
        'prev_html_raw' => $headCompare['prev_html_raw'],
        'current_html_raw' => $headCompare['current_html_raw'],
        'element_human_path' => 'заголовка ' . getElementHumanPath($internalId, $pdo, 'genitive'),
        'changing_elements' => $headCompare['changing_elements'] ?? [],
        'highlights' => normalizeHighlights($headCompare['highlights']),
        'mod_type' => $headCompare['mod_type']
    ];
}

 $stmtHeadAllRevisions = $pdo->prepare("
    SELECT * FROM npa_head_revision
    WHERE npa_id = ?
      AND valid_from <= ?
    ORDER BY valid_from ASC
");
 $stmtHeadAllRevisions->execute([$npa_id, $viewDateSql]);
 $allHeadRevisions = $stmtHeadAllRevisions->fetchAll();
 $headHistoryResult = ['success' => true, 'revisions' => []];
if (!empty($allHeadRevisions)) {
    $lastDocHeadIdx = count($allHeadRevisions) - 1;
    foreach ($allHeadRevisions as $idx => $rev) {
        $dt = parseDate($rev['valid_from']);
        $validFromDate = $dt ? $dt->format('d.m.Y') : '';
        $isLastDocHeadRev = ($idx === $lastDocHeadIdx);
        $revValidToDate = !empty($rev['valid_to']) ? substr($rev['valid_to'], 0, 10) : null;
        $isExpiredDocHeadRev = $isLastDocHeadRev && ($isExpiredDoc || ($revValidToDate !== null && $revValidToDate < $viewDateSql) || (!empty($rev['not_valid']) && $revValidToDate === null));
        $isOriginal = ($idx === 0) && !$isExpiredDocHeadRev;
        $expirySource = '';
        $expiryUrl = '';
        if ($isExpiredDocHeadRev) {
            $notValidId = $rev['not_valid'] ?? null;
            $expirySources = '';
            $expiryUrls = '';
            if ($notValidId && $notValidId !== 'base') {
                $expiryNpaInfo = getNpaInfoByItemId($notValidId, $pdo);
                if ($expiryNpaInfo) {
                    $expiryTypeName = ($expiryNpaInfo['npa_type'] === 'law') ? 'Закона' : 'Постановления Законодательного Собрания';
                    $expiryDateForDisplay = formatRusDate($expiryNpaInfo['date_passed'], $expiryNpaInfo['date_format']);
                    $expirySources = $expiryTypeName . ' города Севастополя № ' . $expiryNpaInfo['npa_number'] . ' от ' . $expiryDateForDisplay;
                    $expiryUrls = $expiryNpaInfo['npa_url'] ?? '';
                }
            }
            $displayTitle = $expirySources ?: 'последнее действующее наименование';
            $sourceDecode = $expirySources ?: 'последнее действующее наименование';
            $npaUrl = $expiryUrls;
            $expirySource = $expirySources;
            $expiryUrl = $expiryUrls;
        } elseif ($isOriginal) {
            $displayTitle = 'Исходное наименование';
            $sourceDecode = 'исходная редакция';
            $npaUrl = '';
        } else {
            $changerElementId = (int)$rev['modified_by_id'];
            $npaInfo = getNpaInfoByItemId($changerElementId, $pdo);
            if ($npaInfo) {
                $typeName = ($npaInfo['npa_type'] === 'law') ? 'Закона' : 'Постановления';
                $dateForDisplay = formatRusDate($npaInfo['date_passed'], $npaInfo['date_format']);
                $displayTitle = $typeName . ' города Севастополя № ' . $npaInfo['npa_number'] . ' от ' . $dateForDisplay;
                $sourceDecode = getElementHumanPath($changerElementId, $pdo);
                $npaUrl = $npaInfo['npa_url'] ?? '';
            } else {
                $displayTitle = 'Неизвестный документ';
                $sourceDecode = '';
                $npaUrl = '';
            }
        }
        $isCurrent = isRevisionCurrent($isExpiredDoc, $rev['valid_to'], $rev['valid_from'], $viewDateSql);
        $headHistoryResult['revisions'][] = [
            'rev_id' => $rev['id'],
            'valid_from' => $validFromDate,
            'valid_to' => $rev['valid_to'] ? formatDateToRus($rev['valid_to']) : null,
            'source_decode' => $sourceDecode,
            'modified_by_id' => $rev['modified_by_id'],
            'display_title' => $displayTitle,
            'is_original' => $isOriginal,
            'is_current' => $isCurrent,
            'is_expired' => $isExpiredDocHeadRev,
            'expiry_source' => $expirySource,
            'expiry_url' => $expiryUrl,
            'element_path' => 'наименование документа',
            'npa_title' => $rev['npa_title'],
            'npa_url' => $npaUrl
        ];
    }
}
 $precomputedHistories['head'] = $headHistoryResult;

 $headCompareData = getHeadCompareHtml($pdo, $npa_id, $viewDateSql);
 $highlightsArray = is_string($headCompareData['highlights'])
    ? json_decode($headCompareData['highlights'], true)
    : $headCompareData['highlights'];
if (!is_array($highlightsArray)) {
    $highlightsArray = ['current_edition' => ['addition' => [], 'difference' => []], 'previous_edition' => ['deletion' => [], 'difference' => []]];
}
 $precomputedCompares['head'] = [
    'success' => true,
    'prev_valid_from' => $headCompareData['prev_valid_from'],
    'current_valid_from' => $headCompareData['current_valid_from'],
    'prev_html_raw' => $headCompareData['prev_html_raw'],
    'current_html_raw' => $headCompareData['current_html_raw'],
    'element_human_path' => 'наименования документа',
    'changing_elements' => $headCompareData['changing_elements'] ?? [],
    'highlights' => $highlightsArray,
    'mod_type' => $headCompareData['mod_type']
];

foreach ($precomputedCompares as $key => &$compare) {
    if (isset($compare['highlights'])) {
        $compare['highlights'] = normalizeHighlights($compare['highlights']);
    } else {
        $compare['highlights'] = normalizeHighlights(null);
    }
}
unset($compare);

 $staticJsData = [
    'npa_id' => $npa_id,
    'view_date' => $viewDateSql,
    'selected_revision_npa_ids' => $selectedRevisionNpaIds,
    'head_revisions' => $headRevisions,
    'items' => $itemsById,
    'revisionContents' => $precomputedRevisions,
    'precomputed' => [
        'histories' => $precomputedHistories,
        'compares' => $precomputedCompares
    ],
    'no_name_ids' => $NPA_NO_NAME_IDS
];

 $json = json_encode($staticJsData, JSON_UNESCAPED_UNICODE | JSON_HEX_TAG);
 $json = str_replace(['[[', ']]'], ['[ [', '] ]'], $json);
 $output .= '<script id="npa-static-data" type="application/json">' . $json . '</script>';

file_put_contents($staticFile, $output);
return $output;
