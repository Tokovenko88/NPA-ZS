<?php
/**
 * NPA-ZS | revisions/head.php — редакции заголовков элементов и наименования.
 *
 * Функции: getPreviousItemHeadRevision, getItemHeadRevisionForDate,
 *          getHeadRevisionForDate.
 * Таблицы: npa_item_head_revision, npa_head_revision.
 * Источник: строки 220-238, 346-379, 409-442 монолита snippet.php.
 */

function getPreviousItemHeadRevision(PDO $pdo, $itemInternalId, $currentRevId) {
    $stmt = $pdo->prepare("
        SELECT r.*
        FROM npa_item_head_revision r
        WHERE r.item_internal_id = ?
          AND (
              r.valid_from < (SELECT c.valid_from FROM npa_item_head_revision c WHERE c.id = ?)
              OR (
                  r.valid_from = (SELECT c.valid_from FROM npa_item_head_revision c WHERE c.id = ?)
                  AND r.id < ?
              )
          )
        ORDER BY r.valid_from DESC, r.id DESC
        LIMIT 1
    ");
    $stmt->execute([$itemInternalId, $currentRevId, $currentRevId, $currentRevId]);
    return $stmt->fetch();
}

function getItemHeadRevisionForDate(PDO $pdo, $itemInternalId, $asOfDate) {
    $stmt = $pdo->prepare("
        SELECT id, head_text, valid_from, valid_to, highlights, mod_type, modified_by_id, not_valid
        FROM npa_item_head_revision
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
        SELECT id, head_text, valid_from, valid_to, highlights, mod_type, modified_by_id, not_valid
        FROM npa_item_head_revision
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

function getHeadRevisionForDate(PDO $pdo, $npa_id, $asOfDate) {
    $stmt = $pdo->prepare("
        SELECT id, npa_title, valid_from, valid_to, highlights, modified_by_id, not_valid
        FROM npa_head_revision
        WHERE npa_id = ?
          AND (valid_from <= ? OR valid_from IS NULL)
          AND (valid_to IS NULL OR valid_to >= ?)
        ORDER BY valid_from DESC
        LIMIT 1
    ");
    $stmt->execute([$npa_id, $asOfDate, $asOfDate]);
    $active = $stmt->fetch();
    if ($active) {
        $active['is_expired'] = false;
        return $active;
    }
    $stmt = $pdo->prepare("
        SELECT id, npa_title, valid_from, valid_to, highlights, modified_by_id, not_valid
        FROM npa_head_revision
        WHERE npa_id = ?
          AND valid_from <= ?
          AND valid_to < ?
        ORDER BY valid_from DESC
        LIMIT 1
    ");
    $stmt->execute([$npa_id, $asOfDate, $asOfDate]);
    $expired = $stmt->fetch();
    if ($expired) {
        $expired['is_expired'] = true;
        return $expired;
    }
    return null;
}

