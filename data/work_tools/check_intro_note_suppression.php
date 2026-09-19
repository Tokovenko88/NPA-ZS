<?php
/**
 * NPA-ZS | проверка правила «не дублировать Введён … у потомков».
 *
 * Прогоняет isIntroductionInheritedFromAncestor() на стабе PDO (SQL, который
 * реально использует функция) и проверяет сценарии:
 *   * элемент, введённый вместе с предком тем же НПА (та же дата) — примечание
 *     «Введён …» скрывается (на любой глубине);
 *   * элемент, введённый позже другим НПА (или тем же НПА, но другой датой) —
 *     примечание выводится;
 *   * предок, у которого только 'change'/'delete' — не основание для скрытия;
 *   * предок, изложенный в новой редакции ('new_redaction') — основание есть;
 *   * другой НПА в ту же дату — не совпадение;
 *   * цикл в parent_id не зацикливает обход (ограничение глубины);
 *   * граничные случаи: пустой valid_from, modified_by_id='base'.
 *
 * Запуск: php data/work_tools/check_intro_note_suppression.php
 */

// helpers/dates.php::parseDate() выдаёт предупреждение PHP 8.2
// (DateTime::getLastErrors() возвращает false, когда ошибок нет) — оно
// существовало и до этой правки и к проверяемой логике не относится.
error_reporting(E_ALL & ~E_WARNING);

$root = dirname(__DIR__, 2) . '/src/site/php/npazs';
require_once $root . '/helpers/dates.php';
require_once $root . '/ui/notes.php';

/** Стаб PDO-запроса: только SQL, который использует проверяемая функция. */
class StubStatement {
    private $sql;
    private $db;
    private $rows = [];
    private $pos = 0;

    public function __construct($sql, $db) {
        $this->sql = preg_replace('/\s+/', ' ', trim($sql));
        $this->db = $db;
    }

    public function execute($params = []) {
        if (strpos($this->sql, 'SELECT parent_id FROM npa_item WHERE id = ?') === 0) {
            $id = (int)$params[0];
            $parent = array_key_exists($id, $this->db->items) ? $this->db->items[$id] : null;
            $this->rows = ($parent === null || $parent['parent_id'] === null)
                ? []
                : [['parent_id' => $parent['parent_id']]];
        } elseif (strpos($this->sql, 'SELECT valid_from, mod_type, modified_by_id FROM npa_item_revision') === 0) {
            $id = (int)$params[0];
            $this->rows = array_key_exists($id, $this->db->revisions) ? $this->db->revisions[$id] : [];
        } else {
            throw new RuntimeException('Неожиданный SQL в стабе: ' . $this->sql);
        }
        $this->pos = 0;
        return true;
    }

    public function fetch($mode = null) {
        return array_key_exists($this->pos, $this->rows) ? $this->rows[$this->pos++] : false;
    }

    public function fetchAll($mode = null) {
        $rest = array_slice($this->rows, $this->pos);
        $this->pos = count($this->rows);
        return $rest;
    }
}

/** Стаб PDO: карта элементов (id => ['parent_id' => ...]) и ревизий (id => строки). */
class StubPdo {
    public $items = [];
    public $revisions = [];

    public function __construct(array $items, array $revisions) {
        $this->items = $items;
        $this->revisions = $revisions;
    }

    public function prepare($sql, $options = []) {
        return new StubStatement($sql, $this);
    }
}

$X = '33699_article_1_point_5';   // изменяющий НПА X
$Y = '41000_article_2_point_3';   // изменяющий НПА Y (другой)
$Z = '27777_article_3';           // изменяющий НПА Z (третий)
$D = '15.12.2017';
$LATER = '20.05.2018';

$passed = 0;
$failed = 0;

/**
 * Прогоняет один сценарий.
 *
 * @param string $name      Название сценария.
 * @param bool   $expected  Ожидаемый результат (true = примечание скрывается).
 * @param array  $items     id => ['parent_id' => ...].
 * @param array  $revisions id => список ревизий.
 * @param int    $itemId    Проверяемый элемент.
 * @param array  $addRev    Его 'add'-ревизия.
 */
function scenario($name, $expected, array $items, array $revisions, $itemId, array $addRev) {
    global $passed, $failed;
    $actual = isIntroductionInheritedFromAncestor(new StubPdo($items, $revisions), $itemId, $addRev);
    if ($actual === $expected) {
        $passed++;
        echo "  OK   $name\n";
    } else {
        $failed++;
        echo "  FAIL $name: ожидалось " . var_export($expected, true)
            . ', получено ' . var_export($actual, true) . "\n";
    }
}

function rev($validFrom, $modType, $modifiedBy) {
    return ['valid_from' => $validFrom, 'mod_type' => $modType, 'modified_by_id' => $modifiedBy];
}
echo "=== splitChangerIds ===\n";
$cases = [
    ['143532,143624', ['143532', '143624']],
    ['143532 , base ', ['143532']],
    ['base', []],
    ['', []],
    [null, []],
    ['33699_article_1_point_5', ['33699_article_1_point_5']],
];
foreach ($cases as $case) {
    $actual = splitChangerIds($case[0]);
    if ($actual === $case[1]) {
        $passed++;
        echo '  OK   splitChangerIds(' . var_export($case[0], true) . ")\n";
    } else {
        $failed++;
        echo '  FAIL splitChangerIds(' . var_export($case[0], true) . '): '
            . json_encode($actual) . ' != ' . json_encode($case[1]) . "\n";
    }
}

echo "=== сценарии ===\n";

// 1. Сам введённый элемент (статья 4): предков нет → примечание показывается.
scenario(
    'корневой элемент: предков нет — примечание показывается',
    false,
    [1000 => ['parent_id' => null]],
    [1000 => [rev($D, 'add', $X)]],
    1000, rev($D, 'add', $X)
);

// 2. Часть 1 внутри введённой статьи 4, тот же НПА и дата → скрываем.
scenario(
    'потомок 1-го уровня того же НПА и даты — примечание скрывается',
    true,
    [1000 => ['parent_id' => null], 1001 => ['parent_id' => 1000]],
    [1000 => [rev($D, 'add', $X)], 1001 => [rev($D, 'add', $X)]],
    1001, rev($D, 'add', $X)
);

// 3. Пункт внутри части внутри статьи (глубина 4) → скрываем.
scenario(
    'потомок 4-го уровня — примечание скрывается',
    true,
    [
        1000 => ['parent_id' => null],
        1001 => ['parent_id' => 1000],
        1002 => ['parent_id' => 1001],
        1003 => ['parent_id' => 1002],
    ],
    [
        1000 => [rev($D, 'add', $X)],
        1001 => [rev($D, 'add', $X)],
        1002 => [rev($D, 'add', $X)],
        1003 => [rev($D, 'add', $X)],
    ],
    1003, rev($D, 'add', $X)
);

// 4. Часть введена НПА X, элемент добавлен позже ДРУГИМ НПА Y → показываем.
scenario(
    'элемент добавлен позже другим НПА — примечание показывается',
    false,
    [1100 => ['parent_id' => null], 1101 => ['parent_id' => 1100]],
    [1100 => [rev($D, 'add', $X)], 1101 => [rev($LATER, 'add', $Y)]],
    1101, rev($LATER, 'add', $Y)
);

// 5. Тот же НПА, но другая дата добавления → показываем.
scenario(
    'тот же НПА, но другая дата вступления — примечание показывается',
    false,
    [1200 => ['parent_id' => null], 1201 => ['parent_id' => 1200]],
    [1200 => [rev($D, 'add', $X)], 1201 => [rev($LATER, 'add', $X)]],
    1201, rev($LATER, 'add', $X)
);

// 6. Предок изложен в новой редакции тем же НПА в ту же дату → скрываем.
scenario(
    'предок изложен в новой редакции (new_redaction) — скрывается',
    true,
    [1300 => ['parent_id' => null], 1301 => ['parent_id' => 1300]],
    [1300 => [rev($D, 'new_redaction', $X)], 1301 => [rev($D, 'add', $X)]],
    1301, rev($D, 'add', $X)
);
// 7. У предка в ту же дату только 'change' → не основание для скрытия.
scenario(
    "у предка только 'change' в ту же дату — примечание показывается",
    false,
    [1400 => ['parent_id' => null], 1401 => ['parent_id' => 1400]],
    [1400 => [rev($D, 'change', $X)], 1401 => [rev($D, 'add', $X)]],
    1401, rev($D, 'add', $X)
);

// 8. modified_by_id предка — список, у элемента — один из них → скрываем.
scenario(
    'пересечение modified_by_id (список у предка) — скрывается',
    true,
    [1500 => ['parent_id' => null], 1501 => ['parent_id' => 1500]],
    [1500 => [rev($D, 'add', $X . ',' . $Y)], 1501 => [rev($D, 'add', $Y)]],
    1501, rev($D, 'add', $Y)
);

// 9. Разные НПА в одну и ту же дату → показываем.
scenario(
    'предок введён другим НПА в ту же дату — примечание показывается',
    false,
    [1600 => ['parent_id' => null], 1601 => ['parent_id' => 1600]],
    [1600 => [rev($D, 'add', $Z)], 1601 => [rev($D, 'add', $X)]],
    1601, rev($D, 'add', $X)
);

// 10. Цикл в parent_id → обход завершается, примечание показывается.
scenario(
    'цикл parent_id: обход ограничен глубиной',
    false,
    [1700 => ['parent_id' => 1701], 1701 => ['parent_id' => 1700]],
    [1700 => [rev($D, 'change', $X)], 1701 => [rev($D, 'change', $X)]],
    1700, rev($D, 'add', $X)
);

// 11. У add-ревизии нет valid_from → сравнивать нечего, показываем.
scenario(
    'add-ревизия без valid_from — примечание показывается',
    false,
    [1800 => ['parent_id' => null], 1801 => ['parent_id' => 1800]],
    [1800 => [rev($D, 'add', $X)], 1801 => []],
    1801, rev(null, 'add', $X)
);

// 12. modified_by_id='base' → не скрываем.
scenario(
    "modified_by_id='base' — примечание показывается",
    false,
    [1900 => ['parent_id' => null], 1901 => ['parent_id' => 1900]],
    [1900 => [rev($D, 'add', $X)], 1901 => []],
    1901, rev($D, 'add', 'base')
);

// 13. Совпадение с ДАЛЬНИМ предком (промежуточный изменён другим НПА).
scenario(
    'совпадение с дальним предком — примечание скрывается',
    true,
    [
        2000 => ['parent_id' => null],
        2001 => ['parent_id' => 2000],
        2002 => ['parent_id' => 2001],
    ],
    [
        2000 => [rev($D, 'add', $X)],
        2001 => [rev($LATER, 'change', $Y)],
        2002 => [rev($D, 'add', $X)],
    ],
    2002, rev($D, 'add', $X)
);

echo "\nитог: $passed проверок пройдено, $failed провалено\n";
exit($failed === 0 ? 0 : 1);