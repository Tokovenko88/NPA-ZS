<?php
/**
 * NPA-ZS | revisions/item.php — редакции содержимого элементов.
 *
 * Функции: getPreviousItemRevision, getRevisionForDate, getActiveRecord,
 *          getLastContentRevision.
 * Источник: строки 200-219, 278-311, 542-571, 2876-2914 монолита snippet.php.
 */

function getPreviousItemRevision(PDO $pdo, $itemInternalId, $currentRevId) {
    $stmt = $pdo->prepare("
        SELECT r.*
        FROM npa_item_revision r
        WHERE r.item_internal_id = ?
          AND (
              r.valid_from < (SELECT c.valid_from FROM npa_item_revision c WHERE c.rev_id = ?)
              OR (
                  r.valid_from = (SELECT c.valid_from FROM npa_item_revision c WHERE c.rev_id = ?)
                  AND r.rev_id < ?
              )
          )
          AND EXISTS (SELECT 1 FROM npa_paragraph p WHERE p.rev_id = r.rev_id)
        ORDER BY r.valid_from DESC, r.rev_id DESC
        LIMIT 1
    ");
    $stmt->execute([$itemInternalId, $currentRevId, $currentRevId, $currentRevId]);
    return $stmt->fetch();
}

function getRevisionForDate(PDO $pdo, $itemInternalId, $asOfDate) {
    $stmt = $pdo->prepare("
        SELECT rev_id, valid_from, valid_to, mod_type, highlights, modified_by_id, not_valid
        FROM npa_item_revision
        WHERE item_internal_id = ?
          AND (valid_from <= ? OR valid_from IS NULL)
          AND (valid_to IS NULL OR valid_to >= ?)
        ORDER BY valid_from DESC
        LIMIT 1
    ");
    $stmt->execute([$itemInternalId, $asOfDate, $asOfDate]);
    $active = $stmt->fetch();
    if ($active) {
        $active['is_expired'] = false;
        return $active;
    }
    $stmt = $pdo->prepare("
        SELECT rev_id, valid_from, valid_to, mod_type, highlights, modified_by_id, not_valid
        FROM npa_item_revision
        WHERE item_internal_id = ?
          AND valid_from <= ?
          AND valid_to < ?
        ORDER BY valid_from DESC
        LIMIT 1
    ");
    $stmt->execute([$itemInternalId, $asOfDate, $asOfDate]);
    $expired = $stmt->fetch();
    if ($expired) {
        $expired['is_expired'] = true;
        return $expired;
    }
    return null;
}

function getActiveRecord(PDO $pdo, $table, $idField, $idValue, $asOfDate) {
    $sql = "SELECT * FROM `$table`
            WHERE `$idField` = ?
              AND (`valid_from` <= ? OR `valid_from` IS NULL)
              AND (`valid_to` IS NULL OR `valid_to` >= ?)
            ORDER BY `valid_from` DESC
            LIMIT 1";
    $stmt = $pdo->prepare($sql);
    $stmt->execute([$idValue, $asOfDate, $asOfDate]);
    $row = $stmt->fetch();
    if ($row) {
        $row['is_expired'] = 0;
        return $row;
    }
    $sql = "SELECT * FROM `$table`
            WHERE `$idField` = ?
              AND `valid_from` <= ?
              AND `valid_to` < ?
            ORDER BY `valid_from` DESC
            LIMIT 1";
    $stmt = $pdo->prepare($sql);
    $stmt->execute([$idValue, $asOfDate, $asOfDate]);
    $expired = $stmt->fetch();
    if ($expired) {
        $expired['is_expired'] = 1;
        return $expired;
    }
    return null;
}

function getLastContentRevision(PDO $pdo, $internal_item_id, $asOfDate = null) {
    if ($asOfDate) {
        $stmt = $pdo->prepare("
            SELECT rev_id, valid_from, valid_to
            FROM npa_item_revision
            WHERE item_internal_id = ?
              AND valid_from <= ?
              AND (valid_to IS NULL OR valid_to >= ?)
              AND EXISTS (SELECT 1 FROM npa_paragraph p WHERE p.rev_id = npa_item_revision.rev_id)
            ORDER BY valid_from DESC
        ");
        $stmt->execute([$internal_item_id, $asOfDate, $asOfDate]);
        $active = $stmt->fetch();
        if ($active) return $active;
        
        $stmt = $pdo->prepare("
            SELECT rev_id, valid_from, valid_to
            FROM npa_item_revision
            WHERE item_internal_id = ?
              AND valid_from <= ?
              AND (valid_to IS NULL OR valid_to >= ?)
              AND EXISTS (SELECT 1 FROM npa_paragraph p WHERE p.rev_id = npa_item_revision.rev_id)
            ORDER BY valid_from DESC
        ");
        $stmt->execute([$internal_item_id, $asOfDate, $asOfDate]);
        return $stmt->fetch();
    } else {
        $stmt = $pdo->prepare("
            SELECT rev_id, valid_from, valid_to
            FROM npa_item_revision
            WHERE item_internal_id = ?
              AND EXISTS (SELECT 1 FROM npa_paragraph p WHERE p.rev_id = npa_item_revision.rev_id)
            ORDER BY valid_from DESC
        ");
        $stmt->execute([$internal_item_id]);
        return $stmt->fetch();
    }
}

