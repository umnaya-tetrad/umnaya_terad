# Отчёт о выполнении задач release

Файл ведётся рядом с [TASKS.md](TASKS.md). Для каждой задачи фиксируется, что именно сделано, какие проверки выполнены и что осталось непроверенным. Статусы не завышаются: если runtime не запускался, это указано явно.

База выполнения: ветка `release_tasks` от `002d814de6bab3b946208e0155e54e65c035cb27`. Коммит после каждой задачи локальный, без push.

## REL-01. Приём B4 и управление интеграцией

**Статус: выполнено (приём), runtime Compose не входил в задачу.**

Сделано:

- Сверены фактические commit вместо имён веток: B0 `1144c49`, B1 `fe3d741`, application `92fd1e8` + `b4ad6ad`, processing `0f8460d` (`9d78895`), source `d62f5ec`.
- Проверено, что сгенерированные DTO не разошлись с контрактом: `app/pilot/contracts.py` и `src/pilot/api/generated.ts` побайтово равны результату `build_contract.render_types()`; OpenAPI, JSON Schema и fixtures без drift.
- Проверено, что SQL `001–007` побайтово совпадают с pinned source; манифест BOOTSTRAP сверен построчно (23 blob без изменений, 12 адаптированы, 4 исключены с уже записанными причинами).
- Зафиксирована однократная передача общих файлов, `infra/`, `scripts/pilot/`, `docs/pilot/`, Compose, Dockerfile и account seed от application к release; `app/config.py`, `domain/`, `processing/`, `analytics/`, `events/` и SQL остались processing.
- Проверено отсутствие секретов в отслеживаемых файлах и в `.env.example`.
- Заполнен [HANDOFF release](HANDOFF.md) с таблицей приёма и [INTEGRATION_STATE](../../../../docs/pilot/INTEGRATION_STATE.md) с фактической базой и ревизиями.

Проверки:

| Команда | Результат |
|---|---|
| `python project-context/pilot/planning/shared/check_shared.py` | PASS, 73 теста (frozen checker, 158 UX-строк, OpenAPI 34 операции, 44 HTTP fixtures, 25 lifecycle, 4 пары analytics) |
| `python scripts/check_context.py` | PASS, 471 файл, 975 ссылок |
| `npm ci && npm test` | PASS, 6 файлов / 26 тестов |
| `npm run build` | PASS (предупреждение Vite о чанке 542 КБ) |
| `pytest --confcutdir tests/pilot/application tests/pilot/application -q` | PASS, 24 теста |
| `git diff --check` | PASS |

Не проверено: Compose/PostgreSQL runtime, браузерные smoke, платный Polza, внешний сервер — это REL-02 и последующие задачи.

## REL-02. Compose и миграции

**Статус: выполнено. Runtime проверен на локальном Compose (fixture), внешний сервер не входил.**

Сделано:

- Создан глобальный `pytest.ini` (маркер `release`, `pythonpath=.`), потому что команды приёмки из ACCEPTANCE заданы из корня.
- Написан `tests/integration/pilot/conftest.py`: HTTP-харнесс над реальным стеком через frontend-origin `/api`, пароли только из env или локального git-ignored `.env`, отсутствие конфигурации даёт ошибку, а не тихий skip.
- Написан `tests/integration/pilot/test_compose_persistence.py`: REL-C02 (один transport-source, отсутствие портов у backend/worker, приватный volume не в frontend, health без модели, polza без ключа fail-closed, Origin/cookie, нет статической раздачи фото), REL-C03 (15 миграций, повтор и параллельные runner'ы), REL-C04 (данные и Job после restart, изоляция второго учителя), REL-C26 (нет register/analyze/control и редактирования title).
- Собран и поднят локальный стек: `build` → `run --rm migrate` → `up -d --wait` → seed дважды. Проверены API smoke, `--retry`, браузерный Compose-прогон и `--restart`.
- Записаны факты проверки в [INTEGRATION_STATE](../../../../docs/pilot/INTEGRATION_STATE.md) и [HANDOFF](HANDOFF.md).

Проверки:

| Команда | Результат |
|---|---|
| `docker compose -f compose.yaml config -q` | PASS |
| `docker compose -f compose.yaml build` | PASS |
| `docker compose -f compose.yaml run --rm migrate` (повтор и параллельно) | PASS, 15 миграций без дублей, checksums стабильны |
| `docker compose -f compose.yaml up -d --wait` | PASS, все сервисы healthy |
| `python -m pilot.operations.create_fixture_accounts` (дважды) | PASS, 2 teacher + 1 staff, пароль не сброшен |
| `python scripts/pilot/smoke_application.py` и `--retry` | PASS |
| `npm run test:browser:compose` и `-- --restart` | PASS |
| `pytest tests/integration/pilot -q -k "rel_c02 or rel_c03 or rel_c04 or rel_c26"` | PASS, 5 тестов |
| `ruff check tests/integration/pilot` | PASS |

Не проверено: реальная модель Polza (платных вызовов нет), настоящие Android/iPhone, внешний HTTPS/deploy.

## REL-03. Accounts и безопасный reset

**Статус: выполнено. Runtime проверен на локальном Compose (fixture).**

Сделано:

- Создан `app/pilot/operations/manage_accounts.py` с командами `seed`, `create`, `reset`. Это тонкая обёртка над `ensure_account` и `reset_account_password` processing: собственного SQL, хеширования и второй модели аккаунтов нет.
- Пароль берётся скрытым вводом или из `PILOT_ACCOUNT_PASSWORD`; флага `--password` не существует, значения не печатаются. `operator_ref`/`request_id` уходят в доменный аудит.
- Написан `tests/integration/pilot/test_acl_staff.py`: REL-C05 (состав, seed дважды, логин/логаут, reset с отзывом только своих сессий, сохранность материалов, отказы CLI) и REL-C06 (ACL на чужие ID, staff read-only, exact Origin, приватные заголовки фото).
- Обновлены [HANDOFF](HANDOFF.md) (раздел управления аккаунтами и расположение локального env-файла) и [INTEGRATION_STATE](../../../../docs/pilot/INTEGRATION_STATE.md) (таблица проверок). Локальный env вынесен из рабочего дерева в `~/.config/smartnote/pilot.env`, потому что `check_context.py` отклоняет `.env` в репозитории; Compose получает его через `--env-file`.

Проверки:

| Команда | Результат |
|---|---|
| `manage_accounts seed` (дважды) | PASS, staff=1 / teacher=2, повтор без сброса |
| `manage_accounts create --role staff` для teacher-логина | отказ `invalid_state` |
| `manage_accounts reset` с новым паролем | PASS, старые cookie 401, новый пароль работает, данные T1 целы |
| `manage_accounts reset` неизвестного логина | отказ `not_found` |
| `reset --password ...` | argparse отклоняет флаг; такого аргумента нет |
| `pytest tests/integration/pilot/test_acl_staff.py -q` | PASS, 3 теста |
| `pytest tests/integration/pilot -q` | PASS, 8 тестов |
| `ruff check tests/integration/pilot app/pilot/operations` | PASS |

Не проверено: выдача аккаунтов школе и reset на внешнем сервере — вне локального выпуска.

## REL-04. Закрытый просмотр команды

**Статус: выполнено. Runtime и браузер проверены на локальном Compose (fixture).**

Сделано:

- Создан `app/pilot/routes/staff.py`: только `GET /staff/checks` (фильтр `owner_login`, курсор, limit 1–100) и `GET /staff/checks/{id}` с `ETag`. Добавлена зависимость `staff_actor`, которая отказывает teacher до обращения к домену.
- Создан `app/pilot/services/staff.py`: тонкая передача в `pilot.domain.queries`, без своей SQL и второй модели прав.
- Staff router подключён в `app/pilot/router.py` — release впервые владеет общей точкой входа.
- Создан `src/pilot/staff/StaffScreens.tsx` (список с фильтром, детали, фото, разборы, третье лицо в отзывах, staff-only история поколений и сводок) и `StaffScreens.test.tsx`. Мутационных кнопок нет.
- В `src/pilot/api/client.ts` добавлены `listStaffChecks`, `getStaffCheck`, `getBundleHistory`, `getSummaryHistory` на сгенерированных типах; в `PilotApp.tsx` подключён staff shell при `role === 'staff'`.
- Добавлены `playwright.config.ts`, `tsconfig.e2e.json`, `@types/node` и скрипт `npm run test:e2e`, потому что команды ACCEPTANCE заданы через `npx playwright test`.
- Созданы `app/tests/pilot/staff/test_staff_routes.py` (ASGI) и `tests/e2e/pilot/staff_readonly.spec.ts`, интеграционный `tests/integration/pilot/test_staff_readonly.py`.
- Тест выявил реальный дефект: release-route не проверял роль сам, полагаясь только на домен. Добавлена явная зависимость, покрыта тестом.
- Обновлены [HANDOFF](HANDOFF.md) и [INTEGRATION_STATE](../../../../docs/pilot/INTEGRATION_STATE.md).

Проверки:

| Команда | Результат |
|---|---|
| `pytest tests/pilot/staff -q` (из `app/`) | PASS, 8 тестов |
| `pytest tests/integration/pilot/test_staff_readonly.py -q` | PASS, 2 теста |
| `pytest tests/integration/pilot -q` | PASS, 10 тестов |
| `npm test` / `npm run build` / `npx tsc -b` | PASS, 28 тестов, сборка |
| `npx playwright test tests/e2e/pilot --grep REL-C07` | PASS |
| `npm run test:browser:compose` | PASS; учительский путь не сломан |
| `ruff check` по затронутым Python-файлам | PASS |

Не проверено: внешний сервер (staff на реальном домене) и реальные устройства.
