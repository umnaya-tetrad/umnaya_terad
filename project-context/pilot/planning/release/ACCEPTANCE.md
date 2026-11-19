# Независимая приемка release

19.11.2026. **REL-C01–REL-C28 выполнены на локальной сборке.** Фактические команды, результаты по каждому кейсу и границы — [report](report.md) и [RELEASE_REPORT](../../../../docs/pilot/RELEASE_REPORT.md). Настоящие Android/iPhone, внешний сервер и платная модель остаются not_run. Источники: [API](../shared/API_CONTRACT.md), [OpenAPI](../shared/api/openapi.json), [UX](../shared/MOBILE_UX.md), [формулы](../../SUMMARY_METRICS.md). Реализационные проверки других направлений: [application ACCEPTANCE](../application/ACCEPTANCE.md) и [processing ACCEPTANCE](../processing/ACCEPTANCE.md); ссылки ниже используют общие A-ID, без выдумывания их локальных case ID.

## Среда, fixtures и исполняемые команды

Все команды из корня `umnaya_terad`, кроме явно указанного `app/`. Результат привязывается к фактическому integration commit, contract commit и safe report. Приемочный проект — отдельная локальная БД/volumes с синтетическими данными, два teacher `T1/T2` и staff `S`, созданные переданным seed. Это обозначения в тесте, не реальные логины/пароли в документации. `PILOT_TRANSPORT=fixture` задается явно; полная сеть к Polza запрещена тестовым harness. `VITE_PILOT_TRANSPORT` приходит из того же Compose source, UI показывает «Учебный режим». Default polza без ключа обязан fail-closed. Тесты не используют данные школы/production.

Сокращения входных данных:

- **H** — [api/fixtures/http.json](../shared/api/fixtures/http.json), имя записи = operation_id, вместе с дополнительными negative fixtures; реальный HTTP использует multipart bytes, не путь из JSON.
- **L** — [api/fixtures/lifecycle.json](../shared/api/fixtures/lifecycle.json), ниже названы точные ключи.
- **G** — [summary-guards.json](../shared/api/fixtures/summary-guards.json), внутренние отправленные/неотправленные Attempt для capability.
- **P** — [synthetic-photo.png](../shared/api/fixtures/synthetic-photo.png), 64×64, синтетический бинарный upload; не математический пример. JPEG/WebP/EXIF/HEIC, битый файл и PDF для runtime-валидации создать синтетически в `tests/integration/pilot/fixtures/`; происхождение записать, чужие материалы не брать.
- **M** — [analytics/fixtures/manifest.json](../shared/analytics/fixtures/manifest.json): oracle, mixed, synonyms, zero-denominator input/result. Task/Report берутся неизмененными из [dev examples](../../ai/README.md).

Harness создает свежие реальные серверные ID, сохраняя связи fixture, а не требует записать фиксированные UUID в чужую БД. Managed delays/temporary/unknown/settlement относятся к transport имитатора и общим сервисам, не к публичному debug API. Каждый тест обязан иметь хотя бы одну assertion; пустой collected-suite или skip не считается pass. Pytest функции именуются `test_rel_cNN_*`, Playwright названия содержат `REL-CNN`, чтобы приведенные selectors исполнялись.

**Уже существующие проверки спецификации**, повторить и записать результат:

```powershell
python project-context/pilot/planning/shared/check_shared.py
python scripts/check_context.py
git diff --check
git diff --cached --check
```

**Требуемая runtime-последовательность после создания кода** (сейчас не выполнялась):

```powershell
$env:PILOT_TRANSPORT='fixture'
docker compose -f compose.yaml build
docker compose -f compose.yaml run --rm migrate
docker compose -f compose.yaml up -d
docker compose -f compose.yaml exec backend python -m pilot.operations.create_fixture_accounts
docker compose -f compose.yaml ps
python -m pytest tests/integration/pilot -q
npm test
npm run build
npx playwright test tests/e2e/pilot
```

Backend regression из `app/`: `python -m pytest tests/pilot -q`. Установку dev-зависимостей/браузеров и безопасные local env имена закрепить в RELEASE_RUNBOOK. Полное окружение перед выполнением должно запретить внешнюю модель, а не надеяться на отсутствие ключа. Все нижеприведенные runtime-команды — будущие обязательные тестовые интерфейсы.

<a id="rel-c01"></a>

## REL-C01 — приемка версии и передачи

**Вход:** реальные B0/B1/B4 HANDOFF/PR/commits. **Действие:** REL-01 сверяет `git status --short`, `git rev-parse HEAD`, фактический diff включаемых коммитов, source manifest и результаты обработки, включая API analytics smoke. **Ожидается:** один source SHA, один contract v1 commit и один integration baseline; ownership application→release записан только B4, готовое ядро/аналитика не TODO; нет повторного source import или секретов в diff. Unknown SHA остается unknown. **Проверка:** ручное чтение коммитов/HANDOFF + общий offline gate выше; записать merge/fix SHA и результат. Нет кода/полного smoke — fail входа, не «принято по описанию».

<a id="rel-c02"></a>

## REL-C02 — чистый Compose и fail-closed режим

**Вход:** чистая приемочная БД, P, fixture mode. **Действие:** build→migrate→up→seed→ps, frontend и API health, один submit через H; сверить [LOCAL_ENV](../shared/LOCAL_ENV.md). **Ожидается:** postgres healthy, migrate exit=0, backend/worker healthy, frontend доступен; Job сохранен и обработан отдельным worker; startup/health не вызывают transport. UI fixture явно помечен, API/worker/frontend режим один; браузер использует relative /api, не контейнерный backend URL. Source Settings намеренно принимает timeout 300/connect 15/minEdge 32, PNG 64 проходит, session HMAC использует VISITOR_COOKIE_SECRET. Polza без ключа/проверенного профиля не делает dispatch и не включает fixture сам. Фото не доступно как static URL. **Команда:** `python -m pytest tests/integration/pilot/test_compose_persistence.py -k rel_c02 -q`.

<a id="rel-c03"></a>

## REL-C03 — цепочка миграций

**Вход:** чистая и сохранная локальные БД с исходными миграциями 001–007 и новой цепочкой processing. **Действие:** применить runner дважды, одновременно запустить два migrate; проверить registry/checksums/ограничения и старые записи. **Ожидается:** SQL выполняется по разу в порядке, конкурирующие runners сериализованы, повтор безопасен, схема/данные не очищаются. Ранее примененный SQL/checksum не переписан; исправление новой миграцией. **Команда:** `python -m pytest tests/integration/pilot/test_compose_persistence.py -k rel_c03 -q`.

<a id="rel-c04"></a>

## REL-C04 — сохранение после закрытия/restart

**Вход:** T1 создал Check/Notebook, P, queued и succeeded Jobs, отзывы/комментарии и сохраненную summary; T2 независим. **Действие:** закрыть UI, выполнить `docker compose -f compose.yaml restart backend worker`, повторно войти с другого browser context. **Ожидается:** прежние ID/байты нормализованных фото, актуальные анализы/отзывы/snapshot/summary сохранены, принятый Job не пропал, новая сессия не делает submit. T2 не получает доступ. Неизвестный исход проверяется отдельно C16. **Команда:** `python -m pytest tests/integration/pilot/test_compose_persistence.py -k rel_c04 -q`.

<a id="rel-c05"></a>

## REL-C05 — seed, вход и reset

**Вход:** переданный create_fixture_accounts и общая auth/schema. **Действие:** seed дважды; login/session/logout H для T1/T2/S; CLI reset одного T1 с паролем из скрытого ввода/local env, затем старые/новые cookie. **Ожидается:** ровно исходные три аккаунта, роли teacher/teacher/staff; password/token не возвращаются и не логируются. После reset старые сессии T1 дают 401, новый пароль работает, T2/S и данные T1 сохранены; logout=204, отозванная cookie не авторизует. **Команда:** `python -m pytest tests/integration/pilot/test_acl_staff.py -k rel_c05 -q`.

<a id="rel-c06"></a>

## REL-C06 — ACL и Origin на реальном HTTP

**Вход:** сохраненная проверка T1 с фото/результатом, T2 и S. **Действие:** T2 перебирает известные ID T1: getCheck/getPhoto/getJob/saveReview/delete; teacher читает staff endpoints; S вызывает teacher mutation; без cookie и без допустимого exact Origin выполнить записи, включая login/logout. **Ожидается:** чужой/удаленный объект 404 без раскрытия, без session 401, teacher на staff и staff mutation 403; неверный/отсутствующий Origin отклонен без записи/Job/денег. Приватное фото `Cache-Control: private,no-store`. Owner видит свое. **Команда:** `python -m pytest tests/integration/pilot/test_acl_staff.py -k rel_c06 -q`.

<a id="rel-c07"></a>

## REL-C07 — staff read-only и аудит

**Вход:** T1/T2 Checks, старые поколения и summary history; S. **Действие:** listStaffChecks с точным owner_login, cursor; открыть детали/фото/Report/review, getBundleHistory/getSummaryHistory, перейти назад; попытаться запись прямым HTTP. **Ожидается:** фильтр не возвращает другого владельца, pagination без дублей; история сохраняет каждый runs Job, Report/review/tombstone. В UI нет agree/skip/retry/delete/finalize/refresh, подписи от третьего лица. На каждый staff-read безопасный audit с реальным actor/role/resource; teacher revision/data_revision/согласия/время не изменены. **Команды:** `npx playwright test tests/e2e/pilot/staff_readonly.spec.ts --grep REL-C07`; из `app/` — `python -m pytest tests/pilot/staff -q`.

<a id="rel-c08"></a>

## REL-C08 — прием фото/неудачи загрузки

**Вход:** P и синтетические JPEG/PNG/WebP/HEIC/HEIF с EXIF, PDF/битый/слишком большой файл. **Действие:** камера/галерея, preview/reorder/replacement, uploadPhoto; прервать upload, изменить revision параллельно; boundary файлы для 8_000_000 байт/36_000_000 пикселей/minEdge 32. **Ожидается:** оригинал приватен, normalized asset корректно ориентирован; один part file. Успех=201 только после сохранения, порядок совпадает с draft. PDF/формат=415, битый=422, вход>8_000_000 байт=413, decoded>36_000_000 пикселей или короткая сторона<32=422. PNG 64 проходит. HEIC/HEIF конвертируется, но если обязательный normalized LLM asset не укладывается в те же 8 000 000 байт / 36 000 000 пикселей — 422 до accepted, без скрытого уменьшения качества/разрешения. PNG/JPEG/WebP без необходимости не перекодируются. При 409 ссылка не добавилась, временный файл убран. Неудачная передача не показана принятой; пустой/передаваемый draft не submit. **Команда:** `npx playwright test tests/e2e/pilot/teacher_flow.spec.ts --grep REL-C08`; API assertions: `python -m pytest tests/integration/pilot/test_acl_staff.py -k rel_c08 -q`.

<a id="rel-c09"></a>

## REL-C09 — многозадачная страница и продолжение

**Вход:** L `multi-task-confirmed`, `two-photo-continuation`, frozen E_C01/K01/M06 Reports. **Действие:** отправить одну страницу с несколькими задачами и два фото одной продолжающейся; затем сценарий целая+начало+продолжение. **Ожидается:** отдельные карточки/analysis_id для независимых задач, продолжение одна задача с двумя photo_indices; число фото не становится числом задач. Фото/тетрадь каждого результата верны; до 4 evidence, первый неверный/исправленный шаг и rule из frozen Report, без полного решения/OCR. **Команда:** `npx playwright test tests/e2e/pilot/teacher_flow.spec.ts --grep REL-C09`.

<a id="rel-c10"></a>

## REL-C10 — три действия и фон/out-of-order

**Вход:** два Bundle в одной/следующей тетради, имитатор задерживает первый. **Действие:** добавить продолжение без submit; submit+stay; новый комплект submit+next; второй ответ готов раньше первого; начать следующую съемку. **Ожидается:** до submit Job нет, оба submit=202 и все фото каждого входа идут одним запросом; навигация только после подтверждения. Следующая тетрадь доступна до ответа модели; результат второго появляется раньше первого с правильным контекстом, камера/открытая карточка не закрывается. Jobs продолжаются без вкладки; пустое действие не создает Job. **Команда:** `npx playwright test tests/e2e/pilot/teacher_flow.spec.ts --grep REL-C10`.

<a id="rel-c11"></a>

## REL-C11 — отзывы и mixed skip

**Вход:** L `mixed-skip-only-one-task`, `red-resolves-review-excluded-from-math`. **Действие:** одной пригодной задаче confirmed, другой system_error без комментария; изменить state и comment→пустая строка. not_assessed отдельно skipTask точного analysis_id. **Ожидается:** оценки ИИ независимы от математики и соседей, просмотра недостаточно для confirmed; красный не запускает retry. not_assessed не имеет фиктивного отзыва; skip одной не пропускает Bundle. Соседняя confirmed first_error может войти в топ, тетрадь mixed остается частичной/вне среднего; комментарий сам не меняет числа. **Команда:** `npx playwright test tests/e2e/pilot/teacher_flow.spec.ts --grep REL-C11`.

<a id="rel-c12"></a>

## REL-C12 — потерянный ответ и идемпотентность

**Вход:** T1 current draft+ETag; H submitBundle/createCheck/finalizeCheck. **Действие:** сервер commit успешен, ответ оборван; повторить те же method/path/key/payload с прежним If-Match, затем тот же key с другим payload; reload/второй клиент. **Ожидается:** возвращен исходный status/body/Job, один intent/Job/outbox/платная попытка; выросший guard не мешает принятому повтору. Другой payload=409 idempotency_conflict, новое изменение с устаревшим guard=409 revision_conflict; UI перечитывает Check, не создает второй intent сам. **Команда:** `python -m pytest tests/integration/pilot/test_lifecycle_recovery.py -k rel_c12 -q`.

<a id="rel-c13"></a>

## REL-C13 — замена поколения 2→3 и stale guard

**Вход:** две confirmed задачи общего Bundle и независимый confirmed Bundle; L `new-segmentation-two-to-three`. **Действие:** createInputVersion, сначала discard, затем новая replacement+submit; задержать старый worker; новая выдача содержит три задачи. Попытаться старым analysis_id записать отзыв. **Ожидается:** discard не снял отзывы; только submit деактивировал прежнее поколение. Активны ровно три новые task_id/analysis_id, все review=null; соседний Bundle сохранен. Старый worker/старый анализ не публикуется/не меняет новое, old review write=409. History сохраняет старые два; похожая формула не переносит согласие. **Команда:** `python -m pytest tests/integration/pilot/test_lifecycle_recovery.py -k rel_c13 -q`.

<a id="rel-c14"></a>

## REL-C14 — удаление и поздняя доставка

**Вход:** L `task-deleted-report-retained`, общее фото двух задач; другой Job running. **Действие:** отменить dialog delete; затем deleteTask, повторить публикацию его Job; deleteNotebook/Bundle и Check во время исполнения, доставить поздний ответ. **Ожидается:** отмена ничего не меняет; удалена только выбранная задача, соседняя и общее фото доступны; исходный Report/исторический review/tombstone сохранены. Тот же Job не пересоздает удаленную задачу. Удаленные родители/фото дают 404, новая платная отправка/публикация подавлены; unknown reserve сохранен для сверки. Корзины/recover UI нет. **Команда:** `python -m pytest tests/integration/pilot/test_lifecycle_recovery.py -k rel_c14 -q`.

<a id="rel-c15"></a>

## REL-C15 — ровно один автоматический повтор

**Вход:** оба kind, имитатор дважды возвращает подтвержденный temporary_failure, отдельно uncheckable/invalid_response/красный отзыв. **Действие:** restart между Attempt 1 и retry. **Ожидается:** Job имеет не более двух Attempt (первый+один auto), счетчик долговечен, далее failed/can_retry по контракту; обе стоимости/резервы учтены. Математическая ошибка, system_error, нечитаемость/нехватка условия, invalid schema/арифметика не запускают auto-retry. **Команда:** `python -m pytest tests/integration/pilot/test_lifecycle_recovery.py -k rel_c15 -q`.

<a id="rel-c16"></a>

## REL-C16 — неизвестный исход, fencing и сверка

**Вход:** Attempt мог быть отправлен, ответ потерян; expired lease и второй worker. **Действие:** restart, поздний ответ старой lease; skip Bundle; CLI сверить имитатором сначала без доказательства, затем settled/rejected; повтор settlement и противоречащий evidence. **Ожидается:** unknown без нового auto-вызова, резерв удержан даже после skip/cancelled; старый fencing token не публикует результат. Неподтвержденная сверка отклонена без изменений; settled один раз заменяет резерв фактом, rejected освобождает только доказанно не списанное. Same request/evidence no-op, конфликт nonzero CLI exit. Поздний результат skipped входа сохраняется для сверки, не возвращается в Check. **Команда:** `python -m pytest tests/integration/pilot/test_lifecycle_recovery.py -k rel_c16 -q`; CLI wrapper проверяет этот же fixture через facade, не SQL.

<a id="rel-c17"></a>

## REL-C17 — общий cumulative cap и hot-change

**Вход:** изолированный fixture budget, два конкурентных Job разных kind/teacher, slots=2. **Действие:** проверить default cap 500, уменьшить cap до границы одного reserve, одновременно dispatch; один usage доставить дважды; через контейнерный `python -m pilot.processing.budget set-limit --rub 500` поднять cap без restart. **Ожидается:** walletinitialize/topup/отдельный pricing-файл не prerequisite. Atomic spent+held допускает только разрешенный запрос; blocked Job сохраняет идентичность и продолжает после повышения. Spent/holds не сбрасываются, settlement один, два global slots соблюдены. Валидный cost=null ответ публикуется с billing hold; execution unknown не resend. Cap не является балансом Polza или месячной квотой; teacher не видит счетчик. **Команда:** `python -m pytest tests/integration/pilot/test_funds_control.py -k rel_c17 -q`. Этот release/container case пока not_run; локальный backend аналог PROC-C27/C29 PASS по [отчету](../processing/RUNTIME_REPORT.md).

<a id="rel-c18"></a>

## REL-C18 — ручная pause/resume

**Вход:** queued checker+analytics, один уже dispatched; facade processing. **Действие:** `python scripts/pilot/processing_control.py pause --operator-ref local-acceptance --reason fixture-check`, затем status/resume с тем же trusted контекстом; поставить красный отзыв отдельно. **Ожидается:** после зафиксированной pause новых dispatch/резервов нет, queued сохраняются, уже dispatched корректно завершается/сверяется; чтение/аккаунты/история доступны. Resume продолжает прежние Jobs, красный отзыв сам ничего не выключает. HTTP control route/третьей роли нет, audit содержит operator_ref/request_id без секретов. **Команда:** `python -m pytest tests/integration/pilot/test_funds_control.py -k rel_c18 -q`.

<a id="rel-c19"></a>

## REL-C19 — два этапа финала и blocker-матрица

**Вход:** L completion-waits-checker, unsent-draft-blocks-finalize, failed-input-no-false-zero, unknown-input-no-false-zero, uncheckable-skipped-input, finalize-queues-analytics; отдельная пустая Check. **Действие:** beginCompletion, пока review редактировать; разрешить все blockers; finalize, повторить двумя клиентами/ключами. **Ожидается:** begin=200, phase review, нет AnalyticsJob; редактирование разрешено. Pending Jobs, null reviews, unresolved tasks/bundles и непустой draft блокируют finalize=409. Пустая Check с нулевыми счетчиками тоже 409. System_error и явный skip разрешают финал, не становятся confirmed. Финал=202, один snapshot/AnalyticsJob, phase finalized; repeat не создает второй, прямой финал из editing409. **Команда:** `python -m pytest tests/integration/pilot/test_analytics_finalization.py -k rel_c19 -q`.

<a id="rel-c20"></a>

## REL-C20 — гонки финала и закрытый состав

**Вход:** can_finalize=true в двух клиентах; управляемые барьеры транзакций. **Действие:** гонки finalize против upload/submit/review/worker publish; после финала попробовать add/deleteTask/deleteNotebook/replace/checker retry/skip, затем изменить существующий review и удалить Check целиком. **Ожидается:** один общий Check guard: выигравшее изменение либо попало в snapshot и revision, либо проигравший запрос получил 409; нет snapshot между проверкой и commit. После finalized состав 409, review разрешен по актуальному guard, deleteCheck разрешен. Snapshot неизменяем, запрос не доверяет старому can_finalize. **Команда:** `python -m pytest tests/integration/pilot/test_analytics_finalization.py -k rel_c20 -q`.

<a id="rel-c21"></a>

## REL-C21 — ошибка аналитики/retry/GET

**Вход:** L saved-analytics, fresh-failed-analytics-can-retry, G; имитатор неверного JSON/арифметики и безопасного failed. **Действие:** polling GET summary/reload/history, неверный ответ, затем retrySummary при can_retry=true/stale=false, повтор intent. **Ожидается:** GET не создает Job и расход. Invalid result не чинится скрытым агрегатором, не показывается как succeeded. Retry создает новый Job по тому же snapshot, один на intent; blocked/unknown/успешный свежий не повторяются; stale+failed не retry. Сохраненный валидный result возвращается после входа. **Команда:** `python -m pytest tests/integration/pilot/test_analytics_finalization.py -k rel_c21 -q`.

<a id="rel-c22"></a>

## REL-C22 — stale, comment-only, refresh и поздний ответ

**Вход:** L review-change-stales-analytics, comment-keeps-analytics-current, stale-analytics-{queued,blocked,running,retry_wait,unknown,failed}; G. **Действие:** state confirmed↔system_error после финала, затем comment-only; refresh при capability; race claim/refresh, завершение старого snapshot. **Ожидается:** state меняет data_revision/stale без auto-запуска; comment только revision и без stale. При can_refresh новый snapshot/Job, старый гарантированно неотправленный superseded атомарно; иначе 409 и перечитывание. Running/unknown/возможно отправленный retry_wait не обходятся refresh. Поздний ответ не выбирает старую сводку; UI скрывает устаревшие числа как актуальные. **Команда:** `python -m pytest tests/integration/pilot/test_analytics_finalization.py -k rel_c22 -q`.

<a id="rel-c23"></a>

## REL-C23 — числовой/смысловой oracle

**Вход:** четыре M пары, валидатор analytics/validate.py, те же данные через настоящий snapshot+fixture worker. **Действие:** финализировать и отрендерить результат; отдельно подать неверный счет/чужой task_id/дублирующиеся ссылки в ответе имитатора. **Ожидается:** oracle total=4/with_errors=1/without_errors=1/partial=1/empty=1, average=0.5 (знаменатель 2), incomplete=1/disputed=1; partial confirmed first_error присутствует в топе, вне среднего. Zero-denominator average=null, не 0. Mixed partial=1/unassessed=1/average=null и confirmed соседняя ошибка в топе. Synonyms — одна смысловая группа с двумя task_ids, average=2. Неполное all_steps_correct не увеличивает errors; rule_id не требуется, описка не отдельный топ. Неверные числа/ссылки отклонены, не исправлены молча. **Команда:** `python -m pytest tests/integration/pilot/test_analytics_finalization.py -k rel_c23 -q`.

<a id="rel-c24"></a>

## REL-C24 — несколько учителей/60 тетрадей/out-of-order

**Вход:** T1 и T2 по 30 Notebook, циклически 3/4/5 задач (по 120 задач каждому, всего 240), синтетический transport, slots=2, достаточно имитированных средств. **Действие:** чередовать submit двух учителей; ответы возвращать в обратном/перемешанном порядке; параллельно открыть съемку/чтение. **Ожидается:** по 30 тетрадей/120 активных задач у каждого, всего 240 без дублей/потерь/смешивания владельцев, все Jobs сценария терминальны после release всех барьеров. Одновременных dispatch≤2, оба владельца обслужены; result принадлежит точным input/job. UI/камера не ждут первый Job; расход только имитированный, внешних вызовов 0. **Команда:** `python -m pytest tests/integration/pilot/test_events_load.py -k rel_c24 -q`.

<a id="rel-c25"></a>

## REL-C25 — события, неполнота и безопасные логи

**Вход:** два client session одного T1 и S, H ingestEvents, до 100 events с семью именами контракта. **Действие:** batch/repeat, ID с другим payload, чужая entity, batch 101, отсутствующая клиентская телеметрия; получить server events/audit/ledger ссылки. **Ожидается:** одинаковый повтор accepted_ids без дубля, другой payload 409, чужая ссылка 404 без частичного приема, >100 отклонен 422. Actor/role/received_at только серверные. Потеря событий не ломает основной путь, наблюдения помечены неполными; пересечения сессий не названы точным временем письма. Нет фото/Base64/полных Reports/промптов/комментариев/паролей/cookie/ключей в общем журнале; cost живет в ledger, неизвестное не 0. **Команда:** `python -m pytest tests/integration/pilot/test_events_load.py -k rel_c25 -q`.

<a id="rel-c26"></a>

## REL-C26 — исключенные функции и режимы

**Вход:** assembled UI и API route table. **Действие:** осмотреть все экраны, POST `/api/auth/register`, старые `/analyze` и `/api/analyze`, поиск публичной анонимной обработки, quota/upsell и control endpoints. Включить fixture и отдельно polza без ключа. **Ожидается:** старые маршруты 404, публичной регистрации/платного анонимного пути/HTTP admin control нет. Нет teacher тарифов/квот 3/20, CAS, оценок, экспорта, OCR-редактора, отдельного фото условия, offline/push, встроенного чата, смены title/number. Fixture явно помечен, polza без ключа не дает fake-success. Исправление до первого ошибочного шага, незавершенность отдельно. **Команда:** `npx playwright test tests/e2e/pilot/teacher_flow.spec.ts --grep REL-C26`; API assertions: `python -m pytest tests/integration/pilot/test_acl_staff.py -k rel_c26 -q`.

<a id="rel-c27"></a>

## REL-C27 — responsive и реальные телефоны

**Вход:** последний integration commit и P/математические Reports. **Автоматически:** `npx playwright test tests/e2e/pilot/mobile_layout.spec.ts --grep REL-C27` — widths 320/360/390/430, текст 200%, keyboard/focus/dialogs, длинный LaTeX/scroll, zoom фото и возврат. **Ручные шаги отдельно для настоящего Android и iPhone:** войти, создать проверку, снять камерой, выбрать галерею/HEIC, отказать разрешению и вернуться, переснять/упорядочить/отправить, открыть готовый результат при съемке, zoom, отзыв, свернуть/вернуться, два этапа финала. **Ожидается:** основная страница без горизонтального scroll, формула скроллится в своем блоке, текст/кнопки не обрезаны, target≥48px, focus/статус доступны; камера не закрыта чужим результатом, серверные материалы после возврата сохранены. Записать device/OS/browser/version/transport и локальный доступ/HTTPS; нет устройства — not_run этой части, эмуляция не закрывает ее.

<a id="rel-c28"></a>

## REL-C28 — backup/restore и безопасный rollback

**Вход:** тестовая БД/photo volume с ready+queued+unknown Attempt/reserve, private backup directory вне Git, RELEASE_RUNBOOK. **Действие:** локальным script остановить новые записи/dispatch и сделать согласованный DB+photos backup; восстановить через `scripts/pilot/restore_local.py` в отдельный Compose project `smartnote-restore-test` с новыми volumes. Сверить ID/байты/сессии/отзывы/snapshot/unknown reserve; restart; rehearsal rollback к совместимому commit/image без SQL downgrade. **Ожидается:** исходная база/volumes не затронуты, данные восстановлены, unknown не превратился в retry/free; rollback не чистит данные и не переписывает примененные миграции. Backup/evidence/ключи не в Git. **Команда:** `python -m pytest tests/integration/pilot/test_compose_persistence.py -k rel_c28 -q`; ручной проход runbook другим исполнителем — отдельная отметка, а не встреча/обязательная зависимость.

## Одна матрица полного покрытия A01–A25

Это назначение проверок, не результаты. В RELEASE_REPORT добавить status/commit/evidence для каждой строки. Application/processing выполняют собственные case по указанным A-ID; release повторяет локальную интеграционную проверку независимо. Реальные телефоны и внешний сервер отмечаются отдельно.

| A-ID | Release cases | Проверки реализации в смежных ТЗ |
|---|---|---|
| A01 | C05/C06/C26 | application A01; processing A01 |
| A02 | C08/C27 | application A02; processing A02 |
| A03 | C09/C11 | processing A03; application сообщения A03 |
| A04 | C09/C10/C13 | application/processing A04 |
| A05 | C09/C11/C15 | processing A05; application renderer A05 |
| A06 | C09/C27 | application A06 |
| A07 | C11 | application/processing A07 |
| A08 | C11/C22/C23 | application/processing A08 |
| A09 | C13/C16 | application/processing A09 |
| A10 | C11/C15/C19 | application/processing A10 |
| A11 | C15/C16 | processing A11 |
| A12 | C04/C05/C27/C28 | application/processing A12 |
| A13 | C12 | application/processing A13 |
| A14 | C13/C19/C20 | application/processing A14 |
| A15 | C14/C20 | application/processing A15 |
| A16 | C19/C20/C21/C22 | application/processing A16 |
| A17 | C23 | processing A17; application rendering A17 |
| A18 | C09/C23 | processing A18; application rendering A18 |
| A19 | C02/C10/C24 | processing A19; release load |
| A20 | C06/C07 | processing ACL/audit A20; release staff |
| A21 | C07/C25 | application emits A21; processing receiver A21 |
| A22 | C01/C25/C28 | все направления A22 |
| A23 | C16/C17/C28 | processing A23; release CLI/races |
| A24 | C18 | processing A24; release CLI |
| A25 | C01/C23/C26/C27 | все направления A25 |

Итог к 21:00: каждый REL-CNN и A-ID имеет pass/fail/not_run, команду/ручные шаги, actual vs expected и commit. Полная локальная готовность не заявляется при скрытых failed/not_run. Нет авторизованного live smoke — качество нового AI-запроса не проверено; нет deploy — серверный выпуск отдельно; нет реальных устройств — соответствующая часть мобильной приемки не выполнена.
