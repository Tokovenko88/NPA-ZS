#!/usr/bin/env python3
from pathlib import Path

TREE = Path(__file__).resolve().parents[2] / "src/site/php/npazs/render/tree.php"
text = TREE.read_text(encoding="utf-8")

if "// НПА выбранной редакции может менять только дочерние элементы." in text:
    print("selected child sources already present")
    raise SystemExit(0)

marker = """            foreach (array_filter(array_map('trim', explode(',', (string)($parentData['modified_by_id'] ?? '')))) as $sourceId) {
                if ($sourceId === 'base') continue;

                // modified_by_id хранит внутренний числовой npa_item.id,
                // not_valid хранит стабильный строковый item_id.
                $parentSources[$sourceId] = true;
                if (ctype_digit($sourceId)) {
                    $stmtSource = $pdo->prepare(
                        'SELECT item_id FROM npa_item WHERE id = ? LIMIT 1'
                    );
                    $stmtSource->execute([(int)$sourceId]);
                    $sourceItemId = $stmtSource->fetchColumn();
                    if ($sourceItemId) {
                        $parentSources[(string)$sourceItemId] = true;
                    }
                }
            }
"""

addition = """
            // НПА выбранной редакции может менять только дочерние элементы.
            // Тогда у родителя modified_by_id остаётся от старой ревизии,
            // но not_valid ребёнка всё равно должен ссылаться на источник
            // текущей выбранной редакции.
            if (!empty($selectedRevisionNpaIds)) {
                $placeholders = implode(',', array_fill(0, count($selectedRevisionNpaIds), '?'));
                $stmtSelectedSources = $pdo->prepare(
                    \"SELECT id, item_id FROM npa_item WHERE npa_id IN ($placeholders)\"
                );
                $stmtSelectedSources->execute(array_values($selectedRevisionNpaIds));
                foreach ($stmtSelectedSources->fetchAll() as $sourceRow) {
                    if (!empty($sourceRow['id'])) {
                        $parentSources[(string)$sourceRow['id']] = true;
                    }
                    if (!empty($sourceRow['item_id'])) {
                        $parentSources[(string)$sourceRow['item_id']] = true;
                    }
                }
            }
"""

if marker not in text:
    raise SystemExit("tree parent source block not found exactly once")

TREE.write_text(text.replace(marker, marker + addition, 1), encoding="utf-8")
print("selected child sources added to tree")
