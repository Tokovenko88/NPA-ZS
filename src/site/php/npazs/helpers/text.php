<?php
/**
 * NPA-ZS | helpers/text.php — текстовые и падежные утилиты.
 *
 * Функции: normalizeHighlightText, getDisplayText, getExpiryGenderSuffix,
 *          getLocalElementGenitive, normalizeHighlights.
 * normalizeHighlights канонизирует JSON-подсветку редакций в структуру
 * previous_edition{deletion,difference} / current_edition{addition,difference}.
 * getDisplayText учитывает no_name и утрату силы элемента.
 * Источник: строки 47-54, 2580-2622, 2739-2771, 3346-3394 монолита snippet.php.
 */


function normalizeHighlightText($text) {
    if (empty($text)) return '';
    $text = str_replace(['–', '—', '‑', '‐'], '-', $text);
    $text = preg_replace('/\s+/', ' ', $text);
    return trim($text);
}

function getDisplayText($item, $isExpired = false, $noNameIds = [], $hideSectionPrefix = false) {
    $type = $item['item_type'];
    $number = $item['display_number'] ?? $item['item_number'] ?? '';
    $head = $item['item_head'];
    $itemId = $item['item_id'] ?? '';
    switch ($type) {
        case 'preamble':    $display = 'Преамбула'; break;
        case 'chapter':     $display = 'Глава ' . $number . ($head ? '. ' . $head : ''); break;
        case 'section':
            if ($hideSectionPrefix) {
                $display = $number . ($head ? '. ' . $head : '');
            } else {
                $display = 'Раздел ' . $number . ($head ? '. ' . $head : '');
            }
            break;
        case 'article':     $display = 'Статья ' . $number . ($head ? '. ' . $head : ''); break;
        case 'part':        $display = 'Часть ' . $number . ($head ? '. ' . $head : ''); break;
        case 'point':       $display = 'Пункт ' . $number . ($head ? '. ' . $head : ''); break;
        case 'subpoint':    $display = 'Подпункт ' . $number . ($head ? '. ' . $head : ''); break;
        case 'appendix':
        case 'nested_appendix': $display = 'Приложение ' . $number . ($head ? '. ' . $head : ''); break;
        case 'structured_table':
            if (!empty($head)) {
                $display = 'Таблица ' . $number . ($head ? '. ' . $head : '');
            } else {
                $display = '';
            }
            break;
        default:            $display = ''; break;
    }
    if ($isExpired && !empty($display)) {
        $suffix = '';
        if ($type === 'article') $suffix = 'а';
        elseif ($type === 'part') $suffix = 'а';
        elseif ($type === 'chapter') $suffix = 'а';
        elseif ($type === 'section') $suffix = 'а';
        elseif ($type === 'appendix' || $type === 'nested_appendix') $suffix = 'о';
        elseif ($type === 'structured_table') $suffix = 'ы';
        $display .= ' (Утратил' . $suffix . ' силу)';
    }
    return $display;
}

function getExpiryGenderSuffix($type) {
     switch ($type) {
            case 'article': return 'а';
            case 'part':    return 'а';
            case 'chapter': return 'а';
            case 'section': return 'а';
            case 'preamble':return 'а';
            case 'appendix':return 'о';
            case 'point':   return '';
            case 'subpoint':return '';
            default:        return '';
        }
}

function getLocalElementGenitive($itemType, $itemNumber) {
        $map = [
            'preamble'  => 'преамбулы',
            'chapter'   => 'главы',
            'section'   => 'раздела',
            'article'   => 'статьи',
            'part'      => 'части',
            'point'     => 'пункта',
            'subpoint'  => 'подпункта',
            'appendix'  => 'приложения',
            'nested_appendix' => 'приложения'
        ];
        $base = $map[$itemType] ?? 'элемента';
        if (in_array($itemType, ['preamble'])) {
            return $base;
        }
                return $base . ' ' . trim($itemNumber, '. ');
}

function normalizeHighlights($highlights) {
    $default = [
        'previous_edition' => ['deletion' => [], 'difference' => []],
        'current_edition'  => ['addition' => [], 'difference' => []]
    ];
    if (empty($highlights)) {
        return $default;
    }
    $toArray = function($data) use (&$toArray) {
        if (is_object($data)) {
            $data = (array) $data;
        }
        if (is_array($data)) {
            foreach ($data as $key => $value) {
                $data[$key] = $toArray($value);
            }
        }
        return $data;
    };
    if (is_string($highlights)) {
        $decoded = json_decode($highlights, true);
        if (is_array($decoded)) {
            $highlights = $decoded;
        } else {
            return $default;
        }
    }
    $highlights = $toArray($highlights);
    if (!is_array($highlights) || empty($highlights)) {
        return $default;
    }
    if (!isset($highlights['previous_edition']) || !is_array($highlights['previous_edition'])) {
        $highlights['previous_edition'] = [];
    }
    if (!isset($highlights['current_edition']) || !is_array($highlights['current_edition'])) {
        $highlights['current_edition'] = [];
    }
    foreach (['deletion', 'difference'] as $key) {
        if (!isset($highlights['previous_edition'][$key]) || !is_array($highlights['previous_edition'][$key])) {
            $highlights['previous_edition'][$key] = [];
        }
    }
    foreach (['addition', 'difference'] as $key) {
        if (!isset($highlights['current_edition'][$key]) || !is_array($highlights['current_edition'][$key])) {
            $highlights['current_edition'][$key] = [];
        }
    }
    return $highlights;
}
