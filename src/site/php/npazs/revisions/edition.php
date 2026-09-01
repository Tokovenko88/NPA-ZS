<?php
/**
 * NPA-ZS | revisions/edition.php — контекст «выбранной редакции» документа.
 *
 * Функции: getSelectedRevisionNpaIds, buildRevisionNpaIdPlaceholders,
 *          getSelectedEditionRegistrationDate, getRevisionForSelectedEdition,
 *          getItemRevisionTimelineForSelectedEdition,
 *          getItemHeadRevisionTimelineForSelectedEdition,
 *          getItemHeadRevisionForSelectedEdition, getItemNumberForSelectedEdition,
 *          getItemPrefixRevisionForSelectedEdition, isDeferredSelectedEditionRevision.
 * Список rev-НПА выбранной редакции пишется в $GLOBALS['selected_revision_npa_ids']
 * (точка входа) и читается в getItemRevisionContent (content/item_content.php).
 * Источник: строки 114-199, 239-277, 312-345, 380-408, 605-638, 1002-1016 монолита.
 */

function getSelectedRevisionNpaIds(PDO $pdo, $baseNpaId, $viewDate) {
    if (empty($baseNpaId) || empty($viewDate)) {
        return [];
    }

    $stmt = $pdo->prepare("
        SELECT revision_id
        FROM npa_revision_info
        WHERE base_npa_id = ?
          AND revision_date_valid = ?
        ORDER BY revision_number ASC
    ");
    $stmt->execute([$baseNpaId, $viewDate]);

    $ids = [];
    foreach ($stmt->fetchAll() as $row) {
        if (isset($row['revision_id']) && (int)$row['revision_id'] > 0) {
            $ids[] = (int)$row['revision_id'];
        }
    }

    return array_values(array_unique($ids));
}

function buildRevisionNpaIdPlaceholders(array $revisionNpaIds) {
    return implode(',', array_fill(0, count($revisionNpaIds), '?'));
}

function getSelectedEditionRegistrationDate(PDO $pdo, $baseNpaId, array $selectedRevisionNpaIds = []) {
    if (empty($baseNpaId) || empty($selectedRevisionNpaIds)) {
        return null;
    }

    $placeholders = buildRevisionNpaIdPlaceholders($selectedRevisionNpaIds);
    $stmt = $pdo->prepare("
        SELECT MAX(revision_date_reg)
        FROM npa_revision_info
        WHERE base_npa_id = ?
          AND revision_id IN ($placeholders)
    ");
    $stmt->execute(array_merge([$baseNpaId], array_values($selectedRevisionNpaIds)));
    $date = $stmt->fetchColumn();

    return $date ?: null;
}

function getRevisionForSelectedEdition(PDO $pdo, $itemInternalId, $asOfDate, array $selectedRevisionNpaIds = []) {
    $revision = getRevisionForDate($pdo, $itemInternalId, $asOfDate);

    if (empty($selectedRevisionNpaIds)) {
        return $revision;
    }

    $placeholders = buildRevisionNpaIdPlaceholders($selectedRevisionNpaIds);
    $sql = "
        SELECT r.rev_id, r.valid_from, r.valid_to, r.mod_type, r.highlights, r.modified_by_id, r.not_valid
        FROM npa_item_revision r
        WHERE r.item_internal_id = ?
          AND EXISTS (
              SELECT 1
              FROM npa_item changer
              WHERE changer.npa_id IN ($placeholders)
                AND INSTR(
                    BINARY CONCAT(',', REPLACE(COALESCE(r.modified_by_id, ''), ' ', ''), ','),
                    BINARY CONCAT(',', CAST(changer.id AS CHAR), ',')
                ) > 0
          )
          AND EXISTS (
              SELECT 1 FROM npa_paragraph p WHERE p.rev_id = r.rev_id
          )
        ORDER BY r.valid_from DESC, r.rev_id DESC
        LIMIT 1
    ";
    $params = array_merge([$itemInternalId], array_values($selectedRevisionNpaIds));
    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    $selectedRevision = $stmt->fetch();

    if ($selectedRevision) {
        $selectedRevision['is_expired'] = false;
        return $selectedRevision;
    }

    return $revision;
}

function getItemRevisionTimelineForSelectedEdition(PDO $pdo, $itemInternalId, $asOfDate, array $selectedRevisionNpaIds = []) {
    $current = getRevisionForSelectedEdition($pdo, $itemInternalId, $asOfDate, $selectedRevisionNpaIds);
    if (!$current) return [];

    $stmt = $pdo->prepare("
        SELECT r.rev_id, r.valid_from, r.valid_to, r.modified_by_id, r.mod_type, r.not_valid
        FROM npa_item_revision r
        WHERE r.item_internal_id = ?
          AND EXISTS (SELECT 1 FROM npa_paragraph p WHERE p.rev_id = r.rev_id)
          AND (
              r.valid_from < ?
              OR (r.valid_from = ? AND r.rev_id <= ?)
              OR r.valid_from IS NULL
          )
        ORDER BY r.valid_from ASC, r.rev_id ASC
    ");
    $stmt->execute([$itemInternalId, $current['valid_from'], $current['valid_from'], $current['rev_id']]);
    return $stmt->fetchAll();
}

function getItemHeadRevisionTimelineForSelectedEdition(PDO $pdo, $itemInternalId, $asOfDate, array $selectedRevisionNpaIds = []) {
    $current = getItemHeadRevisionForSelectedEdition($pdo, $itemInternalId, $asOfDate, $selectedRevisionNpaIds);
    if (!$current) return [];

    $stmt = $pdo->prepare("
        SELECT id, head_text, valid_from, valid_to, modified_by_id, mod_type, highlights, not_valid
        FROM npa_item_head_revision r
        WHERE r.item_internal_id = ?
          AND (
              r.valid_from < ?
              OR (r.valid_from = ? AND r.id <= ?)
              OR r.valid_from IS NULL
          )
        ORDER BY r.valid_from ASC, r.id ASC
    ");
    $stmt->execute([$itemInternalId, $current['valid_from'], $current['valid_from'], $current['id']]);
    return $stmt->fetchAll();
}

function getItemHeadRevisionForSelectedEdition(PDO $pdo, $itemInternalId, $asOfDate, array $selectedRevisionNpaIds = []) {
    $revision = getItemHeadRevisionForDate($pdo, $itemInternalId, $asOfDate);

    if (empty($selectedRevisionNpaIds)) {
        return $revision;
    }

    $placeholders = buildRevisionNpaIdPlaceholders($selectedRevisionNpaIds);
    $sql = "
        SELECT r.id, r.head_text, r.valid_from, r.valid_to, r.highlights, r.mod_type, r.modified_by_id, r.not_valid
        FROM npa_item_head_revision r
        WHERE r.item_internal_id = ?
          AND EXISTS (
              SELECT 1
              FROM npa_item changer
              WHERE changer.npa_id IN ($placeholders)
                AND INSTR(BINARY CONCAT(',', REPLACE(COALESCE(r.modified_by_id, ''), ' ', ''), ','), BINARY CONCAT(',', CAST(changer.id AS CHAR), ',')) > 0
          )
        ORDER BY r.valid_from DESC, r.id DESC
        LIMIT 1
    ";
    $params = array_merge([$itemInternalId], array_values($selectedRevisionNpaIds));
    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    $selectedRevision = $stmt->fetch();

    if ($selectedRevision) {
        $selectedRevision['is_expired'] = false;
        return $selectedRevision;
    }

    return $revision;
}

function getItemNumberForSelectedEdition(PDO $pdo, $itemInternalId, $asOfDate, array $selectedRevisionNpaIds = []) {
    $number = getItemNumberForDate($pdo, $itemInternalId, $asOfDate);

    if (empty($selectedRevisionNpaIds)) {
        return $number;
    }

    $placeholders = buildRevisionNpaIdPlaceholders($selectedRevisionNpaIds);
    $sql = "
        SELECT r.number_text
        FROM npa_item_number_revision r
        WHERE r.item_internal_id = ?
          AND EXISTS (
              SELECT 1
              FROM npa_item changer
              WHERE changer.npa_id IN ($placeholders)
                AND INSTR(BINARY CONCAT(',', REPLACE(COALESCE(r.modified_by_id, ''), ' ', ''), ','), BINARY CONCAT(',', CAST(changer.id AS CHAR), ',')) > 0
          )
        ORDER BY r.valid_from DESC
        LIMIT 1
    ";
    $params = array_merge([$itemInternalId], array_values($selectedRevisionNpaIds));
    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    $selected = $stmt->fetchColumn();

    return ($selected !== false) ? $selected : $number;
}

function getItemPrefixRevisionForSelectedEdition($itemInternalId, $asOfDate, $pdo, array $selectedRevisionNpaIds = []) {
    $prefix = getItemPrefixRevision($itemInternalId, $asOfDate, $pdo);

    if (empty($selectedRevisionNpaIds)) {
        return $prefix;
    }

    $placeholders = buildRevisionNpaIdPlaceholders($selectedRevisionNpaIds);
    $sql = "
        SELECT r.*
        FROM npa_item_prefix_revision r
        WHERE r.item_internal_id = ?
          AND EXISTS (
              SELECT 1
              FROM npa_item changer
              WHERE changer.npa_id IN ($placeholders)
                AND INSTR(BINARY CONCAT(',', REPLACE(COALESCE(r.modified_by_id, ''), ' ', ''), ','), BINARY CONCAT(',', CAST(changer.id AS CHAR), ',')) > 0
          )
        ORDER BY r.valid_from DESC
        LIMIT 1
    ";
    $params = array_merge([$itemInternalId], array_values($selectedRevisionNpaIds));
    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    $selected = $stmt->fetch();

    if ($selected) {
        $selected['is_expired'] = 0;
        return $selected;
    }

    return $prefix;
}

function isDeferredSelectedEditionRevision($revision, $viewDate, array $selectedRevisionNpaIds = []) {
    if (empty($selectedRevisionNpaIds) || empty($revision['valid_from']) || empty($viewDate)) {
        return false;
    }

    $revisionDate = parseDate($revision['valid_from']);
    $viewDateObj = parseDate($viewDate);

    if (!$revisionDate || !$viewDateObj) {
        return false;
    }

    return $revisionDate->format('Y-m-d') > $viewDateObj->format('Y-m-d');
}

