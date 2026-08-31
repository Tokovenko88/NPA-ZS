# Анкортированная сводка: Дискоординация prompt_2_dates_analysis.md с программой

**Дата:** 2026-08-31
**Рабочее окружение:** E:\NPA-JSON-Processor
**HEAD коммит:** `87b7588`

---

## 1. Сводка (executive)

`prompt_2_dates_analysis.md` был переписан в трёх коммитах (`3b8f3a8`, `8137e63`, `87b7588`),
переводя формат ответа ИИ с **плоского JSON-массива** на **JSON-объект с двумя именованными
массивами** (`special_valid_from`, `retroactive_effects`), при этом:

- даты переведены в ISO-формат `ГГГГ-ММ-ДД` (вместо `DD.MM.YYYY`);
- ретроактивные эффекты переименованы из `retroactive_note` (с полями `note_text`,
  `note_valid_from`, `scope`) в `retroactive_effects` (с полями `corrected_text`,
  `original_text`, `date`);
- добавлена инструкция ИИ **самостоятельно рассчитывать** даты по 3-правилам.

Потребительский код (`ai_pipeline.py`, `retroactive_notes.py`) **не был обновлён** после
этих коммитов. Последний коммит, менявший `ai_pipeline.py`, — `900cc05`. В результате
ИИ, следуя новому промпту, выдаёт объект, который код **молча отбрасывает** на этапе 2,
а все специальные даты и ретроактивные примечания теряются.

---

## 2. Проблема

### Проблема-1: JSON-структура (объект vs массив)

| | Prompt (текущий) | Code (ai_pipeline.py) |
|---|---|---|
| **Строка** | `03_prompts/prompt_2_dates_analysis.md:45, 99-122` | `ai_pipeline.py:152` (и `:104`) |
| **Ожидает** | JSON-объект: `{ "special_valid_from": [...], "retroactive_effects": [...] }` | Плоский JSON-массив: `[ {...}, {...} ]` |
| **Код** | `isinstance(parsed, list)` → **false** для dict → возвращает `[]` |

**Последствие:** Когда ИИ следует промпту и выдаёт объект, `isinstance(parsed, list)`
возвращает `False` и вся запись этапа 2 **теряется**. Функция `_stage2_dates_analysis`
возвращает `[]` — ни специальные даты, ни ретроактивные примечания не применяются.

### Проблема-2: Названия полей для ретроактивных эффектов

| | Prompt (текущий) | Code |
|---|---|---|
| **Контейнер** | массив `retroactive_effects` внутри объекта | плоский массив с `action_type: "retroactive_note"` |
| **Поле даты** | `date` (ISO `2023-01-01`) | `note_valid_from` (формат `DD.MM.YYYY`) |
| **Поле текста** | `corrected_text` + `original_text` | `note_text` |
| **Область действия** | (нет) | `scope` (`"all_changes"` \| `"selected_changes"`) |
| **Источник** | `retroactive_notes.py:387,492` | `ai_pipeline.py:1855-1858` |

**Последствие:** Даже если структура JSON исправить (перейти на массив), код ищет
`action_type == "retroactive_note"` и читает `note_text`/`note_valid_from`/`scope`.
Промпт не упоминает эти поля ни в одном из вариантов.

### Проблема-3: Формат дат (ISO vs `DD.MM.YYYY`)

| | Prompt | Code |
|---|---|---|
| **Формат** | `ГГГГ-ММ-ДД` (напр. `2025-01-01`, `2023-01-01`) | `DD.MM.YYYY` (напр. `01.01.2023`) |
| **Источник** | `prompt_2_dates_analysis.md:109, 117, 128, 137, 174, 199, 220, 228, 248` | `AGENT_INSTRUCTION.md:211`; `ai_pipeline.py:1705,1947`; `change_applier.py:493,523,547,621`; `retroactive_notes.py:366,474`; `__init__.py:140,154` |

**Последствие:** Если ИИ выдаёт ISO-дату, а код пытается распарсить её через
`datetime.strptime(date_str, '%d.%m.%Y')` (конвейер `ai_pipeline.py:1705`), это вызывает
`ValueError`. В функции `_apply_special_valid_from_overrides` (строка 1630) дата назначается
в `ch['valid_from']` как есть, без конвертации. Позже в `change_applier.py:493` и далее
все приводят к `'%d.%m.%Y'`.

### Проблема-4: ИИ вычисляет даты, код ожидает готовые

| | Prompt | Code |
|---|---|---|
| **Логика** | Правила 1-2-3: базовая дата → прибавление срока → налоговый период → `max()` | Код **не вычисляет** — берёт `date` из записи как есть |
| **Источник** | `prompt_2_dates_analysis.md:62-97` (Правила 1-3) | `ai_pipeline.py:1621-1648` (`_apply_special_valid_from_overrides`) |

**Последствие:** Промпт заставляет ИИ выполнять календарную арифметику и логику налоговых
периодов. Если ИИ ошибается в расчёте (часто — модели путают начала периодов), код не имеет
механизма проверки или пересчёта. Кроме того, в случае 677-ЗС дата указана **явно в тексте**
закона ("вступают в силу с 1 января 2023 года"), и расчёт не нужен — но промпт не
различяет "дата явно указана" vs "дата требует вычисления".

### Проблема-5: Неиспользуемая переменная `{valid_from}`

| | Prompt | Code |
|---|---|---|
| **Переменная** | `{valid_from}` — **не используется** ни разу в промпте | `ai_pipeline.py:145` — подставляется |
| **Переменная** | `{change_date_effective}` — используется на строке 24 | `ai_pipeline.py:144` — подставляется |

**Последствие:** Код тратит усилия на подстановку `{valid_from}`, которую промпт не
читывает. Это не критично, но создаёт путаницу.

---

## 3. Исследование (investigation details)

### Ход коммитов промпта

```
8137e63  (старая версия: flat JSON array, ISO dates, NO retroactive_effects)
   │
   ├─> 3b8f3a8  (первоначальная перезапись: объект {special_valid_from, retroactive_effects}, ISO dates)
   │
   ├─> 8137e63  (мажорный рерайт: added retroactive_effects, date calculation, ISO dates)
   │
   └─> 87b7588  (HEAD: cosmetica — added Пример 3 "разделение элементов", переформатирована
                секция "Формат ответа", убраны XML-комментарии из ВХОДНЫХ ДАННЫХ)
```

Код (`ai_pipeline.py`, `retroactive_notes.py`) не изменялся после `900cc05` (ранее,
чем все три коммита промпта).

### Что ожидает код (источники истины)

**AGENT_INSTRUCTION.md** (строки 45-63) описывает результат этапа 2:
```
Результат этапа: JSON-массив объектов с полями:
- applies_to: "amending_law" | "target_law"
- action_type: "special_valid_from" | "retroactive_note"
- structural_element: путь к элементу
- date / note_text / note_valid_from
```

**ai_pipeline.py:152** — парсинг ответа этапа 2:
```python
parsed = json.loads(repaired)
if isinstance(parsed, list):  # <-- FAIL для JSON-объекта
    ...
    return parsed
# fallback: ничего не возвращается, [] используется дальше
```

**ai_pipeline.py:104-115** — тот же `isinstance(parsed, list)` для ручного ввода ответа.

**ai_pipeline.py:1850-1903** — потребление записей этапа 2:
```python
for rec in stage2_records:
    action_type = rec.get("action_type")
    applies_to = rec.get("applies_to")
    structural_element = rec.get("structural_element", "").strip()

    if action_type == "retroactive_note":
        note_text = rec.get("note_text", "")          # <-- code reads note_text
        note_valid_from = rec.get("note_valid_from")  # <-- code reads note_valid_from
        scope = rec.get("scope")                       # <-- code reads scope
        ...

    elif action_type == "special_valid_from":
        date = rec.get("date")                          # <-- code reads date
        ...
        amending_special_dates[norm_path] = date      # <-- ISO или DD.MM.YYYY?
```

**retroactive_notes.py:369-396** (`apply_retroactive_rules`) — полное потребление retroactive_note:
```python
if rule.get("action_type") != "retroactive_note":
    continue
if rule.get("applies_to") != "amending_law":
    ...
scope = rule.get("scope") or _infer_scope(structural)
note_text = rule.get("note_text", "")
note_valid_from = rule.get("note_valid_from") or general_str or None
```

**retroactive_notes.py:482-623** (`apply_retroactive_rules_to_groups`) — аналогично для
`target_law` правил.

### Подтверждение на примере 677-ЗС → 110-ЗС (debug run 2026-08-31_09-17-07)

**Исходный закон (677-ЗС):** `date_pub = 14.12.2021`, `valid_from = 14.12.2021`

Текст закона содержит:
> «Настоящий Закон вступает в силу со дня его официального опубликования,
> **за исключением подпунктов «е» и «ж» пункта 2 статьи 1** настоящего Закона.»

> «Подпункты «е» и «ж» пункта 2 статьи 1 настоящего Закона вступают в силу
> **с 1 января 2023 года**.»

**Ожидалось от Stage 2:**
- 2 записи `special_valid_from` с `applies_to: "amending_law"`, датами `01.01.2023`
  для `статья 1 -> пункт 2 -> подпункт е` и `статья 1 -> пункт 2 -> подпункт ж`.

**Фактический `stage_2_answer.json` (debug run 09-17-07 и 10-02-29):**
```json
[
  { "applies_to": "target_law", "action_type": "retroactive_note",
    "structural_element": "статья 2 -> часть 1.4",
    "note_text": "Действие положений части 1.4 статьи 2 ... распространяется на правоотношения, возникшие с 1 января 2023 года",
    "note_valid_from": "01.01.2023" },
  ... (ещё 2 записи для части 1.5 и 1.6) ...
]
```

**Результат:** Ни одной записи `special_valid_from` нет. Все изменения пункта 2
(включая подпункты «е» и «ж») получили `valid_from = 14.12.2021` (общая дата вступления 677-ЗС),
вместо `01.01.2023`.

---

## 4. Сводка несоответствий (mismatch table)

| № | Что | Prompt требует | Code ожидает | Где в коде | Последствие |
|---|-----|----------------|--------------|------------|-------------|
| 1 | **JSON-структура** | JSON-объект `{special_valid_from: [...], retroactive_effects: [...]}` | Плоский JSON-массив `[...]` | `ai_pipeline.py:104, 152` (`isinstance(parsed, list)`) | Object → проверка `False` → `[]`; все данные этапа 2 теряются |
| 2 | **action_type для ретро** | Нет поля `action_type` в `retroactive_effects`; используется `corrected_text`/`original_text`/`date` | `action_type: "retroactive_note"` с `note_text`/`note_valid_from`/`scope` | `ai_pipeline.py:1855`; `retroactive_notes.py:371,484` | `retroactive_note` никогда не распознаётся; ретро-примечания не применяются |
| 3 | **Формат даты** | ISO `ГГГГ-ММ-ДД` (напр. `2023-01-01`) | `DD.MM.YYYY` (напр. `01.01.2023`) | `ai_pipeline.py:1705,1947`; `change_applier.py:493`; `__init__.py:140` | `strptime('%d.%m.%Y')` падает на ISO-датах |
| 4 | **Вычисление даты** | ИИ рассчитывает по 3-правилам (max, налоговые периоды) | Код берёт `date` из записи как есть, без проверки | `ai_pipeline.py:1630,1637` (`ch['valid_from'] = date`) | Ошибки ИИ в календарной арифметике не проверяются |
| 5 | **Переменная `{valid_from}`** | Не используется в промпте | Подставляется в коде | `ai_pipeline.py:145` | Неиспользуемая подстановка (не критична) |
| 6 | **Поле `date` для special_valid_from** | ИИ может вернуть `date: null` при `needs_review: true` | Код проверяет `if not date: continue` (пропуск) | `ai_pipeline.py:1895-1896` | `needs_review: true` случаи тихо отбрасываются |

---

## 5. Предлагаемые поправки к prompt_2

> **Принцип:** промпт должен производить **плоский JSON-массив**, где каждая запись —
> одна ячеек, а поля совпадают с тем, что читает `ai_pipeline.py` (строки 1850-1903)
> и `retroactive_notes.py` (строки 369-396).

### 5.1. Изменить "Формат ответа" — массив, а не объект

**Заменить:**
```
Ответ — строго JSON-объект с двумя массивами:
{
  "special_valid_from": [...],
  "retroactive_effects": [...]
}
```
**На:**
```
Ответ — строго JSON-массив. Каждый объект в массиве — одна запись:
[
  { ... special_valid_from ... },
  { ... retroactive_note ... }
]
```

### 5.2. Единые поля для всех записей

Каждая запись в массиве обязана содержать:

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `applies_to` | `"amending_law"` \| `"target_law"` | ✓ | К чьим правилам относится |
| `action_type` | `"special_valid_from"` \| `"retroactive_note"` | ✓ | Тип записи |
| `structural_element` | string | ✓ | Путь: `статья 1 -> пункт 2 -> подпункт е` |
| `date` | `DD.MM.YYYY` | Для `special_valid_from` | Итоговая дата вступления |
| `note_text` | string | Для `retroactive_note` | Полный текст ретроактивного положения |
| `note_valid_from` | `DD.MM.YYYY` | Для `retroactive_note` | Дата, с которой действие распространяется |
| `scope` | `"all_changes"` \| `"selected_changes"` | Для retroactive_note | Область применения (по умолчанию вычисляется кодом, но может быть указана) |
| `calculation_basis` | string | рекомендуется | Пояснение расчёта (не отбрасывается, просто не используется) |
| `needs_review` | boolean | рекомендуется | Флаг необходимости проверки |

### 5.3. Формат дат — `DD.MM.YYYY`

Во всех примерах и в инструкциях заменить ISO-даты на `DD.MM.YYYY`:
- `2025-01-01` → `01.01.2025`
- `2023-01-01` → `01.01.2023`
- `2024-12-20` → `20.12.2024`
- и т.д.

### 5.4. Убрать обязательство ИИ рассчитывать даты через календарную арифметику

Промпт должен **сохранять** инструкцию о вычислении (это ценная логика), но:
- в примерах показать, что когда дата указана прямо в тексте закона, ИИ берёт её как есть;
- добавить note: если вычисление неоднозначно — ставь `needs_review: true`, `date: null`.

### 5.5. Изменить секцию "Дополнительная задача" (ретроактивные положения)

**Заменить** концепцию `retroactive_effects` + `corrected_text`/`original_text` на
`retroactive_note` в едином массиве:

```json
[
  {
    "applies_to": "target_law",
    "action_type": "retroactive_note",
    "structural_element": "статья 2 -> часть 1.4",
    "note_text": "Действие положений части 1.4 статьи 2 Закона города Севастополя от 3 февраля 2015 года № 110-ЗС «О налоговых ставках по отдельным налогам» (в редакции настоящего Закона) распространяется на правоотношения, возникшие с 1 января 2023 года.",
    "note_valid_from": "01.01.2023",
    "scope": "selected_changes"
  }
]
```

### 5.6. Исправить примеры (few-shot)

Все 4 примера переписать в формате плоского массива с полями из таблицы 5.2.
Особенно важно:
- **Пример 3** (разделение подпунктов «е» и «ж») → две записи `special_valid_from` с `date: "01.01.2023"`.
- **Пример 4** (ретроактив) → одна запись `retroactive_note` с `note_text`/`note_valid_from`.

### 5.7. Добавить `applies_to` и `action_type` во все записи

Промпт должен чётко инструктировать:
- если особая дата относится к **изменяющему** закону (677-ЗС) → `applies_to: "amending_law"`,
  `action_type: "special_valid_from"`;
- если ретроактивное положение относится к **целевому** закону (110-ЗС) →
  `applies_to: "target_law"`, `action_type: "retroactive_note"`;
- если ретроактивное положение сформулировано в изменяющем законе, но распространяется
  на целевой → `applies_to: "amending_law"`, `action_type: "retroactive_note"`.

---

## 6. Состояние работы (work state)

| Задача | Статус |
|--------|--------|
| Прочитан prompt_2 (HEAD `87b7588`) | ✅ |
| Проанализированы diff'ы: `3b8f3a8` → `8137e63` → `87b7588` | ✅ |
| Прочитан `ai_pipeline.py` (`_stage2_dates_analysis`, `_apply_special_valid_from_overrides`, run_all) | ✅ |
| Прочитан `retroactive_notes.py` (`apply_retroactive_rules`, `apply_retroactive_rules_to_groups`) | ✅ |
| Прочитан `AGENT_INSTRUCTION.md` (спецификация этапа 2) | ✅ |
| Проверены debug runs (677-ЗС → 110-ЗС, 09:17-07 и 10:02-29) | ✅ |
| Подтверждена 677-ЗС: "Подпункты «е» и «ж» пункта 2 статьи 1 ... с 1 января 2023 года" | ✅ |
| Подтверждено: stage_2_answer.json не содержит `special_valid_from` записей | ✅ |
| **Написать поправленный prompt_2** | ⏳ (следующий шаг) |
| **Проверить парсинг исправленного prompt_2 кодом** | ⏳ |

---

## 7. Следующие шаги

1. **Переписать `prompt_2_dates_analysis.md`** согласно разделу 5 (массив вместо объекта,
   `DD.MM.YYYY` вместо ISO, `note_text`/`note_valid_from`/`scope` вместо `corrected_text`/
   `original_text`/`date` для ретроактивных эффектов).
2. **Добавить `applies_to` и `action_type` во все записи**, включая ретроактивные.
3. **Сохранить** расчётную логику (Правила 1-3) как «мыслительный процесс», но не делать
   календарную арифметику обязательной — когда дата указана явно, брать её как есть.
4. **Протестировать:** подставить 677-ЗС article 1 в исправленный промпт, убедиться, что
   ИИ выдаёт массив с 2мя `special_valid_from` (01.01.2023) для подпунктов е/ж и 3мя
   `retroactive_note` для частей 1.4-1.6.
5. **Запустить** `python -m pytest tests/ -v` для проверки регрессий.

---

## 8. Ключевые ссылки (anchors)

| Файл | Строки | Что |
|------|--------|-----|
| `03_prompts/prompt_2_dates_analysis.md` | 45, 99-122 | Текущий формат ответа (объект с двумя массивами) |
| `03_prompts/prompt_2_dates_analysis.md` | 128, 137 | ISO-формат дат |
| `03_prompts/prompt_2_dates_analysis.md` | 134-141 | Поля `retroactive_effects`: `corrected_text`/`original_text` |
| `03_prompts/prompt_2_dates_analysis.md` | 62-97 | Правила расчёта дат (Правила 1-3) |
| `npa_processor/processing/ai_pipeline.py` | 104, 152 | `isinstance(parsed, list)` — единственная точка входа |
| `npa_processor/processing/ai_pipeline.py` | 136-145 | Подстановка переменных в промпт |
| `npa_processor/processing/ai_pipeline.py` | 1850-1903 | Потребление Stage 2 records |
| `npa_processor/processing/ai_pipeline.py` | 1621-1648 | `_apply_special_valid_from_overrides` |
| `npa_processor/processing/retroactive_notes.py` | 369-396 | `apply_retroactive_rules` |
| `npa_processor/processing/retroactive_notes.py` | 482-623 | `apply_retroactive_rules_to_groups` |
| `AGENT_INSTRUCTION.md` | 45-63 | Спецификация результата этапа 2 |
| `AGENT_INSTRUCTION.md` | 118-139 | Применение `special_valid_from` и `retroactive_note` |
| `AGENT_INSTRUCTION.md` | 208-211 | "Формат: DD.MM.YYYY" |
| `04_stage_answers/prompt_2_answer.json` | — | Сохранённый ответ этапа 2 (старый формат) |
| `07_debug_runs/2026-08-31_09-17-07/stage_2_answer.json` | — | Ответ этапа 2 для 677-ЗС (без special_valid_from) |
