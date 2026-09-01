<?php
/**
 * NPA-ZS | revisions/number_prefix.php — номера и префиксы элементов на дату.
 *
 * Функции: getItemNumberForDate, getItemNumberAtDate, getItemPrefixRevision.
 * Таблицы: npa_item_number_revision, npa_item_prefix_revision.
 * Источник: строки 443-462, 572-604 монолита snippet.php.
 */

function getItemNumberForDate(PDO $pdo, $itemInternalId, $asOfDate) {
    $stmt = $pdo->prepare("
        SELECT number_text, valid_to
        FROM npa_item_number_revision
        WHERE item_internal_id = ?
          AND (valid_from <= ? OR valid_from IS NULL)
        ORDER BY valid_from DESC
    ");
    $stmt->execute([$itemInternalId, $asOfDate]);
    $revisions = $stmt->fetchAll();
    if (empty($revisions)) {
        return null;
    }
    foreach ($revisions as $rev) {
        if (is_null($rev['valid_to']) || $rev['valid_to'] >= $asOfDate) {
            return $rev['number_text'];
        }
    }
    return $revisions[0]['number_text'];
}
function getItemNumberAtDate(PDO $pdo, $itemInternalId, $asOfDate) {
    $stmt = $pdo->prepare("
        SELECT number_text FROM npa_item_number_revision
        WHERE item_internal_id = ?
          AND (valid_from <= ? OR valid_from IS NULL)
          AND (valid_to IS NULL OR valid_to >= ?)
        ORDER BY valid_from DESC
        LIMIT 1
    ");
    $stmt->execute([$itemInternalId, $asOfDate, $asOfDate]);
    $rev = $stmt->fetch();
    if ($rev) {
        return $rev['number_text'];
    }
    return null;
}

function getItemPrefixRevision($item_internal_id, $asOfDate, $pdo) {
    $sql = "SELECT * FROM npa_item_prefix_revision
            WHERE item_internal_id = ?
              AND (valid_from <= ? OR valid_from IS NULL)
              AND (valid_to IS NULL OR valid_to >= ?)
            ORDER BY valid_from DESC LIMIT 1";
    $stmt = $pdo->prepare($sql);
    $stmt->execute([$item_internal_id, $asOfDate, $asOfDate]);
    $rev = $stmt->fetch();
    if ($rev) {
        $rev['is_expired'] = 0;
        return $rev;
    }
    return null;
}

