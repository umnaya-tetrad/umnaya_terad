# Приемка processing

19.11.2026. **Тесты runtime требуется создать; ни один PROC-Cxx пока не выполнен на приложении.** Уже существующий offline gate описан внизу. Источник assertions – [shared v1](../shared/README.md), [API](../shared/API_CONTRACT.md), [формулы](../../SUMMARY_METRICS.md), [A01–A25](../../TRIAL_AND_ACCEPTANCE.md). Endpoint/DTO не копировать в другую схему: использовать operationId/OpenAPI и валидатор shared.

## Общий стенд и исполняемые команды

Создать `app/tests/pilot/domain/test_proc_contract.py`, `processing/test_proc_contract.py`, `analytics/test_proc_contract.py`, `events/test_proc_contract.py` и общие test fixtures. Каждый случай ниже имеет точный test-node. Одинаковое имя файла допустимо, pytest должен импортировать пакеты/уникальные пути без коллизий.

До запуска application предоставляет Compose services backend/worker/postgres, pool/settings/hooks и ранний seed. **Создать** следующий интерфейс команд из корня репозитория; локальный test profile задает `PILOT_TRANSPORT=fixture` до запуска backend/worker и не берет transport из наличия ключа:

```powershell
docker compose -f compose.yaml exec -T backend python -m pilot.domain.migrate
docker compose -f compose.yaml exec -T backend python -m pilot.operations.create_fixture_accounts
docker compose -f compose.yaml exec -T worker python -m pilot.processing.worker --healthcheck
docker compose -f compose.yaml exec -T backend python -m pytest tests/pilot/domain tests/pilot/processing tests/pilot/analytics tests/pilot/events -q
```

Для **каждого** PROC-Cnn ниже команда из корня имеет точную форму: `docker compose -f compose.yaml exec -T backend python -m pytest <node> -q`, где `<node>` указан у случая целиком. Это команды будущей реализации, а не результат сегодняшнего запуска.

Тесты используют настоящую PostgreSQL16 с независимыми соединениями/транзакциями, не SQLite и не mock repository. `PILOT_TEST_DATABASE_URL` указывает изолированную БД с именем `pilot_test_*`; harness отказывается очищать обычную рабочую БД. Тестовые миграции применяются и туда. Синтетические T1/T2/staff создаются общим auth, credentials – из test profile без Git/вывода паролей. Полный HTTP цикл – настоящий ASGI с cookie/Origin, общими routers и DB; заглушка допустима только на границе провайдера/часов и fault injection. Process-restart cases действительно останавливают/запускают отдельный worker process на той же PG, не просто заново создают Python-объект. Для concurrency использовать barriers/две DB connections и проверять оба порядка, без надежды на sleep.

Test transport – явный `FixtureTransport`, spy считает POST и сохраняет их ID/kind, аварийный network guard запрещает настоящий адрес модели. Синтетический PNG64×64 из shared, JPEG/WebP/HEIC варианты производятся тестовыми codec fixtures; это не математическая фотография. Multi/continuation/mixed/checker responses – существующие разрешенные `ai/examples` и `api/fixtures`; аналитические expected outputs – четыре пары `shared/analytics/fixtures`. Полные реальные работы/production responses не нужны.

Общие точные проверки: все request/response проходят shared schemas; успешная domain mutation повышает Check.revision ровно по таблице API, возвращенная check_revision совпадает с DB; denied/replay/no-op не меняет revision. ErrorResponse имеет ожидаемый code и безопасный message/current_revision, без проверки случайной формулировки. ID создания сравниваются между HTTP и DB, а не с выдуманным статическим UUID. У каждого случая сохраняется отчет с node/commit/transport/HTTP statuses/DB assertions/provider POST count.

## PROC-C01 – Чистая миграция и upgrade; A01/A12/A23

**Node:** `tests/pilot/domain/test_proc_contract.py::test_proc_c01`.

**Вход:** две изолированные PG16: пустая и с source001–007, существующими synthetic users/sessions. **Действие:** migrate дважды, затем изменить локальную копию checksum уже примененного SQL и повторить runner.

**Ожидается:** оба первых запуска exit0, registry каждого SQL содержит один checksum, таблицы/ограничения PROC-01 существуют; второй запуск без новых SQL ничего не пересоздает, старые users/session hashes сохранены. Измененный примененный SQL – ненулевой exit, ни одной новой migration/потери данных. SQL tests отклоняют второй `(check_id,number)`, одинаковые version positions, `(job,ordinal)`, второй Report одного Job, повтор settlement. Backend startup не удаляет таблицы.

## PROC-C02 – B1 hooks и типы; A12/A19

**Node:** `tests/pilot/domain/test_proc_contract.py::test_proc_c02`.

**Вход:** fixture mode, мигрированная PG, shared generated types. **Действие:** импорт factory/access/auth/errors/mutations/queries, processing/events routers; application монтирует каждый ровно раз с /api; запустить отдельный worker и healthcheck, сравнить generated files.

**Ожидается:** ни сети, ни ключа для fixture не требуется; все публичные символы TASKS доступны. Путь /api/api/... отсутствует; нет повторных operationId. Types совпадают с shared output, drift-test падает после контролируемой правки временной копии. Worker сохраняет heartbeat в PG; health exit0 при живом lease, ненулевой после expiry/неработающей PG. Пауза обработки сама по себе health не ломает.

## PROC-C03 – Auth и изоляция; A01/A12/A20

**Node:** `tests/pilot/domain/test_proc_contract.py::test_proc_c03`.

T1/T2/staff через ensure_account. login200/session200 возвращают правильный user_id/teacher|staff; неверный пароль401/unauthenticated, revoked/expired session401. T1 создает Check201, T2 читает Check/фото/Job по ID –404/not_found; анонимный –401. Teacher на staff history –403/forbidden; staff login разрешен, mutation чужой teacher проверки не выполняется. Cookie HttpOnly/SameSite, Secure согласно окружению, неверный Origin mutating403; нет register endpoint/анонимного legacy analyze. Ensure повтор не сбрасывает пароль, смена роли через ensure409. Trusted reset_account_password отзывает все старые сессии только целевого аккаунта, сохраняет ID/данные и остальных пользователей; новый пароль работает, старый нет. В DB нет plaintext password/token, deny не меняет revision/ledger.

## PROC-C04 – Intent до revision, потерянный ответ; A13/A23

**Node:** `tests/pilot/domain/test_proc_contract.py::test_proc_c04`.

Непустой draft и revision r. submitBundle с ключом K фиксируется, HTTP response принудительно теряется после commit. Повтор того же K/payload/старого r возвращает **202 и тот же Mutation/Job**, sealed вход/Job/outbox/intent в единственном экземпляре. Worker может отправить максимум один POST. Тот же K с другим input payload –409/idempotency_conflict, ни новой версии, ни Job. Новый K со старым r –409/revision_conflict с текущей revision; GET/relogin не создают Job.

## PROC-C05 – Долговечность принятого входа; A12/A13

**Node:** `tests/pilot/processing/test_proc_contract.py::test_proc_c05`.

Submit202 до claim, закрыть клиент, остановить дочерние backend ASGI/worker процессы harness и поднять с теми же PG/storage. Не останавливать контейнер, в котором выполняется pytest. GET Check200 сохраняет sealed photo/order и тот же queued Job. Worker завершает его fixture Report, reload дает тот же current_input/Task IDs/reviews, один provider POST. Intent replay202 не создает вторую работу. Неподтвержденная оборванная upload не появляется как принятая Photo. Полный restart контейнеров отдельно независимо проверяет release.

## PROC-C06 – Два отзыва/guard; A07/A08/A09

**Node:** `tests/pilot/domain/test_proc_contract.py::test_proc_c06`.

Два клиента с r читают актуальную assessable Task. Первый saveReview confirmed200, revision r+1/data_revision+1. Второй с r –409/revision_conflict, сохраненный отзыв первого не потерян. С актуальным guard смена на system_error200 исключает математику; очистка/смена только comment200 увеличивает только revision. Review с analysis_id старого поколения –409/stale_analysis, ни изменения current review, ни запроса модели. Точный одинаковый no-op PUT не повышает revision.

## PROC-C07 – Форматы и durable storage; A02/A12/A22

**Node:** `tests/pilot/domain/test_proc_contract.py::test_proc_c07`.

JPEG, PNG64, WebP, HEIC/HEIF c EXIF orientation – uploadPhoto201 после сохранения original+normalized+DBlink; GET assets200 с верным normalized MIME/no-store, bytes декодируются и имеют правильную ориентацию. PDF/неподдерживаемый MIME415, битое объявленное фото 422, превышение размера 413; pixels/shortedge вне общей политики 422. Временный файл при отказе/конфликте не остается активным DBasset. Ни filename/path traversal, ни чужой ID не выдают файл. Пороговые значения берутся из единой общей конфигурации, без отдельного HTTP test override для PNG64.

## PROC-C08 – Порядок/draft/sealed; A04/A09/A14

**Node:** `tests/pilot/domain/test_proc_contract.py::test_proc_c08`.

Два фото draft, reorder200 меняет точный массив; повтор/неполная перестановка/чужой photo_id422 либо 404 согласно принадлежности, без изменения. Submit202 фиксирует этот порядок. PATCH/delete фото sealed входа 409/invalid_state. createInputVersion201 с photo_ids текущего входа создает replacement draft, старые reviews сохранены; discardDraft200 сохраняет current_input/reviews. Изменить draft композиционно upload→delete→reorder, после fault между шагами GET показывает реальный сохраненный draft, старый sealed неизменен.

## PROC-C09 – Четыре сценария страницы и validation; A03–A05/A18

**Node:** `tests/pilot/processing/test_proc_contract.py::test_proc_c09`.

В отдельных Bundle воспроизвести одну Task/одно фото, несколько Task/одно фото, одну Task/два фото, целую+начало+продолжение на двух фото. Число current Task равно 1/2/1/2 соответственно; continuation ссылается на[1,2], это не третья Task. Сохраняются condition/evidence<=4/first_error/raw rule/corrected_latex/completeness/detail_level. all_steps_correct+incomplete не становится ошибкой. Invalid photo index/evidence/first_error consistency переводят Job в failed/invalid_response, result/tasks не публикуются, авто retry0. Недостаток условия остается not_assessed/uncheckable, не first_error ученика.

## PROC-C10 – Новое выделение 2→3; A09/A14

**Node:** `tests/pilot/domain/test_proc_contract.py::test_proc_c10`.

BundleA с двумя confirmed Task, BundleB с одной confirmed. Создать replacement draftA201 – отзывы обоих сохранены. SubmitA202 атомарно делает active tasksA=[], архивирует старые reviews, current_input новый; B неизменен. Fixture publish трех Task: в A ровно 3 новых task_id/analysis_id, пересечение со старыми пусто, все review=null. Поздний Report старого Job/Attempt не изменяет current/data_revision. DBhistory содержит старый и новый runs, не 5 активных Task.

## PROC-C11 – Retry того же входа и tombstone; A09/A10/A15

**Node:** `tests/pilot/domain/test_proc_contract.py::test_proc_c11`.

Mixed Report на sealed input, один assessable confirmed, другой not_assessed; удалить assessable Task200, сохранить tombstone. Ручной retryBundle202 с can_retry=true создает новый Job для **того же input_id**, деактивирует весь старый набор, все новые UUID/review=null. После success staff BundleHistory200 имеет одну версию с двумя runs: разные job.id/result.id/tasks/reviews/deleted_task_ids. Дублировать старую публикацию: удаленный старый task_id не активируется. Новая сегментация может дать похожую математическую Task с новым ID, это не восстановление старой и не наследование отзыва.

## PROC-C12 – Mixed skip и false zero; A07/A10/A16/A17

**Node:** `tests/pilot/domain/test_proc_contract.py::test_proc_c12`.

Report.ok: одна confirmed first_error, соседняя not_assessed. Подтверждение not_assessed –409/invalid_state, без review; skipTask200 с актуальным analysis_id помечает только ее, соседняя confirmed сохраняется. Skip assessable409. Completion после begin разрешает финал; snapshot содержит обе Task, not_assessed с review_state=null. Итог partial=1, with/without=0, average=null, unassessed_tasks=1, в top только ID соседней confirmed first_error. Просмотр/skip не создают математического согласия.

## PROC-C13 – Shared photo и удаление последней Task; A15/A17

**Node:** `tests/pilot/domain/test_proc_contract.py::test_proc_c13`.

Две Task на одном фото. Delete одной 200 оставляет вторую, исходный Report и GET фото 200, ее review сохранен. Delete последней 200 дает tasks=[], но не falsezero: snapshot notebook empty=1/without_errors=0/average=null, unresolved_bundles=0 для успешного явно очищенного Report. Старый callback не восстанавливает Task. Удаление Notebook200 исключает потомков; номера 1,2, удалить 2, создать новую –201 с number3, не 2. Отмена UI-delete не вызывает API и DB неизменна (UI-часть проверяет application).

## PROC-C14 – Delete Check с queued/unknown; A15/A23

**Node:** `tests/pilot/domain/test_proc_contract.py::test_proc_c14`.

Параметры queued до dispatch и unknown после возможной отправки. DeleteCheck200 делает последующие Check/assets/Job чтения 404; queued не отправляется. В unknown вариант e Attempt+reserve остаются в ledger, поздний ответ учитывается только для сверки и не возвращает Check/Task. Intent replay удаления возвращает исходный 200, без повторного side effect. Доступ к техническому аудиту не дает HTTP восстановления.

## PROC-C15 – Claim/fencing двух workers; A11/A13/A19

**Node:** `tests/pilot/processing/test_proc_contract.py::test_proc_c15`.

Один queued Job, два отдельных worker process одновременно. Только один claim/Attempt/POST; второй не получает его. Искусственно состарить lease и сменить epoch до гарантированной отправки; stale worker не renew/settle/publish, возобновленный безопасный worker публикует ровно один набор. После возможного dispatch expired lease обрабатывается иначе – C17. PG global active slots не превышают 2 для обоих kind, process-local mutex недостаточен.

## PROC-C16 – Ровно один autoretry; A05/A11

**Node:** `tests/pilot/processing/test_proc_contract.py::test_proc_c16`.

Fixture доказанный transient failure→success дает 2Attempt/2POST/один Report; transient→transient дает failed после 2POST, третьего нет. Перезапуск между Attempt сохраняет счетчик. Invalid JSON, length, uncheckable, not_assessed, system_error review –0 авто retries. Новая Attempt имеет собственный reserve; count Task не увеличивается от попыток. Timeout после возможной отправки не относится к этому безопасному transient сценарю – C17.

## PROC-C17 – Lost provider response/restart/unknown; A11/A13/A23

**Node:** `tests/pilot/processing/test_proc_contract.py::test_proc_c17`.

Provider spy принимает POST, response теряется; второй параметр теста убивает worker process после dispatch до settlement. Перезапустить с той же PG. Job: unknown/provider_outcome_unknown/can_retry=false, Attempt unknown, hold в точности прежний, provider POST count=1 после recovery, polling и повторного submit с ключом K. Нет освобождения резерва, автоматического второго POST или нулевой стоимости. Для доказанно неотправленной Attempt отдельный параметр допускает безопасное восстановление; один timeout не доказывает отсутствие отправки.

## PROC-C18 – Skip unknown и поздний результат; A10/A16/A17/A23

**Node:** `tests/pilot/processing/test_proc_contract.py::test_proc_c18`.

Из C17 выполнить skipBundle200: current Job cancelled/skipped, Bundle.skipped=true; Attempt unknown и hold неизменны. Begin200 и finalize202 разрешены при остальных разрешенных данных. Snapshot unresolved_bundles=1 даже при tasks=[], summary partial=1/average=null/without_errors=0. Доставить поздний успешный ответ: Report/Task в current не появляются, выбранная summary неизменна; деньги обрабатываются только подтвержденной сверкой один раз. Нового provider POST нет.

## PROC-C19 – Builder и transport contract; A05/A18/A22/A25

**Node:** `tests/pilot/processing/test_proc_contract.py::test_proc_c19`.

Собрать request обоих kind на spy transport. Checker system hash равен frozen, порядок image parts/high/photo indices и strict schema сохранены, один POST. Analytics использует другой prompt и snapshot JSON, image parts=0, schema class-summary/1; frozen analyze не вызывается вместо нового builder. Safe metadata обоих вызовов не содержит ключа/Base64/full report; материалы payload хранятся только приватно. PILOT_TRANSPORT default polza без ключа отказывает, POST0; явно выбранный fixture работает без ключа, настоящий адрес запрещен. Реальный Settings принимает timeout300/min edge32; PNG64 не обходит валидацию. Дополнительно source Settings со старыми 75/180/240 не остается скрытым вторым ограничителем.

## PROC-C20 – Два этапа и блокеры; A14/A16

**Node:** `tests/pilot/domain/test_proc_contract.py::test_proc_c20`.

Прямой finalize из editing409/invalid_state, snapshots и analytics Jobs=0. BeginCompletion200 переводит в review без LLM. Поочередно проверить pending Job, непустой draft, assessable без review, unresolved not_assessed, failed без skip: can_finalize=false/finalize409 completion_blocked, analytics=0. Пустая Check также блокирована. Red review и skip разрешают только свои блокеры. После всех разрешений finalize с актуальным guard202 создает ровно 1snapshot/1AnalyticsJob/outbox, phase=finalized. Изменение состава/checker retry/skip после финала 409 invalid_state; review/comment существующей assessable Task200, deleteCheck200.

## PROC-C21 – Finalize против upload/review/publish; A09/A14/A16

**Node:** `tests/pilot/domain/test_proc_contract.py::test_proc_c21`.

Три подслучая, PG barriers и два независимых соединения, оба порядка. Upload в пустой draft побеждает: upload201/revision+1, finalize с r409 revision_conflict, непустой draft учтен. Finalize побеждает:202/phase finalized, upload с r409 revision_conflict; с последним guard upload409 invalid_state. Review побеждает 200→finalize с r409; finalize побеждает 202→review с r409, повтор review с новым guard200/stale, состав не открывается. Пока checker pending, finalize, получивший lock первым, дает 409 completion_blocked; publish первым повышает revision, finalize со старым r409 revision_conflict. Нет snapshot с частично записанным Report или новой Task без review; analytics Job не появляется от заблокированного finalize.

## PROC-C22 – Двойной финал и snapshot; A08/A16/A17

**Node:** `tests/pilot/domain/test_proc_contract.py::test_proc_c22`.

Два клиента finalize одного r: ровно один 202, другой 409; replay победившего K дает тот же 202/Job. В PG1initial snapshot/1Job. Snapshot валиден по input.schema, содержит только current generation/red/not_assessed; нет comment/photo/title/number/old IDs. Comment-only PUT200 повышает revision, не data_revision/stale; смена state PUT200 повышает оба и ставит stale. Десять GET summary не меняют Job/POST count.

## PROC-C23 – Client events/server dedupe; A21/A22

**Node:** `tests/pilot/events/test_proc_contract.py::test_proc_c23`.

Batch Event202 содержит accepted_ids всех сохраненных ID; точный replay202 дает тот же список и одну DB строку на ID. Другой payload с тем же ID409 idempotency_conflict, чужой entity в batch404 без частичного приема,101event422. Actor/role/received_at не принимаются от клиента, лишние поля 422. Domain commit создает один server audit/outbox fact, HTTP повтор не удваивает его. Сбой доставки client event не откатывает отдельно успешный submit/review.

## PROC-C24 – Staff queries/audit и безопасные логи; A20–A22

**Node:** `tests/pilot/domain/test_proc_contract.py::test_proc_c24`.

Staff query read/materials/history200 с реальным actor=staff; точный owner_login возвращает только его checks, History runs не смешивают поколения input. Teacher history403, чужой teacher asset404. Read не изменяет revision/review, но дает staff audit fact с реальной ролью; он не учитывается как teacher usage. Negative scan синтетических маркеров password/cookie/key/Base64/raw report/comment не находит их в общих логах; приватный artifact может хранить материал по ID. Нет ФИО, внешней регистрации или dashboard.

## PROC-C25 – Analytics oracle/refs/смыслы; A17/A18

**Node:** `tests/pilot/analytics/test_proc_contract.py::test_proc_c25`.

Тестовая DB factory создает current graph с ID/Task четырех shared analytics input fixtures; сам snapshot собирает сервер. Отдельный LLM fixture возвращает заданный result, worker валидирует JSON и сохраняет, summary200 succeeded. Oracle: total4/with_errors1/without_errors1/partial1/empty1, average0.5, incomplete1, disputed1, unassessed0; top содержит два confirmed ID, один из partial. Zero-denominator average=null. Mixed сохраняет partial/unassessed. Synonyms объединяет одинаковый смысл, независимые правила не слиты; проверять группы ID и смысл правила, а не один вердикт. Invalid count/average0 вместо null/чужой red ID/дубли top/4 группы/invalid JSON: Job failed/invalid_response, result не опубликован, auto retry0. Validator не генерирует исправленный итог.

## PROC-C26 – Fresh retry/stale/late summary; A08/A16/A17/A23

**Node:** `tests/pilot/analytics/test_proc_contract.py::test_proc_c26`.

Finalized fresh failed с доказанно безопасным исходом: can_retry=true, retrySummary202 создает новый Job того же snapshot ID, повтор K дает тот же Job. Смена state ставит stale=true/can_retry=false; retry409 invalid_state. Running/unknown stale: can_refresh=false, refresh409 invalid_state, новых POST0. Comment-only не делает stale. Поздний результат старого Job сохраняется в history, не в selected нового. Свежий succeeded повторно retry/refresh409; GET не платный. Terminal stale с актуальным guard/can_refresh=true→refresh202 с новым snapshot/Job, старый result остается историей.

## PROC-C27 – Два worker на последние средства, оба kind; A19/A23

**Node:** `tests/pilot/processing/test_proc_contract.py::test_proc_c27`.

Изолированный fixture wallet10RUB, request bound каждого 6RUB. Одновременно page_check/class_analytics через две DB connections. Ровно один reserve6/dispatch, другой blocked/funds_unavailable без POST, available4/held6, отрицательных значений нет. Topup5 с evidence/request ID дает balance15/held6/available9, повтор не дублирует пополнение. Разрешить второй dispatch→held12/available3. Дублировать settlement одной Attempt: ровно один ledger debit и одно снятие резерва. Test pricing задан явно; polza не использует эти 6 или 400 как реальную цену/баланс.

## PROC-C28 – Pause/resume без HTTP admin; A23/A24

**Node:** `tests/pilot/processing/test_proc_contract.py::test_proc_c28`.

Два queued Job разных kind и одна running Attempt. Trusted set_processing_paused(true) останавливает новые dispatch, POST count не растет, reason=service_paused; running может завершить settlement. Готовые Check/фото/review доступны, worker health жив. Red review не изменяет pause. Resume продолжает исходные Job без новых идентичностей, повтор операции no-op. HTTP admin не появляется, staff/teacher cookie не вызывает control.

## PROC-C29 – Funding/reconciliation с доказательствами; A22–A24

**Node:** `tests/pilot/processing/test_proc_contract.py::test_proc_c29`.

Polza без проверенного initialize/pricing profile не dispatch и не seed400. Trusted fund_wallet initialize с проверенным остатком выполняется один раз, topup>0 с immutable evidence/request ID; replay no-op, иной payload409, отрицательный/NaN amount422, повтор initialize409. Fixture ledger изолирован и не переходит в polza. Для unknown Attempt reconcile без evidence/конечной стоимости settled отказывает без release; rejected с подтверждением отсутствия списания освобождает ровно hold; settled с actual cost дает один debit/settlement. Повтор same evidence возвращает changed=false, противоречащий 409. Полное evidence и секреты не появляются в общих логах; cancel Job не был доказательством rejected.

## PROC-C30 – Масштаб/параллельность без teacher quota; A19/A25

**Node:** `tests/pilot/processing/test_proc_contract.py::test_proc_c30`.

T1/T2 по 30 тетрадей и по 3Task в Bundle, один Report на Bundle, fixture wallet с достаточным резервом. Два worker, детерминированно перемешанная готовность, часть клиентов закрыта. Ровно 60 тетрадей/60currentReport/180activeTask, по 90 научителя; нет смешивания владельцев или лимита 3/20. Максимум 2dispatch одновременно на общую очередь двух kind. Нагрузка использует только специальный fixture, не проверяет live скорость/качество или школьную апробацию.

## PROC-C31 – Stale blocked refresh против claim; A16/A17/A23

**Node:** `tests/pilot/analytics/test_proc_contract.py::test_proc_c31`.

Finalized stale queued/blocked без отправленной Attempt: can_refresh=true. Refresh202 в той же транзакции ставит old Job superseded/replaced, создает new snapshot ID/new Job, история старого сохранена; безопасный unsent reserve освобождается один раз. Старый snapshot не получает POST. Barriers: refresh первым→старый claim не получает dispatch; claim/dispatch intent первым→revision растет, refresh со старым r409 revision_conflict, GET показывает can_refresh=false при running. Unknown/in-flight hold никогда не освобождается через refresh. Проверить все 14 условий shared summary-guards в DB с настоящим внутренним Attempt state, не выводить разрешение из одного enum.

## PROC-C32 – Полный API-only handoff smoke; A01–A05/A07–A25

**Node:** `tests/pilot/analytics/test_proc_contract.py::test_proc_c32`.

Настоящий ASGI+PG+worker fixture без UI: login200→createCheck/Notebook/Bundle/upload201→submit202→GET job/check до succeeded→review каждой assessable200/skip not_assessed200→begin200→finalize202/replay того же Job→analytics queued/running/succeeded→GET summary200 с сохраненным result. Затем failed analytics+fresh retry и смена state+stale+can_refresh+refresh; доставить late old, проверить ранние staff ACL через getBundleHistory/getSummaryHistory/getPhoto владельцев app/processing. listStaffChecks/getStaffCheck и полный staff UI принадлежат REL-04 после B4 и не являются входом PROC-C32 до 17:00. Все ответы валидны по schema; проверить PG Job/Attempt/Report/snapshot/result/intent/outbox/ledger counts и fixture mode. В отчете нет непроверенного TODO по аналитике. До 18 передать файл результатов/commit/команду интегратору.

## Существующий offline gate и границы

Из корня `python project-context/pilot/planning/shared/check_shared.py` проверяет frozen hashes, OpenAPI/DTO/fixtures, analytics validator и UX strings, без приложения/БД/сети. Он не заменяет PROC-C01–C32. `python scripts/check_context.py` и обе команды git diff --check проверяют структуру/пробелы, не продуктовый runtime.

После реализации дополнительно воспроизвести исходные backend tests из pinned source с учетом явных замен старых quota/register сценариев; сохранить список измененных ожиданий, не скрывать регрессию удалением тестов. Live smoke, Android/iPhone, внешний сервер/HTTPS и самостоятельная апробация отдельно от этой mock/PG-приемки; без их выполнения ставить not_run. В HANDOFF записать точные команды, commit, транспорт, результаты и ограничения, а не копировать прежний отчет как новый прогон.
