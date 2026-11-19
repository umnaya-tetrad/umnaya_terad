# Границы модулей и файлов

19.11.2026. **Спецификация для реализации.** Код пилота этим документом не создан. Три направления: **application** — приложение; **processing** — обработка; **release** — локальный выпуск и интеграция. Продукт задают [PRODUCT](../../PRODUCT.md) и R01–R86; HTTP/данные — [API_CONTRACT](API_CONTRACT.md) и `api/`. Эти решения уточняют инженерные вопросы [черновика](../CONTRACT_DRAFT.md), не вводят новый продукт.

## Основа и размещение

Весь будущий код находится в корне `umnaya_terad`. Соседние SmartNoteLanding и product-kit остаются источниками: рабочие изменения в них не выполняются. Сохраняются React/TypeScript/Vite, FastAPI, PostgreSQL 16, серверные cookie и отдельный Python worker; очередь в PostgreSQL, без обязательных Redis/Celery. Документация остается в `project-context/`.

19.11.2026 read-only проверкой установлен чистый checkout `C:\Users\User\Desktop\3_year\SmartNoteLanding`, HEAD **`d62f5ecb8c1c53b1c97faf06530b8d84e691f88d`**. Это выбранная исходная ревизия будущего bootstrap вместо более старого снимка `b8423b0…`. Прочитаны AGENTS, package.json, compose.yaml, наличие auth и миграций; программа не запускалась. Источник содержит frontend/backend/postgres, но не worker пилота. Правило источника о несохранении оригиналов противоречит актуальному пилоту: в новом приложении оригиналы сохраняются приватно. Публичная регистрация, рекламные квоты/тарифы и обработка без входа из источника не переносятся в доступный поток пилота.

До импорта application сохраняет SHA и перечень выбранных файлов в `docs/pilot/BOOTSTRAP.md`. Переносятся только необходимые отслеживаемые код/конфиги/зависимости: `src/`, Python-модули `app/`, `app/migrations/001–007`, соответствующие unit-тесты, package/lock, tsconfig/Vite, index.html, Dockerfile и Compose как основа переработки. Нельзя копировать каталоги целиком без проверки состава: исключены `.env*` кроме заново проверенного безопасного шаблона, `.git`, node_modules, virtualenv, dist, кэши, inputExamples, benchmark-results, outputs, реальные фото и сырые ответы. Не повторять импорт поверх `project-context/`. Сначала проверяется содержимое manifest, затем импортируется именно закрепленная ревизия; незакоммиченные файлы источника не являются входом. Сейчас импорт не выполняется.

## Целевое дерево и единственный владелец

Пути ниже относительны корню `umnaya_terad`; отсутствующие пути — задания на создание, не наличие реализации.

```text
src/
  App.tsx / main.tsx          application до B4 -> release: shell entrypoints
  pilot/                      application: teacher UI, API client, UI events
    api/generated.ts          processing: генерация из api/, без ручных правок
    staff/                    release: закрытый read-only UI
app/
  main.py                     application до B4 -> release после 18:00
  pilot/
    router.py                 application до B4 -> release после 18:00
    contracts.py              processing: генерация из api/
    domain/                   processing: модели, repository, access, revision,
                              storage, mutations, migration runner
    processing/               processing: jobs, worker, transport, funds, pause
    analytics/                processing: snapshot, prompt, schema, validation
    events/                   processing: receiver, dedupe, audit, server events
    routes/
      auth.py                 application
      application.py          application
      processing.py           processing
      events.py               processing
      staff.py                release
    services/
      application.py          application: orchestration стандартных операций
      staff.py                release: read-only queries + audit
    operations/               release: accounts, local commands
      create_fixture_accounts.py
      __init__.py             application до B4 -> release: ранний local seed
  migrations/                 processing: вся SQL-цепочка и registry
  tests/pilot/
    application/              application
    domain/ processing/
    analytics/ events/         processing
    staff/                    release
tests/
  e2e/pilot/                  release: общий сквозной прогон
  integration/pilot/          release: DB/Compose/restart/concurrency
infra/                        application до B4 -> release после 18:00
scripts/pilot/                application до B4 -> release после 18:00;
                              release добавляет processing_control.py
docs/pilot/                   application до B4 -> release после 18:00
compose.yaml                  application до B4 -> release после 18:00
Dockerfile app/Dockerfile     application до B4 -> release после 18:00
package*.json tsconfig*.json
vite.config.* index.html
playwright.config.*           application до B4 -> release после 18:00
.env.example .gitignore
.dockerignore .github/        application до B4 -> release после 18:00
project-context/pilot/planning/shared/
  API_CONTRACT.md api/**       processing
  MODULE_BOUNDARIES.md
  HANDOFF_PROTOCOL.md
  COMPATIBILITY.md            release: интеграционные правила
```

Перечень исчерпывается правилами: `src/**`, кроме указанных исключений, принадлежит application; `app/**`, кроме перечисленных route/service/operations/test/entrypoint-исключений, — processing; корневые инструменты, инфраструктура и общие конфиги принадлежат application до B4, затем release. Сохраняемые старые `app/auth.py`, `config.py`, `image_validation.py`, `polza_client.py`, `schemas.py`, `prompts.py` и backend-тесты относятся к processing; старый UI и его unit-тесты — application. Новые файлы не помещаются в чужую область ради обхода владельца. Каждый `planning/{application,processing,release}/{TASKS,ACCEPTANCE,HANDOFF}.md` обновляет соответствующее направление; сводные planning-документы — release. Продуктовые документы меняются только при действительном doc-impact, без выдуманных R-решений.

## HTTP и доменные операции

| Файл route / владелец | Операции под `/api` |
|---|---|
| `auth.py` / application | login, logout, session; никакого register |
| `application.py` / application | checks list/create/read/delete; notebooks create/delete; bundles create/delete/history; versions create/discard draft; draft photos upload/delete/order; assets read; task review/delete |
| `processing.py` / processing | bundle submit/retry/skip; task skip; job status; begin-completion/finalize; summary read/history/refresh/retry |
| `events.py` / processing | POST events: validation, dedupe, safe acceptance |
| `staff.py` / release | staff checks list/detail; только чтение с аудитом |

Точные URL/методы/DTO берутся только из OpenAPI, эта таблица назначает владельцев. Bundle/history и summary/history — закрытые staff-only операции поддержки, независимо от владельца route-файла. Учителю доступны текущие комплекты/результаты через CheckDetail, история сохраненных проверок и выбранная актуальная сводка; отдельного UI истории версий для него нет. `app/pilot/router.py` подключает каждый router один раз. До B4 main/router изменяет только application, после передачи в 18:00 — release; processing пишет собственные routes/worker entrypoint и не меняет main/router.

До B1 application объявляет стабильные hooks подключения routers и сервисов; processing на B1b дает импортируемые модули с согласованными APIRouter/entrypoint. Поэтапная реализация не ломает импорт API/worker. Временный пустой router не считается реализованным endpoint; запрещено скрывать неожиданные ImportError или выдавать заглушку за успешную обработку. Реализация содержимого модулей до B3 не требует независимых правок main/router processing.

Application выполняет HTTP/UI и стандартный CRUD через общую доменную библиотеку processing. Один `domain/mutations.py` содержит транзакционные операции изменения состава, загрузки/замены/удаления, отзыва и общие guards. Один `domain/revision.py` сериализует влияющие на финал изменения по Check, один `domain/access.py` проверяет владельца/роль; проверка прав в браузере их не заменяет. Application не пишет SQL-дубликат удаления/отзыва и не создает Job отдельно от доменного submit. Processing вызывает те же guards при публикации worker, snapshot и финале. Владелец финансового lifecycle обоих типов Job, глобальной конкурентности и паузы — processing.

Все модели Account/Session, Check/Notebook/Bundle/InputVersion/PhotoAsset, Job/Attempt, BundleAnalysis/Task/TaskAnalysis/Review, Snapshot/AnalyticsResult, Event/Audit и Funds принадлежат processing. Даже поле для staff или UI добавляется через эту область. Processing пишет всю SQL-цепочку и проверяет upgrade; release применяет миграции и независимо проверяет их. После применения SQL-файл неизменяем: исправление новой миграцией. Отдельная корневая `migrations/` не создается. Исходные 001–007 сохраняются как история; новые миграции — начиная с 008, их порядок выделяет processing.

Сессии используют общий auth/access processing; application отвечает за cookie endpoints и UI входа. Контрактные роли — `teacher`, `staff`; `staff` реализует область read-only доступа T09, названную в техническом плане `staff_read`, и никогда не меняет отзывы. Публичной регистрации, роли operator и HTTP endpoint управления обработкой нет.

До B1 application создает минимальный `app/pilot/operations/create_fixture_accounts.py` и пакетный `__init__.py`: локальные два учителя и staff через общие auth/schema processing, без собственной модели паролей/SQL. Команда из корня: `docker compose -f compose.yaml exec backend python -m pilot.operations.create_fixture_accounts`. Секреты берутся из локального окружения, не из аргументов CLI и не из Git; CLI не печатает пароли. Ранний seed и тестовая сессия не зависят от работы release. Эти два файла остаются у application до B4; после 18:00 release принимает их по commit и HANDOFF и доводит безопасное создание/сброс аккаунтов. Передача однократная, раннее владение не распространяется на весь `operations/`.

Ручная пауза/возобновление выполняется release через `scripts/pilot/processing_control.py` с локальным привилегированным доступом к Compose/БД и аудитом. CLI вызывает одну доменную функцию processing, а не вторую реализацию очереди/финансов; учительская cookie и read-only staff роль не дают права менять режим. Processing передает функцию/тесты паузы до 18:00, release дает локальную оболочку и инструкцию.

Клиентские события emits принадлежат application; staff-события и локальные операционные команды — release; схема, прием, дедупликация, серверные события и аудит — processing. Потеря телеметрии не блокирует учительский путь.

## Передача владения и исправления

Application обеспечивает первоначальный Compose, миграции через готовый runner processing, тестовую сессию и подключение router **до раннего рабочего цикла**. B1 из [HANDOFF_PROTOCOL](HANDOFF_PROTOCOL.md) фиксирует рабочий baseline и стабильные hooks, но не передает владение. Application остается единственным владельцем общих entrypoint/config/инфраструктурных файлов до B4. В 18:00 release однократно принимает их вместе с account seed; точный commit и список путей фиксируются в HANDOFF обеих сторон. До этой записи владелец application, автоматического переключения по часам нет. Работа 14:00–18:00 не зависит от release; второй bootstrap не создается.

Ранний account seed application создает и использует до B1, а передает release вместе с общими конфигами на B4 в 18:00. В B1 нет ожидания позднего account CLI или operator endpoint.

После 18:00 интегратор release вправе исправлять любой воспроизводимый дефект по зафиксированному контракту без ожидания автора модуля. Это ограниченное исключение из путей: отдельный fix commit, reproduction, тест и запись в HANDOFF; авторство миграций/семантики остается processing. Несовместимое API или новое продуктовое поведение не являются таким исправлением. Неявное согласование молчанием запрещено.

Processing передает функционально полные обработку **и аналитику** к 17:00, исправления/доказательства — до 18:00. Вечерний выпуск не планирует создание отсутствующего ядра. К 21:00 проверяется локальная сборка, внешний deploy и школьная апробация — отдельные этапы.

## Доступность выбранной ревизии источника

19.11.2026 read-only `git ls-remote --heads https://github.com/svn-re7/SmartNoteLanding.git` подтвердил d62f5ecb8c1c53b1c97faf06530b8d84e691f88d в ветке `codex/direct-landing-experiment`. Default main остается b8423b01a5eb56601539e83d14c382d23eea1a61 и не является выбранной основой. Bootstrap получает указанную ветку/объект и проверяет точный SHA, без записи в upstream и без копирования secrets. Исходная ревизия доступна [по закрепленному tree](https://github.com/svn-re7/SmartNoteLanding/tree/d62f5ecb8c1c53b1c97faf06530b8d84e691f88d). Локальная чистота checkout и удаленные refs проверены, программа при этом не запускалась.

## Staff без ранней зависимости

До B4 application подключает только существующие auth/application/processing/events routers; отсутствующий staff router/UI не импортируется. Ранние auth/asset/history ACL реализуют владельцы app/processing и проверяются до передачи. listStaffChecks/getStaffCheck и полный staff UI создает release в REL-04 после B4. src/App.tsx/src/main.tsx являются bootstrap entrypoint: application до B4, затем release, вместе с main/router/Compose. Application после B4 продолжает teacher-компоненты, не правит принятые shell entrypoint. Функция места подключения не является fake-success staff endpoint; неожиданные ImportError не скрываются.
