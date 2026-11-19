# Офлайн контракт API 1.0.0

19.11.2026. HTTP-сервер пилота еще не реализован. Нормативная семантика – [API_CONTRACT](../API_CONTRACT.md), машинные формы – [openapi.json](openapi.json), [domain.schema.json](schemas/domain.schema.json). Все fixtures синтетические; math JSON для multi/continuation переиспользует разрешенные исходные [examples](../../../ai/examples/provenance.json) без изменения frozen-артефактов. `synthetic-photo.png` – пустой синтетический снимок 64×64 для HTTP/mock, не математический пример и не школьная работа. Размер удовлетворяет frozen adapter minimum edge 32; валидатор проверяет IHDR, CRC каждого chunk и распаковку scanlines.

Из корня репозитория, в отдельном виртуальном окружении Python 3.12 (проверено):

```powershell
python -m pip install -r project-context/pilot/planning/shared/api/requirements.txt
python project-context/pilot/planning/shared/api/build_contract.py --check
python project-context/pilot/planning/shared/api/validate.py
python -m pytest project-context/pilot/planning/shared/api/tests -q
```

Только установка зависимостей может обращаться к package registry. Все команды проверки выполняются без приложения, БД, учетных данных, сети и платного API. `validate.py` сначала разрешает `$ref` через local Registry с запретом сетевых URI и выхода из репозитория; затем проверяет полностью материализованную OpenAPI 3.1 через openapi-spec-validator. JSON Schema 2020-12 проверяется jsonschema с FormatChecker (UUID/date-time). Frozen checker имеет alias `urn:smartnote:page-check:1.2` только в offline resolver, его исходный JSON не изменяется. domain `$id:domain.schema.json` относительный, чтобы переносимые file refs не ломались от URN базы. Идентификаторы DTO – `schemas/domain.schema.json#/$defs/Check` и аналогично другим именам. Analytics IDs – `urn:smartnote:summary-input:1`, `urn:smartnote:class-summary:1`.

Исходник форм – `build_contract.py`. После согласованного изменения:

```powershell
python project-context/pilot/planning/shared/api/build_contract.py
python project-context/pilot/planning/shared/api/build_fixtures.py
```

Генератор выпускает OpenAPI, domain schema, `contracts.ts` и `contracts.py` из одной структуры. Python TypedDict и TypeScript описывают DTO, а не runtime-валидатор; UUID/ranges/strictness проверяются JSON Schema. Будущий processing переносит эти файлы соответственно в `src/pilot/api/generated.ts` и `app/pilot/contracts.py`; публичные поля независимо не дописываются. `build_contract.py --check` сравнивает все четыре артефакта с генерацией в памяти, без перезаписи файлов. Сборку fixtures менять отдельно, когда меняется сценарий; тесты проверяют все объявленные HTTP операции.

`fixtures/http.json`: каждый элемент – operation_id, path_parameters, request.headers/body, response.status/headers/body. Multipart fixture указывает локальный filename в поле file; в настоящем HTTP это бинарный part, не JSON и не путь на сервере. response.body=null для бинарного фото и 204. Ключи и пароли fixtures придуманы и не дают доступа. Staff history содержит два успешных поколения одного InputVersion в отдельных runs с разными Report/reviews/tombstones. `fixtures/lifecycle.json` содержит полные Check DTO: multi-task, continuation, pending/failed/blocked/unknown, смешанный пропуск, финал, stale, comment-only, удаление и новая сегментация 2→3; `fixtures/summary-guards.json` – серверные условия refresh/retry, включая внутренний факт возможной отправки, который не дублируется в teacher DTO. Результат аналитики в примере – тестовый LLM oracle, не реальный вызов.

Проверки пакета не доказывают runtime ACL, SQL atomicity, отсутствие внешних дублей, мобильную камеру или качество математики/LLM. Их проверяют после реализации по модульной приемке. Исходные пользовательские документы и frozen checker здесь не меняются.
