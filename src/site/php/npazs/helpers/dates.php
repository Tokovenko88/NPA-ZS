<?php
/**
 * NPA-ZS | helpers/dates.php — работа с датами и «действием редакции».
 *
 * Функции: parseDate, isRevisionCurrent, formatDateToRus, formatRusDate.
 * ВАЖНО: isRevisionCurrent — эталонная семантика действующей редакции
 * (valid_to >= asOfDate); используется во всех is_current/is_expired.
 * Не менять без сверки с docs/site_output.md §8.3.
 * Источник: строки 55-96, 511-529 монолита snippet.php.
 */

function parseDate($dateStr) {
    if (empty($dateStr)) return null;
    $dateStr = trim($dateStr);
    $originalTz = date_default_timezone_get();
    date_default_timezone_set('UTC');
    try {
        if (preg_match('/^\d{4}-\d{2}-\d{2}$/', $dateStr)) {
            $dt = DateTime::createFromFormat('Y-m-d', $dateStr);
            if ($dt && $dt->getLastErrors()['warning_count'] === 0) {
                date_default_timezone_set($originalTz);
                return $dt;
            }
        }
        if (preg_match('/^\d{2}\.\d{2}\.\d{4}$/', $dateStr)) {
            $dt = DateTime::createFromFormat('d.m.Y', $dateStr);
            if ($dt && $dt->getLastErrors()['warning_count'] === 0) {
                date_default_timezone_set($originalTz);
                return $dt;
            }
        }
        foreach (['d.m.Y', 'Y-m-d'] as $fmt) {
            try {
                $dt = DateTimeImmutable::createFromFormat($fmt, $dateStr);
                if ($dt && $dt->format($fmt) === $dateStr) {
                    date_default_timezone_set($originalTz);
                    return $dt;
                }
            } catch (Exception $e) {
                continue;
            }
        }
    } finally {
        date_default_timezone_set($originalTz);
    }
    return null;
}

function isRevisionCurrent($isDocExpired, $validToRaw, $validFromRaw, $asOfDate) {
    if ($isDocExpired) return false;
    return (is_null($validToRaw) || $validToRaw >= $asOfDate) && $validFromRaw <= $asOfDate;
}

function formatDateToRus($dateStr) {
    if (empty($dateStr)) return '';
    $dt = parseDate($dateStr);
    return $dt ? $dt->format('d.m.Y') : $dateStr;
}

function formatRusDate($dateStr, $dateFormat) {
    if (empty($dateStr)) return '';
    $dt = parseDate($dateStr);
    if (!$dt) return $dateStr;
    $day = (int)$dt->format('d');
    $month = (int)$dt->format('m');
    $year = $dt->format('Y');
    $months = [1 => 'января', 2 => 'февраля', 3 => 'марта', 4 => 'апреля', 5 => 'мая', 6 => 'июня',7 => 'июля', 8 => 'августа', 9 => 'сентября', 10 => 'октября', 11 => 'ноября', 12 => 'декабря'];
    $monthName = $months[$month] ?? '';
    $dayFormatted = ($dateFormat == 0) ? str_pad($day, 2, '0', STR_PAD_LEFT) : $day;
    return $dayFormatted . ' ' . $monthName . ' ' . $year . ' года';
}

