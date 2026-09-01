#!/usr/bin/env python3
from pathlib import Path

TREE = Path(__file__).resolve().parents[2] / "src/site/php/npazs/render/tree.php"
BAD = "            }\n                }\n            }\n            foreach (($parentData['paragraphs'] ?? []) as $block) {"
GOOD = "            }\n            foreach (($parentData['paragraphs'] ?? []) as $block) {"

text = TREE.read_text(encoding="utf-8")
if BAD in text:
    TREE.write_text(text.replace(BAD, GOOD, 1), encoding="utf-8")
    print("tree braces repaired")
else:
    print("tree braces already correct")
