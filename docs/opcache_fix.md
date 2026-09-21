# Предупреждение OPcache «can't be temporary enabled» в журнале событий MODX

## Что видно в «Просмотр событий»

```
Error: Zend OPcache can't be temporary enabled (it may be only disabled till the end of request)
ErrorType[num]  WARNING[2]
File            Unknown
```

Запись появляется на обычных страницах сайта (в примере — `REQUEST_URI http://sevzakon.ru:443/view/laws/sobytiya_normativno-pravovogo_akta/?num=19/34`,
ресурс `[47753] Стадии нормативно-правового акта`), а не только при очистке кэша из админки.

## Кто выдаёт это сообщение

Сообщение выдаёт сам PHP — это INI-обработчик директивы `opcache.enable`
(`ext/opcache/zend_accelerator_module.c`, функция `ZEND_INI_MH(OnEnable)`).
Точная формулировка «can't be **temporary** enabled … **till** the end of request»
существует только в PHP ≤ 8.2; в PHP 8.3+ текст другой
(«temporarily … until the end of request») и на стадии `ACTIVATE` пишется в лог OPcache, а не как warning.

Условие выдачи (PHP 8.0–8.2, сверено по исходникам и воспроизведено на PHP 8.2.33):

- стадии `STARTUP`, `SHUTDOWN`, `DEACTIVATE` — исключены, изменения применяются молча;
- на стадиях `ACTIVATE` (перинаправленные/пуловые настройки) и `RUNTIME` (`ini_set`) **любая попытка выставить
  `opcache.enable` в истинное значение приводит к `E_WARNING` и значение не применяется**.

Смысл сообщения буквальный: внутри одного запроса OPcache можно только **выключить**,
включить его обратно (или «включить, если он был выключен в php.ini») — нельзя.

## Почему запись попадает в журнал MODX

Evolution CMS ставит собственный обработчик ошибок:
`DocumentParser::registerErrorHandlers()` → `set_error_handler([$modx, 'phpError'], E_ALL)`,
а `DocumentParser::phpError()` → `messageQuit()` записывает любое `E_WARNING` в «Просмотр событий»
с заголовком «Evo Parse Error». MODX, таким образом, только **регистрирует** предупреждение PHP;
на рендер страницы, на кэш и на данные это не влияет.

`File: Unknown` — это подстановка самого PHP (`main/main.c`, `php_error_cb()`:
если у ошибки нет файла, он записывается как `"Unknown"`). То есть предупреждение возникло
не в строке какого-то скрипта, а на уровне конфигурации PHP.
Проверено: обычный `ini_set('opcache.enable','1')` из строки скрипта помечается реальным файлом и строкой
(`… in /path/script.php on line 3`), а здесь файла нет.

## Что причиной НЕ является

1. **Не ядро Evolution CMS.** Во всём ядре Evolution 1.4.x есть только одно обращение к OPcache —
   `manager/processors/cache_sync.class.processor.php`:
   ```php
   if (!empty($opcache['opcache_enabled'])) {
       opcache_reset();
   }
   ```
   `opcache_reset()` это предупреждение выдать не может: если кэш выключен, функция молча
   возвращает `false` (проверено на PHP 8.2 с `opcache.enable=0`). Патч вида
   «`ini_get('opcache.enable')` + `@opcache_reset()`» ничего не исправляет — он лечил несуществующую причину.
2. **Не сниппет `HtmlFromNpaZS`.** В `src/site/php/**` нет ни `ini_set()`, ни обращений к OPcache.
3. **Не `opcache_reset()`, не очистка кэша MODX и не `opcache_invalidate()`.**

## Настоящие источники (проверить на сервере)

- перинаправленные/пуловые настройки, пытающиеся включить OPcache по запросу:
  `php_flag`/`php_value opcache.enable` в `.htaccess`,
  `opcache.enable=1` в `.user.ini`,
  `php_admin_value[opcache.enable] = 1` / `php_value[opcache.enable] = 1` в конфиге пула FPM
  (для FPM это же указывает сам PHP: «Are you using php_admin_value[opcache.enable]=1 in an individual pool's configuration?»);
- код, вызывающий `ini_set('opcache.enable', …)` или `ini_restore('opcache.enable')`
  — плагин/сниппет/модуль MODX, сторонний код в `assets/`.

## Как найти

На сервере (SSH):

```bash
# конфигурация сайта и пулов
grep -rn "opcache.enable" /путь/к/сайту/.htaccess /путь/к/сайту/.user.ini /etc/php/*/fpm/pool.d/ /etc/php/*/apache2/
# код MODX на диске
grep -rn "opcache" /путь/к/сайту/manager /путь/к/сайту/assets
```

Плагины/сниппеты/модули хранятся в БД, поэтому их тоже нужно проверить:

```sql
SELECT name FROM site_plugins  WHERE plugincode LIKE '%opcache%';
SELECT name FROM site_snippets WHERE snippet    LIKE '%opcache%';
SELECT name FROM site_modules  WHERE modulecode LIKE '%opcache%';
```

Быстрая проверка «в PHP значение приходит из глобального конфига или подменяется по запросу»:
запустить на сайте `data/work_tools/site_diagnostics/check_opcache_ini.php`
(скрипт ничего не меняет, только печатает `global_value` / `local_value` для директив OPcache,
наличие и содержимое `.user.ini` и наличие `opcache.enable` в `.htaccess`).

## Как устранить

1. **Правильный вариант** — включить OPcache один раз в глобальной конфигурации и убрать попытки
   включать его «на запрос»:
   ```ini
   ; php.ini
   opcache.enable=1
   ```
   либо в пуле FPM:
   ```ini
   php_admin_value[opcache.enable] = 1
   ```
   После правки — перезапуск PHP-FPM/Apache. Убрать `opcache.enable` из `.htaccess` и `.user.ini`.
2. **Если OPcache не будет включён** — удалить директиву `opcache.enable=1` из `.htaccess`/`.user.ini`/пула
   и вызовы `ini_set('opcache.enable', …)` из кода. Предупреждение исчезнет.
3. Обновление до PHP 8.3+ убирает ложные срабатывания на стадии `ACTIVATE` (они уходят в лог OPcache),
   но не отменяет правильную настройку.
4. Чистить журнал событий (MODX → Отчёт → Просмотр событий) — сам журнал можно очистить,
   но если источник не устранён, записи появятся снова. Повышать `error_reporting`/отключать логи не стоит:
   вместе с этим предупреждением исчезнут и реальные ошибки.

## Проверено локально (PHP 8.2.33, OPcache подключён)

| Что делали | Результат |
|---|---|
| `ini_set('opcache.enable','1')` | `Warning: Zend OPcache can't be temporary enabled …` + `false` |
| `ini_set('opcache.enable','0')` и `ini_restore('opcache.enable')` | то же предупреждение (восстановление = попытка включить) |
| `opcache_reset()` (кэш включён) | `true`, предупреждений нет |
| `opcache_reset()` при `opcache.enable=0` | `false`, предупреждений нет |
| `ini_set('opcache.enable','1')` из файла скрипта | предупреждение с указанием файла и строки (не `Unknown`) |
