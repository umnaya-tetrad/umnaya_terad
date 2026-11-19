# ТЗ application: учительское приложение и ранняя сборка

Версия 1 · 19.11.2026 · **planned**. Полное задание на будущую реализацию, не готовый код. Часы ниже относятся к согласованной рабочей сессии; календарная дата отдельно не назначена. Итог к 21:00 – локальная сборка, внешний выпуск отдельно, R85.

## Вход без истории чата

1. Прочитать корневой AGENTS и проектные skills smartnote-pilot, smartnote-doc-sync, smartnote-preflight.
2. Прочитать [shared/README](../shared/README.md), [API_CONTRACT](../shared/API_CONTRACT.md), [OpenAPI](../shared/api/openapi.json), [MODULE_BOUNDARIES](../shared/MODULE_BOUNDARIES.md), [HANDOFF_PROTOCOL](../shared/HANDOFF_PROTOCOL.md) и [COMPATIBILITY](../shared/COMPATIBILITY.md).
3. Для интерфейса – [MOBILE_UX](../shared/MOBILE_UX.md), [ux-flows](../shared/ux-flows.md), [ux-copy](../shared/ux-copy.json). Смысл результатов – [PRODUCT](../../PRODUCT.md), R01–R86 в [DECISIONS](../../DECISIONS.md), [SUMMARY_METRICS](../../SUMMARY_METRICS.md). Старый CONTRACT_DRAFT не альтернативный API.
4. Выполнять [TASKS](TASKS.md), проверять [ACCEPTANCE](ACCEPTANCE.md), факты записывать в [HANDOFF](HANDOFF.md). [COVERAGE_MATRIX](../COVERAGE_MATRIX.md) распределяет A01–A25; это ТЗ детализирует долю application.

Общий пакет получил независимый PASS: [SHARED_REVIEW](../shared/SHARED_REVIEW.md). Офлайн gate подтверждает совместимость спецификации, не auth, очередь, камеру или Compose runtime. Fixture-ответ нельзя выдавать за проверку живой модели.

## Результат и границы

Мобильный teacher UI: готовый аккаунт → история/новая проверка → условная тетрадь → упорядоченные фото → совместный submit → отдельные разборы/отзывы → двухэтапное завершение → текущая сводка. Фото не равно задаче; отзыв оценивает ИИ. Экраны и короткие тексты уже заданы shared. Не создавать второй словарь, переименования, новые роли или функции.

Application также поставляет безопасный bootstrap pinned source, frontend/API/Compose entrypoints и ранний локальный seed аккаунтов. Свои HTTP routes auth/CRUD вызывают публичные доменные сервисы processing; SQL, модели, guards, storage-политика, права, математическая аналитика и worker не дублируются.

| Владение application | Исключения |
|---|---|
| `src/**`, teacher `src/pilot/**`, UI-тесты в `src/pilot/**` | `src/pilot/api/generated.ts` – processing, read-only; `src/pilot/staff/**` – release |
| `app/pilot/routes/auth.py`, `routes/application.py`, `services/application.py`, `app/tests/pilot/application/**` | `domain/**`, `processing/**`, `analytics/**`, `events/**`, SQL и старые backend-модули, включая `app/config.py`, – processing |
| До B4: `app/main.py`, `app/pilot/router.py`, `compose.yaml`, Dockerfile, `app/Dockerfile`, package/tsconfig/Vite/index, Playwright config, `infra/**`, `scripts/pilot/**`, `docs/pilot/**`, безопасные env/ignore/CI | После B4 в 18:00 эти общие файлы – release; не править их параллельно |
| До B4: только `app/pilot/operations/create_fixture_accounts.py` и `operations/__init__.py` | Остальной `operations/**` и сопровождение seed после передачи – release |

Application не пишет тесты в `tests/e2e/pilot` и `tests/integration/pilot`: это release. Здесь поставляются unit/HTTP-тесты и точные сценарии; release создает независимые e2e. После передачи общих файлов исправление направляется текущему владельцу. Правила исключительных интеграционных fixes – в HANDOFF_PROTOCOL.

## Порядок и зависимости

| Этап | Работы | Основание |
|---|---|---|
| После B0 параллельно | APP-01/02: manifest/import/hooks; APP-05/06: API client и экраны на fixtures | Один contract commit; не ждать законченного UI/LLM |
| B1a/B1b → B1 до 14:00 | APP-02/03/04: Compose, auth/CRUD, миграции processing; seed CLI уже в B1a, его runtime+Job на fixture transport до B1 | Импортируемые доменные порты/runner/worker health processing |
| B2 около 16:00 | APP-05–10: вход→фото→Job→разбор→отзыв→reload на локальной БД | Общий domain и актуальные revision; mocks только в тестовом режиме |
| B3 к 17:00, B4 до 18:00 | APP-11–14: финал/сводка/события; передача teacher пути и общих файлов | Processing дает полный API-путь аналитики; одного prompt/schema недостаточно |
| 18:00–21:00 | APP-15: UI-доводка и fixes общей сборки | Release уже владеет общими конфигами+seed; нового проектирования API не требуется |

Контрольные точки – артефакты/коммиты и HANDOFF, не встречи. Отсутствие B1b фиксируется конкретным BLK, независимая работа на fixtures продолжается. Не обходить отсутствие домена собственными таблицами, in-memory хранением или платным запросом из HTTP.

## Transport и учебный режим

`PILOT_TRANSPORT=polza|fixture`, обычный default – `polza`. В polza отсутствие ключа означает отказ конфигурации до dispatch, без автоматического перехода на fixture. Автотесты/локальная приемка явно выбирают `fixture` без платных вызовов. Compose имеет один источник PILOT_TRANSPORT и передает его frontend как VITE_PILOT_TRANSPORT. При fixture в UI постоянно видна тонкая метка `common.fixture_mode` с точным текстом «Учебный режим»; HTTP DTO ради этого не расширяется. Метку берет единый shared-каталог, не создается альтернативный словарь. Полная конфигурация и имена переменных – в [LOCAL_ENV](../shared/LOCAL_ENV.md). Изменения source Settings поставляет processing до B1, application проверяет совместимость и связывает env/Compose.

## Проверки и принятие

Команды будущего приложения в TASKS/ACCEPTANCE **создать и выполнить при реализации**. До импорта нет оснований записывать npm/build/backend/Compose/e2e как PASS. Уже существующий офлайн gate: `python project-context/pilot/planning/shared/check_shared.py`; факты и границы – в SHARED_REVIEW.

Готовность требует APP-01–15 и относящихся APP-C01–35 с pass/fail/not_run по фактам, source/contract/integration/code commit, transport и ограничений. Реальные Android/iPhone, эмуляция, live модель, публичный сервер и самостоятельная апробация – разные результаты. Публикация, внешний доступ и платные вызовы этим ТЗ не разрешены.

Уточнение B4: src/App.tsx/src/main.tsx передаются release вместе с router/main/Compose; teacher-компоненты остаются application. До B4 отсутствующие staff module/UI не импортируются: объявлено лишь место подключения. Полные listStaffChecks/getStaffCheck/staff UI создаются в REL-04; ранние auth/privateasset/history ACL проверяются отдельно и не ждут release. APP-C27 явно разделен на раннюю и позднюю части.
