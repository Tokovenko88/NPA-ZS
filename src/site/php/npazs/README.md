# NPA-ZS | PHP-модули сниппета HtmlFromNpaZS (MODX Evolution)

**Модель работы:** этот каталог — источник истины. ИИ-агент правит только модули
здесь; большой файл для сайта `src/site/php/snippet.php` **генерируется
автоматически** командой сборки и никогда не редактируется вручную.

```
src/site/php/npazs/*.php  (модули — редактирует агент)
        │  make build-snippet   |   python data/work_tools/build_snippet.py
        ▼
src/site/php/snippet.php  (ЕДИНЫЙ скрипт, генерируется — НЕ редактировать)
        │  содержимое вставляется в сниппет HtmlFromNpaZS в БД MODX Evolution
        ▼
Шаблон: [!ConditionalNpaContent? &parent=`[*parent*]`!]
  → ConditionalNpaContent → $modx->runSnippet('HtmlFromNpaZS', array('npa_id' => $parent))
```

На сайте, как и раньше, один большой скрипт. Монолит-предок сохранён в git
(и копия в `data/debug_runs/snippet_monolith_backup.php`) для сверки и отката.

**Агентам: прежде чем править код, прочитайте этот файл целиком.**

## Сборка

| Команда | Действие |
|---|---|
| `make build-snippet` | собрать модули → `src/site/php/snippet.php` |
| `python data/work_tools/build_snippet.py --check` | собрать в память и сравнить с файлом, не записывая |
| `python data/work_tools/build_snippet.py --watch` | следить за модулями и пересобирать при каждом изменении |

Сборка **детерминирована** (без меток времени): повторный запуск не меняет файл.
Механика: сборщик читает точку входа `HtmlFromNpaZS.php` и заменяет каждый
`require_once __DIR__ . '/...'` на содержимое модуля без его `<?php` и докблока;
секции кода (контекст, БД, AJAX, главный поток) переносятся дословно в том же
секции кода (контекст, БД, AJAX, главный поток) переносятся дословно в том же
порядке. Баннер «СГЕНЕРИРОВАНО» в начало файла не пишется — файл начинается
сразу с `<?php` и кода bootstrap.

**Добавить новый модуль:** создать файл (`<?php` + докблок-описание + функции),
добавить `require_once` в точку входа в нужном месте порядка, пересобрать.

## Точка входа: `HtmlFromNpaZS.php`

Не деплоится — это «рецепт сборки» и каркас для локального запуска модульной
версии. Определяет порядок секций монолита:

1. `bootstrap.php` — `.env` → константы `NPA_DB_*`.
2. Модули-функции (по порядку require-строк).
3. **Контекст запроса (MODX)** — `npa_id` (параметр → TV `npa_id`), TV `z-publish`,
   `site_url`, `pageUrl`; `return -6`, если `npa_id` не найден.
4. **Дата просмотра и БД** — `$_GET['view_date']` либо `MAX(valid_from)`; PDO;
   `return -2` при ошибке подключения.
5. **AJAX** — тело `ajax.php` (при `$_GET['ajax_action']`: JSON + `exit`).
6. **Сборка страницы** — кеш (попадание → `return file_get_contents(...)`),
   `npa_base` (`return -7`), `npa_law`/`npa_regulation`, статус, дерево
   `getItemTree`, рендер элементов, TOC, селектор, подпись, предвычисление
   histories/compares → `<script id="npa-static-data">`, запись кеша,
   `return $output`.

Блоки контекста/БД находятся в точке входа (а не в include), потому что содержат
`return -6/-2`, завершающий весь сниппет — include вернул бы только из себя.


## Карта модулей

| Файл | Ответственность | Функции |
|---|---|---|
| `bootstrap.php` | Загрузка `.env` (константы `NPA_DB_*`) | — |
| `helpers/dates.php` | Даты; эталон «действующей редакции» | `parseDate`, `isRevisionCurrent`, `formatDateToRus`, `formatRusDate` |
| `helpers/text.php` | Текст/падежи, канонизация highlights | `normalizeHighlightText`, `getDisplayText`, `getExpiryGenderSuffix`, `getLocalElementGenitive`, `normalizeHighlights` |
| `cache/static.php` | Статический HTML-кеш | `getStaticFilePath`, `generateFilename` |
| `revisions/edition.php` | Контекст выбранной редакции (`npa_revision_info`) | `getSelectedRevisionNpaIds`, `buildRevisionNpaIdPlaceholders`, `getSelectedEditionRegistrationDate`, `getRevisionForSelectedEdition`, `getItem*ForSelectedEdition` (4 шт.), таймлайны (2 шт.), `isDeferredSelectedEditionRevision` |
| `revisions/item.php` | Редакции содержимого элементов | `getPreviousItemRevision`, `getRevisionForDate`, `getActiveRecord`, `getLastContentRevision` |
| `revisions/head.php` | Редакции заголовков и наименования | `getPreviousItemHeadRevision`, `getItemHeadRevisionForDate`, `getHeadRevisionForDate` |
| `revisions/number_prefix.php` | Номера и префиксы на дату | `getItemNumberForDate`, `getItemNumberAtDate`, `getItemPrefixRevision` |
| `document/status.php` | Статус документа, активные редакции | `getDocMaxDate`, `getDocumentStatus`, `getActiveRevisionsForDate`, `getExactRevisionsForDate` |
| `document/head.php` | Редакции наименования документа | `getHeadRevisionsList`, `getHeadRevisionContent`, `getDocumentRevisionNote` |
| `descriptions/npa_refs.php` | Описания НПА-источников изменений | `getNpaInfoByItemId`, `getShortNpaDescription`, `getElementHumanPath`, `getRevisionDocNoteImproved`, `getRevisionSourceNote`, `getIntroducingLawForDate` |
| `content/item_content.php` | HTML-контент элемента на дату | `getParagraphsForRevision`, `getItemHeadRevisionContent`, `getItemRevisionContent` |
| `content/tables.php` | Структурные таблицы | `renderStructuredTable`, `getTableBorderFromContent`, `renderTableFragment`, `renderTableRowWithButtons`, `renderElementAsTableFragment` |
| `content/compare.php` | Сравнение редакций (diff) | `collectExpiredChildChanges`, `getItemCompareForSelectedEdition`, `getItemHeadCompareForSelectedEdition`, `getItemHeadCompareHtml`, `ensureTableWrapperForComparison`, `getHeadCompareHtml` |
| `ui/buttons.php` | Кнопки редакций, дата вступления в силу | `getElementRevisionButtons`, `getHeadRevisionButtons`, `getItemHeadRevisionButtons`, `buildRevisionEffectiveDateBlock` |
| `ui/notes.php` | Примечания к элементам/заголовкам | `isOriginalRevision`, `getItemHeadRevisionNotes`, `getElementRevisionNotes` |
| `ui/selector.php` | Селектор редакций документа | `getRevisionSelectorOptions` |
| `ui/signature.php` | Подписной блок | `renderSignature` |
| `render/tree.php` | Дерево элементов и оглавление | `getItemTree`, `renderTocTree` |
| `render/element.php` | Рекурсивный рендер элементов | `getInternalItemId`, `getElementHtmlById`, `renderElement`, `renderSubtree` |
| `history/lists.php` | Таймлайны для модалок истории | `getItemRevisionsList`, `getItemHeadRevisionsList` |
| `ajax.php` | AJAX-эндпоинт (4 действия) | — |

Каждый файл начинается докблоком: назначение, функции, особенности. Докблоки в
монолит не попадают (срезаются сборщиком).


## Глобальное состояние (общие переменные)

| Переменная | Где задаётся | Кто читает |
|---|---|---|
| `$pdo` | точка входа (PDO) | все функции через параметр; `ajax.php` напрямую |
| `$GLOBALS['selected_revision_npa_ids']` | точка входа, `ajax.php` | `getItemRevisionContent` |
| `$GLOBALS['NPA_NO_NAME_IDS']` | точка входа | `global $NPA_NO_NAME_IDS` в `content/`, `render/` |
| `$itemsByIdGlobal` | точка входа (копия `$itemsById`) | `global` в `render/element.php`, `content/tables.php` |
| `$structured_tree_cache` | точка входа | `global` в `content/item_content.php` |
| `$npaData`, `$viewDateSql`, `$isExpiredDoc`, `$selectedRevisionNpaIds` | точка входа | главный поток, передаются параметрами |

## Коды возврата сниппета

| Код | Причина |
|---|---|
| `-1` | неизвестное `ajax_action` (JSON) |
| `-2` | не удалось подключиться к БД |
| `-6` | не определён `npa_id` (нет параметра и TV) |
| `-7` | документ не найден в `npa_base` |

## AJAX (`ajax.php`)

Действия: `get_item_history`, `get_compare`, `get_item_revision`,
`get_prev_revision_plain`. Параметры: `npa_id`, `item_id`, `rev_id`, `view_date`,
`context`. Клиентский `npa-viewer.js` обычно не обращается к нему — все данные
предвычислены в `npa-static-data`; AJAX — резервный путь. Отвечает JSON + `exit`.

## Кеш

Статический HTML: `/assets/npa/{тип}/{год}/{npa_id}/{npa_id}_{дата}.html`.
Инвалидация: GET `regenerate` / `force` / `nocache`.

## Правила для агентов

1. Править код сайта **только в модулях** этого каталога. `src/site/php/snippet.php` — сгенерированный артефакт: не редактировать (пересоберётся и изменения пропадут).
2. После любых правок модулей — `make build-snippet`; проверка — `python data/work_tools/verify_build.py`.
3. Не переименовывать функции и глобальные переменные без поиска по всему каталогу: связи через `$GLOBALS`/`global`.
4. Семантику `isRevisionCurrent` (`valid_to >= asOfDate`) не менять без сверки с `docs/site_output.md` §8.3 — на ней построены все `is_current`/`is_expired`.
5. Экранирование — `htmlspecialchars()`; JSON — `JSON_UNESCAPED_UNICODE | JSON_HEX_TAG`; SQL — только подготовленные запросы PDO.
6. PHP ≥ 7.0 (используется `??`); синтаксис 7.4+/8.0+ не вводить.
7. Рекурсия (`renderElement`, `getItemTree`, `renderTocTree`) ограничена глубиной 20 — не убирать ограничители.
8. Новый модуль = новый файл + `require_once` в точке входа в нужном месте порядка + пересборка.

## Проверка и деплой

1. `make build-snippet` → `python data/work_tools/verify_build.py`:
   детерминизм, дословность тел модулей, 73 функции, эквивалентность
   монолиту-предку (мультимножество непустых строк минус секционные комментарии).
2. `php -l src/site/php/snippet.php` (на сервере или локально при наличии PHP).
3. Задеплоить: вставить содержимое `src/site/php/snippet.php` в сниппет
   `HtmlFromNpaZS` в БД MODX Evolution — тем же способом, что и раньше
   (сам сайт и его поведение не меняются: один сниппет, один скрипт).
4. Проверить страницы 2–3 НПА с `?regenerate=1`; HTML должен совпасть с тем,
   что генерировал прежний монолит.
