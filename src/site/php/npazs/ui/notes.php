<?php
/**
 * NPA-ZS | ui/notes.php — примечания к элементам и заголовкам.
 *
 * Функции: getItemHeadRevisionNotes, getElementRevisionNotes.
 * Источник: строки 1039-1123, 2786-2875 монолита snippet.php.
 */

function getItemHeadRevisionNotes($internal_item_id, $pdo, $viewDate, $itemType, array $selectedRevisionNpaIds = [], $baseNpaId = null) {
    $currentRev = getItemHeadRevisionForSelectedEdition($pdo, $internal_item_id, $viewDate, $selectedRevisionNpaIds);
    if (!$currentRev || empty($currentRev['id'])) return '';

    $currentRevId = (int)$currentRev['id'];

    $sql = "SELECT r.* FROM npa_item_head_revision r
            WHERE r.item_internal_id = ?
              AND (r.valid_from IS NULL OR r.valid_from <= ?";
    $params = [$internal_item_id, $currentRev['valid_from']];

    if (!empty($selectedRevisionNpaIds)) {
        $placeholders = buildRevisionNpaIdPlaceholders($selectedRevisionNpaIds);
        $sql .= " OR EXISTS (
            SELECT 1 FROM npa_item changer
            WHERE changer.npa_id IN ($placeholders)
              AND INSTR(BINARY CONCAT(',', REPLACE(COALESCE(r.modified_by_id, ''), ' ', ''), ','), BINARY CONCAT(',', CAST(changer.id AS CHAR), ',')) > 0
        )";
        $params = array_merge($params, array_values($selectedRevisionNpaIds));
    }
    $sql .= ") ORDER BY r.valid_from ASC, r.id ASC";
    
    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    $allRevisions = $stmt->fetchAll();

    $allowedRevisions = [];
    foreach ($allRevisions as $rev) {
        if ((int)$rev['id'] <= $currentRevId) $allowedRevisions[] = $rev;
    }
    if (empty($allowedRevisions)) return '';

    $lastNewRedactionIdx = -1;
    foreach ($allowedRevisions as $idx => $rev) {
        if ($rev['mod_type'] === 'new_redaction') $lastNewRedactionIdx = $idx;
    }
    $revisionsToProcess = ($lastNewRedactionIdx !== -1)
        ? array_slice($allowedRevisions, $lastNewRedactionIdx)
        : $allowedRevisions;

    $addNote = $newRedactionNote = null;
    $changeNotes = [];

    foreach ($revisionsToProcess as $rev) {
        $shortDesc = getShortNpaDescription($rev['modified_by_id'], $pdo, true);
        if ($shortDesc === 'исходная редакция') continue;

        switch ($rev['mod_type']) {
            case 'add': if ($addNote === null) $addNote = $shortDesc; break;
            case 'new_redaction': $newRedactionNote = $shortDesc; break;
            case 'change': if (!in_array($shortDesc, $changeNotes, true)) $changeNotes[] = $shortDesc; break;
        }
    }

    $parts = [];
    if ($addNote) $parts[] = '<span class="revision-note">Заголовок введен — ' . $addNote . '</span>';
    if ($newRedactionNote) $parts[] = '<span class="revision-note">Заголовок в редакции — ' . $newRedactionNote . '</span>';
    if (!empty($changeNotes)) $parts[] = '<span class="revision-note">Заголовок изменен: ' . implode(', ', $changeNotes) . '</span>';

    if (empty($parts) && !empty($baseNpaId) && !empty($selectedRevisionNpaIds)) {
        $allNull = true;
        foreach ($allowedRevisions as $rev) {
            if (!empty($rev['mod_type']) || !empty($rev['modified_by_id'])) $allNull = false;
        }
        if ($allNull && !empty($currentRev['valid_from'])) {
            $law = getIntroducingLawForDate($pdo, $baseNpaId, $currentRev['valid_from']);
            if ($law) {
                $lawShort = getShortNpaDescription($law['revision_id'], $pdo, true);
                if ($lawShort !== 'исходная редакция') $addNote = $lawShort;
            }
        }
        if ($addNote) $parts[] = '<span class="revision-note">Заголовок введен — ' . $addNote . '</span>';
    }

    if (empty($parts)) return '';

    $dt = parseDate($currentRev['valid_from'] ?? null);
    $validFromDate = $dt ? $dt->format('d.m.Y') : '';
    $isDeferred = isDeferredSelectedEditionRevision($currentRev, $viewDate, $selectedRevisionNpaIds);
    $dateBlock = buildRevisionEffectiveDateBlock($validFromDate, $isDeferred);

    return '<div class="element-revision-notes" style="margin: 0.5em 0;">'
         . $dateBlock . implode('<br>', $parts) . '</div>';
}

function getElementRevisionNotes($internal_item_id, $pdo, $baseNpaId, $npaType, $viewDate, $itemType, array $selectedRevisionNpaIds = []) {
    $currentRev = getRevisionForSelectedEdition($pdo, $internal_item_id, $viewDate, $selectedRevisionNpaIds);
    if (!$currentRev || empty($currentRev['rev_id'])) return '';

    $currentRevId = (int)$currentRev['rev_id'];

    $sql = "SELECT r.* FROM npa_item_revision r
            WHERE r.item_internal_id = ?
              AND (r.valid_from IS NULL OR r.valid_from <= ?";
    $params = [$internal_item_id, $currentRev['valid_from']];

    if (!empty($selectedRevisionNpaIds)) {
        $placeholders = buildRevisionNpaIdPlaceholders($selectedRevisionNpaIds);
        $sql .= " OR EXISTS (
            SELECT 1 FROM npa_item changer
            WHERE changer.npa_id IN ($placeholders)
              AND INSTR(BINARY CONCAT(',', REPLACE(COALESCE(r.modified_by_id, ''), ' ', ''), ','), BINARY CONCAT(',', CAST(changer.id AS CHAR), ',')) > 0
        )";
        $params = array_merge($params, array_values($selectedRevisionNpaIds));
    }
    $sql .= ") ORDER BY r.valid_from ASC, r.rev_id ASC";
    
    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    $allRevisions = $stmt->fetchAll();

    $allowedRevisions = [];
    foreach ($allRevisions as $rev) {
        if ((int)$rev['rev_id'] <= $currentRevId) $allowedRevisions[] = $rev;
    }
    if (empty($allowedRevisions)) return '';

    $lastNewRedactionIdx = -1;
    foreach ($allowedRevisions as $idx => $rev) {
        if ($rev['mod_type'] === 'new_redaction') $lastNewRedactionIdx = $idx;
    }
    $revisionsToProcess = ($lastNewRedactionIdx !== -1)
        ? array_slice($allowedRevisions, $lastNewRedactionIdx)
        : $allowedRevisions;

    $addNote = null;
    $newRedactionNote = null;
    $changeNotes = [];

    foreach ($revisionsToProcess as $rev) {
        $shortDesc = getShortNpaDescription($rev['modified_by_id'], $pdo, true);
        if ($shortDesc === 'исходная редакция') continue;

        switch ($rev['mod_type']) {
            case 'add': if ($addNote === null) $addNote = $shortDesc; break;
            case 'new_redaction': $newRedactionNote = $shortDesc; break;
            case 'change': if (!in_array($shortDesc, $changeNotes, true)) $changeNotes[] = $shortDesc; break;
        }
    }

    $genderSuffix = '';
    if ($itemType === 'article' || $itemType === 'part') $genderSuffix = 'а';
    elseif ($itemType === 'appendix') $genderSuffix = 'о';

    $parts = [];
    if ($addNote) $parts[] = '<span class="revision-note">Введен' . $genderSuffix . ' — ' . $addNote . '</span>';
    if ($newRedactionNote) $parts[] = '<span class="revision-note">В редакции — ' . $newRedactionNote . '</span>';
    if (!empty($changeNotes)) $parts[] = '<span class="revision-note">С изменениями: ' . implode(', ', $changeNotes) . '</span>';

    if (empty($parts) && !empty($baseNpaId) && !empty($selectedRevisionNpaIds)) {
        $allNull = true;
        foreach ($allowedRevisions as $rev) {
            if (!empty($rev['mod_type']) || !empty($rev['modified_by_id'])) $allNull = false;
        }
        if ($allNull && !empty($currentRev['valid_from'])) {
            $law = getIntroducingLawForDate($pdo, $baseNpaId, $currentRev['valid_from']);
            if ($law) {
                $lawShort = getShortNpaDescription($law['revision_id'], $pdo, true);
                if ($lawShort !== 'исходная редакция') $addNote = $lawShort;
            }
        }
        if ($addNote) $parts[] = '<span class="revision-note">Введен' . $genderSuffix . ' — ' . $addNote . '</span>';
    }

    if (empty($parts)) return '';

    $dt = parseDate($currentRev['valid_from'] ?? null);
    $validFromDate = $dt ? $dt->format('d.m.Y') : '';
    $isDeferred = isDeferredSelectedEditionRevision($currentRev, $viewDate, $selectedRevisionNpaIds);
    $dateBlock = buildRevisionEffectiveDateBlock($validFromDate, $isDeferred);

    return '<div class="element-revision-notes" style="margin: 0.5em 0;">'
         . $dateBlock . implode('<br>', $parts) . '</div>';
}

/**
 * Фильтрует примечания (npa_note_unified) по правилу отображения
 * (docs/db_schema.md §6.1.4, §6.2, docs/site_output.md §8.4):
 *
 *   Примечание выводится только если его valid_to не задан (бессрочно)
 *   ИЛИ valid_to >= даты вступления в силу выбранной редакции ($editionDate).
 *   Примечание, у которого valid_to меньше даты вступления в силу выбранной
 *   редакции, считается истёкшим и не выводится.
 *
 * $editionDate — дата вступления в силу выбранной редакции (view_date);
 * поддерживаются форматы 'Y-m-d' и 'd.m.Y' (через parseDate()).
 *
 * @param array $notes       Список примечаний (строки npa_note_unified).
 * @param mixed $editionDate Дата вступления в силу выбранной редакции.
 * @return array Отфильтрованный список примечаний.
 */
function filterNotesByValidTo(array $notes, $editionDate) {
    $edition = parseDate($editionDate);
    if (!$edition) {
        // Дата просмотра неизвестна — не принимаем решений, показываем как есть.
        return array_values($notes);
    }
    $editionStr = $edition->format('Y-m-d');
    $filtered = [];
    foreach ($notes as $note) {
        $validTo = parseDate($note['valid_to'] ?? null);
        // Бессрочные примечания (valid_to NULL/'') показываются всегда;
        // истёкшие (valid_to < даты вступления в силу редакции) — скрываются.
        if ($validTo === null || $validTo->format('Y-m-d') >= $editionStr) {
            $filtered[] = $note;
        }
    }
    return $filtered;
}

