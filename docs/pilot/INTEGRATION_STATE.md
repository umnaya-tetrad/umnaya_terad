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

## Проверено в приёмке release (REL-02)

19.11.2026 на той же базе собран и поднят локальный Compose-стек в явном `PILOT_TRANSPORT=fixture`. Все runtime-значения — синтетические, реквизиты в `.env` вне Git.

| Проверка | Команда | Факт |
| --- | --- | --- |
| Сборка образов | `docker compose -f compose.yaml build` | PASS: backend/worker/migrate из `smartnote-pilot-python:local`, отдельный frontend |
| Конфигурация | `docker compose -f compose.yaml config -q` | PASS; `PILOT_TRANSPORT` и `VITE_PILOT_TRANSPORT` берутся из одного source |
| Миграции | `docker compose -f compose.yaml run --rm migrate` дважды и параллельно | PASS: 15 строк в `pilot_migrations`, повтор и два одновременных runner'а не добавляют записей и не меняют checksums |
| Стек | `docker compose -f compose.yaml up -d --wait` | PASS: postgres/backend/worker/frontend healthy, migrate exit=0 |
| Seed | `python -m pilot.operations.create_fixture_accounts` дважды | PASS: ровно 3 аккаунта (2 teacher, 1 staff), повтор не сбрасывает пароли |
| Health без модели | `urllib` из контейнера backend | PASS, `/health` = ok; transport не вызывается |
| Polza без ключа | запуск lifespan с `PILOT_TRANSPORT=polza`, пустым ключом | PASS fail-closed: `POLZA_API_KEY is required in polza mode.`, fixture не включается |
| API smoke | `python scripts/pilot/smoke_application.py` | PASS: auth/ACL, пять форматов, reorder/replace, поколения, общее фото, replay, stale revision, история, сводка |
| API smoke с повтором | `python scripts/pilot/smoke_application.py --retry` | PASS: failed analytics retry на том же snapshot |
| Браузерный путь | `npm run test:browser:compose` | PASS: Chrome 320 CSS px, два комплекта, шесть отзывов, финал, сводка после reload |
| Restart | `npm run test:browser:compose -- --restart` | PASS: те же Job и приватные фото после restart backend/worker с новым browser context |
| Приватность и Origin | `pytest tests/integration/pilot -k "rel_c02 or rel_c26"` | PASS: нет статической раздачи фото, `private, no-store`, отказ без/exact-Origin, 404 на чужие ID, нет register/analyze/control |
| Сохранение после restart | `pytest tests/integration/pilot -k rel_c04` | PASS: ID, байты нормализованного фото, Job и изоляция второго учителя сохраняются |
| Идемпотентность миграций | `pytest tests/integration/pilot -k rel_c03` | PASS: 001–015 применяются по разу, конкурирующие runner'ы сериализованы |

Обычный запуск нигде не использует `down -v`; destructive reset не автоматизирован. Backend и worker не публикуют порты — наружу открыт только frontend `127.0.0.1:5173`. Приватный volume `pilot_photos` смонтирован только в backend и worker.

Не проверено этой задачей: реальная модель Polza и её стоимость (платных вызовов не было), настоящие Android/iPhone, внешний сервер/HTTPS и школьная апробация.

## Проверено в приёмке release (REL-03)

Аккаунты и ACL проверены на том же локальном Compose-стеке. Реквизиты не попадали в Git и в вывод команд.

| Проверка | Команда | Факт |
| --- | --- | --- |
| Состав аккаунтов | `psql: select role, count(*) from users` | `staff=1`, `teacher=2` |
| Идемпотентный seed | `python -m pilot.operations.manage_accounts seed` дважды | PASS: 3 аккаунта, повтор без сброса пароля |
| Создание/конфликт роли | `manage_accounts create --login <teacher> --role staff` | отказ `invalid_state`, роль не меняется |
| Reset | `manage_accounts reset --login <teacher>` с `PILOT_ACCOUNT_PASSWORD` | PASS: старый пароль и старые cookie дают 401, новый пароль работает, материалы сохранены |
| Reset отсутствующего | `manage_accounts reset --login release-missing-account` | отказ `not_found` |
| Пароль через argv | `manage_accounts reset --password ...` | отказ argparse; такого флага нет |
| Секреты в выводе | stdout/stderr всех команд | пароль и hash не печатаются |
| Аудит | `select name, payload->>'operator_ref' from pilot_audit` | `account_created`/`password_reset` содержат `operator_ref`, без секретов |
| ACL и Origin | `pytest tests/integration/pilot/test_acl_staff.py -k "rel_c05 or rel_c06"` | PASS: чужие Check/photo/task дают 404, teacher на staff-путях 403, staff mutation 403, запись без/exact-Origin 403, logout без Origin 403 и сессия сохраняется |

Не проверено: HTTP admin/operator role отсутствуют по построению (проверяется REL-C26), реальная выдача аккаунтов школе.

## Проверено в приёмке release (REL-04)

| Проверка | Команда | Факт |
| --- | --- | --- |
| Staff list и фильтр | `pytest tests/integration/pilot/test_staff_readonly.py -k rel_c07` | PASS: точный `owner_login` не возвращает другого учителя, курсор не дублирует элементы |
| Детали и приватность | та же | PASS: `owner.login`, `ETag`, `Cache-Control: private, no-store`; фото доступно staff и не доступно второму учителю |
| История staff-only | та же | PASS: `getBundleHistory` и `getSummaryHistory` отдают сохранённые поколения/снимки staff, учителю — 403 |
| Read-only | та же + `pytest tests/pilot/staff -q` | PASS: staff mutation 403, в router только два GET-маршрута, teacher получает 403 до домена |
| Аудит | та же (`pilot_audit`) | PASS: `staff_read_check/bundle_history/summary_history/photo` содержат реальные `actor_id`, `role=staff`, `request_id` |
| Неизменность учителя | та же | PASS: `revision`, `data_revision` и отзывы не меняются после staff-read |
| Staff UI | `npx playwright test tests/e2e/pilot --grep REL-C07` | PASS: Chrome 390 CSS px, третье лицо в подписях, нет кнопок согласия/skip/retry/delete/finalize/refresh, teacher не видит раздел команды |
| Unit/сборка | `npm test`, `npm run build`, `tsc -b` | PASS: 28 тестов, сборка; предупреждение Vite о чанке 550 КБ |

## Проверено в приёмке release (REL-05)

Приёмка выполняется в отдельном Compose-проекте `smartnote-release-accept` (порт 5273). Сессия тестов сама поднимает чистые volumes этого проекта, поэтому прогон воспроизводим и не трогает рабочий `smartnote-pilot`.

| Проверка | Команда | Факт |
| --- | --- | --- |
| Pause останавливает dispatch | `pytest tests/integration/pilot/test_funds_control.py -k rel_c18` | PASS: при остановленном worker Job остаётся `queued`, pause фиксируется, чтение и вход доступны; после resume Job завершается |
| Аудит операций | та же | PASS: `processing_paused`/`processing_resumed` содержат `operator_ref`; без `--reason` — отказ |
| Красный отзыв ≠ пауза | та же | PASS: `paused` остаётся `false` |
| Общий cap, hot-change | `-k rel_c17` | PASS: уменьшение и возврат cap не сбрасывают `spent`/`held` и не требуют restart; обе смены аудируются (`spend_limit_changed`) |
| Cap блокирует только новые отправки | та же | PASS: материал блокированного Job сохраняется, cap восстанавливается |
| Сверка unknown | `-k rel_c16` | PASS: резерв удерживается, `settled` со стоимостью снимает его один раз, повтор — no-op, другое evidence — конфликт ненулевым кодом, аудит один |
| Unknown без evidence | та же | PASS: состояние и резерв не меняются, повторный проход worker не пересылает запрос |
| Rejected | та же | PASS: отказ с ненулевой стоимостью и evidence без `reference` отклоняются |
| Нет HTTP admin | та же | PASS: `/processing/pause`, `/budget`, `/admin/processing` недоступны teacher и staff |

Полный набор `pytest tests/integration/pilot -q` — 18 тестов, PASS дважды подряд (75,9 с и 75,7 с).

## Проверено в приёмке release (REL-06)

Сквозной учительский путь проверяется в том же изолированном проекте (`smartnote-release-accept`, порт 5273) через Playwright на реальном HTTP/PostgreSQL/worker. Подмены HTTP нет: проверяются сохранённые Job, фото и отзывы.

| Проверка | Команда | Факт |
| --- | --- | --- |
| Исключённые функции | `npx playwright test tests/e2e/pilot --grep REL-C26` | PASS: нет класса/темы/варианта/экспорта/оценок/тарифов/регистрации/чата/корзины; `/api/auth/register`, `/api/analyze`, `/analyze` отвечают 404/405 |
| Загрузка фото | `--grep REL-C08` | PASS: JPEG принят, PDF отклонён 415, приватный asset `private, no-store` |
| Одна страница — несколько задач | `--grep REL-C09` | PASS: два фото (PNG+HEIC) в одном комплекте, evidence ≤4 строк с корректными `photo_index`, исправленный первый шаг присутствует |
| Три действия и фон | `--grep REL-C10` | PASS: до submit Job нет, оба submit = 202, следующая тетрадь доступна до ответа модели, оба комплекта сохранили свой вход |
| Отзывы и красная отметка | `--grep REL-C11` | PASS: отзыв сохраняется только для своей задачи, `system_error` не запускает retry, Job остаётся `succeeded` |
| Два этапа финала | `--grep REL-C19` | PASS: `begin-completion` даёт `review` без AnalyticsJob, прямой finalize с нерешёнными отзывами — 409, после оценок создаётся один AnalyticsJob и сохранённая сводка |
| Новая версия входа | `--grep REL-C13` | PASS: после submit новой версии все отзывы `null`, текущий вход заменён |

Полный прогон `npx playwright test tests/e2e/pilot` — 8 тестов, PASS.

Не проверено этой задачей: реальные Android/iPhone и платная модель; это REL-10 и отдельный live-прогон.

## Проверено в приёмке release (REL-07)

| Проверка | Команда | Факт |
| --- | --- | --- |
| Потерянный ответ и повтор намерения | `pytest tests/integration/pilot/test_lifecycle_recovery.py -k rel_c12` | PASS: повтор с тем же ключом возвращает исходный Job, один `pilot_jobs` и одна строка `pilot_idempotency`; другой payload — 409 `idempotency_conflict`; устаревший `If-Match` — 409 `revision_conflict` с `current_revision`; второй клиент видит тот же Job |
| Reload без нового Job | та же | PASS: открытие проверки не создаёт новых Job |
| Поколение 2→3 | `-k rel_c13_replacement` | PASS: discard черновика не снимает отзывы, submit новой версии делает `current_input` новым и обнуляет отзывы, старый `analysis_id` даёт 404/409, в истории два sealed-поколения |
| Похожая формула | `-k rel_c13_similar` | PASS: независимый комплект не наследует согласие |
| Удаление задачи | `-k rel_c14_delete_task` | PASS: удалена ровно одна задача, общее фото и сохранённый Report остаются, tombstone есть, повторный проход не возвращает задачу |
| Удаление проверки в работе | `-k rel_c14_delete_during` | PASS: Job не публикует Report, Check и Job дают 404, tombstone `deleted` сохраняется |
| Один автоповтор | `-k rel_c15` | PASS: не более двух попыток, счётчик генераций долговечен; красный отзыв не создаёт попытку |
| Истёкший lease и fencing | `-k rel_c16` | PASS: помеченная dispatched попытка переходит в `unknown`, резерв удерживается, поздний ответ старого epoch не публикуется, автоматического resend нет, позднее evidence остаётся для сверки |

Полный набор `pytest tests/integration/pilot -q` — 27 тестов, PASS (109,4 с).
