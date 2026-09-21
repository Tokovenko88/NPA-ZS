# Ошибка «`` is not numeric and may not be passed to makeUrl()» из сниппета FirstChildRedirect

## Что видно

В «Просмотр событий» (Reports → Event log) появляется запись:

```
ID события: 0    Код: Snippet - FirstChildRedirect / `` is not numeric a…
Дата: 21-09-2026 09:44:52
REQUEST_URI  http://sevzakon.ru:443/fotoslajdery/fotoslajder_240_let_sevastopolyu/krasnoyarskij_kraj-_ahmedova_parvana-_11_let1/
Resource     [112018] Красноярский край, Ахмедова Парвана, 11 лет
Referer      (пусто)
User Agent   Mozilla/5.0 (Windows NT 10.0; Win64; x64) … Chrome/152.0.0.0 Safari/537.36
```

Менеджеру вместо страницы показывается «Evo Parse Error» с backtrace и Benchmarks,
обычному гостю — **HTTP 500 и тело `Error`** (проверено снаружи: тело ровно 5 байт).
`Chrome/152.0.0.0` — несуществующая версия, `Referer` пуст: запрос-визит сделал бот/сканер,
но 500 отдаётся **любому** посетителю, то есть страница сломана не из-за бота.

## Кто и где бросает ошибку

Первый оператор `DocumentParser::makeUrl()` в Evolution 1.4.x (сверено по официальному
репозиторию `modxcms/evolution`; в ветке `1.4.7` это L4123–L4132, в `1.0.15` — L2291–L2298):

```php
public function makeUrl($id, $alias = '', $args = '', $scheme = '')
{
    $url = '';
    ...
    if (!is_numeric($id)) {
        $this->messageQuit("`{$id}` is not numeric and may not be passed to makeUrl()");
    }
```

Дальше работает `messageQuit()` (1.4.7: L6232–L6434), который:

* собирает ровно ту страницу, что видит менеджер: заголовок «Evo Parse Error» (L6257),
  таблицы `Error information / Current Snippet` (L6312, L6319), `Basic info`
  (`REQUEST_URI`, `Resource`, `Referer`, `User Agent`, `Current time` — L6323–L6342),
  `Benchmarks` (L6350), `Backtrace` (L6375 → `get_backtrace()`, L6440–L6516);
* пишет запись в журнал: `$this->logEvent(0, $error_level, $str, $source)` (L6405), где
  `$source = 'Snippet - ' . $this->currentSnippet . ' / ' . $msg` (L6377–L6390) — отсюда
  колонка «Код: `Snippet - FirstChildRedirect / `` is not numeric a…`»;
* ставит `header('HTTP/1.1 500 Internal Server Error')` (L6416) и глушит вывод (`ob_get_clean()`);
* если в сессии есть `mgrValidated` — печатает подробную страницу, иначе `echo 'Error'; exit;`
  (L6429–L6433).

`ID события: 0` — это идентификатор записи журнала (событие уровня парсера), а не документа.

## Как читать backtrace (это важно для диагноза)

`get_backtrace()` (L6440–L6516) **не использует типы аргументов** — он подставляет
заглушки по эвристике (L6472–L6501):

| Реальный аргумент | Что печатается |
|---|---|
| `null` | `NULL` |
| длинная строка (≥ 20 символов) | `string $varN` |
| массив | `array $varN` |
| объект | `ИмяКласса $varN` |
| короткая строка / число | значение (строки — в кавычках) |

Отсюда точные выводы по коду из журнала:

* `DocumentParser->makeUrl(NULL)` — в `makeUrl()` пришёл **именно `NULL`** (пустая строка
  напечаталась бы как `''`, а строка `site_start` — как `'site_start'`);
* `evalSnippet(string $var1, array $var2)` — это `evalSnippet($phpcode, $params)`:
  длинная строка + массив;
* `require(string $var1)` из `…(2030) : eval()'d code on line 1` — код сниппета в БД
  состоит из одной строки (`require` файла), а вся логика лежит в
  `assets/snippets/firstchildredirect/snippet.firstchildredirect.php`;
* падает **строка 57** этого файла — она передала NULL в `makeUrl()`.

## Что делает официальный сниппет и почему это важно

Официальный `FirstChildRedirect` 2.0 (копия — `data/debug_runs/fcr/snippet.firstchildredirect.php`,
строки 54–61):

```php
// Execute
$children = $modx->getActiveChildren($docid, $sortBy, $sortDir);
if (!$children === false) {
    $firstChildUrl = $modx->makeUrl($children[0]['id']);   // строка 57
} else {
    $firstChildUrl = $modx->makeUrl($default);             // строка 59
}
return $modx->sendRedirect($firstChildUrl, 0, 'REDIRECT_HEADER', $respcode);
```

`!$children === false` из-за приоритета операторов читается как `(!$children) === false`,
то есть **первая ветка выполняется только когда список детей не пуст**:

| `$children` | Условие `(!$children) === false` | Ветка | Аргумент `makeUrl()` |
|---|---|---|---|
| непустой массив | `false === false` → true | строка 57 | `$children[0]['id']` — числовой |
| пустой массив | `true === false` → false | строка 59 | `$default` (= `site_start`) |
| `false` / `''` | `true === false` → false | строка 59 | `$default` |

`getActiveChildren()` → `DBAPI::makeArray()` возвращает 0-based массив строк, поэтому
`$children[0]['id']` у непустого списка всегда есть. Значит **ванильная версия 2.0 не может
передать NULL** (при заполненной настройке `site_start`), а на сервере лежит
**правленая/упрощённая копия** сниппета либо `&default` указывает на пустой документ.

Наиболее вероятные правки (проверяются пунктом 1 диагностики — печатью файла с номерами строк):

1. условие переписано на «логичное» `if ($children !== false)` — тогда для пустого массива оно
   истинно и строка 57 делает `$children[0]['id']` = `NULL` → ровно наша ошибка;
2. проверка удалена вовсе: сразу `$firstChildUrl = $modx->makeUrl($children[0]['id']);`
   (то же самое: `NULL` при отсутствии детей);
3. ветка `&default` вырезана, и строка 57 — это `$modx->makeUrl($default)` при пустом
   `$modx->config['site_start']` (проверить значение настройки `site_start`).

## Что подтверждено на живом сайте (21.09.2026)

| URL | Ответ |
|---|---|
| `https://sevzakon.ru/` | 200 (страница рендерится) |
| `/fotoslajdery/` | 301 → `/fotoslajdery/fotoslajder-10-let-russkoj-vesny/` (первый ребёнок) |
| `/fotoslajdery/fotoslajder_240_let_sevastopolyu/` | 301 → `…/duplicate_of_test/` |
| `/fotoslajdery/…/krasnoyarskij_kraj-_ahmedova_parvana-_11_let1/` (ресурс из журнала) | **500, тело `Error`** |
| `/fotoslajdery/fotoslajder_240_let_sevastopolyu/duplicate_of_test/` | **500, тело `Error`** |
| `/fotoslajdery/fotoslajder-10-let-russkoj-vesny/foto-1/` | **500, тело `Error`** |
| несуществующий URL | 404 (штатная страница ошибки Evo) |

Картина однозначная: `FirstChildRedirect` стоит в шаблоне страниц фотогалереи. На страницах-контейнерах
(раздел, альбом) он работает как задумано — 301 на первого ребёнка; на листовых страницах-фотографиях
падает в `makeUrl(NULL)` → 500 для всех (люди и поисковые роботы).

Побочная находка: первый ребёнок альбома «240 лет Севастополю» — тестовая страница
`duplicate_of_test`, и 301 с альбома ведёт именно на неё; адрес из журнала `…_11_let1` — тоже дубль
с автодобавленным суффиксом. Контент галереи стоит почистить и настроить 301 на родителя.

## Ядро Evo на сайте — пропатченная 1.4.x

Номера строк ядра из журнала против эталонной 1.4.7 (тот же код, отличия только в нумерации):

| Строка в журнале | Эталон 1.4.7 | Δ | Что это |
|---|---|---|---|
| 2943 | 2860 | +83 | вызов `prepareResponse()` |
| 3052 | 2969 | +83 | вызов `parseDocumentSource()` |
| 2795 | 2715 | +80 | вызов `evalSnippets()` |
| 2097 | 2025 | +72 | вызов `_get_snip_result()` |
| 2185 | 2113 | +72 | вызов `evalSnippet()` |
| 2030 | 1962 | +68 | `eval()` внутри `evalSnippet()` |

Сдвиг растёт к концу файла — на сервере 1.4.x со вставленными патчами (не ванильная 1.4.7 и не
скачанный форк `parser-1.4.x-fork.php`: там сдвиг другой). Поэтому номера строк нельзя сравнивать
«на глаз» — используйте диагностику ниже.

Эталоны для сверки (только чтение, ничего не исполняют): `data/debug_runs/fcr/` —
`parser-1.0.15.php`, `parser-1.4.0.php`, `parser-1.4.4.php`, `parser-1.4.7.php`,
`parser-1.4.x-fork.php`, `parser-2.0.1.php`/`parser-3.0rc3.php` (по 173 байта — заглушки
Evo 2.x/3.x, ядро переехало в `core/`), `dbapi.mysqli.php`, официальный сниппет
`snippet.firstchildredirect.php` и его вариант `fcr-1.0.15.php` (длинный докблок,
`makeUrl()` на строках 75/77).

## Что причиной НЕ является

1. **Не NPA-ZS и не сниппет `HtmlFromNpaZS`.** В `src/site/php/**` единственный вызов `makeUrl` —
   `HtmlFromNpaZS.php:135` (`$modx->makeUrl($modx->documentObject['id'], '', '', 'full')`), id
   текущего документа всегда числовой (тот же код в собранном `snippet.php` — строка 4853).
   В backtrace из журнала сниппета `HtmlFromNpaZS` нет, падающий кадр — файл
   `assets/snippets/firstchildredirect/snippet.firstchildredirect.php`, которого в проекте нет.
2. **Не «атака бота».** UA `Chrome/152.0.0.0` и пустой `Referer` — признаки робота, но 500/`Error`
   получает любой гость (проверено снаружи `curl`'ом); бот лишь дошёл до уже сломанных страниц.
3. **Не «просто нет детей».** Отсутствие детей само по себе даёт ветку `&default` (см. выше);
   ошибка означает, что в копии сниппета на сервере этой защиты нет или она переписана.

## Диагностика на сервере

Готовый скрипт: `data/work_tools/site_diagnostics/check_firstchildredirect.php`. Он **только читает**
(файлы сайта и таблицы БД через `SELECT`), ядро MODX не подключает, `config.inc.php` читает как текст.

1. загрузить файл в корень сайта (рядом с `index.php`);
2. открыть `https://<домен>/check_firstchildredirect.php?id=112018`;
3. удалить файл с сервера.

Он покажет: файл сниппета целиком с номерами строк (включая строку 57), строки ядра из журнала и их
соответствие 1.4.7, все места вызова `[[FirstChildRedirect]]` (сниппеты, шаблоны, чанки, ресурсы, TV),
настройки `site_start`/`error_page`/`site_unavailable_page`, сам ресурс и его детей (с учётом
`published = 1`, `deleted = 0`, `privateweb = 0`).

## Как исправить

* **Вариант A (правильный по сути).** Держать `FirstChildRedirect` только на страницах-контейнерах:
  отдельный шаблон для разделов/альбомов, а у страниц-фотографий — шаблон без редиректа
  (альтернатива — TV-флаг + условие в шаблоне).
* **Вариант B (быстрый, работает при любой причине).** Заменить содержимое сниппета безопасной
  версией с проверкой `empty($children)` — готовый файл для копирования:
  `data/work_tools/site_diagnostics/firstchildredirect_safe.php` (код ниже — то же самое).
* **Вариант C (проверка гипотезы про `&default`).** В вызове в шаблоне указать числовой
  `&default=`1`` — если ошибка исчезнет, значит падала ветка `&default` (пустой
  `$modx->config['site_start']`).
* **Вариант D (страховка, не лечение).** Настройка `error_reporting = 99`: в `messageQuit()` есть
  `if ($this->error_reporting === '99' && !isset($_SESSION['mgrValidated'])) { return true; }` (L6410) —
  гость получит страницу, ошибка останется в журнале. Причина (NULL в `makeUrl`) сохранится.

Безопасная версия сниппета (соглашения Evo 1.4.x: `getActiveChildren()`, `makeUrl()`,
`sendRedirect($url, $attempts, $type, $responseCode)`; `sendRedirect('')` возвращает `false`):

```php
<?php
/**
 * FirstChildRedirect (безопасная версия для Evolution CMS 1.4.x)
 * 301-редирект на первый опубликованный дочерний документ.
 * Если детей нет — страница отдаётся как обычно (без «Evo Parse Error»).
 * Параметр: &docid=`15` (по умолчанию — текущий документ).
 */
$docid = (isset($docid) && is_numeric($docid)) ? (int) $docid : (int) $modx->documentIdentifier;
if (!$docid) {
    return '';
}
$sortBy  = (isset($sortBy)) ? $sortBy : 'menuindex';
$sortDir = (isset($sortDir)) ? $sortDir : 'ASC';

$children = $modx->getActiveChildren($docid, $sortBy, $sortDir);
if (empty($children)) {
    return '';                       // ← ключевая проверка: детей нет, редиректить некуда
}

$child = reset($children);
$childId = isset($child['id']) ? (int) $child['id'] : 0;
if (!$childId) {
    return '';
}

$url = trim((string) $modx->makeUrl($childId, '', '', 'full'));
if ($url !== '') {
    $modx->sendRedirect($url, 0, 'REDIRECT_HEADER', 'HTTP/1.1 301 Moved Permanently');
}
return '';
```

Минимальный патч «как есть»: перед строкой 57 добавить
`if (empty($children) || empty($children[0]['id'])) { return ''; }`.

Проверка после правки:

```powershell
curl.exe -sI https://sevzakon.ru/fotoslajdery/fotoslajder-10-let-russkoj-vesny/foto-1/
```

Ожидается `200` (или `301` на родителя) вместо `500` и тела `Error`.

## Почему ошибка может остаться после правки

Тело `Error` + `500` — это универсальная ветка `messageQuit()` для **любой** фатальной ошибки
парсинга, поэтому по внешнему виду страницы нельзя судить, та же это ошибка или уже другая.
Различать нужно по свежей записи в «Просмотр событий» (сообщение + Resource + время) либо
открыв URL под учётной записью менеджера (тогда вместо `Error` печатается полная страница
«Evo Parse Error» с backtrace).

Проверенный снаружи признак: если страницы-контейнеры по-прежнему отдают `301` на первого ребёнка,
а листовые — `500`, значит сниппет исполняется, синтаксис файла цел, а **ветка «детей нет» так и не
защищена** — правка либо не сделана, либо сделана не в том месте. Если бы файл сломали синтаксически,
`500` отдавали бы и контейнеры.

Типовые причины, почему правка «не сработала»:

1. **Правка не сделана** (ошибка сохраняется в исходном виде) — самый частый случай.
2. **Правка не в том слое.** В БД сниппет может быть одной строкой `require` файла: тогда правка
   текста сниппета в менеджере не влияет ни на что, править нужно файл
   `assets/snippets/firstchildredirect/snippet.firstchildredirect.php` (и наоборот).
3. **Несколько мест вызова.** `[[FirstChildRedirect]]` может стоять в шаблоне, чанке, контенте
   ресурса, TV или вызываться плагином (`$modx->runSnippet('FirstChildRedirect')`) — исправленное
   место может быть не тем, что срабатывает на фотографии. Все места показывает п. 3 диагностики.
4. **Кэш.** OPcache (на этом сервере он настроен нештатно, см. `docs/opcache_fix.md`) при
   `opcache.validate_timestamps=0` держит старую версию файла до перезапуска PHP-FPM; плюс кэш
   MODX (`assets/cache/`) — очистить кэш в менеджере.
5. **После правки появилась новая ошибка** (опечатка, несуществующая функция, неверный параметр
   `sendRedirect`) — снова `messageQuit()` → снова `500` + `Error`, но в журнале сообщение будет
   другим (например, `PHP Parse Error`).
6. **Страница использует другой шаблон**, чем та, которую правили (или вызов идёт из чанка,
   подключённого к TV конкретного ресурса).

Быстрая проверка (30 секунд): под логином менеджера открыть проблемный URL — в заголовке страницы
ошибки будет точное сообщение, а в backtrace — файл и строка.


## Файлы по теме

* `data/work_tools/site_diagnostics/check_firstchildredirect.php` — диагностика на сервере (только чтение);
* `data/debug_runs/fcr/` — эталоны парсера Evo разных версий и официальный сниппет для сравнения;
* `docs/opcache_fix.md` — разбор соседней ошибки из того же журнала событий.

## Применено 21.09.2026 (~11:49): вариант B + Notice'ы TinyMCE

### Что изменено на сервере (все три файла с бэкапами, `php -l` — без ошибок)

Скрипт применения: `data/work_tools/site_diagnostics/apply_fixes_b.py`;
отчёт `data/debug_runs/fcr/apply_fixes_report.txt`, лог `data/logs/apply_fixes_20260921-1149.log`;
бэкапы: на сервере `*.bak-20260921-1149` рядом с файлом + локально `data/debug_runs/fcr/backup/`.

| # | Файл на сервере | Было → Стало | Что изменено |
|---|---|---|---|
| 1 | `assets/snippets/firstchildredirect/snippet.firstchildredirect.php` | 1981 → 3752 байт | заменён безопасной версией (вариант B, явная проверка `empty($children)`) |
| 2 | `assets/plugins/tinymce/plugin.tinymce.php` | 866 → 1147 байт | перед использованием `$mce_path`/`$mce_url` заданы явно (`MODX_BASE_PATH…` / `$modx->config['site_url']…`) |
| 3 | `assets/plugins/tinymce/functions.php` | 18321 → 18329 байт | `if($skin_variant)` → `if(!empty($skin_variant))` (после правки №2; первая попытка — init внутри if-блока, 18424 б, была неуместной) |

OPcache-перезапуск не понадобился — правки подхватились сразу.

### Проверка живыми запросами (после правки)

| URL | До | После |
|---|---|---|
| `…/krasnoyarskij_kraj-_ahmedova_parvana-_11_let1/` (из журнала) | 500 «Error» | **200** |
| `/fotoslajdery/fotoslajder-10-let-russkoj-vesny/foto-1/` | 500 «Error» | **200** |
| `/fotoslajdery/` | 301 | 301 (без изменений) |
| `/fotoslajdery/fotoslajder_240_let_sevastopolyu/` | 301 | 301 → `duplicate_of_test/` (контент, не сниппет) |

Откат: `cp файл.bak-20260921-1149 файл` на сервере (или из `data/debug_runs/fcr/backup/`).

**Правка №2 (11:58, `apply_fixes_b2.py`) для functions.php.** Первая правка ставила init `$skin_variant`
внутрь if-блока (перед `list($skin,$skin_variant) = explode(...)`), а фактически выполняется ветка else
(`mce_editor_skin='default'` — без `:`), поэтому Notice остался и сдвинулся на строку 367. Исправлено
защитой в самой проверке: `if($skin_variant)` → `if(!empty($skin_variant))` — `empty()` не даёт warning
на неопределённой переменной; неуместная строка-инициализация убрана. Бэкап правки №2:
`functions.php.bak-20260921-1158` (на сервере и в `data/debug_runs/fcr/backup/`); итог: 18329 байт,
sha256 `c88381a9…`, `php -l` — без ошибок.

### TinyMCE: причина Notice'ов и связь с «последними правками»

**Напрямую с правками 19.09 не связано: файлы TinyMCE не менялись с 2023 года**
(mtime `plugin.tinymce.php` 03.08.2023, `functions.php` 18.07.2023; `functions.php` побайтово равен
стоку Evo 1.1.1 — 18321 байт). Причина Notice'ов двойная:

1. В свойствах плагина #6 «TinyMCE Rich Text Editor» **нет ключей `mce_path`/`mce_url`** (остальные 17 на месте).
   Ядро передаёт плагину именно свойства как переменные: `evalPlugin()` → `extract($params, EXTR_SKIP)`
   (parser, L1901). Файл читает их в строках 9–10 → Undefined variable. Когда именно ключи пропали —
   установить нельзя: историю свойств Evo не хранит, а `event_log` сегодня уже пуст (очищен между
   09:44 и 11:49 — на сайте кто-то работает).
2. **PHP 8.2.33** (переезд на PHP 8, сборка 28.07.2026): «Undefined variable» стало E_WARNING
   (в PHP 7 — E_NOTICE), и Evo своим обработчиком тащит его в журнал/вывод. Notice `$skin_variant`
   — родовое поведение стока при `mce_editor_skin` без `:` (здесь `default`): сток не инициализирует
   переменную в else-ветке (строки 362–367).

Фикс — в файлах, БД не трогали. Альтернатива «как в стоке»: вернуть ключи `mce_path`/`mce_url`
в свойства плагина #6 (Manager → Элементы → Плагины) — тогда явно заданные строки в файле можно убрать.
Проверить исправление нужно под логином менеджера: Notice'ы выдаются только в панели управления.

### Notice «Undefined index: tv141» (дополнение, 21.09.2026 ~12:10)

* Источник: плагин **changeWords (id=42)**, событие OnDocFormSave, **строка 16** кода:
  `$AutoEditLinks = $_POST['tv'.$tvid];`, где `$tvid` — id TV `AutoEditLinks` из БД (строка 15).
  Notice приходит как `eval()'d code on line 16`, потому что код плагина исполняется через
  `eval($pluginCode)` в `evalPlugin()` (строка 1983 парсера).
* Причина: на момент Notice **TV 141 не существовал/не был привязан** (первая проверка его не видела),
  позже TV появился снова с привязкой к шаблонам 102 и 245 — его пересоздали параллельно работающие
  люди. `$_POST['tv141']` при этом в форме не было → Undefined index.
* Фикс (правка кода плагина в БД, id=42, `apply_changewords_guard.py`):
  строка 16 заменена на guard
  `$AutoEditLinks = ($tvid && isset($_POST['tv'.$tvid])) ? $_POST['tv'.$tvid] : '';`
  Бэкап старого кода: `data/debug_runs/fcr/backup/changewords_id42_20260921-1212.php`;
  лог `data/logs/apply_changewords_guard_20260921-1212.log`.
* Откат: восстановить код из бэкапа (Manager → Плагины → changeWords или SQL UPDATE).

### Что осталось (контент и гигиена, вне сниппета)

* альбом «240 лет Севастополю» редиректит 301 на тестовый дубль `duplicate_of_test` — почистить контент;
* листовые фото-страницы теперь 200 с пустым телом (шаблон 46 — только `[[FirstChildRedirect]]`);
  после чистки дублей назначить им нормальный шаблон;
* в БД много задублированных плагинов (TinyMCE4 — три активные копии #18/#28/#39 с одинаковым набором
  событий 3/20/85/87/88/91/92, CodeMirror ×4, ManagerManager ×5 и т.д.) — кандидат на отдельную чистку;
  сейчас активен старый редактор (`which_editor=TinyMCE`), а не TinyMCE4.
