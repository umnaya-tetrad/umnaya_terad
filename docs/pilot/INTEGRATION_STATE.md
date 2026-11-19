# Состояние локальной интеграции пилота

Локальная work/application объединена с origin/main 0f8460df6465612a815810b77eb2f60a72376350. Контракт shared v1 / API 1.0.0 взят из 1144c498b4aba1e4e4fe118abe7c3f6f1b940198. Локальный B1 и учительский путь до сохранённой сводки проверены. Приём B4 остаётся за release. [HANDOFF application](../../project-context/pilot/planning/application/HANDOFF.md)

## Приём B4 в release

19.11.2026 release принял общие файлы на базе `002d814de6bab3b946208e0155e54e65c035cb27` (`main`, включая application `92fd1e8` и исправления `b4ad6ad`). Процессинг влит через `0f8460df6465612a815810b77eb2f60a72376350`, контракт — `1144c498b4aba1e4e4fe118abe7c3f6f1b940198`. Приём выполнен чтением фактического diff, а не по именам веток: перечисленные ниже проверки относятся к этой базе. Отдельная ветка `integration/pilot-local` не создавалась, её роль выполняет `release_tasks` от указанной базы. Подробная таблица — в [HANDOFF release](../../project-context/pilot/planning/release/HANDOFF.md).

- DTO побайтово совпадают с `build_contract.py render_types()`: `app/pilot/contracts.py`, `src/pilot/api/generated.ts`, OpenAPI/схемы/fixtures без drift.
- SQL `001–007` побайтово совпадают с pinned SmartNoteLanding `d62f5ecb8c1c53b1c97faf06530b8d84e691f88d`; цепочка продолжается `008–015` processing.
- Владельцы по `MODULE_BOUNDARIES` приняты: общие entrypoint/config, Compose, Dockerfile, `infra/`, `scripts/pilot/`, `docs/pilot/` и account seed — release; `app/config.py`, `domain/`, `processing/`, `analytics/`, `events/` и SQL — processing.
- Выполнено на этой базе: `check_shared.py` PASS (73 теста), `scripts/check_context.py` PASS, `npm test` PASS (26), `npm run build` PASS, application pytest PASS (24). Compose/PostgreSQL/браузер в этот приём не входили.

## Что подключает application

- FastAPI создаёт один asyncpg pool и Services в lifespan. app/pilot/router.py агрегирует auth/application/processing/events и монтируется один раз под /api. APP маршруты передают данные в общие порты. Общие обработчики ошибок устанавливаются один раз.
- PostgreSQL 16, одноразовый migrate, backend, worker, frontend и три именованных volume описаны в Compose. API и worker используют один приватный каталог через PILOT_STORAGE_ROOT. Для API используется /health, для worker — согласованный python -m pilot.processing.worker --healthcheck.
- Учительский UI использует относительный /api и сгенерированные типы processing. Сгенерированные Python/TS DTO побайтово совпадают с B0. HTTP-адаптеры вызывают общий валидатор processing.
- В точках входа выделено место для подключения staff в REL-04. Ранний staff может войти, а teacher workspace для него закрыт.

## Проверено в совместном стеке

1. Чистая PostgreSQL 16.15, SQL 001–015, повторный мигратор и seed, healthy API/worker/frontend. Использованы [команды bootstrap](BOOTSTRAP.md).
2. В реальном API прошли доступ двух учителей и staff, приватные фото, пять форматов, повторы ключей, сохранённая сводка и refresh после изменения оценки.
3. В Chrome прошли два комплекта, шесть отзывов, двухэтапный финал и чтение результата после reload. Отдельный запуск остановил worker, оставил два принятых Job в очереди, закрыл браузер и подтвердил сохранность после перезапуска backend и worker.
