# Состояние и передача release

20.11.2026, Asia/Yekaterinburg. **status: in_progress — формальная передача release; локальная fixture-приемка исправлений завершена.** B4 принят 19.11, исходные REL-01–REL-12 завершены в `release_tasks` и объединены в main `a7a7454` (база аудита). В `fix/release-audit` все шесть исходных дефектов и дополнительный mount R1 закрыты; production fixes завершаются `9980048`, code/test HEAD — `261bb6e`. 63 ops-теста, 43 frontend-теста/build, усиленные C24/C15 (3), финальный E2E (15), application/staff/legacy (24/8/11), backend processing 99 и полный integration 51 — PASS. Это проверка локальных исправлений, без общей готовности пилота, платной модели, физических телефонов, deploy и школьной апробации. Точные SHA, новые команды/результаты и ограничения — [RELEASE_REPORT](../../../../docs/pilot/RELEASE_REPORT.md). Таблицы приемки 19.11 ниже сохранены как история, а не сегодняшний повтор.

## Формат формальной передачи

`in_progress` относится к документальной передаче, а не к незавершенным тестам или открытым дефектам. Формат `ready` в `check_tasks.py` требует собственные release `RUNTIME_REPORT.md`/`runtime-results.json` и clean tree в начале/конце прогона. Эта задача их не создавала: фактический processing run `e801c0690ca94853885ca244f9fa7b1c` имеет неизменный code/test HEAD, но `working_tree_clean_at_start/end=false` из-за 9 файлов doc-sync. Это не подменяется ложным `clean=true`; все 193 backend/integration-теста (99+24+8+11+51) реально прошли. Протокол gate сохранен без изменений, сведения о прогоне зафиксированы в RELEASE_REPORT и приватном evidence.

## Ревизии первоначальной передачи, 19.11.2026

| Поле | Фактическое значение |
|---|---|
| Рабочая ветка | `release_tasks`, создана от `main` `002d814de6bab3b946208e0155e54e65c035cb27` |
| Интеграционная база (факт) | `002d814de6bab3b946208e0155e54e65c035cb27` (`origin/main`). Отдельная ветка `integration/pilot-local` не создавалась; её роль выполняет линейная история `release_tasks` поверх этой базы |
| B0 contract commit | `1144c498b4aba1e4e4fe118abe7c3f6f1b940198` — shared v1, OpenAPI 1.0.0 |
| B1 runtime baseline | `fe3d741dc92fd7d2d6c24500fd4e824775563e80` — интеграция processing с приложением |
| B4 application commit | `92fd1e83ea17b2002b195ea0e555f8b75c8da899` (`work/application`), поверх — исправления `b4ad6ad8d5c43a2640a9b61fce01fbc74a3b8c42` и merge `002d814` |
| B4 processing commit | `9d788953a298ff03b7e7903a6b3015cc83f3045d` (`processing`), влит как `0f8460df6465612a815810b77eb2f60a72376350` |
| Source provenance | SmartNoteLanding `d62f5ecb8c1c53b1c97faf06530b8d84e691f88d`; повторный импорт не выполнялся |
| Миграции | `app/migrations/001–015`; 001–007 побайтово совпадают с pinned source |
| Candidate 20:15 / final 21:00 | Кандидат локальный: коммит REL-12 в `release_tasks`; внешний выпуск не создавался |
| Transport | Приемка только `PILOT_TRANSPORT=fixture`; платных вызовов в release нет |

## Приём B4 (REL-01)

Сверено по фактическому репозиторию, а не по именам веток:

| Проверка | Как выполнено | Результат |
|---|---|---|
| Наличие переданных commit | `git cat-file -t` для B0/B1/B4/source SHA | все объекты существуют в локальном репозитории |
| Один contract v1 | `build_contract.py check_generated()` + сравнение `render_types()` с файлами | `app/pilot/contracts.py` и `src/pilot/api/generated.ts` побайтово совпадают с генератором; OpenAPI/схемы без drift |
| Pinned source, SQL 001–007 | `git hash-object` по каждому файлу против manifest `docs/pilot/BOOTSTRAP.md` | 7/7 совпадают |
| Pinned source, прочий импорт | сравнение 39 строк manifest | 23 blob без изменений, 12 изменены осознанно при адаптации, 4 исключены (`app/tests/conftest.py`, `app/tests/test_security.py`, `src/lib/useModal.ts`, `src/styles.css`) — причины уже записаны в BOOTSTRAP |
| Владельцы путей | чтение diff и `MODULE_BOUNDARIES` | общие entrypoint/config, `infra/`, `scripts/pilot/`, `docs/pilot/`, `compose.yaml`, `Dockerfile`, `app/Dockerfile`, seed приняты release; `app/config.py`, `domain/`, `processing/`, `analytics/`, `events/`, SQL остаются processing |
| Секреты в diff | `git grep` по шаблонам ключей, проверка `.env*` | отслеживаемых ключей/паролей нет; `.env.example` содержит пустые значения |
| Shared offline gate | `python project-context/pilot/planning/shared/check_shared.py` | PASS, 73 теста: frozen checker, 158 UX-строк, OpenAPI 34 операции, 44 HTTP fixtures, 25 lifecycle-снимков, 4 пары analytics |
| Структура документации | `python scripts/check_context.py` | PASS, 471 файл, 975 локальных ссылок |
| Frontend unit | `npm ci && npm test` | PASS, 6 файлов / 26 тестов |
| Frontend build | `npm run build` | PASS; предупреждение Vite о чанке 542 КБ не является ошибкой |
| Application API-тесты | `pytest --confcutdir tests/pilot/application tests/pilot/application -q` | PASS, 24 теста |
| Diff hygiene | `git diff --check` | PASS |

Не проверено этим приёмом: Compose/PostgreSQL runtime, браузерные smoke-прогоны, платный Polza, внешний сервер. Они относятся к REL-02 и далее.

## Границы локальной приемки после аудита

Полный повтор integration-приемки (51 тест), включая actual backup/restore и защиту остановленной цели, — PASS. Backend processing 99 PASS. Финальный E2E уже прошел на пересобранном image с проверкой source/image parity. Усиленные REL-C24/C15 проверяют настоящие очередь/worker/settlement с синтетической HTTP-границей поставщика; внешних запросов нет. Реальная модель, настоящие Android/iPhone, интерактивный полный `run.sh up` на Windows, внешний deploy и школьная апробация — not_run. Bash/Docker-stub и read-only Compose config не заменяют такой запуск launcher. Актуальный состав проверки — [RELEASE_REPORT](../../../../docs/pilot/RELEASE_REPORT.md), операторский маршрут — [RELEASE_RUNBOOK](../../../../docs/pilot/RELEASE_RUNBOOK.md).

## Runbook, backup и recovery (REL-11)

| Артефакт | Назначение |
|---|---|
| `docs/pilot/RELEASE_RUNBOOK.md` | Полная операторская инструкция: env, build/migrate/up/seed/health, pause/resume, cap, reconcile, backup, restore, rollback, приёмка |
| `docs/pilot/RUNBOOK.md` | Короткий вход-ссылка на полный runbook |
| `scripts/pilot/backup_local.py` | Приватный согласованный backup БД и фото в каталог вне репозитория; отказывается работать при запущенных writers |
| `scripts/pilot/restore_local.py` | Restore только в отдельный проект `smartnote-restore-*` с новыми volumes, с отказом поверх рабочей базы |

Обычный запуск не использует `down -v`; destructive reset не автоматизирован. Rollback: пауза dispatch, сохранение unknown/evidence/reserve, возврат к совместимому commit/image без SQL-downgrade.

## Запуск и данные

Имена локального окружения без значений: `POSTGRES_PASSWORD`, `VISITOR_COOKIE_SECRET`, `ALLOWED_BROWSER_ORIGINS`, `PILOT_TRANSPORT`, `PILOT_FIXTURE_TEACHER_1_LOGIN/PASSWORD`, `PILOT_FIXTURE_TEACHER_2_LOGIN/PASSWORD`, `PILOT_FIXTURE_STAFF_LOGIN/PASSWORD`. Значения хранятся вне Git: локальный файл лежит за пределами репозитория (например `~/.config/smartnote/pilot.env`) и передается Compose через `--env-file`. Пароли и ключ не вписываются в tracked `run.sh` и не передаются значениями в argv. Обычный startup не сбрасывает несовпадающий пароль; явный trusted reset сохраняет ID/роли/материалы. Точные команды — [RELEASE_RUNBOOK](../../../../docs/pilot/RELEASE_RUNBOOK.md) и [BOOTSTRAP](../../../../docs/pilot/BOOTSTRAP.md).

## Управление аккаунтами (REL-03)

`app/pilot/operations/manage_accounts.py` — trustless-обёртка над доменными функциями processing (`ensure_account`, `reset_account_password`); собственного SQL, хеширования и второй таблицы аккаунтов нет.

### Закрытый просмотр команды (REL-04)

| Артефакт | Состав |
|---|---|
| `app/pilot/routes/staff.py` | Только `GET /staff/checks` и `GET /staff/checks/{id}`. Зависимость `staff_actor` отказывает teacher до любого запроса; мутационных маршрутов нет |
| `app/pilot/services/staff.py` | Тонкая передача в `pilot.domain.queries` (`list_staff_checks`, `get_staff_check`, `get_bundle_history`, `get_summary_history`); своей SQL и второй проверки прав нет |
| `src/pilot/staff/StaffScreens.tsx` | Список с фильтром по точному `owner_login`, детали проверки, фото, разборы, отзывы от третьего лица, staff-only история поколения и сводок. Нет кнопок согласия/возражения/skip/retry/delete/finalize/refresh |
| `app/pilot/router.py` | Staff router подключён один раз; владение общими entrypoint-файлами перешло к release |
| `src/pilot/api/client.ts` | `listStaffChecks`, `getStaffCheck`, `getBundleHistory`, `getSummaryHistory` поверх сгенерированных типов |

История комплектов и сводок доступна только staff (`require_staff` в домене), учителю возвращается 403. Каждый staff-read пишет `pilot_audit` с реальным `actor_id`, `role` и `request_id`, не меняя `revision`/`data_revision` учителя и его отзывы. Read-only удерживается трижды: отсутствием мутационных маршрутов, зависимостью роли и доменной проверкой.

### Эксплуатационные CLI (REL-05)

| Артефакт | Назначение |
|---|---|
| `scripts/pilot/processing_control.py` | Хостовый wrapper: `status`, `pause --reason`, `resume --reason`. Запускает фасад внутри backend-контейнера и передаёт `COMPOSE_PROJECT_NAME`/`PILOT_FRONTEND_PORT` |
| `app/pilot/operations/processing_cli.py` | Контейнерная часть: вызывает `get_processing_control`/`set_processing_paused` и `get_budget`; своей SQL и второго ledger нет |
| `scripts/pilot/reconcile_attempt.py` | Хостовый wrapper сверки: читает и хеширует evidence-файл локально, передаёт только digest |
| `app/pilot/operations/reconcile_cli.py` | Контейнерная часть: вызывает `reconcile_attempt` с `ReconciliationEvidence` |
| `python -m pilot.processing.budget status` / `set-limit --rub` | Готовый processing CLI общего cap; release только вызывает его, второй лимит не заводится |

Правила, проверенные тестами: пауза останавливает только новые dispatch, queued Jobs и чтение сохраняются; resume продолжает прежнюю работу; красный отзыв ничего не выключает. Сверка принимает `rejected|settled`, требует доказательство, повтор с тем же `request_id` и evidence — no-op, иное evidence — конфликт с ненулевым кодом. Unknown не освобождается по таймауту, skip или restart; settlement с известной стоимостью снимает резерв один раз. HTTP admin-маршрутов и роли operator нет.

Приёмка идёт в отдельном Compose-проекте `smartnote-release-accept` на `127.0.0.1:5273`; `compose.yaml` принимает `COMPOSE_PROJECT_NAME` и `PILOT_FRONTEND_PORT`. Рабочий проект `smartnote-pilot` приёмкой не затрагивается, `down -v` применяется только к выделенному acceptance-проекту.

### Команды управления аккаунтами

| Команда | Назначение |
|---|---|
| `python -m pilot.operations.manage_accounts seed` | Создать три локальных fixture-аккаунта из `PILOT_FIXTURE_*`; повторный запуск ничего не сбрасывает |
| `python -m pilot.operations.manage_accounts create --login <login> --role teacher\|staff` | Создать один аккаунт; существующий логин с той же ролью — no-op, другая роль — конфликт |
| `python -m pilot.operations.manage_accounts reset --login <login>` | Заменить пароль и отозвать все сессии только этого аккаунта, сохранив ID и материалы |

Пароль приходит скрытым вводом в терминале или из `PILOT_ACCOUNT_PASSWORD`; аргумента `--password` нет, значения не печатаются. Для аудита задаётся `--operator-ref` или `PILOT_OPERATOR_REF`, по умолчанию `local-cli`; `request_id` генерируется на каждый вызов. HTTP admin API и роль operator не создаются.

## Исторический итог REL-01–REL-12, 19.11.2026

Все двенадцать задач выполнены и зафиксированы отдельными коммитами в `release_tasks` без push. Итоговые результаты:

| Проверка | Результат |
|---|---|
| `python project-context/pilot/planning/shared/check_shared.py` | PASS, 73 офлайн-теста |
| `python scripts/check_context.py` | PASS |
| `npm test` / `npm run build` / `npx tsc -b` | PASS, 28 тестов |
| `pytest tests/pilot/application` / `tests/pilot/staff` из `app/` | PASS, 24 / 8 |
| `pytest tests/integration/pilot -q` | PASS, 49 тестов |
| `npx playwright test tests/e2e/pilot` | PASS, 14 тестов; 8 полных прогонов подряд |
| `ruff check`, `git diff --check` | PASS |

Матрица A01–A25 и таблица REL-C01–C28 с доказательствами — в [RELEASE_REPORT](../../../../docs/pilot/RELEASE_REPORT.md). Runbook — [RELEASE_RUNBOOK](../../../../docs/pilot/RELEASE_RUNBOOK.md).

Остаются отдельными фактами, а не частью локального выпуска: реальная модель Polza и платные вызовы, внешний сервер/HTTPS/deploy, настоящие Android/iPhone, самостоятельная апробация учителя и письменный итог школы.

## Блокеры

На production fixes до `9980048` независимое ревью не оставило открытых P1/P2; полный runtime/browser повтор на code/test HEAD `261bb6e` завершен. Финальное ревью зафиксированного doc-sync commit выполняется перед Git-передачей. Внешний выпуск приложения этим не подтвержден. Формат нового блокера: `BLK-release-NN / severity / contract+A-ID / commit / fixture+команда / actual / expected / next action`.
