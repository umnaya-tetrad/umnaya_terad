# Задачи application

19.11.2026 · **план реализации**. Область и порядок чтения – [README](README.md), обязательные проверки – [ACCEPTANCE](ACCEPTANCE.md). Источник API – [OpenAPI](../shared/api/openapi.json), поведения – [ux-flows](../shared/ux-flows.md), ролей файлов – [MODULE_BOUNDARIES](../shared/MODULE_BOUNDARIES.md). Все будущие пути ниже относительны корню umnaya_terad. Отсутствующий файл означает задание создать его, не наличие реализации. Generated DTO и frozen checker read-only.

## Входные зависимости B0/B1b и публичные порты

B0: один зафиксированный commit [shared](../shared/README.md), включая схемы/типы, 44 HTTP fixtures, 25 lifecycle-состояний, UX и аналитику. Не генерировать свою форму Mutation/Review/Check. Processing поставляет `src/pilot/api/generated.ts`, `app/pilot/contracts.py`; application может работать на [fixtures](../shared/api/fixtures/http.json) до runtime B1b.

B1b processing поставляет следующие **плановые публичные интерфейсы**, согласованные между направлениями. Их реализация принадлежит processing; application импортирует, тестирует адаптацию и сообщает о несовпадении. Внутренние типы не копируются в application.

| Модуль/символ processing | Точная форма использования application |
|---|---|
| `domain/services.py` | `create_services(pool: asyncpg.Pool, storage_root: Path, settings: Settings) -> Services`; синхронная композиция без запуска миграций/worker. `Settings` импортируется `from config import Settings`. Экземпляр `app.state.pilot_services` |
| `domain/access.py` | `Actor(user_id: UUID, role: teacher|staff)`; `get_services(request)` и `require_actor(request) -> Actor` – dependencies маршрутов; неверная сессия дает DomainError 401 |
| `domain/revision.py` | `MutationContext(actor, expected_revision: int|None, idempotency_key: UUID, request_id: UUID)`; отсутствующая revision только у createCheck |
| `domain/errors.py` | `DomainError(http_status:int, code:str, message:str, current_revision:int|None=None)`, `.to_response() -> ErrorResponse`; `install_error_handlers(app:FastAPI)` вызывается единожды |
| `domain/mutations.py` | Все функции async `(svc:Services, ctx:MutationContext, ...)->Mutation`: `create_check(payload:Title)`, `create_notebook(check_id)`, `create_bundle(notebook_id)`, `create_input_version(bundle_id,payload:VersionCreate)`, `reorder_photos(input_version_id,payload:PhotoOrder)`, `discard_draft(input_version_id)`, `delete_draft_photo(input_version_id,photo_id)`, `delete_task(task_id)`, `delete_bundle(bundle_id)`, `delete_notebook(notebook_id)`, `delete_check(check_id)`, `save_review(task_id,payload:ReviewWrite)`, `upload_photo(input_version_id,prepared:PreparedPhoto)` |
| `domain/storage.py` | `prepare_photo(stream:BinaryIO,declared_type:str)->PreparedPhoto`; проверка/нормализация оригинала – processing, route не пишет другую image-validation политику |
| `domain/queries.py` | Async `list_checks(svc,actor,*,cursor=None,limit=30,request_id)->Checks`, `get_check(svc,actor,check_id,*,request_id)->Check`, `get_bundle_history(svc,actor,bundle_id,*,request_id)->BundleHistory`, `open_photo(svc,actor,photo_id,*,request_id)->PrivatePhoto(path:Path,media_type:str)`; queries уже проверяют доступ и аудит |
| `domain/auth.py` | Async `authenticate(svc,login,password)->SessionGrant(session:Session,token:секрет без repr)`, `actor_for_token(svc,token)->Actor|None`, `revoke(svc,token)`, `ensure_account(svc,login,password,role)->Session`; последняя только для локального seed, не HTTP signup |
| Router/entrypoints processing | `app/pilot/routes/processing.py` и `events.py` экспортируют `router:APIRouter`; `python -m pilot.processing.worker`, `python -m pilot.domain.migrate` выполняются из `/app` |

Функциональная зависимость B1 – runner/SQL/auth/storage/guard processing и ранний fixture-worker, а не законченный LLM. Пока порты не поставлены, разрешены явные test doubles, не рабочее сохранение в памяти. При несовпадении фиксировать BLK с именем символа и входом, не скрывать ImportError. Cookie name, безопасная локальная конфигурация и transport берутся из [LOCAL_ENV](../shared/LOCAL_ENV.md); нового HTTP поля для transport нет. `app/config.py` принадлежит processing: до B1 он обновляет POLZA_TIMEOUT_SECONDS до допустимых 300 и MIN_IMAGE_EDGE до 32, сохраняя общие MAX_IMAGE_BYTES=8000000/MAX_IMAGE_PIXELS=36000000. Application только импортирует pinned baseline этого файла, подключает env и проверяет совместимость; самостоятельно Settings не переписывает.

## APP-01. Безопасный pinned source и manifest — B1a

- **Зачем:** техническая основа T01, R26/R58/R85, A25. Получить воспроизводимый код без школьных материалов и секретов.
- **Вход:** SmartNoteLanding commit `d62f5ecb8c1c53b1c97faf06530b8d84e691f88d`, B0; прочитать исходный AGENTS и проверить status/HEAD обоих checkout. Незакоммиченные файлы источника не импортировать.
- **Файлы:** разрешенный одноразовый manifest-импорт tracked `src/`, нужного `app/`, `app/migrations/001–007`, соответствующих тестов, lock/package/tsconfig/Vite/index/Dockerfile/Compose; отчет `docs/pilot/BOOTSTRAP.md`. После baseline backend/SQL принадлежит processing, это не постоянное право application на них.
- **Сделать/выход:** перечень source path→target path с blob/SHA и основанием; просмотреть список до переноса; импортировать только pinned blobs. Исключить `.git`, секретные `.env*`, node_modules, venv, dist, inputExamples, benchmark/output/cache/production-ответы. Не перезаписывать `project-context/`. Безопасный env-шаблон подготовить заново. Зафиксировать версии runtime/lockfiles; не обновлять `latest` автоматически.
- **Проверка:** APP-C01/C34; выполнить исходные `npm test`, `npm run build`, backend `python -m pytest` из `app/` после подготовки тестовой БД. Записать реальные команды/неуспех, не присвоить старому отчету новый PASS.
- **DoD:** есть проверяемый manifest, pinned SHA и перечень отклоненных категорий; импорт не включает рабочие/неотслеживаемые секреты и не меняет источники. Расхождения старого несохранения фото/квот/регистрации с пилотом описаны, устранение назначено владельцам.

## APP-02. Ранний Compose, hooks и общий bootstrap — B1a/B1

- **Зачем:** B1 до 14:00, R28/R73/R85, A12/A13/A19/A25; убрать зависимость ранних данных от готового UI.
- **Вход:** APP-01, B0 и порты B1b; параллельно processing создает миграции/worker. Application объявляет hooks до B1, не ждет release.
- **Файлы:** `compose.yaml`, `Dockerfile`, `app/Dockerfile`, `.env.example`, ignore/CI, `vite.config.*`, `src/main.tsx`, `src/App.tsx`, `app/main.py`, `app/pilot/router.py`, `docs/pilot/BOOTSTRAP.md`, `docs/pilot/INTEGRATION_STATE.md`; только до B4.
- **Сделать/выход:** общий `router:APIRouter` до B4 агрегирует auth/application/processing/events routers по одному разу; отсутствующий staff router до 18:00 не импортируется и не подключается. Подмодули задают пути без `/api`; main добавляет prefix `/api` единожды. Lifespan создает pool/Services и общие error handlers, закрывает ресурсы. Processing поставляет свои импортируемые hooks до B1b. Для staff объявлены место и интерфейс подключения без импорта отсутствующего модуля; release после B4 поставляет настоящий staff router и подключает его в принятом router/main. Ранний frontend также не импортирует src/pilot/staff: до B4 staff-сессия не открывает данные и показывает существующее common.unavailable. После B4 release подключает настоящий staff UI через принятый src/App.tsx. Пустой router не считается реализованным endpoint; не маскировать неожиданные ImportError.
- **Compose:** `postgres` PostgreSQL16, `backend`, `frontend`, `worker`, одноразовый `migrate`. API `uvicorn main:app --host 0.0.0.0 --port 8000`, worker `python -m pilot.processing.worker`, migrate `python -m pilot.domain.migrate`, Python workdir `/app`. Volumes `postgres_data`, приватный `pilot_photos` общий API/worker, `frontend_node_modules`. Порядок healthy DB→успешный migrate→API/worker healthy→frontend. Не создавать второй migration runner или публичную раздачу photo volume.
- **Режим:** один Compose-source `PILOT_TRANSPORT`, default polza; frontend получает его как `VITE_PILOT_TRANSPORT`. Без ключа polza fail-closed, без fixture fallback; тестовый профиль явно fixture. Health не вызывает LLM. Минимальный seed APP-03 готов до B1.
- **Проверка/DoD:** APP-C02/C31/C34. Создать и выполнить команды build→run migrate→up→seed→API smoke из ACCEPTANCE; один startup без реального ключа в явном fixture. Чистая БД/миграции/сессия/долговечный Job проверены совместно, B1 commit и hooks записаны. `down -v` отсутствует в штатном запуске. Общие файлы остаются у application до APP-14.

## APP-03. Auth cookies и ранние аккаунты — код к B1a, runtime до B1

- **Зачем:** R27/R48/R73, A01/A12/A20; готовые личные аккаунты без signup.
- **Вход:** APP-02, processing auth/access/schema/миграции B1b. Ни release CLI, ни публичная регистрация источника не зависимость.
- **Файлы:** `app/pilot/routes/auth.py`, `app/pilot/operations/{__init__,create_fixture_accounts}.py`, `app/tests/pilot/application/test_auth.py`, `src/pilot/screens/LoginScreen.tsx`, `src/pilot/auth.ts`.
- **Сделать/выход:** login/getSession/logout по operationId и cookie из общего конфигурационного контракта. Cookie HttpOnly, SameSite=Lax, Secure при HTTPS; мутации, login/logout проверяют exact Origin. Пароли/токены не возвращаются и не логируются. Session маршрутизирует только teacher/staff; staff UI подключается release, не открывает teacher editing.
- **Seed:** локальная команда `docker compose -f compose.yaml exec backend python -m pilot.operations.create_fixture_accounts` создает два teacher и одного staff через `ensure_account`, без собственного SQL/хеширования. Код/importable CLI предоставляется уже в B1a; запуск на общей auth/schema B1b проверяется до B1. Обязательные env: `PILOT_FIXTURE_TEACHER_1_LOGIN`, `PILOT_FIXTURE_TEACHER_1_PASSWORD`, `PILOT_FIXTURE_TEACHER_2_LOGIN`, `PILOT_FIXTURE_TEACHER_2_PASSWORD`, `PILOT_FIXTURE_STAFF_LOGIN`, `PILOT_FIXTURE_STAFF_PASSWORD`. Значения без defaults; реквизиты не argv/HTTP/Git, пароль не печатается. Повтор не меняет действующий пароль молча; неполные/конфликтующие данные дают безопасный отказ.
- **Проверка/DoD:** APP-C02/C03/C27/C35; 200 login/session, 204 logout, 401 неверная/истекшая сессия, отказ неверного Origin. Нет signup endpoint. Тестовая сессия существует до B1; seed+пакетный init включены в список B4-передачи.

## APP-04. Тонкий HTTP CRUD и приватное фото — B1/B2

- **Зачем:** R25–R28/R46–R49/R62/R69/R70/R79–R82, A01/A02/A07–A09/A12–A15/A20/A22.
- **Вход:** перечисленные доменные порты B1b и shared schema. Нельзя создавать вторую транзакцию/таблицы или обходить единый guard.
- **Файлы:** `app/pilot/routes/application.py`, `app/pilot/services/application.py`, `app/tests/pilot/application/{test_crud,test_photos,test_review,test_access}.py`.
- **Сделать/выход:** маршруты `listChecks/createCheck/getCheck/deleteCheck`, `createNotebook/deleteNotebook`, `createBundle/deleteBundle/createInputVersion/reorderPhotos/discardDraft/uploadPhoto/deleteDraftPhoto/getPhoto/getBundleHistory`, `saveReview/deleteTask`. Каждый переводит shared request и заголовки в общую функцию mutations/queries. Status/DTO строго по таблице ACCEPTANCE, DomainError маппится единым handler.
- **Детали:** createNotebook без body, server number монотонный, без rename. Multipart один `file`; prepare_photo и сохранение выполняет processing. GET asset вызывает авторизованный/аудированный open_photo и возвращает бинарный файл `Cache-Control: private,no-store`; нет пути к оригиналу в JSON. Bundle history разрешен только staff. Review всегда конкретные task_id/analysis_id. Нельзя подтверждать весь Report, создавать Job в CRUD handler или разрешать состав после финала.
- **Проверка/DoD:** APP-C04–09/C17–20/C27/C28/C35. Валидируются shared формы/status, 401/403/404/409/413/415/422, идемпотентный replay и revision. Каждый handler использует общий service, тесты проверяют переданные actor/ctx/resource/payload и отсутствие самостоятельного SQL.

## APP-05. Типизированный клиент, revision и намерения — начало на B0, B2

- **Зачем:** A08/A09/A12/A13/A16/A22, R26/R28/R46/R47; потерянный ответ не создает вторую обработку.
- **Файлы:** `src/pilot/api/{client,intents,errors}.ts`, `src/pilot/state/{checkStore,useCheckPolling}.ts`, соответствующие `*.test.ts`, `src/pilot/__fixtures__/transport.ts`.
- **Вход:** generated.ts processing read-only, HTTP/lifecycle fixtures. Не объявлять DTO вручную. Fixture adapter доступен только в явно выбранном тестовом режиме.
- **Сделать/выход:** cookie credentials same-origin; JSON/multipart/бинарный asset и ErrorResponse; текущий revision/ETag. Mutation.check_revision обновляет guard. Для каждого намерения сохранять UUID key до отправки; потеря ответа повторяет тот же canonical payload+key, не новый запрос. Намерение связано с текущим аккаунтом/ресурсом; после 401/смены аккаунта не выполнять прежние формы автоматически, не переносить локальный текст/контекст другому учителю. Принятый replay может вернуть прежнюю revision – затем getCheck, не откатить более новый store. 409 перечитывает Check, сохраняет несохраненный текст локально и требует нового явного выбора с новым ключом; 401 ведет ко входу, чужой/удаленный 404 не раскрывает данные.
- **DoD/проверка:** APP-C08/C11/C24/C28/C31. Двойной клик, reload после потери submit/finalize response и второй клиент не создают дополнительные Job. Intent-метаданные не являются офлайн-режимом: выбранные, но не переданные фото не объявляются сохраненными. GET сам не создает mutation/LLM. Поздний fetch старого состояния не перетирает новый store.

## APP-06. Shell, история, название и условные тетради — B2

- **Зачем:** R13/R25/R27/R41/R48/R67/R68/R69, A01/A12/A14/A25.
- **Файлы:** `src/pilot/PilotApp.tsx`, `src/pilot/copy.ts`, `src/pilot/screens/{ChecksScreen,NewCheckScreen,CheckScreen}.tsx`, `src/pilot/styles/pilot.css`, unit-тесты рядом.
- **Вход:** APP-05, shared UX S00–S03 и тексты. Встраивание shell в `src/App.tsx` до B4; staff mount остается отдельным release hook.
- **Сделать/выход:** auth gate, история с cursor/limit, обязательное title при create, server Notebook.number; возврат к незавершенной проверке и сохраненной текущей сводке. Нет class/topic/variant/FIO/rename. Поля/состояния из API, номера удаленных тетрадей не переиспользовать локально. Повторное открытие не submit. Общий copy adapter импортирует shared JSON; не дублирует тексты. При fixture постоянная тонкая метка common.fixture_mode «Учебный режим», независимо от конкретного экрана.
- **DoD/проверка:** APP-C03–06/C30/C34. Состояния editing/review/finalized определяют доступность действий; крупный текст/клетка/палитра сохраняются. На экране только актуальные сообщения, служебные MD-параграфы не переносятся в продукт.

## APP-07. Камера, галерея и упорядоченный draft — B2

- **Зачем:** R15/R16/R44/R45/R71/R80/R81, A02/A03/A04/A06.
- **Файлы:** `screens/NotebookScreen.tsx`, `components/{PhotoCapture,PhotoStrip,PhotoViewer,ConfirmDialog}.tsx`, `src/pilot/photos.ts`, тесты и синтетические media в `src/pilot/__fixtures__/`.
- **Вход:** APP-04/05; upload/reorder/deleteDraftPhoto/discardDraft/getPhoto; нормализация/валидация processing.
- **Сделать/выход:** камера и галерея, разрешения/cancel, предпросмотр с порядком, добавление продолжения до submit, выбор/замена/удаление фото. Новый Bundle уже имеет draft. Замена draft-фото: upload нового→delete старой ссылки→reorder полного photo_ids, каждый шаг с новой revision; при сбое getCheck и фактические фото, sealed/отзывы не меняются. Не добавлять crop/rotate/PDF или отдельное фото условия. Пустой draft и upload in-flight не отправляются. Удаление/уход с непустым draft требует явного решения, не потери данных.
- **DoD/проверка:** APP-C07–10/C12/C30. JPEG/PNG/WebP и серверный HEIC/HEIF путь; frontend не отсекает iPhone HEIC. Backend конвертирует HEIC/HEIF, оригинал приватный; допустимые JPEG/PNG/WebP без ненужного перекодирования. Нормализованный LLM asset тоже укладывается в 8000000/36M/min32; превышение после конвертации дает 422 до accepted, без молчаливого resize. Corrupt/unsupported/size errors отличаются от принятого input. Камера denied оставляет gallery. PhotoViewer показывает приватное фото с увеличением, не общий static URL.

## APP-08. Две отправки, async results и восстановление — B2

- **Зачем:** R17–R20/R26/R28/R64/R80/R81, A04/A12/A13/A19.
- **Файлы:** `NotebookScreen.tsx`, `state/useCheckPolling.ts`, `components/JobStatus.tsx`, `api/client.ts`, unit-тесты рядом.
- **Вход:** submitBundle/getCheck/getJob processing, shared pending/continuation fixtures; долговечный fixture-worker B1b.
- **Сделать/выход:** обе кнопки вызывают один submit с точным input_version_id. Только после 202 либо открыть новый Bundle текущей тетради, либо следующую server Notebook и Bundle. Не ждать checker. Пустая следующая тетрадь не отправляет пустой запрос. Результаты чужого текущему экрану комплекта появляются у исходной тетради; готовые доступны прежде pending независимо от съемочного порядка. Камера/открытая карточка не прерываются polling.
- **DoD/проверка:** APP-C11–14/C31. Принятое сохраняется при закрытии; restore не создает новую работу. Не обещать streaming частей одного Report/результат за 15 секунд. retry_wait/blocked/unknown имеют простые сообщения и серверные разрешения действий.

## APP-09. Компактный AI-render и отдельный отзыв — B2

- **Зачем:** R10/R11/R21–R24/R38–R40/R46/R82, A05–A08/A17/A18.
- **Файлы:** `screens/ReviewScreen.tsx`, `components/{TaskCard,MathText,ReviewControls}.tsx`, renderer/review unit-тесты.
- **Вход:** frozen Task в shared TaskAnalysis, E_C01/K01/M06, saveReview. Client не перепроверяет математику и не меняет checker.
- **Сделать/выход:** контекст тетради/задачи/фото; максимум четыре evidence; first_error wrong/rule/explanation/corrected; independent completeness. JSON parse один раз, без ручного unescape; недоверенный текст без HTML execution, KaTeX без trusted commands. Фото 1/2 относятся к photo_indices, continuation не дает лишнюю задачу. all_steps_correct не означает complete.
- **Отзыв:** зеленая галочка «Согласен с проверкой»=confirmed, красная «Ошибка в проверке ИИ»=system_error; null не подтвержден. Нажатие сохраняет только эту задачу, комментарий необязателен/очищаем, без редактора OCR/вывода и без автоматического retry. При ошибке save не показывать новый отзыв как сохраненный.
- **DoD/проверка:** APP-C13/C15–18/C30/C35. Подтверждение найденной ученической ошибки допустимо. Просмотр/next/выход/финал не ставят согласие. Сокращение/незавершенность не штрафуются; описка остается гипотезой исходного пояснения.

## APP-10. Замена, удаление, retry/skip и mixed Report — до B4

- **Зачем:** R30/R47/R62/R69/R70/R78–R81, A09–A11/A14/A15.
- **Файлы:** `ReviewScreen.tsx`, `NotebookScreen.tsx`, `CheckScreen.tsx`, `components/ConfirmDialog.tsx`, application routes APP-04, unit/HTTP-тесты.
- **Вход:** createInputVersion/delete/discard и processing retryBundle/skipBundle/skipTask; fixture поколения 2→3 и mixed.
- **Сделать/выход:** replacement draft копирует photo_ids только текущего sealed input; cancel/discard не снимает старый отзыв, submit/retry снимает все отзывы поколения общего комплекта. Не сопоставлять новые задачи по формуле/порядку/task_id модели. DeleteTask сохраняет общее фото соседей. Подтверждения удаления точны для фото/задачи/тетради/проверки; без корзины и обещания физической очистки копий.
- **Неудачи:** retry только whole Bundle по can_retry и с предупреждением снятия соседних отзывов; один автоповтор делает worker. not_assessed не имеет review, skipTask только ее; failed/uncheckable/blocked/unknown вход пропускается skipBundle, без математического нуля. После финала нет checker retry/skip/изменения состава, но остается deleteCheck.
- **DoD/проверка:** APP-C19–22/C28/C31. Поздний старый ответ не возвращает поколение/удаленное. Mixed: согласие соседней пригодной задачи сохраняется при task skip; retry целого комплекта снимает его. Техническая обработка/финансовый reserve принадлежит processing.

## APP-11. Двухэтапное завершение — до B4

- **Зачем:** R84/R86, A14/A16; финальный клик не массовое согласие.
- **Файлы:** `screens/CompletionScreen.tsx`, completion unit-тесты, client вызовы processing.
- **Вход:** beginCompletion/finalizeCheck/getCheck, Completion; B3 API processing не зависит от завершенного оформления.
- **Сделать/выход:** первый finish переводит в review, показывает ожидание и отдельные блокеры, сохраняет редактируемость. Null assessable блокирует, system_error разрешает review, not_assessed/failed требуют явного разрешения; непустой draft submit/discard. При всех нулевых счетчиках без активного sealed input finish.empty и camera/gallery. Client не выводит can_finalize из суммы счетчиков: финальная кнопка только по серверному true.
- **Финал:** отдельный диалог последствий/спорного/пропусков; POST finalize с revision+key, 202 → summary pending. После подтвержденного finalized состав закрыт, отзыв/comment и чтение доступны. Потеря ответа/409 не создает новый AnalyticsJob и не ставит review=confirmed.
- **DoD/проверка:** APP-C23/C24/C28/C33; переход назад ничего не подтверждает, редактура до финала пересчитывает серверные блокеры, после финала сервер тоже защищает состав.

## APP-12. Текущая сводка и capability — до B4

- **Зачем:** R24/R34–R39/R46/R83–R86, A16–A18.
- **Файлы:** `screens/SummaryScreen.tsx`, `components/JobStatus.tsx`, summary unit-тесты.
- **Вход:** getSummary/refreshSummary/retrySummary, shared analytics result и четыре пары fixtures. Группирует/валидирует итог processing, UI не создает классификатор по raw rule.
- **Сделать/выход:** not_started/queued/running/retry_wait/blocked/unknown/failed/succeeded и независимый stale. Refresh только can_refresh=true: новый snapshot, возможна безопасная замена queued/blocked, которую определяет сервер. Retry только can_retry=true && !stale: тот же snapshot. running/unknown не обходить новым запросом. GET/открытие истории не запускает аналитику; у teacher нет истории запусков.
- **Числа:** with_errors/without_errors только полностью confirmed непустые; знаменатель рядом со средним; null ≠0. Top до трех raw-названий правил с частотой task_ids.length, confirmed задачи partial тетради допустимы. Отдельно partial/empty/incomplete/disputed/unassessed; skipped tasks/bundles берутся из актуального Check, неизвестное число задач не выдумывается. Устаревшие цифры не выдавать за актуальные. Comment-only не stale, state change stale.
- **DoD/проверка:** APP-C25/C26/C33; oracle 4 тетради, 1+1 полных, partial1/empty1, среднее 0,5, incomplete1, два правила с частотой 1. Нулевой знаменатель показывает отсутствие данных. После финала review редактируем, состав закрыт.

## APP-13. UI telemetry без блокирования работы — до B4

- **Зачем:** R50/R51/R61/R77, A21/A22. Приблизительные интервалы, без таймеров/дополнительных кнопок учителю.
- **Файлы:** `src/pilot/telemetry/{client,useLifecycle}.ts`, тесты; HTTP ingest принадлежит processing.
- **Вход:** Event/Events, ingestEvents, enum capture_opened/photo_selected/result_opened/result_closed/app_visible/app_hidden/heartbeat. Actor/role/received_at определяет сервер.
- **Сделать/выход:** UUID event/session, UTC occurred_at, допустимые check_id/entity_id только Bundle/Task этой проверки; batch до 100, одинаковый ID при повторной доставке. Бизнес-факты upload/review/skip/finish пишет сервер – не создавать выдуманные client enum. Ошибка очереди событий не блокирует фото/отзыв/финал; не обещать offline upload. Очередь не содержит текста математики, фото, комментария, cookie, пароля, raw ответа/произвольного payload.
- **DoD/проверка:** APP-C29/C35. Видимость/выход/возврат и два устройства различаются по session_id, browser focus не объявляется доказанным временем проверки. Staff события реализует release.

## APP-14. Доказательства и передача общих файлов — B4 до 18:00

- **Зачем:** A01–A18/A21/A22/A25 в своей доле, R85; release получает конкретную основу вместо ожидания автора.
- **Файлы:** `planning/application/HANDOFF.md`, до передачи `docs/pilot/{BOOTSTRAP,INTEGRATION_STATE}.md`; свой application code/test diff. Не писать release/processing HANDOFF.
- **Вход:** B3 полный API финала/аналитики processing; результаты APP-C01–35, каждый pass/fail/not_run; ранняя часть APP-C27 до B4, полный staff list/get/UI по APP-C27/REL-C07 только после REL-04. Отсутствие позднего staff mount до B4 не блокирует передачу ядра. До B4 application интегрирует малые commits/PR в integration в пределах порученной разработки и согласованной GitHub-передачи.
- **Сделать/выход:** source/contract/baseline/code commits, режим fixture, точные команды и ограничения, список миграций processing, воспроизводимые defects. Зафиксировать явный commit передачи общих файлов из README, main/router/src/App.tsx/src/main.tsx/Compose/bootstrap-config/infra/docs/scripts и двух seed-файлов release (app/config.py всегда processing) в 18:00. До записи приема владелец application, время само по себе не переключает владение.
- **DoD/проверка:** APP-C32/C33. Запущен реальный локальный путь begin→отзывы→finalize→AnalyticsJob→сохраненная summary на fixture transport, без статического fake-success. Unit/mock не обозначен DB/e2e/live. Функциональные пробелы не объявлены плановой задачей вечера.

## APP-15. UI-доводка и интеграционные fixes — 18:00–21:00

- **Зачем:** R85, A06/A16/A25; закончить локальный пользовательский путь после приема ядра.
- **Файлы:** только собственные `src/pilot/**`, auth/application routes/services и тесты; общие конфиги+seed уже release. `src/pilot/staff/**` не затрагивать.
- **Вход:** B4 code/contract/baseline и журнал integration; не ожидать синхронной встречи/автора processing. Release ведет интеграцию, кандидат около 20:15.
- **Сделать/выход:** исправлять воспроизводимые UI/HTTP-дефекты по зафиксированному контракту, пересобирать нужные unit/build проверки. Для общих файлов/домена передавать reproduction владельцу/release, не создавать обход или несовместимую форму. Четко отмечать реальные устройства и оставшееся not_run.
- **DoD/проверка:** APP-C30/C32–35, `npm test`, `npm run build`, backend application tests; release независимо выполняет e2e/DB/restart. В 21:00 переданы commit и доказательства; не обещать внешний deploy/реальную школу/live качество.
