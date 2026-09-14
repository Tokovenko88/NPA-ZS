# Исправление Notice MultiTV (TV `mfile`, id 87) — sevzakon.ru, 13.09.2026

## Симптом
При открытии документов в админке MODX Evolution 1.4.37 сыпались PHP Notice:
- `Undefined index: tpl_config` — multitv.class.php:106
- `Undefined index: templates` — multitv.class.php:270
- `Undefined index: width` — multitv.class.php:521 (×4, по числу полей)

## Диагноз (проверено на сервере и в БД)
1. **Ядро MODX Evo 1.4.37 не передаёт в custom TV ключ `tpl_config`** (grep по
   `manager/includes/` и `core/` — 0 вхождений), а установленная версия MultiTV
   (старая ветка Jako master, задеплоена 18.07.2023) читает его без `isset`
   → Notice №1 у любого multiTV TV.
2. `configs/mfile.config.inc.php` был неполный: 4 поля (file, text, id, date),
   display=vertical, но **нет ключа `templates`** (→ Notice №2, т.к. после п.1
   `$tvTemplates = 'templates'`) и **нет `width` у полей** (→ 4 × Notice №3).
3. Данные TV в БД не пострадали: 8210 записей, имена полей в JSON совпадают
   с конфигом (`file/text/id/date`); редакторы активно используют TV.

## Внесённые изменения (на сервере, под пользователем u0220513, 644)
1. `assets/tvs/multitv/configs/mfile.config.inc.php` — переписан:
   - те же 4 поля с теми же caption/type/default; добавлен `width`
     (file 400, text 400, id 60, date 120);
   - добавлен блок `templates` (outerTpl/rowTpl, дефолты для сниппета —
     фронт их не использует: все вызовы multiTV передают свои outerTpl/rowTpl).
2. `assets/tvs/multitv/includes/multitv.class.php` — 4 строки с isset/!empty:
   - 106: `tpl_config` через isset (как в поддерживаемом форке extras-evolution);
   - 270: `$settings[$tvTemplates]` через isset, fallback `array()`;
   - 487, 521: `if (!empty($this->fields[$fieldname]['width']))`.
   Итог: 69202 → 69312 байт; `php -l` OK; изменены ровно строки 106/270/487/521.

## Бэкапы
- сервер: `/tmp/multitv.class.php.bak` (69202), `/tmp/mfile.config.inc.php.bak` (455)
- локально: `data/output/multitv_backup_2026-09-13/` (*.orig + *.fixed)
- откат: скопировать .bak обратно в includes/ и configs/.

## Скрипты
`data/work_tools/multitv/`: inspect_multitv.py (диагностика, read-only),
backup_and_check.py, check_usage.py, build_fix.py, deploy_fix.py.

## Проверка
- `php -l` обоих файлов — без ошибок; конфиг include-тест: templates OK,
  width у всех полей, default `{i}` сохранён.
- Проверить визуально: открыть в админке любой документ с TV «Список файлов»
  (mfile) — Notice должны исчезнуть; фронтенд (вывод списков файлов) не менялся.
