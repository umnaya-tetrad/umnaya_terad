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
