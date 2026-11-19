# Задачи processing

19.11.2026. **Реализовано и проверено локально**:99 PASS,32/32 PROC-Cxx на чистом `9d78895`; [матрица и ограничения](RUNTIME_REPORT.md). Ниже сохраняются требования и порты для интеграции. Существуют [shared v1](../shared/README.md), frozen checker и исходный source. HTTP/DTO только из OpenAPI/schema, не из второй схемы в ТЗ. Владение/сроки – [README](README.md), PROC-C01–PROC-C32 – [ACCEPTANCE](ACCEPTANCE.md).

## Публичные порты до B1b

Это внутренние Python-интерфейсы, не новый HTTP. Application/release не пишут SQL/ACL повторно. Методы async, кроме явно отмеченных factory/DTO/prepare. DTO берутся из generated `pilot.contracts`; аргументы ID – UUID. `Settings` импортируется из исходного `config`, asyncpg сохраняется без второго ORM.

| Модуль | Сигнатуры и выход |
|---|---|
| `domain/services.py` | sync `create_services(pool:asyncpg.Pool,storage_root:Path,settings:Settings)->Services`. Services – pool/storage/auth и внутренние queue/funds/transport зависимости. Factory не мигрирует БД, не запускает worker/сеть; application кладет ее результат в `app.state.pilot_services` |
| `domain/access.py` | immutable `Actor(user_id:UUID,role:Literal['teacher','staff'])`; `get_services(request:Request)->Services`; `require_actor(request:Request)->Actor`; sync `require_staff(actor)->None`. Actor берется из действительной серверной сессии, не client role |
| `domain/revision.py` | immutable `MutationContext(actor:Actor,expected_revision:int|None,idempotency_key:UUID,request_id:UUID)`. None допустим только createCheck. HTTP adapter парсит headers, домен окончательно проверяет guard/права/intent |
| `domain/errors.py` | `DomainError(http_status:int,code:str,message:str,current_revision:int|None=None)`; `.to_response()->ErrorResponse`; sync `install_error_handlers(app:FastAPI)->None`. Один безопасный маппинг для всех routes |
| `domain/auth.py` | `authenticate(svc,login:str,password:str)->SessionGrant`; SessionGrant содержит shared `session:Session` и secret `token:str` с repr=False; `actor_for_token(svc,token:str|None)->Actor|None`; `revoke(svc,token:str|None)->None`; `ensure_account(svc,login,password,role,*,operator_ref:str='local-seed',request_id:UUID|None=None)->Session` только seed/CLI. Повтор существующего login с той же ролью – no-op без сброса пароля; другая роль 409. Для seed без request_id сервис генерирует UUID аудита. `reset_account_password(svc,*,login:str,password:str,operator_ref:str,request_id:UUID)->Session` только trusted local CLI: общий scrypt, атомарный reset и revoke всех сессий этого аккаунта; данные/ID и другие аккаунты сохраняются. HTTP register/reset отсутствуют |
| `domain/storage.py` | sync `prepare_photo(stream:BinaryIO,declared_type:str)->PreparedPhoto` в threadpool; PreparedPhoto содержит приватные temp original/normalized paths, фактический media_type/sha256/bytes/размеры, не HTTP DTO; sync `discard_prepared(prepared)->None` очищает только свои временные файлы |
| `domain/queries.py` | `list_checks(svc,actor,*,cursor:str|None=None,limit:int=30,request_id:UUID)->Checks`; `get_check(svc,actor,check_id:UUID,*,request_id)->Check`; `get_bundle_history(svc,actor,bundle_id,*,request_id)->BundleHistory`; `open_photo(svc,actor,photo_id,*,request_id)->PrivatePhoto(path:Path,media_type:str)`; `get_job(svc,actor,job_id,*,request_id)->Job`; `get_summary(svc,actor,check_id,*,request_id)->Summary`; `get_summary_history(svc,actor,check_id,*,request_id)->SummaryHistory`. ACL/audit внутри, history только staff; PrivatePhoto.path клиенту не сериализуется |
| `domain/queries.py`, staff | `list_staff_checks(svc,actor,*,owner_login:str|None=None,cursor=None,limit=30,request_id)->StaffChecks`; `get_staff_check(svc,actor,check_id,*,request_id)->StaffCheck`. Release services/staff вызывает их, без собственного доступа/SQL |

Все следующие mutations: `(svc:Services,ctx:MutationContext,...) -> Mutation`, commit/outbox до возврата. Application не вызывает queue/ledger отдельно. Method/path определяется operationId shared.

| operationId | `domain/mutations.py`: имя и оставшиеся аргументы |
|---|---|
| createCheck | `create_check(...,payload:Title)` |
| createNotebook | `create_notebook(...,check_id:UUID)`; без тела, серверный монотонный number |
| createBundle | `create_bundle(...,notebook_id:UUID)`; Bundle+пустой draft |
| createInputVersion | `create_input_version(...,bundle_id:UUID,payload:VersionCreate)` |
| uploadPhoto | `upload_photo(...,input_version_id:UUID,prepared:PreparedPhoto)`; при отказе cleanup |
| reorderPhotos / discardDraft | `reorder_photos(...,input_version_id,payload:PhotoOrder)` / `discard_draft(...,input_version_id)` |
| deleteDraftPhoto | `delete_draft_photo(...,input_version_id,photo_id:UUID)` |
| deleteTask / deleteBundle / deleteNotebook / deleteCheck | `delete_task(...,task_id)` / `delete_bundle(...,bundle_id)` / `delete_notebook(...,notebook_id)` / `delete_check(...,check_id)` |
| saveReview | `save_review(...,task_id,payload:ReviewWrite)` |
| submitBundle / retryBundle / skipBundle | `submit_bundle(...,bundle_id,payload:Submit)` / `retry_bundle(...,bundle_id,payload:InputTarget)` / `skip_bundle(...,bundle_id,payload:InputTarget)` |
| skipTask | `skip_task(...,task_id,payload:AnalysisTarget)` |
| beginCompletion / finalizeCheck | `begin_completion(...,check_id)` / `finalize_check(...,check_id)` |
| refreshSummary / retrySummary | `refresh_summary(...,check_id)` / `retry_summary(...,check_id)` |

Дополнительные порты:

- `events/receiver.py`: `ingest_events(svc,actor,payload:Events,*,request_id:UUID)->EventsAccepted`; отдельная дедупликация Event.id, не MutationContext.
- `processing/control.py`: `get_processing_control(svc)->ControlState`; `set_processing_paused(svc,*,paused:bool,operator_ref:str,reason:str,request_id:UUID)->ControlState`. Внутренний ControlState: paused:bool, available_rub:Decimal, held_rub:Decimal, unknown_attempt_ids:tuple[UUID,...]. Это не teacher payload и не новая аккаунтная роль.
- `processing/reconciliation.py`: `reconcile_attempt(svc,*,attempt_id:UUID,outcome:Literal['rejected','settled'],evidence:ReconciliationEvidence,operator_ref:str,request_id:UUID)->ReconciliationResult`. Evidence: reference:str,sha256:str,actual_cost_rub:Decimal|None,provider_request_id:str|None. Результат: attempt_id,state,held_rub,changed:bool. Settled допускает неизвестную цену с сохранением billing hold; finite actual cost позднее завершает billing. Rejected требует доказательства отсутствия списания. Неполное evidence не освобождает hold. Повтор request/evidence no-op, противоречащий повтор 409. Raw evidence файл не копируется в общий лог.
- Release CLI `processing_control.py status|pause|resume`, `reconcile_attempt.py --attempt-id UUID --outcome rejected|settled --evidence-file LOCAL_PATH` вызывают эти порты; trusted local доступ и аудит operator_ref, без HTTP admin/staff write.
- `processing/budget.py`: `get_budget(svc)->BudgetState`; `set_spend_limit(svc,*,spend_limit_rub,operator_ref='container-shell',request_id=None)->BudgetState`. Поля: spend_limit_rub/spent_rub/held_rub/available_rub/paused. Накопительный cap по R87 –500 RUB на все teacher и оба kind; fixture/polza изолированы. CLI: `python -m pilot.processing.budget status`; `python -m pilot.processing.budget set-limit --rub 500`. Изменение trusted CLI без restart, spent/holds не обнуляются. Initialize/topup и внешний pricing-файл не являются prerequisite dispatch; встроенный conservative profile находится в `processing/pricing.py`.
- `processing/funds.py` сохраняет legacy `fund_wallet` для совместимости учета; это не актуальный способ разрешить dispatch или изменить cap. Trusted reconciliation обрабатывает execution unknown и отдельный billing unknown; при settled с неизвестной стоимостью hold сохраняется, затем уточняется новым evidence.

- `pilot.routes.processing.router` и `pilot.routes.events.router` – APIRouter с путями **без `/api`**. Application один раз агрегирует их и подключает с prefix='/api'. Entry points: `python -m pilot.domain.migrate`, `python -m pilot.processing.worker`, `python -m pilot.processing.worker --healthcheck`. Импорты не имеют сетевых побочных действий.

## PROC-01 – Схема, миграции и types; B1b

**Цель/основание:** единое сохранение R26/R28/R46/R47/R62/R70/R73/R80–R86; A01/A09/A12/A15/A16/A23. **Вход:** pinned bootstrap application B1a, SQL 001–007, shared schemas/fixtures. **Файлы:** `app/migrations/008_pilot_domain.sql` и последовательные новые SQL, `domain/{models,repository,migrate}.py`, generated contracts.py/generated.ts, `app/tests/pilot/domain/test_proc_contract.py`. Не менять примененные 001–007/чужие entrypoints.

**Действия/выход:** сверить SHA/manifest и исходные auth/experiment/Polza тесты. Сохранить users/auth_sessions, добавить role teacher/staff. Создать pilot-таблицы: checks,notebooks,bundles,input_versions,photo_assets,version_photos,jobs,attempts,workers,bundle_reports,task_analyses,reviews,snapshots,analytics_results,idempotency,outbox,events,audit,funds,fund_reservations,fund_ledger (в SQL все с префиксом `pilot_`). Check содержит next_notebook_number и selected_summary_job_id. FK владения; unique номер тетради, position версии, draft Bundle, Job/ordinal Attempt, Report/Result на Job, task/analysis IDs, intent tuple, actor/event и settlement Attempt. Job имеет ровно один input согласно kind. Sealed links/Report/snapshot immutable, tombstones не стираются повторной публикацией. History.runs привязывается к каждому Job, не одному Report на input. Workers хранит безопасный process identity/heartbeat для health даже при пустой очереди.

Runner под advisory lock и registry checksum выполняет цепочку один раз; повтор безопасен, несовпадение примененного checksum fail closed. Проверить чистую PG16 и upgrade от 001–007 без потери users/sessions. Нет startup destructive reset. Types генерировать/копировать из shared, drift и runtime schema проверять отдельно.

**Приемка:** PROC-C01/C02/C24. **DoD:** runner/models/types импортируемы B1b, обе цепочки проходят в PG, ограничения проверены. Application получает Services без собственного SQL; наличие schema не объявляет worker реализованным.

## PROC-02 – Auth/access/revision/idempotency; B1b

**Цель:** R25/R26/R28/R46/R49/R76/R79; A01/A08/A12/A13/A20/A22. **Вход:** PROC-01, shared roles/errors/If-Match, application auth HTTP/seed. **Файлы:** `domain/{services,auth,access,revision,errors,queries,mutations}.py`, исходные `app/auth.py`, `config.py`, domain tests.

**Действия:** адаптировать scrypt/token hash/expiry/revoke, роль читать с сервера; register не подключать. Все порты B1b фиксированы. Mutation блокирует Check, проверяет owner/phase/current entity; принятый intent ищет **до** нового If-Match. Mutation+key+outbox+revision одним commit. Multipart hash включает bytes/version, guard не часть payload hash. Replay/no-op не увеличивает revision, comment-only не увеличивает data_revision. Единый порядок Check→Bundle→InputVersion/Job→Task; деньги/slots в одном устойчивом порядке, внешнего HTTP под DB-lock нет. Чужой ID404, staff только явно разрешенное read/audit, отказ не резервирует деньги. DomainError единообразно маппится в shared ErrorResponse.

**Приемка:** PROC-C03–C06/C23. **DoD:** denied/replay/no-op не меняют данные; application/release используют общий auth/guard, не обходят его SQL.

## PROC-03 – Storage, CRUD и ранние hooks; B1b, негативные случаи B2

**Цель:** R15/R26/R28/R44/R45/R48/R71/R80/R81; A02/A04/A12/A14/A15. **Вход:** PROC-01/02, application HTTP/volumes. **Файлы:** `domain/{storage,mutations,queries}.py`, ранние `routes/{processing,events}.py`, `processing/worker.py`, codec зависимости `app/requirements.txt`, domain tests; не main/Compose.

**Действия:** named CRUD, монотонный number без переиспользования, Bundle+draft. Единая политика [LOCAL_ENV](../shared/LOCAL_ENV.md) для upload и нормализованного LLM asset: 8 000 000 bytes, 36 000 000 pixels, короткая сторона от 32. JPEG/PNG/WebP в пределах политики не перекодировать/не уменьшать без необходимости; EXIF orientation учитывать. HEIC/HEIF конвертировать реальным закрепленным server decoder, original сохранять приватно. Если необходимая конвертация дает asset вне этих границ –422 до accepted; без циклов поджатия и молчаливого ухудшения. Settings старого source намеренно исправить: timeout75/max180→300 и MIN_IMAGE_EDGE240/ge64→32. PNG64 проходит реальный upload без обхода validator. Битый/PDF/type отклонять. Prepare в threadpool; безопасные storage keys, durable files+DBlink до 201, при конфликте cleanup без изменения состава. GET normalized только после ACL/staff audit, no-store. Draft-link delete не удаляет sealed/history/соседний asset. GC только непривязанных temp. Replacement draft create/cancel сохраняет reviews. Draft replace: upload→delete old→полный reorder с новым guard; после сбоя GET фактического draft, sealed неизменен.

До B1 реально работают create/read/photo/submit→queued и worker health; все прочие порты импортируемы/зафиксированы, функционально завершаются B2. Не выдавать пустой router/заглушку за успешную обработку. **Приемка:** PROC-C02/C07–C09/C24. **DoD:** форматные тесты декодируют файлы, assets не публичны, принятый ввод живет без вкладки, школьных данных в Git нет.

## PROC-04 – Поколения/reviews/skip/delete; B2

**Цель:** R21–R24/R46/R47/R62/R69/R70/R78–R82; A04/A07–A10/A14/A15. **Вход:** PROC-01–03, frozen Task/Report/lifecycle. **Файлы:** domain mutations/queries/repository, `processing/publish.py`, domain/processing tests.

**Действия:** submit sealed+Job/outbox атомарно; старое поколение снимается при submit, не draft create. Ручной retry того же input – новый Job и снятие ВСЕХ reviews; mixed пересматривает весь Bundle. Publish guards current version+Job+Attempt fencing, новые Task/Analysis UUID без сопоставления формул/номеров. Две→три дают три текущие, history сохраняет оба successful runs. Task deletion=tombstone поколения; raw Report/общее фото прежние. Bundle/Notebook/Check delete закрывает publish/будущие вызовы, unknown hold не трогает. Assessable review confirmed/system_error отдельно, not_assessed только skip. Bundle skip failed/uncheckable/blocked/unknown сохраняет отсутствие математики и историю, cancelled Job не освобождает unknown Attempt. Незатронутый Bundle не сбрасывается.

**Приемка:** PROC-C10–C14. **DoD:** один активный набор, old ID не воскресает, mixed не теряет соседей, skipped failed не false zero; comment не переписывает checker JSON.

## PROC-05 – Queue/lease/fencing/restart; B1 queue+health, B2 worker

**Цель:** R20/R26/R28/R30/R73/R78/R81; A04/A11–A13/A19/A23. **Вход:** PROC-01/02/04, резерв PROC-07 обязателен до любого dispatch; пока только явный fixture без внешней сети. **Файлы:** `processing/{worker,queue,attempts,publish}.py`, processing tests.

**Действия:** Job/outbox до 202. PG claim: выбрать кандидата без удержания Job-lock, затем в транзакции Check→Bundle→Job с `FOR UPDATE SKIP LOCKED`, повторно проверить кандидата; не брать Job перед Check, создавая обратный порядок с finalize. Lease60s, heartbeat10s, health stale после 30s; продление идет независимо от долгого HTTP, значения фиксируются в коде и проверяются управляемыми часами. Global slots2 для обоих kind, не только process mutex. Renew/settle/publish текущего состояния сравнивают epoch; потерявший lease worker не публикует и не меняет current Job. Поздние финансовые сведения сохраняются как evidence для сверки старой Attempt, не теряются с отклоненным callback. Перед dispatch повторить live/current/snapshot/funds guards. Один POST на Attempt, HTTP за DB-транзакцией. Expired lease до доказанной отправки можно вернуть; после возможной отправки unknown+hold без resend. Ровно один авто retry доказанного временного сбоя, счетчик/next_run_at в PG переживает restart. Фото/invalid JSON/length/red сами не retry. Отключить транспортные скрытые retries.

**Приемка:** PROC-C05/C15–C18/C30. **DoD:** restart не теряет ввод/счетчик, два worker не дублируют POST, health читает PG heartbeat, pause не изображает crash; GET не запускает модель.

## PROC-06 – Shared transport и frozen checker; B2

**Цель:** R10/R16/R38/R68/R71/R80–R82; A03–A05/A11/A18/A25. **Вход:** reference adapter/contract/prompt/schema и source Polza, PROC-03/05/07. **Файлы:** `processing/{transport,checker,fixture_transport}.py`, config, безопасные frozen assets package, tests/processing.

**Действия:** общий `send_once(request,attempt_context)->TransportResult`, httpx, safe diagnostics/usage, один POST. Checker builder воспроизводит system text hash, ordered images1..N/high и strict schema; локальные semantic checks до publish. Профиль 25k/300s/connect15/medium – прежняя инженерная рекомендация, не новый live факт. Report.uncheckable при transport success не математический успех. Raw response приватно, safe metadata без фото, секретов и полного JSON. Аналитика вызывает тот же transport другим builder, а не analyze с подмененным checker.

PILOT_TRANSPORT default polza: ключ/URL/route/config обязательны, без ключа fail closed; fixture только явно, без сети, сценарии success/refusal/failure/unknown. Spy считает каждый POST и запрещает настоящий Polza в тестах. **Приемка:** PROC-C08/C09/C16/C19/C25/C30. **DoD:** multi/continuation/mixed, до четырех evidence, первый неверный шаг, его исправление и raw rule сохранены; нет CAS/confidence/rule_id/полного OCR. HEIC нормализован до checker.

## PROC-07 – Общий накопительный cap, pause и unknown; B3

**Цель:** R87 уточняет финансовый контроль R59/R60; A11/A13/A19/A23/A24. **Файлы:** `processing/{budget,funds,control,reconciliation,attempts,pricing}.py`, PG tests. **Вход:** общий queue/dispatch и два global slots.

По последнему решению действует общий накопительный backend cap 500 RUB в PostgreSQL: spent+active holds+новый консервативный reserve не превышают cap перед dispatch. Контроль один для всех учителей/page_check/class_analytics; режимы fixture/polza изолированы. Суммы Decimal/Numeric, reserve и claim атомарны. Cap изменяется через `python -m pilot.processing.budget set-limit --rub 500` без restart; lowering не отменяет начатое, повышение продолжает исходные Job. Ни walletinitialize/topup, ни ручной pricing-файл не требуются. Цена берется из встроенного проверенного route profile; средний benchmark расход не служит bound.

Execution unknown отделен от billing unknown. Валидный ответ с cost=null публикуется и освобождает worker slot, но удерживает финансовый reserve; неизвестная стоимость не равна 0. Потерянный исход исполнения сохраняет unknown и не допускает blind resend. Trusted reconciliation с reference/sha256 и request_id идемпотентна: доказанный rejected подтверждает 0; settled с неизвестной ценой не освобождает hold, позднее finite actual cost закрывает его один раз. Отмена/skip/delete/restart сами не являются финансовым доказательством. Manual pause отдельно блокирует новые dispatch, сохраняя read/review/health и завершение running.

**Приемка:** PROC-C17/C18/C26–C29. **DoD:** атомарные гонки cap, hot CLI, оба kind/teacher, restart, valid-result/cost-null, execution unknown и trusted dedupe проходят PG tests; [результат](RUNTIME_REPORT.md). Старое требование initialize/проверенного wallet balance superseded R87.

## PROC-08 – Completion/finalize/snapshot; B3

**Цель:** R24/R34–R39/R46/R84/R86; A08/A14/A16/A17. **Вход:** PROC-04/05/07, shared completion/snapshot. **Файлы:** `domain/{completion,mutations,queries}.py`, `analytics/snapshot.py`, processing router, domain/analytics tests.

**Действия:** begin editing→review без аналитики, пять счетчиков current data. Finalize editing/pending/draft/unreviewed/unresolved/empty –409 без snapshot/Job. Red разрешает оценку, not_assessed требует skip, skipped failed остается partial. Под одной Check-lock transaction: If-Match/phase/completion, composition freeze, immutable snapshot current generation, один AnalyticsJob/outbox. После финала состав/checker retry/skip запрещены, assessable reviews/comments и deleteCheck разрешены. Snapshot серверный, без comments/photo/title/number/old/tombstones, с red/not_assessed и unresolved_bundles.

**Приемка:** PROC-C12/C14/C20–C22/C24. **DoD:** один final snapshot/Job, точный состав; upload/review/publish не вклиниваются в финал, can_finalize клиенту не доверен.

## PROC-09 – Отдельная аналитика/stale/refresh/retry; B3

**Цель:** R34–R39/R46/R83/R86; A08/A16–A18/A23. **Вход:** весь shared/analytics, PROC-05–08. **Файлы:** `analytics/{builder,runner,validation,snapshot}.py`, prompt/schema assets пакета, processing routes, analytics tests.

**Действия:** отдельный system prompt и snapshot JSON текстом, без images; общий transport/queue/funds. Перенести prompt/schema/validate_pair без смены смысла, хеши/fixtures сохранить. Профиль 25k/300s/medium для аналитики проверен отдельным text-only live smoke: [отчет](RUNTIME_REPORT.md); это не live-проверка checker с 25k. Invalid/length не чинить детерминированной сводкой и не считать transient. LLM группирует смыслы, validator проверяет арифметику/refs. Oracle0.5/null/mixed/synonyms; partial error входит в top, не в average.

Review.state меняет data_revision/stale, comment-only нет. can_retry только finalized+fresh failed+declared safe, тот же snapshot/новый Job. can_refresh только finalized+stale и terminal либо гарантированно неотправленный queued/blocked без in-flight/unknown. Последний supersede атомарно: освобождение только safe unsent reserve, новый snapshot/Job. Running/unknown/retry_wait с возможной отправкой нельзя обходить refresh. Claim/refresh используют один guard, проигравший 409+GET. Перед первым POST stale snapshot не dispatch; уже отправленный может сохраниться stale, late не подменяет выбранный новый. GET не запускает LLM.

**Приемка:** PROC-C21/C22/C25/C26/C30–C32. **DoD:** полный worker/API cycle в PG, failure/retry/refresh/history; аналитика закончена к 17, mock не выдается за live.

## PROC-10 – Events/server audit; B3

**Цель:** R49–R52/R76/R77; A20–A22. **Вход:** PROC-01/02, shared Event, app/staff emits. **Файлы:** `events/{receiver,audit,outbox}.py`, events router/tests.

**Действия:** batch1..100, actor+event ID dedupe, тот же payload accepted, измененный 409, foreign ref атомарный 404. Actor/role/received_at серверные, контекст проверяется. Server mutation/attempt/funds/finalize/staff read пишутся commit/outbox с ID/реальной ролью, не повторами HTTP; staff не teacher usage. Не логировать password/cookie/Base64/prompt/raw response/comment. Нет dashboard, таймера письма или рекламы. Потеря client events не отменяет доменную работу. **Приемка:** PROC-C23/C24/C29. **DoD:** путь восстанавливается по ID, дубли не увеличивают счетчики, приблизительность/роль различимы, negative log scan PASS.

## PROC-11 – Routes и полный API smoke; B3

**Цель:** независимость ядра от UI, A01–A05/A07–A25 в своей области. **Вход:** PROC-01–10, app hooks. **Файлы:** processing/events routers, tests/processing+analytics. Свои operationId: submitBundle/retryBundle/skipBundle/skipTask/getJob/beginCompletion/finalizeCheck/getSummary/getSummaryHistory/refreshSummary/retrySummary/ingestEvents; CRUD/Bundle history HTTP application, staff HTTP release.

**Действия/DoD:** runtime request/response schema, Origin/session/headers, точные 202/200/409; не давать legacy analyze/register/admin/quota обхода. Настоящий ASGI+PG+worker fixture smoke: login→Check/Notebook/photo→submit/replay→Report/review→begin→finalize/replay→отдельная summary; failed+retry; смена state+stale+refresh; late old. Machine report с mode/commit/cases/HTTP/DB assertions. Никакого static success вместо ядра. **Приемка:** PROC-C03–C32, полный путь PROC-C32 без зависимости от UI.

## PROC-12 – Исправления/preflight/передача; B4 до 18

**Цель:** воспроизводимая локальная сборка R85, все свои Axx. **Вход:** PROC-01–11 закончены к 17. **Файлы:** свои код/тесты и четыре processing MD; чужие main/Compose не менять.

17–18: исправить дефекты с negative tests, повторить shared/source/backend/PG smoke; записать реальный commit/миграции/импорты/CLI ports/env names/fixture mode/диагностику unknown в HANDOFF. **Приемка:** повтор PROC-C32 на передаваемом commit плюс затронутые PROC-C01–PROC-C31; отчет C32 – обязательное доказательство B4. Указать pass/fail/not_run по case, реальные/mock отдельно. Передать полное ядро и аналитику, без планового дописывания вечером. Doc-impact/preflight по skills, push только отдельным запросом. **DoD:** ready только с кодовым commit и выполненным API доказательством, не по наличию ТЗ.
