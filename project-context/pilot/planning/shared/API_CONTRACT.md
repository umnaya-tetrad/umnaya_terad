# Общий API и данные SmartNote

Версия **1.0.0**, 19.11.2026. Инженерный контракт для независимой реализации приложения, обработки и локального выпуска. Это спецификация и проверенные офлайн артефакты, а не реализованный HTTP-сервер. Основание – R01–R86, [продукт](../../PRODUCT.md), [поток](../../TEACHER_FLOW.md), [формулы](../../SUMMARY_METRICS.md), [AI-интеграция](../../AI_INTEGRATION.md). Технические неоднозначности [черновика](../CONTRACT_DRAFT.md) закрыты правилами ниже; новые продуктовые R-ID не присваиваются.

Нормативные формы: [OpenAPI 3.1 JSON](api/openapi.json), [JSON Schema 2020-12](api/schemas/domain.schema.json), [переносимые TypeScript](api/contracts.ts) и [Python TypedDict](api/contracts.py), [HTTP fixtures](api/fixtures/http.json), [состояния сценариев](api/fixtures/lifecycle.json). Типы не заменяют runtime-валидацию. Команды и границы проверки – [api/README](api/README.md). Несовместимые самостоятельные переименования маршрутов, enum и полей запрещены; общий контракт изменяет владелец processing с синхронизацией всех потребителей по [границам модулей](MODULE_BOUNDARIES.md).

## Минимальные сущности

`Check → Notebook → Bundle → InputVersion → Job → BundleReport → TaskAnalysis`.

Check – одна именованная проверка; название задается только при создании. Notebook – условная работа без ФИО, не постоянный ученик. POST Notebook не принимает тело; сервер назначает number от 1, UI форматирует «Тетрадь N», увеличивая внутренний счетчик Check в той же транзакции. Номер монотонный и не переиспользуется после удаления; переименования проверки/тетради нет. Bundle – логический комплект совместных фото одной тетради. Отдельные Bundle независимы: продолжение надо включить до отправки либо явно заменить прежний вход. InputVersion содержит упорядоченные ссылки на приватные PhotoAsset; файл не хранит собственный глобальный порядковый номер. После submit версия sealed и неизменяема. Фото можно повторно использовать в replacement draft только из последней текущей sealed версии того же Bundle. Удаление ссылки в draft не меняет прежнюю sealed версию.

Bundle имеет не более одного draft и одного current_input. При создании Bundle сервер сразу создает пустой draft; его ID клиент получает через GET Check. Submit убирает draft и назначает current_input; новый пустой комплект для следующих страниц создается отдельным POST notebooks/{id}/bundles. Это позволяет снимать следующий комплект, пока прежний работает. POST bundles/{id}/versions создает replacement draft для текущего Bundle, не новый самостоятельный Bundle. Второй draft при уже существующем дает 409. Отмена replacement draft **не снимает** прежние отзывы. Снятие происходит только при submit или ручном retry.

BundleReport – неизменяемый полный Report `page-check/1.2`. Его JSON сохраняется отдельно от отзывов и удаления задач. TaskAnalysis оборачивает один исходный Task: серверные task_id и analysis_id, review либо null, skipped. `analysis.task_id` модели локален внутри Report и никогда не становится первичным ключом БД. Отдельного устойчивого объекта математической задачи между повторными выделениями нет. Ключ поколения – актуальный Job.id и опубликованный BundleReport.id.

## Поля и конкретные потребители

Все объектные DTO закрыты `additionalProperties:false`. Нет confidence, обязательных rule_id, класса, темы, варианта, оценок, координат фото или дублирующего числа задач. Все поля DTO обязательны; отсутствие состояния выражено null, а не пропущенным ключом. UUID – серверные идентификаторы; даты UTC RFC3339.

| DTO и поля | Кто использует и зачем |
|---|---|
| Login.login/password; Session.user_id/role | Auth принимает выданные реквизиты; router выбирает teacher/staff. Пароль никогда не возвращается и не логируется. Общий login доступен обеим ролям |
| CheckListItem.id/title/phase/revision/created_at | История учителя, переход к проверке, режим экрана, защита изменений и порядок истории |
| Check.data_revision/notebooks/completion/summary | Восстановление всего текущего состояния и polling без повторной отправки; версия основания аналитики отдельно от общего guard |
| Notebook.id/number/bundles | Навигация условных тетрадей и принадлежность комплектов; number не попадает в LLM-сводку |
| Bundle.id/draft/current_input/job/result/tasks/skipped | Съемка, статус фоновой работы, только актуальные разборы и явное разрешение неудачного входа |
| InputVersion.id/state/photos; Photo.id/media_type | Редактор draft, submit точного входа, порядок photo_index от 1 и приватная выдача/декодирование фото |
| VersionCreate.photo_ids; PhotoOrder.photo_ids; Submit.input_version_id | Явное копирование входа, точная перестановка всех фото текущего draft и отправка нужной версии. Перестановка не добавляет/удаляет фото |
| BundleReport.id/input_version_id/report | Worker, поддержка и UI сопоставляют неизмененный отчет с входом; полный JSON остается историей при удалении одной задачи |
| TaskAnalysis.task_id/analysis_id/analysis/review/skipped | Карточка, отзыв, удаление, snapshot. analysis – точный frozen Task, review – педагогическая оценка ИИ; skipped разрешает только not_assessed |
| ReviewWrite.analysis_id/state/comment; Review.state/comment | PUT относится только к актуальному анализу. confirmed – согласие с ИИ, system_error – красная отметка. comment необязателен по смыслу, пустая строка очищает |
| AnalysisTarget.analysis_id; InputTarget.input_version_id | Skip отдельного not_assessed; retry/skip точного текущего входа, без случайного действия над новым поколением |
| Job.id/kind/input_id/state/reason/can_retry | Polling, разделение checker/analytics, привязка входа, безопасное объяснение и серверное разрешение повтора. Подробные Attempt/usage/расходы – серверные записи, не лишние teacher DTO |
| Completion.pending_jobs/unreviewed_tasks/unresolved_tasks/unresolved_bundles/unsent_drafts/can_finalize | Первый этап завершения показывает конкретные оставшиеся действия; окончательное согласие не создает отзывы вместо учителя |
| Summary.state/stale/snapshot_id/job_id/data_revision/can_retry/can_refresh/result | Выбранный сохраненный запуск, его актуальность и вычисленные сервером разрешения двух разных действий. UI использует can_refresh, а не один stale; result – JSON отдельного LLM. Нет дополнительного paid-запроса при чтении |
| Mutation.check_id/check_revision/entity_id/job | Общий ответ на изменение: обновить guard, найти созданную сущность, при обработке получить Job. entity_id null для самой проверки, ее завершения и операций summary; иначе ID измененного объекта |
| Checks.items/next_cursor | История с курсором; limit 1–100, по умолчанию 30. Порядок created_at desc,id desc |
| Owner.user_id/login; StaffChecks.items/next_cursor; StaffCheck.owner/check | Поддержка находит учителя по точному выданному owner_login, затем проверку. Отдельного каталога людей/ФИО нет |
| HistoryVersion.input/runs; HistoryRun.job/result/tasks/deleted_task_ids; BundleHistory.bundle_id/versions | Только staff анализирует прежние версии. Каждый runs[] связан со своим поколением по job.id и сохраняет именно его Report, отзывы и tombstones; несколько успешных retry одного input не теряют историю. current UI учителя не зависит от этой истории |
| SummaryHistory.items; SummaryHistoryItem.created_at/summary | Только staff сверяет сохраненные запуски, snapshot и причины устаревания. У учителя история проверок и текущая выбранная сводка |
| Event.id/session_id/occurred_at/name/check_id/entity_id; Events.events; EventsAccepted.accepted_ids | Приблизительное время просмотра/съемки и дедупликация клиентских наблюдений. Никакого произвольного payload, комментариев, фото или сырых ответов в событии |
| ErrorResponse.error; Error.code/message/current_revision | Клиент различает отказ доступа, конфликт и блокер, показывает безопасное объяснение и перечитывает актуальную проверку |

Каждое frozen поле Task/Report потребляет renderer и snapshot по [исходному контракту](../../ai/response-schema-v1.2.json); они не переопределяются этой оберткой. Input/output аналитики – [схема snapshot](analytics/input.schema.json), [схема результата](analytics/result.schema.json), [промпт](analytics/prompt-v1.txt). Для среднего знаменатель выводится из with_errors+without_errors; частота топа из длины task_ids, поэтому дублирующих полей нет.

## HTTP-поверхность

Все пути имеют префикс `/api`. Полные формы и коды – в OpenAPI. Успешное изменение возвращает Mutation; `201` для создания/сохранения фото, `202` для принятой фоновой работы, прочие изменения `200`. Logout – `204`. Списки и чтение `200`. Ни один GET не создает Job, не меняет отзыв и не списывает деньги.

| Группа | Маршруты и потребитель |
|---|---|
| Вход | POST auth/login; GET auth/session; POST auth/logout – приложение обеих ролей |
| История/проверка | GET/POST checks; GET/DELETE checks/{check_id} – только владелец teacher; title вводится один раз при создании |
| Тетради | POST checks/{check_id}/notebooks без тела; DELETE notebooks/{notebook_id} – условная тетрадь с серверным монотонным number; UI форматирует «Тетрадь N» |
| Комплекты/версии | POST notebooks/{notebook_id}/bundles; DELETE bundles/{bundle_id}; POST bundles/{bundle_id}/versions – съемка нового независимого комплекта либо замена существующего |
| Фото/draft | POST input-versions/{input_version_id}/photos; PATCH/DELETE input-versions/{input_version_id}; DELETE input-versions/{input_version_id}/photos/{photo_id} – только текущий draft |
| Приватное фото | GET assets/{photo_id} – владелец или staff, без публичного static URL; каждый доступ проверяется и staff-доступ аудируется |
| Обработка | POST bundles/{bundle_id}/submit, /retry, /skip; GET jobs/{job_id} – точный вход и долговечный фон; статус доступен владельцу/staff |
| Отзыв/задача | PUT tasks/{task_id}/review; POST tasks/{task_id}/skip; DELETE tasks/{task_id} – независимые оценки/пропуск/удаление результатов общего Report |
| Завершение | POST checks/{check_id}/begin-completion; POST checks/{check_id}/finalize – два разных этапа |
| Сводка | GET checks/{check_id}/summary; POST checks/{check_id}/summary/refresh, /retry – только владелец; платный запуск только явной мутацией |
| Поддержка | GET staff/checks?owner_login=...; GET staff/checks/{check_id}; GET bundles/{bundle_id}/history; GET checks/{check_id}/summary/history – staff, только чтение |
| Наблюдения | POST events – обе роли, события staff не считаются работой учителя |

Multipart содержит единственный part `file`. Сервер надежно сохраняет оригинал приватно, проверяет декодирование, применяет EXIF orientation, создает нормализованный JPEG/PNG/WebP и лишь затем подтверждает прием. Вход JPEG/PNG/WebP/HEIC/HEIF; HEIC конвертирует сервер, несовместимый/битый файл дает 415/422 с действием переснять или выбрать другое фото. Нельзя отмечать неподтвержденную загрузку принятой. Единая техническая граница upload и нормализованного входа worker — 8 000 000 байт, 36 000 000 пикселей, короткая сторона от32; это не пользовательская квота задач. JPEG/PNG/WebP без необходимого изменения ориентации не перекодируются. Если обязательная конвертация HEIC/HEIF/EXIF дает вход вне этих границ, сервер возвращает 422 до принятия, а не молча уменьшает разрешение или запускает заведомо невалидный Job. Приватный GET возвращает нормализованное фото, Cache-Control: private,no-store; оригинал нужен поддержке/хранению и не публикуется отдельным URL. При upload вне транзакции временный объект сначала сохраняется, затем под guard фиксируется ссылка; при конфликте ссылка не появляется, временный объект убирается.

У обеих кнопок отправки одинаковый submit. После ответа 202 клиент остается в тетради либо создает следующую, не дожидаясь LLM. Сетевой timeout не означает отказ сервера: клиент повторяет **то же намерение с тем же ключом**, затем перечитывает Check. Не отправляет каждую выделенную Task отдельно.

## Revision и идемпотентность

Check.revision – единственный общий конкурентный guard, в GET Check возвращается также `ETag: "12"`. **Все domain-мутации существующей проверки** требуют `If-Match: "12"` и `Idempotency-Key: UUID`, включая загрузку, удаление, отзыв, версии, submit, retry, begin-completion, finalize и analytics refresh/retry. Отдельного expected_review_revision нет: один guard предотвращает гонки отзыва с финалом/заменой. Идемпотентное создание Check требует только Idempotency-Key.

В PostgreSQL 16 операция блокирует родительскую Check строку, проверяет владельца/phase/версию и выполняет все побочные изменения одной транзакцией. Worker использует тот же guard и порядок блокировок: Check → Bundle → InputVersion/Job → TaskAnalysis. Finalize блокирует Check и читает полное текущее состояние в той же транзакции. Worker, upload и review не могут вклиниться между проверкой completion и фиксацией snapshot. Устаревшее клиентское can_finalize не разрешение.

До каждого возможного внешнего вызова worker повторно под этим guard проверяет живую Check, current input/Job/Attempt или выбранный snapshot/Job и его data_revision, затем фиксирует dispatch/резерв. Устаревший еще не отправленный snapshot не запускается платно: остается доступен явный refresh. Review/refresh, пришедшие после зафиксированного dispatch, не делают уже начатую Attempt бесплатной и не разрешают второй вызов до ее исхода/сверки. Долговечное разрешение отправки и изменение текущего Job сериализованы, а не проверяются независимыми GET перед LLM.

| Действие | Check.revision | Check.data_revision |
|---|---|---|
| Создание Check | 0 | 0 |
| Create/edit/reorder/discard draft; upload/delete draft-photo; создание пустого Bundle | +1 | без изменения: это еще не основание расчета |
| Создание/удаление Notebook; удаление Bundle/Task; submit/ручной retry с деактивацией поколения | +1 | +1 |
| Публикация нового актуального Report/tasks worker | +1 | +1 |
| Новый отзыв или смена review.state; skip Task/Bundle | +1 | +1 |
| Изменение только review.comment | +1 | без изменения |
| Начало завершения, финал, запуск/прогресс/завершение AnalyticsJob; публичный прогресс checker Job | +1 | без изменения, кроме публикации Report |
| Удаление всей Check | +1 и deleted | +1; больше не доступна |
| Точный повтор/no-op PUT, GET, Event, staff-аудит, внутренняя бухгалтерская запись без смены Job | без изменения | без изменения |

Идемпотентность сохраняется транзакционно по `(actor_id, method, canonical_path, Idempotency-Key)` на весь срок существования проверки, включая успешный ответ ее удаления. Сохраняются canonical payload/hash и исходный status/body. Для multipart hash считается по байтам входного файла и версии; If-Match не входит в payload hash. Сначала аутентификация и поиск уже принятого намерения, **затем** If-Match для нового намерения. Тот же ключ/действие/payload возвращает прежний ответ, даже если guard уже вырос. Другой payload дает 409 idempotency_conflict. Непринятый из-за 409/422 запрос не резервирует ключ навсегда: после перечитывания исправленное намерение получает новый ключ. Уникальная запись ключа и mutation/job фиксируются вместе; ответ не отправляется до commit. Это защита приема внутри приложения, не exactly-once внешнего провайдера.

Коды: 401 нет сессии; чужой ID/удаленное – 404 без раскрытия существования; teacher на staff-маршруте – 403; конфликт revision/state/analysis/idempotency – 409; битый/неполный вход – 422, слишком большой файл – 413, формат – 415. Ошибка имеет безопасный message и current_revision либо null. Auth использует серверную HttpOnly/SameSite=Lax cookie, Secure в HTTPS; все mutating запросы проверяют exact Origin приложения, login/logout тоже, запрос без допустимого Origin не выполняет изменение. Новый API регистрации отсутствует.

## Поколения, повторное выделение и удаление

1. Sealed InputVersion никогда не редактируется. Замена создает draft с новым UUID. Только его submit атомарно делает current_input новой версией, архивирует прежние активные TaskAnalysis/отзывы, очищает current result/tasks, создает один новый Job. Пока Job идет, старый вывод доступен только staff-истории и не участвует в completion/summary.
2. Ручной retry того же sealed входа создает новый Job и так же атомарно деактивирует все прежнее поколение. Разрешен до финала при failed, uncheckable/пустом Report либо Report.ok с not_assessed; server can_retry обязателен. Для mixed UI явно предупреждает о повторе **всего комплекта** и снятии соседних отзывов. Не запускается из-за красной отметки автоматически. Для исправления фото используется replacement draft.
3. При публикации каждому выделенному результату назначаются **новые** task_id/analysis_id. Они не сопоставляются по формуле, номеру, позиции или task_id модели. Было две задачи, стало три – активны ровно три новые, все без отзывов; не пять. Стабильный идентификатор математики между сегментациями не обещается. Число тетрадей от retry не растет.
4. Worker публикует один раз только если Check/Notebook/Bundle не deleted, current_input совпадает, current Job совпадает и еще не опубликован. Автоповтор временной ошибки – новая Attempt того же Job; worker принимает ответ только текущей Attempt. Старая Attempt/Job/версия остается историей, не заменяет новое и не возвращает удаленное.
5. Удаление Task ставит tombstone `(generation_id, task_id)`, убирает только эту активную Task, сохраняет исходный Report и отзывы в истории. Повтор доставки публикации того же Job не пересоздает задачи. Явно запрошенная новая версия/ручной retry создает полностью новое поколение с новыми ID: может заново выделить тот же участок страницы, но не «восстанавливает» старую Task и не наследует отзыв. Именно этот ограниченный смысл проверяется fixture two-to-three; запрет математически похожего нового результата через все будущие сегментации не вводится.
6. Удаление Task не удаляет общее фото соседней задачи. Фото sealed входа нельзя удалить поштучно: нужно заменить вход. DELETE Bundle удаляет комплект целиком; Notebook – потомков; Check – весь набор. Требуется подтверждение UI. Транзакционно запрещается новая публикация/старт работ потомков. Нет корзины/восстановления. Удаленные Check/Notebook/Bundle и их фото недоступны HTTP; технический аудит и резерв неизвестной попытки сохраняются. Физическая очистка отдельна от продуктового удаления и не восстанавливает доступ.

## Просмотр, пропуски и финал

phase: `editing → review → finalized`. Begin-completion переводит editing в review и возвращает Mutation; при повторе phase=review остается. Не закрывает состав и не создает аналитику. Все изменения до финала разрешены и пересчитывают completion; phase обратно в editing не требуется.

Assessable Task (`all_steps_correct`/`first_error_found`) обязана иметь review confirmed либо system_error. Красная отметка завершает оценку ИИ, но исключена из математического основания. not_assessed не получает ни фиктивного confirmed, ни красной математической отметки; POST task/skip с точным analysis_id разрешает только ее. Остальные задачи mixed Report остаются отдельно подтверждаемыми и могут войти в топ. Нечитаемость/нехватка условия берется из message/uncheckable_reason, не становится ошибкой ученика.

POST bundle/skip разрешает terminal failed/uncheckable/пустой Report, а также заблокированный/unknown вход. Для blocked/unknown Job становится cancelled с reason=skipped, новые старты/публикация подавлены. **Attempt с неизвестным внешним исходом и ее финансовый резерв остаются для сверки**; cancelled не означает бесплатный исход. Поздний ответ сохраняется для внутренней сверки, но не публикуется. Пропущенный вход остается в snapshot.unresolved_bundles; тетрадь частичная, даже при tasks=[]; ноль ошибок не выдумывается.

Completion считает активные, не пропущенные queued/running/retry_wait/blocked/unknown Jobs, assessable без review, not_assessed без skip, неразрешенные failed/uncheckable входы и непустые draft. Пустой draft не блокирует. Финал допустим только в review, при нулевых пяти счетчиках и наличии хотя бы одного активного sealed входа. Пустую проверку нельзя финализировать. Явно пропущенные входы разрешают финал, но не математическую полноту тетради.

Finalize одной транзакцией: проверяет guard/phase/completion, фиксирует состав, создает неизменяемый snapshot и один AnalyticsJob/outbox, ставит finalized. Прямой finalize из editing – 409. Двойной клик с тем же ключом возвращает тот же Job; иной ключ после финала не создает второй Job. Состав после финала запрещен, включая checker retry/skip/замену и удаление отдельных объектов. Сохраняются R46: PUT review с изменением state/comment по уже существующим assessable анализам, чтение и удаление Check целиком. Повторного открытия нет.

## Snapshot и аналитика

Snapshot `summary-input/1`: snapshot_id, check_id, data_revision, notebooks[{notebook_id, unresolved_bundles, tasks[{task_id, analysis_id, review_state, analysis}]}]. Все активные задачи текущего поколения включаются, включая красные и not_assessed, чтобы видеть частичность. Старые поколения, tombstones, фото, комментарии, title/number, Report.message исключены. Для active sealed Bundle без доступного пригодного Report, failed/unknown/skipped/uncheckable/пустого Report unresolved_bundles увеличивается на 1 даже при tasks=[]. Успешный Bundle, все задачи которого явно удалены, не создает unresolved; при отсутствии других задач тетрадь пустая. Дополнительный пустой draft не попадает в snapshot.

Только finalized запускает отдельный LLM по snapshot; checker-промпт не меняется. Числа и ссылки результата валидируются [analytics/validate.py](analytics/validate.py) строго по SUMMARY_METRICS; некорректный результат не чинится скрытым генератором и не показывается как успех. Top – максимум три смысловые группы свободного rule, ссылки только на confirmed first_error; модель не получает каталог кодов. После валидации результат сохраняется с snapshot и Job.

GET summary возвращает выбранный последний запуск. История прежних запусков сохраняется для staff. Изменение review.state после финала повышает data_revision: выбранный результат помечается stale; никакого нового запроса автоматически. Изменение только comment не меняет snapshot-основание и не делает stale. Title/number не редактируются.

POST summary/refresh разрешен только при серверном **can_refresh=true**: finalized, stale=true и прежний Job либо терминален (succeeded/failed/cancelled/superseded), либо queued/blocked и гарантированно еще не отправлен провайдеру, без in-flight/unknown Attempt. Во втором случае refresh одной транзакцией ставит старому неотправленному Job superseded/replaced, сохраняет историю и создает **новый snapshot** по текущим отзывам и новый Job. Резерв освобождается только для гарантированно неотправленной Attempt; неизвестное списание не освобождается из-за смены состояния Job.

Running, retry_wait с возможной отправкой и unknown нельзя supersede ради повтора: can_refresh=false до терминального исхода/сверки, даже при stale=true. Для queued/blocked UI также не выводит разрешение из enum: can_refresh учитывает внутренний факт отправки. Claim worker и refresh конкурируют под одной блокировкой; если worker уже закрепил dispatch, refresh получает 409 revision_conflict/invalid_state и клиент перечитывает GET, не создает запрос обходным путем. Если snapshot уже устарел до claim, worker не тратит деньги на его отправку.

POST summary/retry разрешен только при **can_retry=true**: finalized, stale=false, state=failed и сервер подтвердил безопасный исход прежней попытки. Повторяется **тот же snapshot**, создается новый Job. Blocked/unknown не дают retry; для stale нужен refresh. Гарантированно неотправленный blocked Job может продолжить первоначальную свежую работу после снятия причины, без новой операции retry. Свежий succeeded повторно платно не запускается. Если review изменен во время уже отправленного AnalyticsJob, он может завершиться и сохраниться stale; после исхода доступен refresh. Поздний ответ старого не заменяет выбранный новый Job/snapshot. Отдельной teacher функции просмотра всех попыток нет.

## Очередь, расходы и события

Job состояния: queued/running/retry_wait/blocked/unknown/succeeded/failed/cancelled/superseded. `succeeded` означает валидный сохраненный ответ: checker Report.status=uncheckable по-прежнему не математический успех. reason enum описывает funds_unavailable/service_paused/provider_outcome_unknown/temporary_failure/provider_rejected/invalid_response/input_uncheckable/deleted/replaced/skipped. Учителю не показываются баланс и квота; can_retry вычисляется сервером, UI не угадывает по enum.

Внутренняя Attempt хранит id/job_id/ordinal, lease, состояние started/settled/unknown, время, provider_request_id если выдан, usage и стоимость; уникальна по job+ordinal. Перед внешним вызовом долговечно создается Attempt и резерв верхней границы возможной стоимости по конфигурации модели/токенов. Общая строка кошелька блокируется транзакционно для обоих kind; available=balance-sum(active reserves), отрицательный резерв/остаток запрещен. Нет достаточных средств или ручная пауза – Job blocked до внешнего вызова; готовые материалы доступны. 400 рублей не жесткий стоп месяца. Верхняя граница должна соответствовать отправляемому max_tokens и входным данным, не выдумываться из средней стоимости benchmark.

Подтвержденный временный технический отказ допускает **один** автоматический повтор в новой Attempt того же Job; новая Attempt имеет отдельный резерв/учет. Timeout/обрыв после возможной отправки дает unknown, а не бесплатный retry. После рестарта expired lease с возможно отправленным вызовом также unknown. Нового вызова нет, пока команда привилегированной CLI не сверит провайдера/списание и не зафиксирует результат либо доказанный отказ. Settlement уникален по Attempt.id; повтор доставки usage не списывает дважды. При success резерв заменяется фактом, неизрасходованная часть освобождается; при unknown остается. Ограничение worker slots общее для двух kind (по умолчанию 2), учет денег не выводится из одного лишь числа слотов. Локальные имитаторы покрывают конкуренцию, live-вызовы этой задачей не разрешены.

Ручная pause/resume и сверка unknown выполняются привилегированной CLI в Compose, вызывающей domain service processing. HTTP processing-control и третьей роли нет. staff остается полностью read-only. Красные отзывы не выключают обработку автоматически.

POST events принимает не более 100 наблюдений одним batch; дедупликация `(actor_id,event.id)` и проверка принадлежности всех ссылок транзакционны. Повтор идентичного ID возвращает его в accepted_ids, иной payload – 409. При чужой ссылке весь batch 404, без частичного приема. Клиент никогда не задает actor/role/received_at – их пишет сервер. name: capture_opened/photo_selected/result_opened/result_closed/app_visible/app_hidden/heartbeat. check_id/entity_id nullable, entity только Bundle/Task внутри указанной своей проверки; staff может указать только доступный прочитанный материал с реальной ролью staff. Сеанс наблюдений отделен от cookie, время приблизительное; отсутствие клиентских событий не блокирует работу.

Сервер сам пишет факты auth, создания/загрузки/submit, переходов Job/Attempt/денег, публикации, отзыва, skip/delete, begin/finalize/refresh/retry и staff-read. Событие сервера имеет собственный event_id, actor_id/role (либо system), request_id, occurred_at, check_id, entity_id, job/attempt/snapshot ID при наличии и enum результата. Числа usage/стоимости живут в ledger, событие ссылается ID; тексты комментариев/математики/сырые ответы, пароли/cookie/ключи/Base64 в общий журнал не копируются. Имена серверных событий и payload производятся только успешным commit/outbox, не повторным входящим HTTP. Пересечения устройств учитываются по session_id, не складываются как точное время письма на бумаге.

## Офлайн приемка пакета

`api/validate.py` проверяет формальную OpenAPI 3.1, разрешение всех refs без сети, строгие формы всех маршрутов, валидные UUID, frozen examples и согласованность lifecycle fixtures. `api/tests/test_contract.py` дополнительно проверяет ошибки индексов/первой ошибки, отрицательные формы, mixed skip, false zero, текущие блокеры, замену 2→3 без наследования ID/reviews, два успешных поколения одного входа с разными отзывами, tombstone и stale/comment, разрешения refresh/retry и отсутствие лишних rename-маршрутов. Синтетический PNG 64×64 проверяется по IHDR/CRC и распаковке, не является математическим примером. `build_contract.py --check` ловит рассинхронизацию генератора, схем, OpenAPI и переносимых типов.

Это проверка спецификации. Транзакционные гонки, перезапуск worker, недопуск платного дубля и права реального HTTP/БД должны пройти runtime-приемку модулей по тем же fixtures; офлайн артефакты этого не доказывают. Модельный checker, его схемы и примеры не изменены. Новых платных прогонов, бюджета, аккаунтов, публикации и внешнего доступа нет.
