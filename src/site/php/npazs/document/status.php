<?php
/**
 * NPA-ZS | document/status.php — статус документа и активные редакции на дату.
 *
 * Функции: getDocMaxDate, getDocumentStatus, getActiveRevisionsForDate,
 *          getExactRevisionsForDate.
 * getDocumentStatus возвращает status=actual|expired и данные об утрате силы.
 * Источник: строки 97-113, 1945-2022 монолита snippet.php.
 */

function getDocMaxDate(PDO $pdo, $npa_id, $asOfDate = null) {
    $stmtMax = $pdo->prepare("
        SELECT MAX(valid_from) as max_date FROM (
            SELECT valid_from FROM npa_base WHERE npa_id = ?
            UNION
            SELECT revision_date_valid FROM npa_revision_info WHERE base_npa_id = ?
        ) AS dates
    ");
    $stmtMax->execute([$npa_id, $npa_id]);
    $maxRow = $stmtMax->fetch();
    $maxDate = $maxRow['max_date'] ?? null;
    if ($asOfDate && ($maxDate === null || $asOfDate > $maxDate)) {
        $maxDate = $asOfDate;
    }
    return $maxDate;
}

function getDocumentStatus(PDO $pdo, $npa_id, $viewDateSql) {
    $stmt = $pdo->prepare("SELECT valid_from, not_valid, not_valid_note, not_valid_npa_id, date_format FROM npa_base WHERE npa_id = ?");
    $stmt->execute([$npa_id]);
    $base = $stmt->fetch();
    if (!$base) {
        return ['status' => 'unknown', 'message' => ''];
    }
    $validFrom = $base['valid_from'];
    $notValid = $base['not_valid'] ?? null;
    $notValidNote = $base['not_valid_note'] ?? '';
    $dateFormat = (int)$base['date_format'];
    if ($validFrom && $viewDateSql < $validFrom) {
        $formattedDate = formatRusDate($validFrom, $dateFormat);
        return [
            'status' => 'future',
            'message' => "Документ вступает в силу с {$formattedDate}"
        ];
    }
    if ($notValid) {
        $dtNotValid = parseDate($notValid);
        if ($dtNotValid) {
            $dtNotValid->modify('+1 day');
            $formattedDate = formatRusDate($dtNotValid->format('Y-m-d'), $dateFormat);
        } else {
            $formattedDate = formatRusDate($notValid, $dateFormat);
        }
        $maxDate = getDocMaxDate($pdo, $npa_id, $viewDateSql);
        $isAlreadyExpired = ($maxDate !== null && $maxDate >= $notValid);
        $msg = $isAlreadyExpired ? "Документ утратил силу с {$formattedDate}" : "Документ утрачивает силу с {$formattedDate}";
        $cancellingNpaId = $base['not_valid_npa_id'] ?? null;
        if ($cancellingNpaId) {
            $stmtCancel = $pdo->prepare("SELECT npa_type, npa_number, npa_url, date_passed FROM npa_base WHERE npa_id = ?");
            $stmtCancel->execute([$cancellingNpaId]);
            $cancellingNpa = $stmtCancel->fetch();
            if ($cancellingNpa) {
                $type = ($cancellingNpa['npa_type'] === 'law') ? 'Закон' : 'Постановление Законодательного Собрания';
                $datePassed = formatRusDate($cancellingNpa['date_passed'], $dateFormat);
                $url = $cancellingNpa['npa_url'] ?? '';
                $cancellingText = $type . ' города Севастополя № ' . $cancellingNpa['npa_number'] . ' от ' . $datePassed;
                if ($url) {
                    $cancellingText = '<a href="' . $url . '" target="_blank" class="npa-revision-link">' . $cancellingText . '</a>';
                }
                $msg .= ' — ' . $cancellingText;
            }
        }
        if (!empty($notValidNote)) {
            $msg .= ' (' . htmlspecialchars($notValidNote) . ')';
        }
        return [
            'status' => $isAlreadyExpired ? 'expired' : 'future_expired',
            'message' => $msg
        ];
    }
    return ['status' => 'active', 'message' => ''];
}

function getActiveRevisionsForDate(PDO $pdo, $npa_id, $date) {
    $stmt = $pdo->prepare("
        SELECT * FROM npa_revision_info
        WHERE base_npa_id = ?
          AND revision_date_valid <= ?
        ORDER BY revision_date_valid ASC, revision_number ASC
    ");
    $stmt->execute([$npa_id, $date]);
    return $stmt->fetchAll();
}

function getExactRevisionsForDate(PDO $pdo, $npa_id, $date) {
    $stmt = $pdo->prepare("
        SELECT * FROM npa_revision_info
        WHERE base_npa_id = ?
          AND revision_date_valid = ?
        ORDER BY revision_number ASC
    ");
    $stmt->execute([$npa_id, $date]);
    return $stmt->fetchAll();
}

