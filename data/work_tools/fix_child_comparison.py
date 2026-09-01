#!/usr/bin/env python3
"""Repair child-only revision detection in comparison/tree modules.

The selected document revision may change only child elements. In that case:
- the parent may have no new npa_item_revision;
- a structural parent revision may have no own paragraphs, while its body lives
  in a content revision;
- not_valid stores stable item_id values, while modified_by_id may contain
  internal numeric npa_item.id values.

This script is intentionally idempotent so CI can run it on every build.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
COMPARE = ROOT / "src/site/php/npazs/content/compare.php"
TREE = ROOT / "src/site/php/npazs/render/tree.php"


def patch_compare(text: str) -> str:
    if "$loadBodyChildRefs = function($revisionId) use ($pdo)" not in text:
        pattern = re.compile(
            r"    // Только child_ref текущего body\..*?"
            r"    if \(empty\(\$bodyChildIds\)\) \{\n"
            r"        return \[\];\n"
            r"    \}\n",
            re.S,
        )
        replacement = r'''    // Только child_ref актуального body. У структурной ревизии может не быть
    // собственных paragraph-записей: в этом случае тело хранится в последней
    // content-ревизии, как и в getItemTree()/getElementHtmlById().
    $loadBodyChildRefs = function($revisionId) use ($pdo) {
        $stmt = $pdo->prepare('
            SELECT ref_item_internal_id
            FROM npa_paragraph
            WHERE rev_id = ?
              AND block_type = 'child_ref'
              AND ref_item_internal_id IS NOT NULL
            ORDER BY sort_order
        ');
        $stmt->execute([$revisionId]);
        $ids = [];
        foreach ($stmt->fetchAll() as $row) {
            $childId = (int)$row['ref_item_internal_id'];
            if ($childId > 0 && !isset($ids[$childId])) {
                $ids[$childId] = true;
            }
        }
        return $ids;
    };

    $bodyChildIds = $loadBodyChildRefs($parentRevisionId);
    if (empty($bodyChildIds)) {
        // Структурная ревизия может быть без body. Берём именно последнюю
        // content-ревизию, действовавшую на дату parentRevision.
        $stmtParentRevision = $pdo->prepare(
            'SELECT valid_from FROM npa_item_revision WHERE rev_id = ? LIMIT 1'
        );
        $stmtParentRevision->execute([$parentRevisionId]);
        $parentRevisionValidFrom = $stmtParentRevision->fetchColumn();
        if ($parentRevisionValidFrom) {
            $contentRevision = getLastContentRevision(
                $pdo,
                $internal_item_id,
                $parentRevisionValidFrom
            );
            if ($contentRevision) {
                $bodyChildIds = $loadBodyChildRefs($contentRevision['rev_id']);
            }
        }
    }
    if (empty($bodyChildIds)) {
        return [];
    }
'''
        # The replacement above uses single quotes inside a PHP single-quoted SQL
        # string. Convert those SQL literals to the escaped form used by the module.
        replacement = replacement.replace("AND block_type = 'child_ref'", "AND block_type = \\'child_ref\\'")
        text, count = pattern.subn(replacement, text, count=1)
        if count != 1:
            raise RuntimeError("compare.php body-ref block not found")

    if "SELECT id, item_id FROM npa_item WHERE npa_id IN ($placeholders)" not in text:
        marker = re.compile(
            r"    // Если дочерний элемент утратил силу из-за самого родителя, not_valid\n"
            r"    // содержит item_id родителя, а не обязательно item_id элемента-источника НПА\.\n"
            r"    if \(!empty\(\$parent\['item_id'\]\) && \$parent\['item_id'\] !== 'base'\) \{\n"
            r"        \$changerItemIdSet\[\$parent\['item_id'\]\] = true;\n"
            r"    \}\n",
        )
        replacement = r'''    // При выбранной редакции родитель мог вообще не получить собственной
    // ревизии: НПА меняет только его child_ref. Поэтому источником удаления
    // может быть item из выбранной revision_info, которого нет в parent.modified_by_id.
    if (!empty($selectedRevisionNpaIds)) {
        $placeholders = implode(',', array_fill(0, count($selectedRevisionNpaIds), '?'));
        $stmtSelectedSources = $pdo->prepare(
            "SELECT id, item_id FROM npa_item WHERE npa_id IN ($placeholders)"
        );
        $stmtSelectedSources->execute(array_values($selectedRevisionNpaIds));
        foreach ($stmtSelectedSources->fetchAll() as $sourceRow) {
            if (!empty($sourceRow['id'])) {
                $changerItemIdSet[(string)$sourceRow['id']] = true;
            }
            if (!empty($sourceRow['item_id'])) {
                $changerItemIdSet[(string)$sourceRow['item_id']] = true;
            }
        }
    }

    // Если дочерний элемент утратил силу из-за самого родителя, not_valid
    // содержит item_id родителя, а не обязательно item_id элемента-источника НПА.
    if (!empty($parent['item_id']) && $parent['item_id'] !== 'base') {
        $changerItemIdSet[$parent['item_id']] = true;
    }
'''
        text, count = marker.subn(replacement, text, count=1)
        if count != 1:
            raise RuntimeError("compare.php parent-source block not found")

    return text


def patch_tree(text: str) -> str:
    if "// НПА выбранной редакции может менять только дочерние элементы." in text:
        return text

    marker = re.compile(
        r"            foreach \(array_filter\(array_map\('trim', explode\(',', \(string\)\(\$parentData\['modified_by_id'\] \?\? ''\)\)\)\) as \$sourceId\) \{.*?"
        r"            \}\n",
        re.S,
    )
    replacement = r'''            foreach (array_filter(array_map('trim', explode(',', (string)($parentData['modified_by_id'] ?? '')))) as $sourceId) {
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

            // НПА выбранной редакции может менять только дочерние элементы.
            // Тогда у родителя modified_by_id остаётся от старой ревизии,
            // но not_valid ребёнка всё равно должен ссылаться на источник
            // текущей выбранной редакции.
            if (!empty($selectedRevisionNpaIds)) {
                $placeholders = implode(',', array_fill(0, count($selectedRevisionNpaIds), '?'));
                $stmtSelectedSources = $pdo->prepare(
                    "SELECT id, item_id FROM npa_item WHERE npa_id IN ($placeholders)"
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
'''
    text, count = marker.subn(replacement, text, count=1)
    if count != 1:
        raise RuntimeError("tree.php parent-source block not found")
    return text


def main() -> None:
    compare_text = COMPARE.read_text(encoding="utf-8")
    tree_text = TREE.read_text(encoding="utf-8")
    new_compare = patch_compare(compare_text)
    new_tree = patch_tree(tree_text)
    if new_compare != compare_text:
        COMPARE.write_text(new_compare, encoding="utf-8")
    if new_tree != tree_text:
        TREE.write_text(new_tree, encoding="utf-8")
    print(f"compare changed: {new_compare != compare_text}")
    print(f"tree changed: {new_tree != tree_text}")


if __name__ == "__main__":
    main()
