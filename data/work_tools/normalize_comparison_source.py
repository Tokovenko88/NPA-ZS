#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
COMPARE = ROOT / 'src/site/php/npazs/content/compare.php'

COMPARE_RE = re.compile(r"(?ms)^    \$changerItemIdSet = \[\];.*?^    \}\n(?=    // Если дочерний элемент)")
COMPARE_NEW = '''    $changerItemIdSet = [];
    foreach ($changerIds as $cid) {
        foreach (array_filter(array_map('trim', explode(',', $cid))) as $c) {
            if ($c === 'base') continue;

            // modified_by_id хранит внутренний числовой npa_item.id,
            // not_valid хранит стабильный строковый item_id.
            $changerItemIdSet[$c] = true;
            if (ctype_digit($c)) {
                $stmtChanger = $pdo->prepare(
                    'SELECT item_id FROM npa_item WHERE id = ? LIMIT 1'
                );
                $stmtChanger->execute([(int)$c]);
                $changerItemId = $stmtChanger->fetchColumn();
                if ($changerItemId) {
                    $changerItemIdSet[(string)$changerItemId] = true;
                }
            }
        }
    }
    // Если дочерний элемент'''

compare = COMPARE.read_text(encoding='utf-8')
if 'SELECT item_id FROM npa_item WHERE id = ? LIMIT 1' not in compare:
    if len(COMPARE_RE.findall(compare)) != 1:
        raise SystemExit('compare target not found exactly once')
    COMPARE.write_text(COMPARE_RE.sub(COMPARE_NEW, compare, count=1), encoding='utf-8')
    print('patched compare.php')
else:
    print('compare.php already normalized')
