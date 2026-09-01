#!/usr/bin/env python3
"""Normalize comparison source identifiers in the PHP source modules.

npa_item_revision.modified_by_id stores internal numeric npa_item.id values,
while npa_item_revision.not_valid stores stable string item_id values.  The
comparison/tree logic must therefore keep the original value and also add its
stable item_id equivalent before comparing against not_valid.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]

COMPARE = ROOT / "src" / "site" / "php" / "npazs" / "content" / "compare.php"
TREE = ROOT / "src" / "site" / "php" / "npazs" / "render" / "tree.php"

COMPARE_RE = re.compile(
    r"(?ms)^    \$changerItemIdSet = \[\];\n"
    r"    foreach \(\$changerIds as \$cid\) \{\n"
    r"        foreach \(array_filter\(array_map\('trim', explode\(',', \$cid\)\)\) as \$c\) \{\n"
    r"            if \(\$c !== 'base'\) \{\n"
    r"                \$changerItemIdSet\[\$c\] = true;\n"
    r"            \}\n"
    r"        \}\n"
    r"    \}\n"
)

COMPARE_REPLACEMENT = """    $changerItemIdSet = [];
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
"""

TREE_RE = re.compile(
    r"(?ms)^(\s*)foreach \(array_filter\(array_map\('trim', explode\(',', \(string\)\(\$parentData\['modified_by_id'\] \?\? ''\)\)\)\) as \$sourceId\) \{\n"
    r".*?^\1\}\n(?=\s*foreach \(\(\$parentData\['paragraphs'\])"
)

TREE_REPLACEMENT = """            foreach (array_filter(array_map('trim', explode(',', (string)($parentData['modified_by_id'] ?? '')))) as $sourceId) {
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


def replace_once(path: Path, pattern: re.Pattern[str], replacement: str, label: str) -> bool:
    text = path.read_text(encoding="utf-8")
    matches = list(pattern.finditer(text))
    if not matches:
        return False
    if len(matches) != 1:
        raise SystemExit(f"{label}: expected exactly one target, found {len(matches)}")
    path.write_text(pattern.sub(replacement, text, count=1), encoding="utf-8")
    print(f"patched {path.relative_to(ROOT)}")
    return True


def main() -> None:
    compare_changed = replace_once(COMPARE, COMPARE_RE, COMPARE_REPLACEMENT, "compare")
    if not compare_changed:
        current = COMPARE.read_text(encoding="utf-8")
        if "SELECT item_id FROM npa_item WHERE id = ? LIMIT 1" not in current:
            raise SystemExit("compare: target block not found and normalization marker is absent")
        print("compare: already normalized")

    tree_changed = replace_once(TREE, TREE_RE, TREE_REPLACEMENT, "tree")
    if not tree_changed:
        current = TREE.read_text(encoding="utf-8")
        if "SELECT item_id FROM npa_item WHERE id = ? LIMIT 1" not in current:
            raise SystemExit("tree: target block not found and normalization marker is absent")
        print("tree: already normalized")


if __name__ == "__main__":
    main()
