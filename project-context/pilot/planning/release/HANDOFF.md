# Состояние и передача release

19.11.2026, Asia/Yekaterinburg. **status: in_progress.** B4 принят, задачи REL-01–REL-12 выполняются; отдельные результаты записываются по факту выполнения, а не авансом.

## Ревизии

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
| Candidate 20:15 / final 21:00 | Не созданы; заполняются в REL-12 по факту |
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

## Еще не готово

REL-02 выполнен и проверен на локальном Compose-стеке (см. таблицу приёмки в [INTEGRATION_STATE](../../../../docs/pilot/INTEGRATION_STATE.md)). Дальше по порядку идут REL-03–REL-12. Все REL-C01–REL-C28 получают статус по факту; кейсы вне уже выполненных остаются not_run. Реальная модель, настоящие Android/iPhone, внешнее развёртывание и школьная апробация — отдельные факты и в локальный результат не входят.

## Запуск и данные

Точные команды — в [BOOTSTRAP](../../../../docs/pilot/BOOTSTRAP.md); `docs/pilot/RELEASE_RUNBOOK.md` создаётся в REL-11. Имена локального окружения без значений: `POSTGRES_PASSWORD`, `VISITOR_COOKIE_SECRET`, `ALLOWED_BROWSER_ORIGINS`, `PILOT_TRANSPORT`, `PILOT_FIXTURE_TEACHER_1_LOGIN/PASSWORD`, `PILOT_FIXTURE_TEACHER_2_LOGIN/PASSWORD`, `PILOT_FIXTURE_STAFF_LOGIN/PASSWORD`. Значения хранятся вне Git.

## Блокеры

Активных блокеров нет. Формат записи при появлении: `BLK-release-NN / severity / contract+A-ID / commit / fixture+команда / actual / expected / next action`.
