# ТЗ processing: домен, обработка и AI-сводка

19.11.2026. Статус исполнения – **planned**. Это индивидуальное ТЗ, не реализация и не отчет о готовом пилоте. HTTP и данные задает [shared v1](../shared/README.md), получивший [два независимых PASS](../shared/SHARED_REVIEW.md): [API_CONTRACT](../shared/API_CONTRACT.md), [OpenAPI](../shared/api/openapi.json), [схемы/типы](../shared/api/README.md), [аналитика](../shared/analytics/README.md). Основание – R01–R86 и [A01–A25](../../TRIAL_AND_ACCEPTANCE.md). Q49 заново не проектируется: snapshot, prompt, результат и lifecycle определены shared v1.

Прочитать [TASKS](TASKS.md), [ACCEPTANCE](ACCEPTANCE.md), [HANDOFF](HANDOFF.md), [границы файлов](../shared/MODULE_BOUNDARIES.md), [передачу](../shared/HANDOFF_PROTOCOL.md), [совместимость](../shared/COMPATIBILITY.md), [формат ТЗ](../TASK_FORMAT.md), [матрицу Axx](../COVERAGE_MATRIX.md), frozen [AI-пакет](../../ai/README.md) и весь `shared/analytics/`, включая prompt/schema/validator/fixtures. CONTRACT_DRAFT не альтернативный контракт.

## Обязательный результат и сроки

Постоянные данные и доступ, общая библиотека операций для CRUD, приватные фото, долговечная очередь двух типов Job, защищенная публикация поколений, отдельные отзывы/пропуски, атомарный двухэтапный финал, сохраненная LLM-сводка, stale/refresh/retry, общий резерв средств, сверка unknown, ручная пауза и безопасные события. Путь проверяется без UI через fixture transport и PostgreSQL 16.

| Gate согласованной сессии | Выход processing |
|---|---|
| B0 до независимой реализации | Один contract commit shared v1 с offline PASS; новые поля/enum/HTTP самостоятельно не вводятся |
| B1b до B1 к 14:00 | Миграции/runner, auth/access/revision/errors, Services и публичные сигнатуры, storage, рабочие create/read/photo/submit-queue, импортируемые routers, worker health, generated DTO. CRUD не ждет аналитики |
| B2 около 16:00 | Фото→сохраненный Job→валидный Report→независимый отзыв→reload на fixture; фон и версии работают |
| B3 к 17:00 | PROC-01–PROC-11 функционально готовы: финал, отдельная аналитика, деньги/unknown/пауза, события, гонки и отрицательные случаи |
| B4 до 18:00 | Исправления, повтор приемки, commit/HANDOFF. Нет планового дописывания аналитики после 18 |

Часы – контрольные точки сессии, не назначение календарной даты. Непройденный gate записывается конкретным BLK-processing-NN; отсутствие ядра не переносится молча на вечер.

## Область и зависимости

Processing: `app/migrations/**`, `app/pilot/domain/**`, `processing/**`, `analytics/**`, `events/**`, `routes/processing.py`, `routes/events.py`, соответствующие backend-тесты; унаследованные backend auth/config/Polza/budget и `app/requirements.txt`. `app/pilot/contracts.py` и `src/pilot/api/generated.ts` производятся из shared, без ручной правки. Shared после B0 фиксирован; несовместимость передается координатору.

`main.py`, общий `pilot/router.py`, Compose, Dockerfiles, frontend и общие конфиги до B4 – application. Processing дает готовые импорты/команды, эти файлы не меняет. Application предоставляет pinned bootstrap, pool/settings, подключение HTTP и ранний seed через общий auth. Release делает оболочки локальных CLI и независимую приемку; это не зависимость разработки ядра до 17. Staff HTTP/UI read-only – release через общие query/access/audit порты.

При подготовке ТЗ read-only проверен чистый source SmartNoteLanding SHA `d62f5ecb8c1c53b1c97faf06530b8d84e691f88d`: asyncpg/FastAPI/httpx/Pillow, salted scrypt и hashed opaque sessions в auth, PostgreSQL reserve/unknown в experiment, Polza client, SQL001–007. Это задел, не готовая очередь. Не переносить register, visitor/daily/hourly/send_limit квоты, несохранение оригиналов или `RESERVE_RUB=100` как правила пилота. После bootstrap повторно сверить manifest/реальные исходные тесты, сохранить происхождение.

## Режимы и проверки

`PILOT_TRANSPORT=polza|fixture`, обычный режим **polza**: без серверного ключа fail closed, без автоматического fallback. Fixture выбирается явно для локальной приемки/тестов и запрещает вызов провайдера. Application передает одну Compose-переменную как `VITE_PILOT_TRANSPORT`; UI показывает «Учебный режим» при fixture. HTTP DTO не расширяются. Live smoke только opt-in после отдельного разрешения бюджета, с учетом расхода и границ проверки; не скрытая часть CI и не апробация.

Реально существующие проверки из корня:

```powershell
python project-context/pilot/planning/shared/check_shared.py
python scripts/check_context.py
git diff --check
git diff --cached --check
```

Зависимости gate – `shared/requirements.txt`, проверено отдельным Python3.12 venv. Runtime-команды ACCEPTANCE **требуется создать**, сейчас они не выполнены. По умолчанию они используют PG16 и явный fixture без платных вызовов.
