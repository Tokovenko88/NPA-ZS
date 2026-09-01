#!/usr/bin/env python3
"""Верификация сборки src/site/php/snippet.php из модулей src/site/php/npazs/.

Проверки:
  1) сборка детерминирована (два запуска дают байт-в-байт один результат) и
     совпадает с записанным src/site/php/snippet.php;
  2) ровно один <?php в начале; в коде не осталось require __DIR__ (всё развёрнуто);
  3) набор функций совпадает с исходным монолитом (каждая ровно один раз);
  4) тело каждого модуля входит в snippet.php дословно (сплошным блоком);
  5) (опция --against <старый монолит>) эквивалентность старому файлу:
     мультимножество непустых строк нового минус строки баннера равно старому —
     доказательство того, что сборка лишь переставила дословные строки кода.

Запуск:
  python data/work_tools/verify_build.py
  python data/work_tools/verify_build.py --against data/debug_runs/snippet_monolith_backup.php
"""
import argparse
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_snippet as bs  # noqa: E402

FUN = re.compile(r"^\s*function\s+([A-Za-z_]\w*)\s*\(", re.M)
BACKUP = ROOT / "data" / "debug_runs" / "snippet_monolith_backup.php"

# Легальные добавления сборки сверх строк монолита-источника:
# секционные комментарии, которые точка входа несёт в собранный файл.
EXTRA_BUILD_LINES = {
    "/* ================= Модули (функции; при сборке разворачиваются в монолит) ================= */",
    "/* ================= Контекст запроса (MODX) ================= */",
    "/* ================= Дата просмотра и подключение к БД ================= */",
    "/* ================= AJAX-обработка (может завершить выполнение) ================= */",
    "/* ================= Сборка страницы НПА ================= */",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--against", help="старый монолит для сверки мультимножества строк")
    args = ap.parse_args()
    errors = []

    content = bs.build()
    if content != bs.build():
        errors.append("сборка недетерминирована")
    if not bs.OUT.exists() or bs.OUT.read_bytes() != content:
        errors.append("snippet.php не совпадает с результатом сборки — запустите build")

    if not content.startswith(b"<?php\n"):
        errors.append("файл не начинается с <?php")
    if content.count(b"<?php") != 1:
        errors.append("в собранном файле больше одного <?php")
    if b"__DIR__" in content:
        errors.append("в монолите остались require __DIR__ (не развёрнуты)")

    text = content.decode("utf-8")
    names = FUN.findall(text)
    if len(names) != len(set(names)):
        errors.append("есть дубликаты функций")
    if BACKUP.exists():
        src_names = FUN.findall(BACKUP.read_bytes().decode("utf-8"))
        if sorted(names) != sorted(src_names):
            errors.append(f"census функций: собрано {len(names)}, в монолите-источнике {len(src_names)}")
    print(f"функций: {len(names)}")

    for rel in bs.required_modules():
        body = "\n".join(bs.read_body_lines(bs.SRC_DIR / rel))
        if body.strip() and body not in text:
            errors.append(f"тело модуля {rel} не найдено в монолите целиком")

    against = args.against or (str(BACKUP) if BACKUP.exists() else None)
    if against:
        old = Path(against).read_bytes().decode("utf-8")
        new_lines = Counter(l for l in text.splitlines() if l.strip())
        for l in bs.banner_lines(bs.required_modules()):
            if l.strip() and l in new_lines:
                new_lines[l] -= 1
                if new_lines[l] <= 0:
                    del new_lines[l]
        for l in EXTRA_BUILD_LINES:
            if l in new_lines:
                new_lines[l] -= 1
                if new_lines[l] <= 0:
                    del new_lines[l]
        old_lines = Counter(l for l in old.splitlines() if l.strip())
        if new_lines != old_lines:
            only_new = list((new_lines - old_lines).items())[:10]
            only_old = list((old_lines - new_lines).items())[:10]
            errors.append(
                f"строки не эквивалентны; только в новом: {only_new}; только в старом: {only_old}"
            )
        else:
            print("эквивалентность монолиту-источнику: мультимножества непустых строк совпадают")

    if errors:
        print("FAIL:")
        for e in errors:
            print("  -", e)
        raise SystemExit(1)
    print(f"OK: snippet.php = {len(content.splitlines())} строк, сборка корректна")


if __name__ == "__main__":
    main()
