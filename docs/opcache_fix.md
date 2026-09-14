# Исправление ошибки "Zend OPcache can't be temporary enabled"

## Проблема

В логах Evolution CMS появляется предупреждение:

```
Error: Zend OPcache can't be temporary enabled (it may be only disabled till the end of request)
ErrorType[num] WARNING[2]
File: Unknown
```

Ошибка возникает при каждом сбросе кэша MODX из админки.

## Причина

Файл `manager/processors/cache_sync.class.processor.php` (ядро Evolution CMS) вызывает `opcache_reset()` при пересборке кэша, но на сервере OPcache отключён через `php.ini`:

```ini
opcache.enable=0
```

Zend OPcache разрешает только **отключение** во время запроса, но **не разрешает включение** — поэтому `opcache_reset()` выбрасывает предупреждение.

## Решение

Патч добавляет проверку `ini_get('opcache.enable')` и подавляет предупреждение через `@`:

```php
// Было:
if (!empty($opcache['opcache_enabled'])) {
    opcache_reset();
}

// Стало:
if (!empty($opcache['opcache_enabled']) && ini_get('opcache.enable')) {
    @opcache_reset();
}
```

## Применение

### Автоматически (через SSH)

```bash
python data/work_tools/site_diagnostics/fix_opcache_reset.py
```

С проверкой без записи:

```bash
python data/work_tools/site_diagnostics/fix_opcache_reset.py --dry-run
```

Откат к исходному состоянию:

```bash
python data/work_tools/site_diagnostics/fix_opcache_reset.py --restore
```

### Вручную (через SSH)

```bash
# 1. Бэкап
cp manager/processors/cache_sync.class.processor.php /tmp/cache_sync.class.processor.php.bak

# 2. Патч через sed
sed -i "s/if (!empty(\$opcache\['opcache_enabled'\])) {/if (!empty(\$opcache['opcache_enabled']) \&\& ini_get('opcache.enable')) {/" manager/processors/cache_sync.class.processor.php
sed -i 's/opcache_reset();/@opcache_reset();/' manager/processors/cache_sync.class.processor.php

# 3. Проверка
grep -n "ini_get('opcache.enable')" manager/processors/cache_sync.class.processor.php
```

## После применения

1. Зайти в админку MODX → Система → Очистить кэш
2. Проверить логи — ошибка должна исчезнуть

## Альтернативные решения

- **Включить OPcache** в `php.ini` (рекомендуется для производительности):
  ```ini
  opcache.enable=1
  opcache.restrict_api=""
  ```
- **Игнорировать** — ошибка не критична, не влияет на работу сайта
