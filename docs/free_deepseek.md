# FreeDeepseekAPI — локальный бесплатный DeepSeek-прокси (бэкенд по умолчанию)

NPA-ZS работает с локальным прокси
[FreeDeepseekAPI](https://github.com/dekrezz/FreeDeepseekAPI) как с обычным
OpenAI-совместимым провайдером (бэкенд `free_deepseek`) — это провайдер
**по умолчанию** для всех селекторов LLM.
Прокси превращает авторизованную web-сессию `chat.deepseek.com`
в локальные эндпоинты `POST /v1/chat/completions`, `/v1/responses`,
`/v1/messages` и `GET /v1/models`. В вебе сейчас одна модель —
**DeepSeek-V4.1-Flash** (`deepseek-v4-flash`, алиас `deepseek-flash`,
legacy-алиас `deepseek-v4-pro`, суффиксы `-thinking` / `-search`).

## 1. Настройка (один раз)

```bash
python scripts/setup_free_deepseek.py
```

Скрипт интерактивно:
1. Клонирует репозиторий (если ещё не развёрнут).
2. Выполняет `npm install` (если нужно).
3. **Проверяет авторизацию**: если `deepseek-auth.json` уже есть — пропускает, иначе открывает Chrome для логина в chat.deepseek.com.
4. Показывает меню: запуск прокси / повторная авторизация / выход.

Прокси запускается из меню или вручную:

```bash
cd tools/FreeDeepseekAPI && npm start
```

Или из корня NPA-ZS:

```bash
make run-free-deepseek
```

Повторная авторизация (заново):

```bash
python scripts/setup_free_deepseek.py
# в меню выберите «4»
```

Или напрямую:

```bash
cd tools/FreeDeepseekAPI && npm run auth
```

Альтернатива браузерному логину — импорт готового auth-файла
(шаблон: `auth.example.json`) или cookies:

```bash
npm run auth -- --import
```

Проверка:

```bash
curl http://127.0.0.1:9655/v1/models
curl http://127.0.0.1:9655/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-agent-session: npazs-main" \
  -d '{"model":"deepseek-v4-flash","messages":[{"role":"user","content":"ping"}]}'
```

### Диагностика ошибки подключения

`WinError 10061 … 127.0.0.1:9655` в NPA-ZS означает, что **прокси не
запущен** (или слушает другой порт) — это не проблема URL/ключа:

1. `netstat -ano | findstr :9655` — нет `LISTENING` →
    `make run-free-deepseek`; если процесс падает — смотреть лог
    (`data/logs/free_deepseek_proxy.log`) и выполнить
    `make auth-free-deepseek` (или `python scripts/setup_free_deepseek.py`).
2. Порт занят/другой → переопределить `FREE_DEEPSEEK_BASE_URL`.
3. Список моделей в GUI при недоступном прокси подставляется из
    встроенного fallback-списка, поэтому селектор модели остаётся рабочим.

**Ловушка cmd.exe**: `cd E:\NPA-ZS\tools\FreeDeepseekAPI` из `C:\…` не
переключает диск — npm продолжит искать `package.json` в старой папке
(`ENOENT … package.json`). Нужен `cd /d E:\…` (или запускайте
`python scripts/setup_free_deepseek.py` / `make auth-free-deepseek`
из корня NPA-ZS — смена каталога не требуется).

## 2. Подключение в NPA-ZS

`.env` (см. `.env.example`):

```ini
FREE_DEEPSEEK_BASE_URL=http://127.0.0.1:9655/v1
FREE_DEEPSEEK_DEFAULT_MODEL=deepseek-v4-flash
FREE_DEEPSEEK_SESSION=npazs-main
# FREE_DEEPSEEK_API_KEY=...  # только если в прокси задан PROXY_API_KEY
LLM_BACKEND=free_deepseek
```

Или выберите **FreeDeepseek** в GUI (окна ревизии / сравнения /
верификации) — URL/ключ/модель сохранятся в `.env` автоматически
(`FREE_DEEPSEEK_*`, активный бэкенд — `LLM_BACKEND`).

## 3. Бэкенд по умолчанию (оба селектора)

`free_deepseek` — дефолтный провайдер для обоих селекторов окна ревизии:

* основной — `LLM_BACKEND` (константа `DEFAULT_BACKEND`);
* пост-анализ — `POST_ANALYSIS_BACKEND`; при пустом значении наследует
  основной бэкенд, который по умолчанию тоже `free_deepseek`.

У пост-анализа в GUI свой редактор URL/ключа («API URL (пост)» /
«API Key (пост)» + «Сохранить в .env»), независимый от редактора основного
селектора. Непустые значения пишутся в `POST_ANALYSIS_BASE_URL` /
`POST_ANALYSIS_API_KEY` и имеют приоритет над кредами самого пост-бэкенда
(`get_post_analysis_llm_config`), пустые — креды наследуются. Модель
пост-анализа — `POST_ANALYSIS_MODEL`. Так пост-анализ может работать,
например, на своём инстансе прокси или на другом провайдере, не трогая
основной прогон.

## 4. Особенности

* `PROXY_API_KEY` прокси опционален: без него `FREE_DEEPSEEK_API_KEY`
  остаётся пустым, заголовок `Authorization` не отправляется.
* `FREE_DEEPSEEK_SESSION` → заголовок `x-agent-session` (sticky-сессия
  прокси). **Каждый параллельный клиент — своя сессия**: один web-логин
  обслуживает только один in-flight чат, иначе прокси вернёт `429`
  (`concurrent_chat_blocked`). Пулы из 2–3 логинов — через
  `accounts/*.json` в каталоге прокси.
* `base_url` принимает и `http://127.0.0.1:9655`, и
  `http://127.0.0.1:9655/v1` (суффикс `/v1` добавляется автоматически).
* Без запущенного прокси список моделей берётся из встроенного fallback
  (`deepseek-v4-flash`, `-thinking`/`-search` варианты), а запросы
  ретраятся как у остальных бэкендов.
