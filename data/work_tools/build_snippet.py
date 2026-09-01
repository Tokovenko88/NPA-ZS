#!/usr/bin/env python3
"""Сборка единого скрипта сниппета из модулей src/site/php/npazs/.

Модули — источник истины. Скрипт читает точку входа HtmlFromNpaZS.php
(«рецепт сборки»), заменяет каждый require на содержимое соответствующего
файла (без <?php и докблока) и записывает src/site/php/snippet.php —
единственный большой скрипт для сайта, как и раньше.

Сборка детерминирована (без меток времени): повторный запуск не меняет файл.

Режимы:
  python data/work_tools/build_snippet.py            собрать и записать
  python data/work_tools/build_snippet.py --check    собрать в память, сравнить, не писать
  python data/work_tools/build_snippet.py --watch    следить за модулями, пересобирать при изменении
"""
import argparse
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "src" / "site" / "php" / "npazs"
ENTRY = SRC_DIR / "HtmlFromNpaZS.php"
OUT = ROOT / "src" / "site" / "php" / "snippet.php"

REQ = re.compile(r"^\s*require(_once)?\s+__DIR__\s*\.\s*'([^']+)'\s*;\s*$")


def read_body_lines(path: Path) -> list:
    """Содержимое модуля без <?php, докблока и пустых строк после него."""
    lines = path.read_bytes().decode("utf-8").splitlines()
    if not lines or not lines[0].lstrip().startswith("<?php"):
        raise ValueError(f"{path.name}: файл должен начинаться с <?php")
    i = 1
    if i < len(lines) and lines[i].lstrip().startswith("/**"):
        while i < len(lines) and lines[i].strip() != "*/":
            i += 1
        i += 1  # за '*/'
        while i < len(lines) and not lines[i].strip():
            i += 1
    return lines[i:]


def required_modules() -> list:
    """Относительные пути модулей в порядке require-строк точки входа."""
    mods = []
    for line in ENTRY.read_bytes().decode("utf-8").splitlines():
        m = REQ.match(line)
        if m:
            mods.append(m.group(2).lstrip("/"))
    if not mods:
        raise RuntimeError("в точке входа не найдено ни одного require")
    return mods


def build() -> bytes:
    mods = required_modules()
    for rel in mods:
        if not (SRC_DIR / rel).exists():
            raise FileNotFoundError(f"модуль из точки входа не найден: {rel}")

    entry_lines = ENTRY.read_bytes().decode("utf-8").splitlines()
    if not entry_lines or not entry_lines[0].lstrip().startswith("<?php"):
        raise ValueError("точка входа должна начинаться с <?php")
    i = 1
    if not entry_lines[i].lstrip().startswith("/**"):
        raise ValueError("ожидается докблок точки входа")
    while entry_lines[i].strip() != "*/":
        i += 1
    i += 1
    while i < len(entry_lines) and not entry_lines[i].strip():
        i += 1

    parts = ["<?php"]
    while i < len(entry_lines):
        line = entry_lines[i]
        m = REQ.match(line)
        if m:
            body = read_body_lines(SRC_DIR / m.group(2).lstrip("/"))
            parts += body
            if parts and parts[-1].strip():
                parts.append("")
        else:
            parts.append(line)
        i += 1

    return ("\n".join(parts) + "\n").encode("utf-8")
def watch(interval: float = 2.0) -> None:
    """Пересборка при любом изменении файлов в src/site/php/npazs/."""
    def snapshot():
        sig = {}
        for p in SRC_DIR.rglob("*.php"):
            st = p.stat()
            sig[str(p)] = (st.st_mtime_ns, st.st_size)
        return sig

    print(f"[watch] слежу за {SRC_DIR} (Ctrl+C — выход)")
    last = snapshot()
    while True:
        time.sleep(interval)
        now = snapshot()
        if now == last:
            continue
        changed = sorted(
            Path(k).name for k in set(now) | set(last) if now.get(k) != last.get(k)
        )
        last = now
        content = build()
        if not OUT.exists() or OUT.read_bytes() != content:
            OUT.write_bytes(content)
            stamp = time.strftime("%H:%M:%S")
            print(f"[watch] {stamp} изменены {changed} -> snippet.php пересобран")
        else:
            print(f"[watch] изменение {changed} не повлияло на результат сборки")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="собрать и сравнить, не записывать")
    ap.add_argument("--watch", action="store_true", help="следить за модулями и пересобирать")
    args = ap.parse_args()

    if args.watch:
        watch()
        return

    content = build()
    if args.check:
        if not OUT.exists():
            print(f"{OUT.name} отсутствует")
            raise SystemExit(1)
        same = OUT.read_bytes() == content
        print(f"сборка: {len(content.splitlines())} строк; совпадает с {OUT.name}: {same}")
        raise SystemExit(0 if same else 2)

    if OUT.exists() and OUT.read_bytes() == content:
        print(f"без изменений: {OUT.name} ({len(content.splitlines())} строк)")
        return
    OUT.write_bytes(content)
    print(f"собрано: {OUT.relative_to(ROOT)} ({len(content.splitlines())} строк)")


if __name__ == "__main__":
    main()

