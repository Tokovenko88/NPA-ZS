# Qwen2API — локальный бесплатный Qwen-прокси (бэкенд `qwen2api`)

Аналог FreeDeepseekAPI (см. `docs/free_deepseek.md`): NPA-ZS работает с
локальным прокси [Qwen2API](https://github.com/Rfym21/Qwen2API)
(Qwen-Proxy) как с обычным OpenAI-совместимым провайдером (бэкенд
`qwen2api`). Прокси превращает аккаунты `chat.qwen.ai` (и CLI-эндпоинт
Qwen Code) в локальные эндпоинты `POST /v1/chat/completions`,
`GET /v1/models`, а также Anthropic-совместимый `POST /v1/messages`.
Порт по умолчанию — **3000** (переменная `SERVICE_PORT` в `.env` прокси).

**Важно:** в отличие от FreeDeepseekAPI, `API_KEY` прокси **обязателен** —
клиент обязан отправлять `Authorization: Bearer <API_KEY>`.

## 1. Настройка (один раз)

Требуется **Bun 1.3.14+** (https://bun.sh) — на нём запускается сам сервер.
Node.js/npm используется только как fallback для установки зависимостей.

```bash
python scripts/setup_qwen2api.py
# или из корня NPA-ZS:
make setup-qwen2api
```

Скрипт интерактивно:
1. Клонирует репозиторий в `tools/Qwen2API` (если ещё не развёрнут).
2. Устанавливает зависимости (`bun install`, fallback — `npm install`).
3. Создаёт `.env` прокси: `SERVICE_PORT=3000`, `LISTEN_ADDRESS=127.0.0.1`,
   `DATA_SAVE_MODE=file` и **сгенерированный API_KEY** (существующие
   значения не перезаписываются).
4. Печатает строку `QWEN2API_API_KEY=...` — скопируйте её в `.env` NPA-ZS.
5. Показывает меню: запуск прокси / открытие веб-панели аккаунтов / выход.

Аккаунт chat.qwen.ai добавляется через **веб-панель** прокси
(http://127.0.0.1:3000 → «Добавить аккаунт», логин/пароль от chat.qwen.ai)
или переменной `ACCOUNTS=email:pass` в `.env` прокси. Наличие аккаунта
скрипт проверяет автоматически (`data/data.json` прокси при
`DATA_SAVE_MODE=file`).

Запуск прокси:

```bash
make run-qwen2api
# или вручную:
cd tools/Qwen2API && bun src/server.js
# или фоново: scripts\qwen-proxy.bat / powershell -File scripts\qwen-proxy.ps1
```

**Важно (Windows):** запускайте прокси через `scripts\qwen-proxy.bat`,
`scripts\qwen-proxy.ps1` или `make run-qwen2api`. Эти launcher’ы собирают
PEM-бандл доверенных корней Windows (`scripts/export_system_ca.ps1`) и передают
его Node/bun через `NODE_EXTRA_CA_CERTS` — без этого антивирус с проверкой
защищённых соединений ломает часть TLS-запросов прокси к `chat.qwen.ai`
(подробно — раздел 5 «Диагностика»).

Проверка:

```bash
curl http://127.0.0.1:3000/v1/models -H "Authorization: Bearer sk-..."
curl http://127.0.0.1:3000/v1/chat/completions ^
  -H "Content-Type: application/json" ^
  -H "Authorization: Bearer sk-..." ^
  -d "{\"model\":\"qwen3-coder-plus\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}]}"
```

Альтернатива — Docker:

```bash
docker run -p 3000:3000 -e API_KEY=sk-... -e ACCOUNTS=email:pass rfym21/qwen2api
```

## 2. Подключение в NPA-ZS

`.env` (см. `.env.example`):

```ini
QWEN2API_API_KEY=sk-...          # тот же API_KEY, что в .env прокси
QWEN2API_BASE_URL=http://127.0.0.1:3000/v1
QWEN2API_DEFAULT_MODEL=qwen3-coder-plus
# LLM_BACKEND=qwen2api           # если нужен активным по умолчанию
```

Или выберите **Qwen2API** в GUI (окна ревизии / сравнения / верификации) —
URL/ключ/модель сохранятся в `.env` автоматически (`QWEN2API_*`, активный
бэкенд — `LLM_BACKEND`). `base_url` принимает и bare-host
(`http://127.0.0.1:3000`) — суффикс `/v1` добавляется автоматически.

CLI-модели (256K контекст, tools): `qwen3-coder-plus`, `qwen3-coder-flash`
(`coder-model` / `qwen3.5-plus` — алиасы Qwen 3.5 Plus). Чат-модели
chat.qwen.ai зависят от аккаунта; суффиксы `-thinking` / `-search`
включают мышление/поиск (например, `Qwen3.6-Plus-thinking`).

## 3. Особенности

* `QWEN2API_API_KEY` обязателен — без него прокси вернёт `401`.
* Список моделей в GUI при недоступном прокси подставляется из встроенного
  fallback-списка (`HTTP_BACKEND_DEFS['qwen2api']['free_models']`), а
  запросы ретраятся как у остальных бэкендов.
* Диагностика `WinError 10061 … 127.0.0.1:3000` — прокси не запущен:
  `make run-qwen2api`; лог запуска смотреть в консоли прокси.
* Sticky-сессии (`x-agent-session`), как у FreeDeepseekAPI, не требуются —
  параллельные клиенты обслуживаются аккаунтами самого прокси.
* Пост-анализ может работать на `qwen2api` независимо: выберите его в
  селекторе пост-бэкенда или задайте `POST_ANALYSIS_BACKEND=qwen2api`.

## 4. Что осталось вручную

* Войти в аккаунт chat.qwen.ai через веб-панель прокси (логин/пароль).
* Скопировать `API_KEY` прокси в `QWEN2API_API_KEY` файла `.env` NPA-ZS.

## 5. Диагностика

### `HTTP 500 {"error":"无法创建或续接 Qwen 会话"}` — перехват TLS

Симптом в NPA-ZS: `qwen2api ошибка (попытка 1/5): HTTP 500: {"error":"无法创建或续接 Qwen 会话"}`.
Прокси работает (порт отвечает), `API_KEY` верный, `GET /v1/models` отдаёт список —
но **создание чата падает**: Qwen2API не может открыть сессию на `chat.qwen.ai`.

Причина — **антивирус или корпоративный прокси с проверкой защищённых соединений**
(Kaspersky «Проверять защищённые соединения», Dr.Web, ESET, Zscaler и т.п.).
Такой продукт подменяет TLS-сертификаты своим самоподписанным корнем:

* браузеры и Python `requests` берут доверенные корни из хранилища Windows;
* **Node.js и bun используют собственный список CA** и часть соединений
  отвергают (`SELF_SIGNED_CERT_IN_CHAIN` / `UNABLE_TO_VERIFY_LEAF_SIGNATURE`).

Проявляется «миганием»: часть запросов проходит напрямую (инспекция
кешируется/обновляется), часть обрывается — отсюда именно 1 попытка из 5.

Проверка (оба зонда лежат в репозитории):

```powershell
node data\debug_runs\tls_probe.js 10                 # Node/bun-путь прокси
python data\debug_runs\py_tls_probe.py 10            # python-путь NPA-ZS
# FAIL + issuer=Kaspersky Anti-Virus Personal Root Certificate → это перехват
```

Решение (уже встроено в launcher’ы, отдельные действия не нужны):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\export_system_ca.ps1
# → data\work_tools\ssl\system-ca-bundle.pem (корни Windows + certifi)
```

| Стек | Переменная | Где задаётся |
| --- | --- | --- |
| Node.js / bun (прокси Qwen2API, FreeDeepseekAPI) | `NODE_EXTRA_CA_CERTS` | `scripts\qwen-proxy.ps1`/`.bat`, `scripts\fd-proxy.*`, `setup_qwen2api.py`, `make run-qwen2api` |
| Python (NPA-ZS, загрузка моделей, HTTP-запросы) | `REQUESTS_CA_BUNDLE` | `.env` NPA-ZS (`REQUESTS_CA_BUNDLE=data/work_tools/ssl/system-ca-bundle.pem`) |

`NODE_EXTRA_CA_CERTS` (корни **добавляются** к встроенным) достаточно, чтобы
прокси заработал; `REQUESTS_CA_BUNDLE` для Python бандл **заменяет**, поэтому
`export_system_ca.ps1` дополнительно вклеивает корни Mozilla из `certifi`.

Если закрыть вопрос бандлом нельзя (например, инспекция блокирует даже
сертификат прокси), остаются варианты:

1. Исключить `chat.qwen.ai` / `bun.exe` / `node.exe` из проверки защищённых
   соединений в антивирусе (Kaspersky: *Настройки → Угрозы и исключения*).
2. Крайняя мера для Python-пути: `SSL_VERIFY=false` и `NPAZ_DISABLE_SSL_VERIFY=1`
   в `.env` NPA-ZS (снижает безопасность — только для локальной отладки).
3. Запускать прокси в Docker (TLS-трафик контейнера вне инспекции хоста):
   `docker run -p 3000:3000 -e API_KEY=sk-... rfym21/qwen2api`.

### `HTTP 502 ... upstream_waf_challenge` — капча WAF chat.qwen.ai

Симптом в NPA-ZS: `qwen2api ошибка (попытка 1/5): HTTP 502: {"error":{"message":
"Qwen 网页上游触发 WAF/captcha…","code":"upstream_waf_challenge"}}`.
В логе прокси (`logs/app.log`) видны коды апстрима `FAIL_SYS_USER_VALIDATE` /
`RGV587_ERROR::SM::通量异常,被拦截` — антибот Aliyun WAF на `chat.qwen.ai`
сработал на **частоту/объём запросов или тяжёлый контекст**. Это не поломка
прокси и не неверный ключ.

Как ведёт себя стек:

1. Прокси ставит аккаунт на паузу **5 минут** (`AccountRotator.cooldownPeriod`);
   при единственном аккаунте все запросы внутри паузы отклоняются.
2. NPA-ZS распознаёт маркеры (`npazs.revision.ai_utils.is_waf_challenge_error`)
   и поднимает паузу до `WAF_CHALLENGE_WAIT_SECONDS` (330 с > 300 с охлаждения),
   чтобы не жечь 5 попыток внутри паузы; в лог пишется подсказка
   (`waf_challenge_hint`).
3. Основная причина, которая была у нас: **размер JSON-тела**. WAF отдаёт
   капчу, когда тело приближается к **128 KiB**, а `requests.post(json=...)`
   сериализует с `ensure_ascii=True` — кириллица едет как `\u0420` (6 байт
   вместо 2), и тело раздувается втрое. NPA-ZS теперь шлёт UTF-8-байты
   (`ensure_ascii=False`) и пишет размер в лог (`Тело запроса: X KiB`), а у
   порога печатает подсказку (`waf_body_size_hint`).

### Размер JSON-тела и WAF (замер 2026-09-23)

`prompt_3.md` — самый тяжёлый промпт (промпт стадии извлечения изменений):

| стадия | текст промпта | тело `json=payload` (было) | тело UTF-8 (стало) |
| --- | --- | --- | --- |
| `prompt_1.md` | 17.8 KB | 44.4 KiB | 18.1 KiB |
| `prompt_2.md` | 26.9 KB | 65.6 KiB | 26.8 KiB |
| `prompt_3.md` | 87.9 KB | **124.3 KiB** (порог капчи ~128 KiB) | **87.7 KiB** |
| `prompt_4.md` | 11.0 KB | 13.1 KiB | 11.1 KiB |

Проверка на своей машине::

    python data\debug_runs\qwen_payload_size_report.py   # таблица размеров по стадиям
    python data\debug_runs\qwen_waf_payload_probe.py     # реальный stage 3 → HTTP 200

После перехода на UTF-8-тело запрос stage 3 проходит (HTTP 200), до правки
тот же промпт уходил телом 124.3 KiB и получал `502 upstream_waf_challenge`.

Что делать, если ошибка повторяется:

1. Посмотреть в логе строку `Тело запроса: X KiB`: если X ближе к 112–128 KiB,
   дело в размере промпта, а не в частоте. Код уже отправляет UTF-8-тело
   (экономия до 3×), но при необходимости сократите `prompt_3.md` или выберите
   другой бэкенд для тяжёлых стадий (вкладка выбора бэкенда в GUI).
2. Подождать 5–15 минут и продолжить — охлаждение самоисцелящееся.
3. Открыть `http://127.0.0.1:3000` (веб-панель прокси) → аккаунт → войти на
   `chat.qwen.ai` в браузере и пройти капчу вручную (`FAIL_SYS_USER_VALIDATE` —
   валидация пользователя).
4. Добавить **второй аккаунт** chat.qwen.ai в веб-панель — ротация аккаунтов
   снижает нагрузку на один (прокси выбирает наименее используемый).
4. Уменьшить темп: не запускать параллельно несколько конвейеров NPA-ZS на
   одном бэкенде; при больших документах разбивать пакет изменений на части.
5. Настроить исходящий прокси `PROXY_URL` в `.env` прокси (смена IP снижает
   риск IP-блокировок WAF).

### Прочие типовые ошибки

| Симптом | Причина и действие |
| --- | --- |
| `HTTP 401 {"error":...}` | `QWEN2API_API_KEY` ≠ `API_KEY` из `.env` прокси. |
| `WinError 10061 … 127.0.0.1:3000` | Прокси не запущен: `make run-qwen2api`. |
| `HTTP 500 … 会话` + `tls_probe` чистый | Аккаунт chat.qwen.ai отвалился/не добавлен — проверьте веб-панель прокси. |
| `HTTP 502 … upstream_waf_challenge` | Капча WAF chat.qwen.ai (часто при большом числе запросов) — см. раздел выше: подождать, пройти капчу в браузере, добавить аккаунт. |
| `HTTP 429 … insufficient_quota / upper limit for today / 已达上限` | Дневной лимит модели на chat.qwen.ai исчерпан — NPA-ZS НЕ делает повторов, а сразу показывает диалог «Лимит модели исчерпан» с кнопкой «Переключить бэкенд» (процесс останавливается, выберите другой бэкенд/модель). Лимит обновляется утром; помогает второй аккаунт в веб-панели прокси. |
| Список моделей пуст | Прокси недоступен; GUI подставит fallback-список `HTTP_BACKEND_DEFS`. |
| `'bool' object has no attribute 'rstrip'` | Старый баг GUI (исправлен): неверные аргументы `_fetch_http_models` для `qwen2api`. |

При ошибке `HTTP 500` от `qwen2api` NPA-ZS сам печатает подсказку про
`NODE_EXTRA_CA_CERTS` (см. `npazs.revision.ai_utils.tls_interception_hint`);
при `HTTP 502 … upstream_waf_challenge` — подсказку про капчу WAF
(`npazs.revision.ai_utils.waf_challenge_hint`); при исчерпании дневной квоты
(`HTTP 429 … insufficient_quota`, см. `npazs.revision.ai_utils.is_quota_exhausted_error`)
повторы НЕ делаются — NPA-ZS сразу показывает диалог «Лимит модели исчерпан»
с предложением переключиться на другой бэкенд.

