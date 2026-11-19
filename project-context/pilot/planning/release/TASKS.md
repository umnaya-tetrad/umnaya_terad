# Задачи release

19.11.2026. **Спецификация для реализации. Все задачи planned; код и runtime-проверки здесь не выполнены.** Общие правила — [README](README.md), ожидаемые результаты — [ACCEPTANCE](ACCEPTANCE.md). Работа только 18:00–21:00; ранние bootstrap/seed и полное ядро являются входом B4.

## REL-01. Принять B4 и управление интеграцией — 18:00

**Зачем:** R85, A12/A16/A25; [HANDOFF_PROTOCOL](../shared/HANDOFF_PROTOCOL.md). **Вход:** HANDOFF application/processing с реальными branch+commit, B0 contract commit, B1 baseline, миграциями, командами и полным API smoke аналитики. SHA не предполагаются по имени ветки. **Файлы:** полученные `app/main.py`, `app/pilot/router.py`, `compose.yaml`, `package.json`, `package-lock.json` и общие конфиги по MODULE_BOUNDARIES; `docs/pilot/INTEGRATION_STATE.md`, данный HANDOFF.

Сверить status/diff, source manifest, владельцев и один contract v1. Последовательно включить переданные коммиты в `integration/pilot-local`; рабочая ветка `work/release`. Записать однократную передачу общих файлов/скриптов/account seed на B4 и итоговый commit. Не импортировать source повторно. Недостающий артефакт — BLK-release-NN с воспроизведением; исправлять известный контракт, не ждать встречи. **Проверка:** [REL-C01](ACCEPTANCE.md#rel-c01). **DoD:** включенные изменения связаны с commit/контрактом и проверкой, прием владения записан; нет выдуманных SHA или статуса готового пилота.

## REL-02. Compose и миграции — до 18:40

**Зачем:** R26/R28/R85, A12/A19/A22. **Вход:** B1 Compose, Settings `app/config.py` processing уже до B1, runner `pilot.domain.migrate`, worker B4. **Файлы:** `compose.yaml`, `Dockerfile`, `app/Dockerfile`, `infra/`, безопасный `.env.example`, `tests/integration/pilot/test_compose_persistence.py`; SQL `app/migrations/` читать/применять, не переписывать. Основные Settings остаются processing; release изменяет wiring/config inputs по переданному интерфейсу.

Проверить frontend/backend/postgres/worker/migrate, health без модели, зависимости DB→migrate→API/worker, приватный общий photo volume и postgres volume. Приемка явно `PILOT_TRANSPORT=fixture`; тот же Compose source передается frontend `VITE_PILOT_TRANSPORT` для метки «Учебный режим». В `polza` без ключа fail-closed, без подставного ответа. Применить миграции на чистой/сохранной БД, повторить без повторного SQL. Проверить origin/cookie/порты и отсутствие статической раздачи фото. **Проверки:** [REL-C02](ACCEPTANCE.md#rel-c02)/[REL-C03](ACCEPTANCE.md#rel-c03)/[REL-C04](ACCEPTANCE.md#rel-c04)/[REL-C26](ACCEPTANCE.md#rel-c26). **DoD:** старт/повторный migrate воспроизводимы, restart сохраняет данные, worker независим, обычный запуск не использует `down -v`; версии/команды записаны.

## REL-03. Accounts и безопасный reset — до 19:00

**Зачем:** R13/R48/R76, A01/A12/A20. **Вход:** ранний application seed `app/pilot/operations/create_fixture_accounts.py`, общий auth/schema processing; два teacher и staff уже создаются до B1. **Файлы:** переданные `app/pilot/operations/create_fixture_accounts.py` и `app/pilot/operations/__init__.py`, `app/pilot/operations/manage_accounts.py`, `tests/integration/pilot/test_acl_staff.py`, account-раздел runbook.

Проверить идемпотентный seed; CLI вызывает `app/pilot/domain/auth.py`: `ensure_account(svc, login, password, role, *, operator_ref, request_id)` и `reset_account_password(svc, *, login, password, operator_ref, request_id)` с keyword-only аргументами по фасаду processing. Не писать свою SQL/криптографию. Existing login с той же role — no-op без сброса; role mismatch — конфликт. Reset атомарно меняет hash и отзывает все сессии только этого аккаунта, сохраняет его ID/материалы и остальных пользователей; отсутствующий login — not_found. Пароль скрыто вводится либо берется из local env, не из CLI args/лога/Git. Исключить register/анонимный анализ/старые квоты 3/20. **Проверки:** [REL-C05](ACCEPTANCE.md#rel-c05)/[REL-C06](ACCEPTANCE.md#rel-c06)/[REL-C26](ACCEPTANCE.md#rel-c26). **DoD:** обе роли входят, reset проверен, секретов в артефактах нет, HTTP admin API не создан.

Seed env согласован с application: `PILOT_FIXTURE_TEACHER_1_LOGIN/PASSWORD`, `PILOT_FIXTURE_TEACHER_2_LOGIN/PASSWORD`, `PILOT_FIXTURE_STAFF_LOGIN/PASSWORD` (каждая пара означает два имени переменных). Нет defaults и передачи пароля через argv; повтор seed не меняет действующий пароль молча. Авторство `app/config.py`/общего auth остается processing, B4 передает только bootstrap wiring/seed и перечисленные общие файлы.

## REL-04. Закрытый просмотр команды — до 19:15

**Зачем:** R49/R76, A20/A21/A22; S11 [ux-flows](../shared/ux-flows.md). **Вход:** Session/ACL/audit processing, repository и contract operations listStaffChecks/getStaffCheck/getPhoto/getBundleHistory/getSummaryHistory. **Файлы:** `app/pilot/routes/staff.py`, `app/pilot/services/staff.py`, `src/pilot/staff/`, `app/tests/pilot/staff/`, `tests/e2e/pilot/staff_readonly.spec.ts`.

После B4 впервые подключить настоящий staff router в принятых app/main.py/app/pilot/router.py и staff UI через принятый src/App.tsx/src/main.tsx; до этого их импорт не требуется. Собрать список/точный owner_login/cursor, детали, фото/разборы/отзывы и staff-only историю поколений/сводок. Использовать общие модели/repository и renderer. Постоянная метка read-only, отзыв от третьего лица; mutation-кнопок нет. Проверить серверный отказ staff-записи, teacher на staff-путях и чужие фото/ID. Реальный staff-read аудируется отдельно и не меняет teacher revision/activity. **Проверки:** [REL-C06](ACCEPTANCE.md#rel-c06)/[REL-C07](ACCEPTANCE.md#rel-c07). **DoD:** путь проходим, аудит проверен; нет dashboard/чата/правки за учителя.

## REL-05. Pause и unknown reconciliation — до 19:15

**Зачем:** R59/R60/R74/R78, A11/A22/A23/A24. **Вход:** B4 facade processing: `app/pilot/processing/control.py` get_processing_control/set_processing_paused, `reconciliation.py` reconcile_attempt, `funds.py` fund_wallet, общий `Services`/`create_services`. **Файлы:** `scripts/pilot/processing_control.py`, `scripts/pilot/reconcile_attempt.py`, `scripts/pilot/funds.py`, wrappers `app/pilot/operations/`, `tests/integration/pilot/test_funds_control.py`, runbook.

CLI status/pause/resume через Compose вызывает facade, а не второй ledger SQL. Сверка получает attempt_id, outcome rejected|settled, evidence-file, operator_ref и request_id; читает/хеширует evidence локально. Внутренний Evidence: reference, sha256, actual_cost_rub, provider_request_id. Settled требует конечную стоимость≥0; rejected — доказанное непринятие/отсутствие списания. Повтор request_id+attempt+outcome+hash — no-op, иное доказательство/исход — конфликт. Unknown не освобождается по таймауту/skip/restart. HTTP эти функции не экспортирует; audit не копирует rawfile/ключи. **Проверки:** [REL-C16](ACCEPTANCE.md#rel-c16)/[REL-C17](ACCEPTANCE.md#rel-c17)/[REL-C18](ACCEPTANCE.md#rel-c18). **DoD:** оба kind подчиняются паузе/резерву, сверка безопасна/идемпотентна, история доступна; неизвестное не объявлено бесплатным.

`funds.py initialize|topup --evidence-file PATH --operator-ref REF --request-id UUID` читает amount/profile/reference из локального файла и вызывает `fund_wallet(operation, amount_rub, evidence, operator_ref, request_id)`. FundsEvidence содержит reference/sha256/profile_id; mode приходит из Services/settings, не из CLI. Initialize допустим только для неинициализированного wallet, topup требует конечный положительный Decimal; повтор того же request/evidence — no-op, другой payload — конфликт. Polza требует проверенный фактический баланс и консервативный reservation profile, иначе dispatch blocked. 400 рублей не seed реального остатка; fixture wallet изолирован и не переносится в polza. Это часть [REL-C17](ACCEPTANCE.md#rel-c17)/DoD, без собственной SQL в оболочке.

## REL-06. E2E учителя — до 19:40

**Зачем:** R80–R82/R84/R86, A01–A08/A10/A12/A14/A16/A25. **Вход:** UI/CRUD application, worker processing, [lifecycle](../shared/api/fixtures/lifecycle.json), frozen dev Reports. **Файлы:** `tests/e2e/pilot/teacher_flow.spec.ts`, `tests/integration/pilot/conftest.py`, синтетические assets.

Пройти вход→название→тетради→камера/галерея→три действия→готовность→отзывы→два этапа финала→сводка→история/reload. Настоящие API/БД и fixture transport; подмена только HTTP-ответа UI не доказывает сохранение. Сверить photo/Task связи, четыре evidence, исправленный первый шаг, mixed skip и нейтральное disputed. **Проверки:** [REL-C08](ACCEPTANCE.md#rel-c08)–[REL-C11](ACCEPTANCE.md#rel-c11)/[REL-C13](ACCEPTANCE.md#rel-c13)/[REL-C19](ACCEPTANCE.md#rel-c19)/[REL-C26](ACCEPTANCE.md#rel-c26). **DoD:** happy/error пути прошли на integration commit, навигация не запускает LLM и не подтверждает задачи молча.

## REL-07. Версии, дубли и восстановление — до 19:50

**Зачем:** R26/R28/R46/R78/R80/R84, A09/A11–A15. **Вход:** общий guard/jobs/attempts и управляемый fixture transport. **Файлы:** `tests/integration/pilot/test_lifecycle_recovery.py`, соответствующие teacher E2E.

Проверить потерянный ответ/повтор прежнего намерения, два клиента, replacement 2→3, tombstone, общее фото после deleteTask, deleteCheck во время работы, restart/fencing/один retry. Имитатор контролирует задержки/исходы, не оплачивая API. **Проверки:** [REL-C04](ACCEPTANCE.md#rel-c04)/[REL-C12](ACCEPTANCE.md#rel-c12)–[REL-C16](ACCEPTANCE.md#rel-c16). **DoD:** один intent не дает два Job/settlement; старый worker не публикует новое поколение; сходная формула не переносит отзывы, удаленное не возвращается.

## REL-08. Финал и полный lifecycle аналитики — до 20:00

**Зачем:** R46/R83/R84/R86, A08/A14/A16–A18. **Вход:** полный API analytics smoke processing до 18:00, [fixtures/валидатор](../shared/analytics/README.md), can_retry/can_refresh. **Файлы:** `tests/integration/pilot/test_analytics_finalization.py`, summary E2E.

Повторить begin→blockers/reviews→finalize→snapshot→сохраненный result; гонки upload/review/publish с финалом, repeat finalize. Проверить failed/retry того же snapshot, state→stale/refresh нового snapshot, comment-only, capability queued/blocked/running/unknown и поздний старый ответ. Проверить oracle 0,5, нулевой знаменатель, mixed/синонимы/незавершенность. **Проверки:** [REL-C19](ACCEPTANCE.md#rel-c19)–[REL-C23](ACCEPTANCE.md#rel-c23). **DoD:** GET ничего не запускает; состав закрыт, отзывы разрешены; валидатор проверил числа/ссылки, stale не показан актуальным, аналитика не осталась TODO.

## REL-09. События и нагрузка без оплаты — до 20:10

**Зачем:** R17–R20/R51/R59/R60, A19/A21–A24. **Вход:** events/dedupe/audit и общие slots/reserve; два teacher. **Файлы:** `tests/integration/pilot/test_events_load.py`, безопасный диагностический отчет.

Проверить batch≤100, повторы/конфликт, чужую ссылку без частичного приема, потерю событий без остановки работы. Каждому из двух teacher создать по 30 тетрадей, циклически 3/4/5 задач, перемешать готовность/съемку. Проверить изоляцию, завершение очереди, число сущностей, общий предел slots и средства. Реальные интервалы теста не объявлять скоростью модели/экономией. **Проверки:** [REL-C17](ACCEPTANCE.md#rel-c17)/[REL-C18](ACCEPTANCE.md#rel-c18)/[REL-C24](ACCEPTANCE.md#rel-c24)/[REL-C25](ACCEPTANCE.md#rel-c25). **DoD:** принятые входы получили ожидаемый terminal/blocked исход, счетчики и имитированные расходы точны, содержимого/секретов в общих логах нет.

## REL-10. Мобильная приемка — до 20:15

**Зачем:** R13/R41/R61, A02/A06/A12/A25. **Вход:** локальная сборка/синтетические фото, [MOBILE_UX](../shared/MOBILE_UX.md), реальные устройства при наличии. **Файлы:** `tests/e2e/pilot/mobile_layout.spec.ts`, `docs/pilot/RELEASE_REPORT.md`.

Проверить 320/360/390/430 CSS px, текст 200%, фото/формулы/диалоги/кнопки/возврат. На настоящих Android и iPhone отдельно пройти камеру/галерею, JPEG/HEIC, отказ разрешения, повторный вход/возврат/фон; записать устройство/ОС/браузер/версию. Нет устройства — not_run, эмуляция отдельно. Локальный HTTPS для камеры не является внешней публикацией. **Проверка:** [REL-C27](ACCEPTANCE.md#rel-c27). **DoD:** ограничения записаны, действия доступны, готовность другого комплекта не закрывает камеру.

## REL-11. Runbook, backup и recovery — до 20:15

**Зачем:** R26/R28/R55/R56/R85, A12/A22/A23. **Вход:** проверенные Compose/CLI/миграции/volumes/unknown. **Файлы:** `docs/pilot/RELEASE_RUNBOOK.md`, `docs/pilot/RUNBOOK.md` (вход-ссылка), `scripts/pilot/backup_local.py`, `scripts/pilot/restore_local.py`, `tests/integration/pilot/test_compose_persistence.py`.

Дать точные cwd/команды startup/seed/health/status/pause/reconcile/funds, безопасную диагностику и restart без удаления volumes. Следовать LOCAL_ENV: общая env source, proxy relative /api, VISITOR_COOKIE_SECRET для session HMAC, timeout 300/connect 15, minEdge 32 и fixture 64; ключ не VITE-переменная, старые квоты отключены. Backup приватно сохраняет согласованные DB+photos при остановленных записывающих сервисах/dispatch; бэкапы/секреты вне Git. Restore проверяется в отдельном Compose project/новых volumes с явным целевым именем, не поверх рабочей базы. Rollback: пауза dispatch, сохранение unknown/evidence/reserve, возврат к совместимому image/commit без отката SQL. Несовместимый downgrade запрещен; восстановление backup — отдельная осознанная операция. **Проверки:** [REL-C03](ACCEPTANCE.md#rel-c03)/[REL-C04](ACCEPTANCE.md#rel-c04)/[REL-C28](ACCEPTANCE.md#rel-c28). **DoD:** release самостоятельно воспроизводит восстановление тестового набора из runbook, неизвестные резервы сохранены; destructive reset не автоматизирован как обычный запуск, дополнительный исполнитель не обязательная зависимость.

## REL-12. Кандидат 20:15 и итог до 21:00

**Зачем:** R85, A01–A25. **Вход:** [REL-C01](ACCEPTANCE.md#rel-c01)–[REL-C28](ACCEPTANCE.md#rel-c28), реальные integration commits, [полномочия](../shared/MODULE_BOUNDARIES.md). **Файлы:** `docs/pilot/INTEGRATION_STATE.md`, `docs/pilot/RELEASE_REPORT.md`, данный HANDOFF; fix-коммиты затронутых модулей по frozen contract.

В 20:15 записать candidate commit/config/transport; до 21:00 только блокирующие исправления, затронутая регрессия и итоговый smoke. Автора не ждать: фиксировать reproduction/diff/test. Не менять API/продукт ради теста. Заполнить одну A01–A25 матрицу pass/fail/not_run, команды/среду/результаты/ограничения и следующий отдельный внешний выпуск. **Проверки:** [REL-C01](ACCEPTANCE.md#rel-c01)–[REL-C28](ACCEPTANCE.md#rel-c28) и полный набор команд ACCEPTANCE. **DoD:** реальный commit и воспроизводимый запуск с отчетом; failed/not_run видны, live/устройства/сервер не выданы за проверенные.
