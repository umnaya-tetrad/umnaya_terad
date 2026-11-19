# Приемка application

19.11.2026 · **все APP-C ниже planned/not_run для приложения**. Код/Compose еще не созданы этим ТЗ. Это требования к созданию проверок, не результаты запусков. Общая спецификация уже проверена отдельно: [SHARED_REVIEW](../shared/SHARED_REVIEW.md). Задачи – [TASKS](TASKS.md), источник ответов – [OpenAPI](../shared/api/openapi.json), [HTTP fixtures](../shared/api/fixtures/http.json), [lifecycle](../shared/api/fixtures/lifecycle.json), [UX](../shared/ux-flows.md).

## Воспроизводимые входы и команды

`H:name` означает элемент HTTP fixtures с точным `name`, `L:key` – точный ключ lifecycle JSON. У всех HTTP-запросов, кроме оговоренных auth/GET/createCheck, действующая cookie, exact Origin, `If-Match` текущего Check и UUID Idempotency-Key. Каждый **новый** замысел имеет новый key; сетевой replay того же действия сохраняет key/payload. `Mutation` содержит check_id/check_revision/entity_id/job; после изменения перечитать getCheck, если replay/конкурентность могли сделать ответ старым. Ошибки имеют ErrorResponse с code/message/current_revision, без внутренних исключений.

При реализации **создать** тестовые файлы из TASKS и именовать unit-тест `APP-CNN ...`, backend-тест `test_app_cNN_...`. Обозначения ниже задают точную целевую команду:

- `U(APP-CNN)` – из корня `npx vitest run src/pilot -t APP-CNN`; файлы `src/pilot/**/*.test.{ts,tsx}` принадлежат application. Полный набор – `npm test`, production build – `npm run build`.
- `H(APP-CNN)` – из `app/` выполнить `python -m pytest tests/pilot/application -q -k app_cNN`; route-тесты используют общий domain и отдельную test DB либо явные port doubles. Указывать, какой из двух видов реально пройден. Двойник не доказывает сохранение БД.
- `M(APP-CNN)` – точные ручные шаги кейса ниже на локальном Compose с `PILOT_TRANSPORT=fixture`, записать ОС/браузер/реальное устройство либо эмуляцию, commit, HTTP-трассу без секретов и pass/fail. Release автоматизирует их отдельно в своих e2e, application эти чужие файлы не создает.

Эти команды будущего приложения **создать и выполнить при реализации**, не объявлять существующими/PASS. Npm/dependencies/runner фиксируются в B1, без установки произвольного latest. Готовый офлайн gate документации: `python project-context/pilot/planning/shared/check_shared.py` в изолированном dev-env; он не выполняет APP-C.

Плановые дополнительные fixtures application: `src/pilot/__fixtures__/ui-scenarios.ts`, `media/manifest.json` и безопасные синтетические JPEG/PNG/WebP/HEIC/HEIF. Manifest фиксирует происхождение/формат, без реальных школьных фото. В ui-scenarios только валидные schema варианты: empty Check, еще не подтвержденные соседние задачи, out-of-order два Bundle, first-error/correct/incomplete/omitted_steps/unknown, pending→ready, lost response, ошибки файла. Математический Task копируется из разрешенных dev-ответов, не переписывается ради ожидаемого теста. Вариации состояния/оберток явно синтетические и проходят B0 schema. Existing shared/frozen fixtures read-only.

## Точная поверхность 34 HTTP operationId

Это распределение реализации и проверки, не новый API. У каждой строки success status по OpenAPI; отрицательные ответы проверяются в кейсах. Префикс путей `/api`. Если route принадлежит processing/release, application только вызывает его клиентом или проверяет свой auth/bootstrap hook, не реализует чужой route.

| operationId | Success | Route-владелец / задача | Case |
|---|---|---|---|
| login | 200 Session + cookie | application APP-03 | APP-C03 |
| getSession | 200 Session | application APP-03 | APP-C03 |
| logout | 204 без body | application APP-03 | APP-C03 |
| listChecks | 200 Checks | application APP-04/06 | APP-C04 |
| createCheck | 201 Mutation | application APP-04/06 | APP-C04 |
| getCheck | 200 Check | application APP-04/05 | APP-C04/C28/C31 |
| deleteCheck | 200 Mutation | application APP-04/10 | APP-C20 |
| createNotebook | 201 Mutation | application APP-04/06 | APP-C05 |
| deleteNotebook | 200 Mutation | application APP-04/10 | APP-C05/C20 |
| createBundle | 201 Mutation | application APP-04/07 | APP-C06 |
| deleteBundle | 200 Mutation | application APP-04 | APP-C06/C20 |
| createInputVersion | 201 Mutation | application APP-04/10 | APP-C19 |
| reorderPhotos | 200 Mutation | application APP-04/07 | APP-C09 |
| discardDraft | 200 Mutation | application APP-04/07 | APP-C06/C09/C19 |
| uploadPhoto | 201 Mutation | application APP-04/07 | APP-C07/C08 |
| deleteDraftPhoto | 200 Mutation | application APP-04/07 | APP-C09 |
| getPhoto | 200 бинарное фото | application APP-04 | APP-C07/C27 |
| submitBundle | 202 Mutation с Job | processing, client APP-08 | APP-C11/C12 |
| retryBundle | 202 Mutation с Job | processing, client APP-10 | APP-C21/C22 |
| skipBundle | 200 Mutation | processing, client APP-10 | APP-C21 |
| getBundleHistory | 200 BundleHistory, staff-only | application APP-04, UI release | APP-C27 |
| deleteTask | 200 Mutation | application APP-04/10 | APP-C20 |
| saveReview | 200 Mutation | application APP-04/09 | APP-C17/C18 |
| skipTask | 200 Mutation | processing, client APP-10 | APP-C22 |
| getJob | 200 Job | processing, client APP-08 | APP-C14 |
| beginCompletion | 200 Mutation | processing, client APP-11 | APP-C23 |
| finalizeCheck | 202 Mutation с AnalyticsJob | processing, client APP-11 | APP-C24 |
| getSummary | 200 Summary | processing, client APP-12 | APP-C25/C26 |
| getSummaryHistory | 200 SummaryHistory, staff-only | processing, UI release | APP-C27 |
| refreshSummary | 202 Mutation с новым Job | processing, client APP-12 | APP-C25 |
| retrySummary | 202 Mutation с новым Job | processing, client APP-12 | APP-C25 |
| listStaffChecks | 200 StaffChecks | release, общий auth/shell APP-03/06 | APP-C27 |
| getStaffCheck | 200 StaffCheck | release, общий auth/shell APP-03/06 | APP-C27 |
| ingestEvents | 202 EventsAccepted | processing, emits APP-13 | APP-C29 |

31 пара method/path общего ux-flows покрыта этой таблицей и кейсами. Дополнительно учтены backend deleteBundle, getJob и ingestEvents; отсутствие отдельной teacher-кнопки для служебного endpoint не повод добавлять продуктовую функцию. Главные teacher actions: back/cancel/close/save/refresh/more; login/logout/create; addNotebook; camera/gallery/add/replace/remove/discard; submitStay/submitNext/nextNotebook; openReady/zoom/agree/disagree/comment/nextResult; retry/skip/changePhotos/delete; begin/finalize; read/refresh/retry summary. Их условия заданы shared S00–S11.

## APP-C01. Pinned bootstrap и безопасность импорта

**Задача/основание:** APP-01; A25. **Вход:** чистые checkout и source SHA `d62f5ecb8c1c53b1c97faf06530b8d84e691f88d`.

**Шаги:** проверить source status/HEAD, собрать manifest tracked blobs, осмотреть исключения, импортировать в целевой repo, воспроизвести исходные проверки. **Ожидается:** source не изменен; project-context не перезаписан; нет env/secrets/cache/school data; каждый файл объяснен manifest; lock/runtime и реальные ошибки зафиксированы. HTTP здесь неприменим.

**Команда/доказательство:** M(APP-C01): `git -C <source> status --short`, `git -C <source> rev-parse HEAD`, manifest-diff; затем `npm test`, `npm run build`, из app `python -m pytest`. Это будущие прогоны, результат каждого отдельно.

## APP-C02. B1 bootstrap, миграции и ранний seed

**Задачи:** APP-02/03; A01/A12/A13/A19. **Вход:** B0/B1b, чистый изолированный Compose, явный fixture.

**Шаги:** build; `docker compose -f compose.yaml run --rm migrate`; `up -d`; `exec backend python -m pilot.operations.create_fixture_accounts`; повторить seed; login/createCheck/createNotebook/createBundle/uploadPhoto/submitBundle/getJob. **Ответы:** соответственно 200/201/201/201/201/202/200; DB и Job реально сохранены, два teacher+staff доступны, повтор seed не меняет действующие пароли молча. Worker/API health без платного вызова; API/worker видят один photo volume.

**Проверка:** M(APP-C02), H(APP-C02). Команды и env-имена в BOOTSTRAP, пароли/ключи не в argv/выводе. Повтор migrate не выполняет SQL дважды; применение/runner проверяет processing, application фиксирует интеграционный результат.

## APP-C03. Вход, cookie, session, logout

**Задачи:** APP-03/06; A01/A12. **Вход:** H:login/getSession/logout и локальные fixture accounts.

**Шаги:** войти, получить session, перезагрузить, выйти, запросить session снова; отдельно неверный пароль/Origin. **Ожидается:** login 200 Session без token; HttpOnly/SameSite=Lax, Secure при HTTPS; getSession 200 правильная роль, logout 204 без body, затем 401. Неверные реквизиты 401, запрещенный Origin 403; отсутствие регистрации и выданный аккаунт в коротком UI. Обработка принятого Job не отменяется logout.

**Команда:** U(APP-C03), H(APP-C03), M(APP-C03). Проверить что пароль/cookie отсутствуют в логах/telemetry.

## APP-C04. Название, история, возврат, pagination

**Задачи:** APP-04–06; A01/A12. **Вход:** H:createCheck/listChecks/getCheck, title «ДЗ 19 ноября».

**Шаги:** пустой title → ввести название → createCheck → listChecks/getCheck; создать больше страницы в test DB; открыть next_cursor. **Ожидается:** пустое поле не отправляется; create 201 Mutation с check_id и revision; GET 200 показывает свой title/phase/created_at. History включает editing/review/finalized, page created_at desc,id desc без дублей; повторное открытие не вызывает submit/finalize. Класс/тема/ФИО/rename отсутствуют.

**Команда:** U(APP-C04), H(APP-C04). После server409 не показывать созданный дубликат.

## APP-C05. Нумерация тетрадей и удаление

**Задачи:** APP-04/06/10; A01/A14/A15. **Вход:** H:createNotebook/deleteNotebook, одна редактируемая проверка.

**Шаги:** POST без body дважды с разными ключами, удалить тетрадь 1 после cancel/confirm, создать еще одну. **Ожидается:** каждый create 201; GET показывает numbers1,2, затем 2,3, без повторного номера 1. Cancel не отправляет DELETE; confirm 200 исключает ровно тетрадь с потомками. UI использует number напрямую, нет поля имени. PATCH rename не существует.

**Команда:** U(APP-C05), H(APP-C05). Финализированная проверка отклоняет создание/удаление 409.

## APP-C06. Независимый Bundle, пустой draft и discard

**Задачи:** APP-04/07; A02/A14/A15. **Вход:** H:createBundle/discardDraft/deleteBundle.

**Шаги:** createBundle 201; getCheck 200 → Bundle с draft, current_input null. Пустые submit-кнопки недоступны; добавить фото; уйти → явный submit/discard/cancel. Discard200 удаляет только неотправленный input; deleteBundle 200 проверяется API напрямую без новой teacher-функции.

**Ожидается:** пустой draft не отправлен и не блокирует финал, непустой не теряется; deleteBundle не затрагивает независимый соседний комплект/тетрадь. Изменения только через domain ports.

**Команда:** U(APP-C06), H(APP-C06), M(APP-C06).

## APP-C07. Upload, форматы и приватная выдача

**Задачи:** APP-04/07; A02/A06. **Вход:** H:uploadPhoto/getPhoto, synthetic-photo.png64×64 из shared и плановые синтетические JPEG/PNG/WebP/HEIC/HEIF с manifest.

**Шаги:** multipart `file` каждого формата в draft, затем приватный getPhoto. **Ожидается:** upload 201 только после сохранения; normalized photo200 с корректным media_type, orientation и `private,no-store`; HEIC/HEIF не отсекаются frontend и конвертируются сервером. Оригинал приватный, JPEG/PNG/WebP без ненужного перекодирования. В getCheck порядок photo_ids и image associations сохранены. PNG64×64 проходит общие 8000000 байт/36Mпикселей/min32 и Settings, скрытого min240 нет. Asset после конвертации за пределами общей политики дает 422 до accepted, без молчаливого resize.

**Команда:** H(APP-C07), U(APP-C07); M(APP-C07) фиксирует реальный mobile файл отдельно от синтетического. Нет публичного URL оригинала/файлового пути в DTO.

## APP-C08. Отказ файла и несохраненная передача

**Задачи:** APP-04/05/07; A02/A13/A22. **Вход:** H:bad-photo, синтетические PDF/битыйJPEG/файл выше MAX_IMAGE_BYTES/разрешение выше MAX_IMAGE_PIXELS.

**Шаги:** выбрать/передать каждый файл, оборвать передачу до подтверждения, восстановить связь. **Ожидается:** формат 415, повреждение 422, размер 413, допустимость resolution по общему validator422; ErrorResponse безопасен. Пока нет 201, только preview/uploading, не «принято». Другие фото draft не теряются, камера/галерея позволяют замену. После сомнительного исхода getCheck/replay того же upload key, без двойного asset.

**Команда:** H(APP-C08), U(APP-C08), M(APP-C08). Значения ограничений только из LOCAL_ENV, не видимая квота учителю.

## APP-C09. Порядок, замена draft-фото, удаление

**Задачи:** APP-04/07; A02/A04/A15. **Вход:** H:reorderPhotos/deleteDraftPhoto/discardDraft, draft с photo A,B.

**Шаги:** reorder на B,A (PATCH полного photo_ids)200; заменить A: upload C201→deleteDraftPhoto A200→reorder B,C200. Каждый шаг использует revision предыдущего Mutation. Отмена диалога удаления не отправляет запрос. Повторить со сбоем между шагами.

**Ожидается:** полный порядок точен, новый факт getCheck после сбоя показан без ложной атомарности; sealed и старые отзывы не меняются. Удаление – только `/input-versions/{input_version_id}/photos/{photo_id}`, запечатанная версия 409; дублированные photo_ids нарушают uniqueItems и дают 422, существующий объект другого аккаунта не раскрывается 404.

**Команда:** H(APP-C09), U(APP-C09), M(APP-C09).

## APP-C10. Camera/gallery и предпросмотр

**Задача:** APP-07; A02/A06. **Вход:** мобильный браузер/эмуляция, разрешенная и запрещенная камера, те же файлы APP-C07.

**Шаги:** camera→cancel; camera→снимок→preview; add→снять продолжение; повторить через gallery; запретить камеру. **Ожидается:** cancel не добавляет фото; preview показывает порядок текущей тетради, add не submit. При denied gallery остается доступна. Backend upload 201 – единственное подтверждение сохранения. Нет crop/ручного rotate/PDF/отдельного учебника.

**Команда:** U(APP-C10), M(APP-C10). Записать реальный Android/iPhone либо not_run; fake getUserMedia в тесте не назвать реальной съемкой.

## APP-C11. Потерянный submit response и два клика

**Задачи:** APP-05/08; A13. **Вход:** H:submit-response-lost-replay и same-key-different-payload.

**Шаги:** submitBundle принят сервером, скрыть ответ; второй клик/reload повторяет тот же input_version_id+key. **Ожидается:** оба ответа 202 относятся к одному Job/input; getCheck 200 показывает один current Job, без второго набора задач/списания от клиента. Измененный payload с тем же ключом 409; после принятого replay перечитать current revision, не понижать store до старого Mutation.check_revision.

**Команда:** U(APP-C11), H(APP-C11) с общим доменом/route processing, M(APP-C11). HTTP stub доказывает клиентский replay, DB exactly-once проверяет processing/release отдельно.

## APP-C12. Submit stay/next и пустой переход

**Задачи:** APP-07/08; A04/A14. **Вход:** H:submitBundle/createBundle/createNotebook, запаздывающий checker.

**Шаги:** submitStay; затем новый draft текущей тетради; второй раз submitNext. Пока ответ не 202, не менять тетрадь. После 202 создать следующую серверную тетрадь/Bundle; в пустом draft next без submit.

**Ожидается:** оба отправляющих действия имеют одинаковый POST input; sealed неизменяем, следующая съемка не ждет LLM. Переход не завершает Check/не запускает summary. Непустой draft на обычном next требует решения, не исчезает.

**Команда:** U(APP-C12), M(APP-C12); статусы 202/201/201 и сохраненная принадлежность фото проверяются по трассе.

## APP-C13. Все четыре сценария страниц

**Задачи:** APP-07–09; A03/A04/A05. **Вход:** K01, E_C01, M06 в frozen examples; L:two-photo-continuation. Для single-task-two-photo создать явно синтетическую wrapper-фикстуру с неизмененной второй Task M06 и двумя фото, без выдуманной математики.

**Шаги:** отрендерить/пройти submit→getCheck для 1 фото/1 задача; 1 фото/несколько; 2 фото/1 продолжение; целая+начало/продолжение на 2 фото. **Ожидается:** независимых карточек соответственно 1,2,1,2, у продолжения photo_indices=[1,2], не третья задача. Отзыв каждой выделенной задачи независим. Незагруженные номера не объявляются пропущенными.

**Команда:** U(APP-C13), M(APP-C13) на fixture transport, status submit 202/getCheck 200. Это проверка интеграции/рендера заданного ответа, не качества распознавания реальных фото.

## APP-C14. Готовность вне очереди и Job states

**Задачи:** APP-05/08; A12/A19. **Вход:** L:completion-waits-checker и два синтетических Bundle, второй завершается раньше первого.

**Шаги:** poll getCheck/getJob 200, открыть готовую карточку второго, продолжить снимать; завершить первый. Поочередно показать queued/running/retry_wait/blocked/unknown.

**Ожидается:** результаты у исходных тетрадей и правильных input; камера/открытая карточка/фокус не переключаются автоматически. Один Report публикуется целиком, streaming частей не обещается; targeted getJob совпадает с current Bundle.job. Нет таймера отказа на 15 сек, неизвестный исход не запускает автоматический новый запрос.

**Команда:** U(APP-C14), M(APP-C14); долговечность/restart дополнительно APP-C31 и release.

## APP-C15. Компактный рендер и конкретная первая ошибка

**Задача:** APP-09; A05/A06/A18. **Вход:** E_C01/K01/M06 без изменения.

**Шаги:** открыть карточки, увеличить фото/переключить страницу, прочитать evidence и FirstError. **Ожидается:** E_C01 неверно `(2x−1)(6x−1)=0`, исправление `(2x−1)(6x+1)=0`; K01 first_error=null без пустых секций; M06 ошибка на фото 2, исправление `x₂=−4/20=−1/5=−0,2`. Не более 4 evidence, raw rule/explanation сохранены, нет полного OCR/эталонного решения/подсветки координат.

**Команда:** U(APP-C15), M(APP-C15), getCheck/getPhoto 200. Исходных фото dev-примеров в пакете нет: synthetic media доказывает zoom-механику, не визуальное совпадение почерка.

## APP-C16. Незавершенность, сокращение, неоценимость

**Задачи:** APP-09/10; A03/A05/A18. **Вход:** oracle.input Task с all_steps_correct+incomplete; mixed.input not_assessed; плановый валидный synthetic omitted_steps.

**Шаги:** отрендерить каждую, открыть подробное пояснение, перейти дальше без отзыва. **Ожидается:** корректное начало не подписано завершенным; incomplete не добавляет ошибку. Omitted_steps не штрафуется за краткость, отсутствие строки в evidence не считается пропуском ученика. Not_assessed не имеет зеленого/красного review, есть причина/skip. Не придумываются условие/правило/диагноз описки; next не подтверждает.

**Команда:** U(APP-C16), M(APP-C16), read 200; без мутации от одного просмотра.

## APP-C17. Независимые согласие/красный отзыв

**Задачи:** APP-04/09; A07. **Вход:** E_C01 wrapper с двумя review=null; H:saveReview.

**Шаги:** у ошибочной ученической задачи agree → PUT с точным analysis_id/state=confirmed/comment=""; у соседней disagree без комментария. **Ожидается:** оба 200 Mutation, первый review.confirmed, второй system_error, исходный анализ неизменен. Зеленый текст оценивает ИИ, не ученика. Красный отзыв не вызывает retryBundle/worker/автоотключение; соседняя кнопка не подтверждается массово.

**Команда:** U(APP-C17), H(APP-C17), M(APP-C17). Проверить payload и сохраненное getCheck 200.

## APP-C18. Смена отзыва, комментарий, ошибки save

**Задачи:** APP-04/09/12; A08/A17. **Вход:** H:saveReview/review-conflict/stale-analysis; L:comment-keeps-analytics-current/review-change-stales-analytics.

**Шаги:** confirmed→system_error→confirmed, добавить/очистить comment отдельным save, затем имитировать 409/сетевой сбой. **Ожидается:** успешные PUT 200 меняют только целевой актуальный анализ; state change после финала stale=true, comment-only не меняет data_revision/числа и не запускает LLM. 409 не перезаписывает новую версию, unsaved текст остается локально, нет ложного «сохранен». Красный отзыв допускает пустой комментарий.

**Команда:** U(APP-C18), H(APP-C18), M(APP-C18).

## APP-C19. Replacement, cancel и новое поколение 2→3

**Задачи:** APP-04/10; A09/A14. **Вход:** L:multi-task-confirmed/new-segmentation-two-to-three; H:createInputVersion/discardDraft/submitBundle.

**Шаги:** открыть replacement с текущими photo_ids201; изменить draft, затем cancel/discard200; повторить и submit 202; получить новое поколение 200. **Ожидается:** до submit старые согласия сохранены; после него все затронутые reviews сняты и старое result не current. Новых задач ровно 3, все с новыми server task/analysis IDs и review=null; не 5 и не перенос по похожей формуле. Другой Bundle не затронут. Старый поздний ответ не заменяет новый.

**Команда:** U(APP-C19), H(APP-C19), M(APP-C19). После финала createInputVersion/submit дают 409, соответствующих кнопок нет.

## APP-C20. Delete с отменой и общим фото

**Задачи:** APP-04/10; A15. **Вход:** L:task-deleted-report-retained; H:deleteTask/deleteNotebook/deleteBundle/deleteCheck/finalized-composition.

**Шаги:** для каждого UI-объекта cancel → getCheck без изменения; confirm → DELETE 200. Удалить одну задачу общего фото; отдельно целую проверку с pending Job; доставить поздний ответ.

**Ожидается:** task удалена из active, соседняя Task и photo asset доступны 200, исходный Report/старый отзыв только в staff history. Notebook/Bundle/Check удаляют ровно своих потомков, чужие не затронуты; удаленное get404, позднее не восстанавливается. После finalized deleteTask 409, deleteCheck 200 разрешен. Нет корзины/физического обещания удаления всех копий.

**Команда:** U(APP-C20), H(APP-C20), M(APP-C20). DeleteBundle проверяется напрямую API, новой teacher-кнопки не создавать.

## APP-C21. Failed/uncheckable/blocked/unknown: retry и skip

**Задачи:** APP-08/10; A10/A11/A23/A24 в доле UI. **Вход:** L:failed-input-no-false-zero/unknown-input-no-false-zero/blocked-input-no-false-zero/uncheckable-skipped-input/skipped-unknown-attempt-reserve-retained.

**Шаги:** показать причину; retryBundle 202 только при Job.can_retry и после предупреждения общего входа; отдельно skipBundle 200 для допустимого failed/uncheckable/blocked/unknown с точным input_version_id. **Ожидается:** skip не review и не математический 0; материал виден, тетрадь partial. Unknown skip подавляет позднюю публикацию, но не утверждает бесплатный исход. UI не запускает второй автоповтор и не предлагает учителю баланс/паузы.

**Команда:** U(APP-C21), M(APP-C21); финансовые/Attempt инварианты проверяет processing/release, не mock UI.

## APP-C22. Mixed Report: task skip и whole retry

**Задачи:** APP-09/10; A07/A10/A17. **Вход:** L:mixed-skip-only-one-task; H:skipTask/retryBundle.

**Шаги:** у not_assessed skipTask с analysis_id200; пригодную соседнюю подтвердить saveReview 200. Затем отдельно запросить разрешенный retryBundle 202 после явного предупреждения.

**Ожидается:** первый skip касается только неоценимой задачи, ее review отсутствует; соседний confirmed сохранен, может быть в топе, тетрадь вне среднего. Retry заново проверяет весь Bundle и снимает все его отзывы, не запускает /tasks/retry. Модельные task_id не принимаются вместо server IDs.

**Команда:** U(APP-C22), M(APP-C22); новые результаты все review=null.

## APP-C23. Первый finish, блокеры и пустая проверка

**Задача:** APP-11; A16. **Вход:** H:beginCompletion/finalize-pending; L:completion-waits-checker/unsent-draft-blocks-finalize плюс synthetic empty Check.

**Шаги:** beginCompletion 200; по очереди pending, unreviewed, unresolved_tasks/bundles, непустой draft, empty-check. **Ожидается:** phase=review, нет AnalyticsJob/фиксации состава. Готовые карточки доступны, материалы редактируются. Финал недоступен при can_finalize=false. При всех счетчиках 0, но без sealed input – finish.empty и camera/gallery; нет ложного нулевого финала. Unresolved задачи/комплекты не подписаны общим числом задач. Draft можно отправить/удалить.

**Команда:** U(APP-C23), M(APP-C23). Прямой finalize/устаревшее разрешение при блокерах 409.

## APP-C24. Финал и потерянный ответ

**Задачи:** APP-05/11; A14/A16. **Вход:** L:red-resolves-review-excluded-from-math/finalize-queues-analytics; H:finalizeCheck.

**Шаги:** при серверном can_finalize=true открыть диалог, cancel не меняет данные; confirm finalize 202; повторить клик/потерять ответ/открыть второй клиент. **Ожидается:** один snapshot/AnalyticsJob, finalized, summary queued; повтор key возвращает тот же Job, новый key после финала не создает второй. Ни один null review не становится confirmed. system_error/skip сохраняются исключенными, состав закрыт. Read/saveReview/deleteCheck разрешены; изменение состава 409.

**Команда:** U(APP-C24), M(APP-C24), общие DB race tests processing/release. API-path, не только mock, обязателен до B4.

## APP-C25. Summary capabilities и устаревший snapshot

**Задачи:** APP-11/12; A16/A17. **Вход:** все L:stale-analytics-*; L:fresh-failed-analytics-can-retry/comment-keeps-analytics-current; H:getSummary/refreshSummary/retrySummary.

**Шаги:** прочитать GET 200 во всех состояниях; менять review state/comment; нажимать разрешенную операцию. **Ожидается:** fresh failed can_retry=true,!stale → retry 202 того же snapshot; stale failed → только refresh 202 при can_refresh. Stale queued/blocked can_refresh=true позволяет новый snapshot с атомарным supersede еще неотправленного; running/retry_wait/unknown can_refresh=false, кнопка недоступна и короткий статус. Client не вычисляет безопасность из enum. Comment-only не stale/не Job; GET не создает запрос. Старый поздний ответ не снимает stale/не заменяет выбранное новое.

**Команда:** U(APP-C25), M(APP-C25); снимки сравнить по snapshot_id/job_id/data_revision, не только по картинке pending.

## APP-C26. Числовой oracle, null и топ

**Задача:** APP-12; A17/A18. **Вход:** analytics/fixtures oracle, zero-denominator, mixed, synonyms input/result пары.

**Шаги:** подать валидированный result через getSummary 200, открыть подробные состояния Check. **Ожидается oracle:** total4, with_errors1, without_errors1, partial1, empty1; среднее 0,5 и знаменатель 2; incomplete1, disputed1; две строки топа, каждая 1. Подтвержденная ошибка partial тетради в топе, вне среднего. Zero-denominator average=null – «Нет полностью подтвержденных тетрадей», не 0. Для положительного знаменателя/нулевых ошибок показать 0, отдельное пустое топ/no_errors, не no_data. Synonyms отображает готовую смысловую группу, не собственную группировку клиента. Пропуски/спорное не добавляют математику.

**Команда:** U(APP-C26), M(APP-C26). Сверять raw число и видимый русский формат, не только наличие заголовка.

## APP-C27. Teacher/private assets и поэтапная staff-интеграция

**Задачи:** APP-03/04/06/14; A01/A20/A22. **Вход:** H:foreign-account/unauthenticated-photo/teacher-cannot-read-history и staff history fixtures.

**До B4:** teacher A/B с одинаковыми title; B запрашивает Check/photo A; без cookie getPhoto; teacher getBundleHistory. Staff входит общим login и читает допустимые getBundleHistory/getSummaryHistory/getPhoto через уже реализованные app/processing handlers. Полный staff router и src/pilot/staff до B4 не импортируются; отсутствие будущего модуля не ломает сборку.

**После REL-04/B4:** release подключает listStaffChecks/getStaffCheck и настоящий staff UI в принятых main/router/src/App.tsx. Проверить ответы200, query owner_login точный, доступ к history200. Эта часть — поздний integration scope APP-C27 вместе с REL-C07, не prerequisite раннего B1/B3/B4.

**Ожидается:** чужое404, без cookie401, teacher history403; staff только читает материалы, его teacher-mutation403 и отзывы не меняются. Фото отдается после проверки прав, пути/секреты не раскрываются. Staff-read/audit не считаются временем учителя. До B4 не требуется ложный200 от еще не реализованного list/get staff.

**Команда:** H(APP-C27); U(APP-C27) для ранней auth/query/asset части; M(APP-C27) для позднего staff UI после REL-04. Итог всей A20 принимает release. В HANDOFF результаты двух частей отмечаются раздельно.


## APP-C28. Два клиента, текущий revision и stale analysis

**Задачи:** APP-04/05/10/11; A08/A09/A13/A16. **Вход:** H:review-conflict/stale-analysis, две сессии одного teacher.

**Шаги:** A читает revisionN, B меняет отзыв/worker публикует результат, A пишет старый If-Match либо старый analysis_id. **Ожидается:**409, серверный current_revision; A не перезаписывает B и не считает старое can_finalize разрешением. GET 200 обновляет состояние; новый явный выбор имеет новый key и актуальный analysis_id. Поздний старый GET/Mutation replay не откатывает store. Idempotent replay принятой операции проверяется до guard, не заставляет придумывать новую операцию.

**Команда:** H(APP-C28), U(APP-C28), M(APP-C28).

## APP-C29. Client telemetry и отказ доставки

**Задача:** APP-13; A21/A22. **Вход:** H:ingestEvents; Event enum shared.

**Шаги:** capture/photo/result open-close/visible-hidden/heartbeat; отправить batch≤100, повторить те же ID; отключить endpoint; два устройства. **Ожидается:**202 accepted_ids без дубля наблюдения; error не блокирует submit/review/finalize. Session UUID различает устройства. Нет actor/role/payload/comments/photo/math/secrets в client body; create/review/finalize бизнес-факты не дублируются выдуманным enum. Серверная дедупликация/отказ чужих ссылок – processing.

**Команда:** U(APP-C29), M(APP-C29), проверить сеть и безопасный журнал на синтетике; видимость не считается точным временем чтения.

## APP-C30. Мобильное чтение и короткие сообщения

**Задачи:** APP-06–12/15; A06/A25. **Вход:** экраны S00–S10, длинные формулы/объяснения, 320px и text200%.

**Шаги:** пройти формы, preview, zoom, результаты, оба отзыва/комментарий, диалоги, финал, ошибки и summary; клавиатура/фокус/scroll. **Ожидается:** основной текст≥18CSSpx, пояснения≥16, кнопки≥48px, две полные подписи отзывов в отдельных строках; клетка/палитра сохранены, текст на спокойной поверхности. Ничего не перекрыто footer/keyboard/safe area; формула имеет локальную прокрутку, карточка не обрезана. Цвет дополняет текст/значок, контраст по MOBILE_UX. Только текущий статус/нужный диалог, без технических подробностей. Fixture метка постоянна и кратка.

**Команда:** U(APP-C30), M(APP-C30); реальное устройство и эмуляция в отчете раздельно. HTTP200/201/202 по соответствующим предыдущим кейсам.

## APP-C31. Закрытие, reload и локальный restart

**Задачи:** APP-02/05/08/10; A12/A13/A19. **Вход:** принятый submit 202, сохраненные фото/отзывы, часть pending.

**Шаги:** закрыть браузер, дождаться fixture-worker, открыть на другом устройстве; локально restart backend/worker без удаления volumes, войти снова. **Ожидается:** getCheck/getPhoto 200 возвращают те же актуальные материалы; Job продолжился без UI, нет нового submit/дублей задач/возврата старой версии. Неотправленный локальный файл не объявлен сохраненным. Перезапуск не удаляет DB/photo volume.

**Команда:** M(APP-C31), `docker compose -f compose.yaml restart backend worker`; worker-level exactly-once/unknown/reserve assertions принадлежат processing/release, application записывает наблюдаемый API/UI результат, а не угадывает backend факт.

## APP-C32. Однократная передача B4 и ownership

**Задачи:** APP-14/15; A25. **Вход:** code/baseline/contract commits, заполненный HANDOFF.

**Шаги:** сопоставить diff с MODULE_BOUNDARIES, перечислить передаваемые общие файлы и два seed-файла, получить запись приема release и commit. **Ожидается:** до приема application – один владелец, после B4 main/router/Compose/общие frontend-конфиги/infra/docs/scripts/seed – release. `app/config.py` остается processing и в передачу application не входит. Вечерний application diff не содержит shared/generated/domain/SQL/staff/переданных конфигов; fixes чужой области идут интегратору. Часы сами не переключают владельца.

**Команда:** M(APP-C32), `git diff --name-only <baseline>...<codecommit>` и просмотр HANDOFF обеих сторон. Нет выдуманного SHA/успеха; HTTP неприменим.

## APP-C33. Полный B4 путь и вечерний кандидат

**Задачи:** APP-11–15; A01–A18/A21/A22/A25 в своей доле. **Вход:** integration baseline, реальная локальная DB/worker с fixture transport, минимум две тетради.

**Шаги:** login 200→create/draft/photo201→submit 202→getCheck 200→saveReview 200→reload→beginCompletion 200→разрешить блокеры→finalize 202→getSummary 200 pending→saved result; изменить state→stale→refresh 202→current; fresh failed→retry 202. Выполнить APP-C11/C24 для replay.

**Ожидается:** приложение использует настоящие локальные HTTP/DB/queue, только LLM transport подставной и помечен «Учебный режим». Сохранены правильные числа/версии/отзывы, состав закрыт только на финале. B4 не содержит функционального TODO аналитики. Кандидат 20:15 и итог 21:00 фиксируются release, application передает UI fixes и проверки без внешнего deploy.

**Команда:** M(APP-C33), полный `npm test`, `npm run build`, из app `python -m pytest tests/pilot/application -q`; независимый e2e runner создается release, его результат не присваивается application без реального запуска.

## APP-C34. Отсутствие лишнего и transport fail-closed

**Задачи:** APP-01/02/06/15; A25. **Вход:** обычный polza без ключа и явный fixture profile; old source routes/links.

**Шаги:** проверить config/route map/собранный UI и сетевые обращения; запустить fixture без ключа, отдельно polza без ключа. **Ожидается:** fixture явно отмечен common.fixture_mode, не распознает произвольные реальные фото под видом модели. Polza без ключа отказывает доdispatch, не переходит на fixtures и не показывает фальшивый success. Один PILOT_TRANSPORT управляет API/worker/frontend. Нет публичной регистрации/anonymous analyze, quotas3/20/pricing/upsell/CAS/export/PDF/offline/push/редактора OCR/rename/роли operator/HTTP pause. Поля класса/темы/ФИО не требуются. Старые пути отключены серверно, обычный frontend не включает рекламную аналитику/внутренние benchmark-инструменты.

**Команда:** U(APP-C34), H(APP-C34), M(APP-C34). Политика Settings/имена env – LOCAL_ENV; не изобретать AUTH_ENABLED.

## APP-C35. Безопасные ошибки и границы доказательства

**Задачи:** APP-03–05/09/13–15; A22/A25. **Вход:** синтетический недоверенный LaTeX/HTML, invalid DTO, server503, неверный file, telemetry error.

**Шаги:** вызвать ошибки/невалидные payload и просмотреть UI/network/log без секретов; проверить renderer и HANDOFF. **Ожидается:** JSON/формулы не исполняют HTML/script/доверенные команды; ошибка схемы не рисует частичный success. Сообщения короткие, без HTTP/provider/balance/key/traceback. Общие логи не содержат фото/Base64/raw Report/comment/password/cookie. Fail/not_run видны в отчете, fixture/эмуляция не названы live/реальным устройством/апробацией.

**Команда:** U(APP-C35), H(APP-C35), M(APP-C35); безопасные synthetic traces и выводы в HANDOFF, не production-ответы.

## Покрытие общей матрицы

| A-ID | Задачи application | Проверки application / граница другого владельца |
|---|---|---|
| A01 | APP-03/04/06 | APP-C02–05/C27 |
| A02 | APP-04/07 | APP-C07–10 |
| A03 | APP-07/09 | APP-C13/C16; математическое различение processing |
| A04 | APP-07/08/09 | APP-C09/C12–14 |
| A05 | APP-09 | APP-C15/C16; checker processing |
| A06 | APP-06/07/09/15 | APP-C10/C15/C30 |
| A07 | APP-04/09 | APP-C17/C22 |
| A08 | APP-04/05/09/12 | APP-C18/C28 |
| A09 | APP-05/10 | APP-C19/C28; транзакция processing |
| A10 | APP-10 | APP-C21/C22 |
| A11 | APP-08/10 | APP-C21 только UI; retry/restart invariant processing |
| A12 | APP-02/03/05/08 | APP-C03/C04/C14/C31 |
| A13 | APP-05/08 | APP-C08/C11/C28/C31 |
| A14 | APP-06/10/11 | APP-C05/C19/C24 |
| A15 | APP-04/10 | APP-C05/C06/C09/C20 |
| A16 | APP-05/11/12/14 | APP-C23–25/C33 |
| A17 | APP-09/12 | APP-C18/C22/C26 |
| A18 | APP-09/12 | APP-C15/C16/C26 |
| A19 | APP-02/08 | APP-C14/C31; массовая нагрузка 30×3–5 release |
| A20 | APP-03/04/06 | APP-C27 в auth/assets/mount; staff UI release |
| A21 | APP-13 | APP-C29; server receiver/audit processing |
| A22 | APP-03/05/13/14 | APP-C29/C35; независимый log audit release |
| A23 | APP-08/10 | APP-C21 только корректный UI; деньги/конкурентность processing/release |
| A24 | APP-08/10 | APP-C21 только UI paused; CLI release, механизм processing |
| A25 | APP-01/06/14/15 | APP-C01/C30/C32–35 |

Нет новых продуктовых блокеров. Непоставленные B1b symbols/миграции, непрошедший runtime или несовпадение контракта при реализации записываются конкретным BLK-application-NN с reproduction и владельцем, а не скрываются готовым fixture-экраном.
