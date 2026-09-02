#!/usr/bin/env python3
"""Сборка единого скрипта сниппета из модулей src/site/php/npazs/.

Модули — источник истины. Скрипт читает точку входа HtmlFromNpaZS.php
(«рецепт сборки»), заменяет каждый require на содержимое соответствующего
файла (без <?php, докблока и PHP-комментариев //, #, /* */) и записывает
src/site/php/snippet.php — единственный большой скрипт для сайта.

Комментарии удаляются с учётом строковых литералов и регулярных выражений,
чтобы '#' внутри '/.../' или одиночных/двойных кавычек не пострадал.

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


def strip_php_comments(src: str) -> str:
    """Удаляет //, # и /* */ комментарии с учётом строк и регулярных выражений.

    Состояния:
      - CODE: обычный PHP-код
      - SQ:   одиночная кавычка (без интерполяции)
      - DQ:   двойная кавычка (с поддержкой \\{$var\\} и простых экранирований)
      - RE:   регулярное выражение /.../[flags] (PCRE-флаги после /)
      - LC:   строчный комментарий // или # до конца строки
      - BC:   блочный комментарий /* ... */
    """
    n = len(src)
    i = 0
    out = []
    state = "CODE"
    last_non_ws = ""  # последний значащий символ в CODE для эвристики регулярок

    def prev_code_char(j: int) -> str:
        """Предыдущий непустой символ в CODE-контексте перед позицией j в out."""
        k = len(out) - 1
        while k >= 0 and out[k] in " \t\r\n":
            k -= 1
        return out[k] if k >= 0 else last_non_ws

    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""

        if state == "CODE":
            if c == "/" and nxt == "/":
                state = "LC"
                i += 2
                continue
            if c == "#":
                state = "LC"
                i += 1
                continue
            if c == "/" and nxt == "*":
                state = "BC"
                i += 2
                continue
            if c == "'":
                state = "SQ"
                out.append(c)
                i += 1
                continue
            if c == '"':
                state = "DQ"
                out.append(c)
                i += 1
                continue
            if c == "/":
                prev = prev_code_char(i)
                if prev in "(=,[;:?&|%<>!~^{}+-*":
                    state = "RE"
                    i += 1
                    continue
            if c not in " \t\r\n":
                last_non_ws = c
            out.append(c)
            i += 1
            continue

        if state == "SQ":
            out.append(c)
            if c == "\\" and nxt:
                out.append(nxt)
                i += 2
                continue
            if c == "'":
                state = "CODE"
            i += 1
            continue

        if state == "DQ":
            out.append(c)
            if c == "\\" and nxt:
                out.append(nxt)
                i += 2
                continue
            if c == "$" and nxt == "{":
                state = "DQ_INTERP"
                out.append("{")
                i += 2
                continue
            if c == "{" and nxt == "$":
                state = "DQ_INTERP"
                i += 1
                continue
            if c == '"':
                state = "CODE"
            i += 1
            continue

        if state == "DQ_INTERP":
            if c == "{":
                out.append(c)
                depth = 1
                i += 1
                while i < n and depth:
                    cc = src[i]
                    if cc == "{":
                        depth += 1
                    elif cc == "}":
                        depth -= 1
                    elif cc == "'":
                        out.append(cc)
                        i += 1
                        while i < n and src[i] != "'":
                            if src[i] == "\\" and i + 1 < n:
                                out.append(src[i]); out.append(src[i + 1]); i += 2
                                continue
                            out.append(src[i]); i += 1
                        if i < n:
                            out.append(src[i]); i += 1
                        continue
                    elif cc == '"':
                        out.append(cc)
                        i += 1
                        while i < n and src[i] != '"':
                            if src[i] == "\\" and i + 1 < n:
                                out.append(src[i]); out.append(src[i + 1]); i += 2
                                continue
                            if src[i] == "$" and i + 1 < n and src[i + 1] == "{":
                                out.append(src[i]); out.append(src[i + 1]); i += 2
                                sub_depth = 1
                                while i < n and sub_depth:
                                    if src[i] == "{": sub_depth += 1
                                    elif src[i] == "}": sub_depth -= 1
                                    out.append(src[i]); i += 1
                                continue
                            out.append(src[i]); i += 1
                        if i < n:
                            out.append(src[i]); i += 1
                        continue
                    out.append(cc); i += 1
                state = "DQ"
                continue
            if c == "$" and (nxt.isalpha() or nxt == "_"):
                out.append(c)
                i += 1
                while i < n and (src[i].isalnum() or src[i] == "_"):
                    out.append(src[i]); i += 1
                if i < n and src[i] == "[":
                    out.append(src[i]); i += 1
                    while i < n and src[i] != "]":
                        if src[i] == "\\" and i + 1 < n:
                            out.append(src[i]); out.append(src[i + 1]); i += 2
                            continue
                        out.append(src[i]); i += 1
                    if i < n:
                        out.append(src[i]); i += 1
                continue
            if c == '"':
                out.append(c)
                state = "CODE"
                i += 1
                continue
            out.append(c); i += 1
            continue

        if state == "RE":
            if c == "\\" and nxt:
                out.append(c); out.append(nxt); i += 2
                continue
            if c == "[":
                out.append(c); i += 1
                while i < n and src[i] != "]":
                    if src[i] == "\\" and i + 1 < n:
                        out.append(src[i]); out.append(src[i + 1]); i += 2
                        continue
                    out.append(src[i]); i += 1
                if i < n:
                    out.append(src[i]); i += 1
                continue
            if c == "/":
                state = "RE_FLAGS"
                out.append(c); i += 1
                continue
            out.append(c); i += 1
            continue

        if state == "RE_FLAGS":
            if c.isalpha():
                out.append(c); i += 1
                continue
            state = "CODE"
            if c not in " \t\r\n":
                last_non_ws = c
            out.append(c); i += 1
            continue

        if state == "LC":
            if c == "\n":
                state = "CODE"
                out.append(c)
            i += 1
            continue

        if state == "BC":
            if c == "*" and nxt == "/":
                state = "CODE"
                i += 2
                continue
            if c == "\n":
                out.append(c)
            i += 1
            continue

    return "".join(out)


def collapse_blank_lines(text: str) -> str:
    """Схлопывает подряд идущие пустые строки до одной (после удаления комментов)."""
    lines = text.split("\n")
    out = []
    prev_blank = False
    for ln in lines:
        is_blank = ln.strip() == ""
        if is_blank and prev_blank:
            continue
        out.append(ln)
        prev_blank = is_blank
    return "\n".join(out)


def read_body_lines(path: Path) -> list:
    """Содержимое модуля без <?php, докблока, PHP-комментариев и лишних пустых строк."""
    text = path.read_bytes().decode("utf-8")
    lines = text.splitlines()
    if not lines or not lines[0].lstrip().startswith("<?php"):
        raise ValueError(f"{path.name}: файл должен начинаться с <?php")
    i = 1
    if i < len(lines) and lines[i].lstrip().startswith("/**"):
        while i < len(lines) and lines[i].strip() != "*/":
            i += 1
        i += 1  # за '*/'
        while i < len(lines) and not lines[i].strip():
            i += 1
    body = "\n".join(lines[i:])
    body = strip_php_comments(body)
    body = collapse_blank_lines(body)
    return body.split("\n")


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

    entry_text = ENTRY.read_bytes().decode("utf-8")
    entry_lines = entry_text.splitlines()
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

    tail_text = "\n".join(entry_lines[i:])
    tail_text = strip_php_comments(tail_text)
    tail_text = collapse_blank_lines(tail_text)
    tail_lines = tail_text.split("\n")

    parts = ["<?php"]
    for line in tail_lines:
        m = REQ.match(line)
        if m:
            body = read_body_lines(SRC_DIR / m.group(2).lstrip("/"))
            parts += body
            if parts and parts[-1].strip():
                parts.append("")
        else:
            parts.append(line)

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

