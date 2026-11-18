# Контракт LLM: проверка решения математической задачи

Этот документ — источник истины для адаптера LLM, Pydantic-моделей и UI. Пилот принимает задачи любого математического типа: уравнения, системы, дроби, функции, производные, интегралы, геометрию и доказательства. Модель не должна ограничивать разбор по теме, но обязана честно отказаться от оценки при нечитаемом фото или недостатке контекста.

## Назначение и правила

За один вызов LLM получает фотографию с условием и решением пользователя, а возвращает JSON для интерфейса.

1. Распознать условие и только те шаги, которые реально написал пользователь.
2. Представить каждый отображаемый математический шаг в LaTeX без разделителей `$` или `\\(` — их добавляет клиент.
3. Проверять шаги строго слева направо и сверху вниз.
4. Вернуть все корректные шаги до первой ошибки и сам первый ошибочный шаг. Не добавлять и не оценивать шаги после ошибки.
5. Для ошибочного шага вернуть короткое название ошибки, понятное объяснение и корректный вариант этого же шага, если его можно сформулировать однозначно.
6. Не исправлять шаги молча, не выдумывать пропущенные шаги, не предлагать полное решение задачи вместо разбора работы пользователя.
7. При нечитаемом символе, невидимом условии, необходимом, но отсутствующем чертеже или низкой уверенности вернуть статус отказа, а не угадывать.

Все человекочитаемые строки возвращаются на русском языке. Технические значения перечислений и ключи JSON — на английском.

## Статусы результата

| `status` | Когда использовать | Что показывает UI |
|---|---|---|
| `ok` | Условие и нужные шаги прочитаны достаточно уверенно | Карточки шагов и итог проверки |
| `needs_clearer_photo` | Нечитаемый текст, формула, знак или фрагмент решения | Просьбу сфотографировать лист заново |
| `insufficient_context` | Нет условия, важной части решения, обозначения или необходимого чертежа | Просьбу приложить полный контекст |
| `not_a_math_solution` | На фото нет проверяемого математического решения | Сообщение о допустимом формате загрузки |
| `processing_error` | Техническая/внутренняя ошибка анализа | Нейтральную ошибку и кнопку повтора |

При любом статусе, кроме `ok`, поле `steps` пустое, а `first_incorrect_step_number` равно `null`. Текст для пользователя приложение строит по статусу само; не надо отображать технические ошибки или внутренние рассуждения модели.

## Структура успешного результата

### Пример: найдена первая ошибка

```json
{
  "schema_version": "1.0",
  "status": "ok",
  "overall_confidence": 0.96,
  "problem": {
    "latex": "2x + 5 = 13",
    "text": "Решить уравнение 2x + 5 = 13",
    "topic": "linear_equation"
  },
  "result": "first_error_found",
  "first_incorrect_step_number": 1,
  "steps": [
    {
      "number": 1,
      "latex": "2x = 13 + 5",
      "status": "incorrect",
      "confidence": 0.98,
      "error": {
        "code": "sign_error",
        "label": "Неверный знак при переносе слагаемого",
        "explanation": "При переносе +5 в правую часть равенства знак меняется на противоположный: нужно вычесть 5, а не прибавить.",
        "corrected_latex": "2x = 13 - 5"
      }
    }
  ]
}
```

### Пример: все записанные шаги корректны

```json
{
  "schema_version": "1.0",
  "status": "ok",
  "overall_confidence": 0.94,
  "problem": {
    "latex": "\\frac{x}{3} - 2 = 4",
    "text": "Решить уравнение x/3 - 2 = 4",
    "topic": "equation"
  },
  "result": "all_steps_correct",
  "first_incorrect_step_number": null,
  "steps": [
    {
      "number": 1,
      "latex": "\\frac{x}{3} = 6",
      "status": "correct",
      "confidence": 0.99,
      "error": null
    },
    {
      "number": 2,
      "latex": "x = 18",
      "status": "correct",
      "confidence": 0.99,
      "error": null
    }
  ]
}
```

### Пример: нельзя надёжно проверить

```json
{
  "schema_version": "1.0",
  "status": "insufficient_context",
  "overall_confidence": 0.42,
  "problem": null,
  "result": "not_assessed",
  "first_incorrect_step_number": null,
  "steps": []
}
```

## Поля ответа

| Поле | Тип | Правило |
|---|---|---|
| `schema_version` | строка | Сейчас строго `"1.0"` |
| `status` | перечисление | Один из пяти статусов выше |
| `overall_confidence` | число от 0 до 1 | Уверенность в распознавании и проверке всего ответа |
| `problem` | объект или `null` | Условие, если оно уверенно распознано |
| `problem.latex` | строка | Условие в raw LaTeX, без разделителей |
| `problem.text` | строка | Короткая русская текстовая запись условия |
| `problem.topic` | строка | Свободная метка темы для аналитики, например `geometry`, `calculus`, `proof` |
| `result` | перечисление | `first_error_found`, `all_steps_correct` или `not_assessed` |
| `first_incorrect_step_number` | целое или `null` | Номер последней возвращённой карточки при первой ошибке |
| `steps` | массив | Только шаги, видимые пользователю, в порядке записи |
| `steps[].number` | целое | Последовательная нумерация с 1 без пропусков |
| `steps[].latex` | строка | Точная математическая запись шага пользователя в raw LaTeX; без `$` и без Markdown |
| `steps[].status` | перечисление | `correct` или `incorrect` |
| `steps[].confidence` | число от 0 до 1 | Уверенность именно в распознавании и оценке шага |
| `steps[].error` | объект или `null` | `null` у корректного шага, обязателен у ошибочного |
| `error.code` | перечисление | `sign_error`, `arithmetic_error`, `formula_error`, `invalid_transformation`, `domain_or_condition`, `logical_gap`, `other` |
| `error.label` | строка | Краткое название ошибки, до 100 символов |
| `error.explanation` | строка | Объяснение для школьника, до 500 символов, без Markdown |
| `error.corrected_latex` | строка или `null` | Верный вариант этого шага, если он однозначен |

### Инварианты, которые проверяет сервер

- В ответе не допускаются дополнительные поля.
- При `status != "ok"`: `result = "not_assessed"`, `problem = null` или уверенно распознанное условие, `steps = []`, `first_incorrect_step_number = null`.
- При `result = "all_steps_correct"`: есть хотя бы один шаг, все шаги `correct`, `error = null`, а `first_incorrect_step_number = null`.
- При `result = "first_error_found"`: есть хотя бы один шаг, все шаги до последнего `correct`, последний строго `incorrect`, `error` заполнен, а `first_incorrect_step_number` равен номеру последнего шага.
- Шагов после первого `incorrect` быть не должно.
- LaTeX и строки должны укладываться в лимиты размера. UI экранирует простой текст; LaTeX рендерится только проверенным математическим рендерером.

## JSON Schema для Structured Outputs

Эту схему следует передавать в режим structured output у провайдера, а затем всё равно валидировать Pydantic на сервере. Для краткости ограничение «только последний шаг может быть ошибочным» реализуется Pydantic-валидатором, а не только JSON Schema.

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "status", "overall_confidence", "problem", "result", "first_incorrect_step_number", "steps"],
  "properties": {
    "schema_version": { "const": "1.0" },
    "status": { "enum": ["ok", "needs_clearer_photo", "insufficient_context", "not_a_math_solution", "processing_error"] },
    "overall_confidence": { "type": "number", "minimum": 0, "maximum": 1 },
    "problem": {
      "anyOf": [
        { "type": "null" },
        {
          "type": "object",
          "additionalProperties": false,
          "required": ["latex", "text", "topic"],
          "properties": {
            "latex": { "type": "string", "maxLength": 4000 },
            "text": { "type": "string", "maxLength": 4000 },
            "topic": { "type": "string", "maxLength": 100 }
          }
        }
      ]
    },
    "result": { "enum": ["first_error_found", "all_steps_correct", "not_assessed"] },
    "first_incorrect_step_number": { "anyOf": [{ "type": "integer", "minimum": 1 }, { "type": "null" }] },
    "steps": {
      "type": "array",
      "maxItems": 30,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["number", "latex", "status", "confidence", "error"],
        "properties": {
          "number": { "type": "integer", "minimum": 1 },
          "latex": { "type": "string", "minLength": 1, "maxLength": 4000 },
          "status": { "enum": ["correct", "incorrect"] },
          "confidence": { "type": "number", "minimum": 0, "maximum": 1 },
          "error": {
            "anyOf": [
              { "type": "null" },
              {
                "type": "object",
                "additionalProperties": false,
                "required": ["code", "label", "explanation", "corrected_latex"],
                "properties": {
                  "code": { "enum": ["sign_error", "arithmetic_error", "formula_error", "invalid_transformation", "domain_or_condition", "logical_gap", "other"] },
                  "label": { "type": "string", "maxLength": 100 },
                  "explanation": { "type": "string", "maxLength": 500 },
                  "corrected_latex": { "anyOf": [{ "type": "string", "maxLength": 4000 }, { "type": "null" }] }
                }
              }
            ]
          }
        }
      }
    }
  }
}
```

## Инструкция для LLM

Схема выше должна быть передана механизмом structured output. В текст системной инструкции добавить:

```text
Ты проверяешь решение математической задачи по фотографии. Возвращай только объект JSON, соответствующий переданной схеме.

Сначала прочитай условие и рукописные/напечатанные шаги пользователя. Не добавляй отсутствующие шаги, не подменяй запись пользователя своим более красивым решением и не придумывай неразборчивые символы.

Проверяй шаги строго в порядке записи. Верни все корректные шаги до первой математической ошибки и сам первый ошибочный шаг. Не возвращай шаги после первой ошибки и не оценивай их. Если все записанные шаги корректны, верни их все.

Для ошибочного шага назови тип ошибки простым русским языком, объясни её кратко и дай corrected_latex только для правильного варианта этого же шага, если он однозначен. Не пиши полное решение задачи и не раскрывай внутренние рассуждения.

Если условие, важный символ, необходимый чертёж или часть решения нельзя прочитать уверенно, верни подходящий статус отказа, пустой список steps и не угадывай. Все текстовые поля пиши по-русски. LaTeX возвращай без $ и без Markdown.
```

## Что сохраняем

В PostgreSQL сохраняются валидированный JSON или его нормализованные поля, версия схемы, версия промпта, модель, время обработки, статус и обезличенные продуктовые события. Оригинальное изображение, его байты, ключ объекта, хеш содержимого и OCR-текст в пилоте не сохраняются. В логи и трассировки эти данные также не попадают.
