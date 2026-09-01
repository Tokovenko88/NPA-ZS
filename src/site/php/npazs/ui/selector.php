<?php
/**
 * NPA-ZS | ui/selector.php — селектор редакций документа.
 *
 * Функции: getRevisionSelectorOptions.
 * Источник: строки 2623-2705 монолита snippet.php.
 */

function getRevisionSelectorOptions(PDO $pdo, $npa_id, $displayDate) {
    $options = [];
    $stmt = $pdo->prepare("SELECT valid_from, not_valid FROM npa_base WHERE npa_id = ?");
    $stmt->execute([$npa_id]);
    $base = $stmt->fetch();

    $baseValidFrom = $base['valid_from'] ?? null;
    $notValidDate = $base['not_valid'] ?? null;
    $isDocExpired = !empty($notValidDate);

    $stmt = $pdo->prepare("
        SELECT revision_date_valid
        FROM npa_revision_info
        WHERE base_npa_id = ?
        ORDER BY revision_date_valid ASC, revision_number ASC
    ");
    $stmt->execute([$npa_id]);

    $dates = [];
    foreach ($stmt->fetchAll() as $row) {
        if (!empty($row['revision_date_valid'])) $dates[$row['revision_date_valid']] = true;
    }
    $dates = array_keys($dates);
    sort($dates);

    $selectedDate = $baseValidFrom;
    foreach ($dates as $dateRaw) {
        if ($isDocExpired && $notValidDate && $dateRaw >= $notValidDate) continue;
        if ($dateRaw <= $displayDate) $selectedDate = $dateRaw;
    }

    $currentDate = $baseValidFrom;
    foreach ($dates as $dateRaw) {
        if ($isDocExpired && $notValidDate && $dateRaw >= $notValidDate) continue;
        $currentDate = $dateRaw;
    }

    if ($baseValidFrom) {
        $baseDateFormatted = formatDateToRus($baseValidFrom);
        $options[] = [
            'date_raw' => $baseValidFrom,
            'date_display' => $baseDateFormatted,
            'label' => 'Первоначальная редакция (вступление в силу ' . $baseDateFormatted . ')',
            'is_original' => true,
            'is_current' => ($baseValidFrom === $currentDate),
            'is_selected' => ($baseValidFrom === $selectedDate)
        ];
    }

    foreach ($dates as $dateRaw) {
        if ($isDocExpired && $notValidDate && $dateRaw >= $notValidDate) continue;

        $stmtRev = $pdo->prepare("
            SELECT revision_number, revision_date_reg
            FROM npa_revision_info
            WHERE base_npa_id = ? AND revision_date_valid = ?
            ORDER BY revision_number ASC
        ");
        $stmtRev->execute([$npa_id, $dateRaw]);

        $items = [];
        foreach ($stmtRev->fetchAll() as $rev) {
            $items[] = '№' . $rev['revision_number'] . ' от ' . formatDateToRus($rev['revision_date_reg']);
        }

        $options[] = [
            'date_raw' => $dateRaw,
            'date_display' => formatDateToRus($dateRaw),
            'label' => 'Редакция — ' . implode('; ', $items),
            'is_original' => false,
            'is_current' => ($dateRaw === $currentDate),
            'is_selected' => ($dateRaw === $selectedDate)
        ];
    }

    return [
        'options' => $options,
        'selected_date' => $selectedDate,
        'current_date' => $currentDate,
        'active_date' => $selectedDate
    ];
}

