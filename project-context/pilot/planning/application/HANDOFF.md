# Состояние application и передача

Направление **application**. Срез 19.11.2026. Статус: **in_progress**. Локальный учительский сценарий прошёл с processing, PostgreSQL и fixture-worker. Приём B4 со стороны release и проверки физических устройств остаются открыты.

## Ревизии

| Артефакт | Факт |
| --- | --- |
| Цель | [TASKS APP-01–15](TASKS.md), [ACCEPTANCE APP-C01–35](ACCEPTANCE.md) |
| Pinned source | SmartNoteLanding d62f5ecb8c1c53b1c97faf06530b8d84e691f88d. Импорт и проверка blob описаны в [BOOTSTRAP](../../../../docs/pilot/BOOTSTRAP.md). |
| База и контракт B0 | 1144c498b4aba1e4e4fe118abe7c3f6f1b940198. Shared v1, API 1.0.0. |
| Processing | origin/main 0f8460df6465612a815810b77eb2f60a72376350, SQL 001–015. Сгенерированные DTO совпадают с B0. |
| Application / B1 | Локальная work/application. Родитель кода application 92fd1e83ea17b2002b195ea0e555f8b75c8da899. Интеграционный commit INTEGRATION_COMMIT_SHA. |
| B4 / B5 | Доказательства application и перечень передачи подготовлены. Приём release и вечерний кандидат **not_run**. |
| Transport | Настоящий локальный HTTP, PostgreSQL и отдельный worker в явном режиме fixture. Есть отдельные проверки с перехватом HTTP и двойниками. Paid Polza **not_run** в application. |

## Что поставлено

- APP-01: импорт выбранных blob, исходные npm/build/pytest и проверяемый манифест.
- APP-02–04: Dockerfiles и Compose, API lifespan и router hooks, auth cookie и exact Origin, seed CLI, CRUD и приватное фото через processing.
- APP-05–13: мобильный учительский сценарий, HTTP-клиент с revision и ключами, фото и фоновые состояния, отдельный отзыв, замена/skip/retry, два шага финала, актуальная сводка и телеметрия. Сквозной код smoke подготовлен для совместного fixture-стека.
- APP-14: совместный путь до сводки и перезапуск проверены. Этот файл содержит доказательства и перечень передаваемых файлов. Приём B4 и проверки APP-15 после смены владельцев ожидают release.

## Фактические команды и результаты

| Проверка | Результат |
| --- | --- |
| Исходный npm test и npm run build из pinned SmartNoteLanding | PASS, 31 тест и сборка. Предупреждение Vite о чанке больше 500 КБ. |
| Исходный python -m pytest -q из pinned app с отдельной PostgreSQL 16.15 | PASS, 120 тестов. Первый запуск дал 6 ошибок ZoneInfo на Windows, после установки tzdata==2025.2 на временное окружение — PASS. |
| npm test и npm run build | PASS, 19 unit-тестов и сборка на Windows. Production build основной реализации также прошёл внутри frontend-образа с отключённой сетью. Предупреждение Vite о чанке больше 500 КБ. |
| python -m pytest --confcutdir tests/pilot/application tests/pilot/application -q из app | PASS, 24 ASGI-теста с общим валидатором, обработчиками ошибок и явными сервисными двойниками. |
| npm run test:browser | PASS, Chrome на Windows, headless mobile 320 CSS px, увеличение текста до 200%, перехват HTTP. Вход, история, разбор и отзыв, reload, загрузка PNG и submit-next, конкурентная 409, двухэтапный финал и показ готовой сводки. |
| docker compose -f compose.yaml config -q с синтетическими значениями | PASS. |
| docker compose -f compose.yaml build backend frontend | PASS из проверенной копии файлов в ASCII-пути. Из исходного кириллического пути локальный BuildKit завершился ошибкой gRPC о непечатаемых ASCII в заголовке сессии. |
| Compose migrate, up --wait и повторный seed | PASS. Чистая PostgreSQL 16.15, миграции 001–015, успешное повторное применение, postgres/backend/worker/frontend healthy. |
| python scripts/pilot/smoke_application.py --retry | PASS. Реальные HTTP/DB/worker, три аккаунта, пять форматов фото, приватность, история и нумерация, порядок и поколения комплектов, повторы submit/finalize и событий, сводка, refresh и retry того же snapshot после принудительного fixture-отказа. |
| npm run test:browser:compose | PASS. Chrome 320 CSS px, два комплекта, шесть отзывов, оба варианта отправки, двухэтапный финал, сводка после reload. |
| npm run test:browser:compose -- --restart | PASS. Два задания в queued при остановленном worker, закрытие браузера, restart backend/worker, новый браузерный контекст и вход. Идентификаторы Job и приватные фото сохранились. |
| Запуск backend в режиме polza без ключа с отключённой сетью | PASS. Startup отказал до открытия пула и внешних запросов. |
| python scripts/check_context.py, shared/check_shared.py, planning/check_tasks.py и git diff --check | Проверки структуры и контракта. Shared gate прошёл 73 офлайн-теста. |
| Real Android/iPhone, staff UI, приём B4, платный Polza, внешний выпуск | **not_run**. |

## APP-C01–35

Статус относится к кейсу целиком. Частичный результат записан в колонке доказательства. Проверки на fixtures не подтверждают качество модели и работу физической камеры.

| Кейсы | Статус | Текущее доказательство |
| --- | --- | --- |
| C01 | pass | Манифест, базовые npm/build и PostgreSQL pytest. |
| C02 | pass | Чистый Compose, миграции, повторный seed, три аккаунта, созданный и обработанный Job. |
| C03 | pass | Реальные 200/204/401/403 для auth, Chrome login/reload; приложен ASGI-тест заголовка cookie. |
| C04 | pass | На реальном API прошли пробельный title, нормализация названия, чтение Check и cursor без дубля. Chrome создал проверку и вернулся к сохранённой истории. |
| C05 | pass | На реальном API после удаления первой тетради остались номера 2 и 3, после финала состав закрыт. Chrome с перехватом HTTP подтвердил отмену диалога. |
| C06 | pass | На реальном API пустой submit вернул 409, discard непустого draft отозвал ссылку на его фото, delete сохранил соседний Bundle. Chrome при попытке уйти оставил непустой draft на экране. |
| C07–C09 | not_run | В Compose JPEG/PNG/WebP вернули исходные байты, HEIC/HEIF нормализованы в JPEG. Проверены 413/415/422, хранимый порядок фото, приватные headers и роли. Реальное мобильное фото и сбой между тремя шагами замены впереди. |
| C10 | not_run | Галерея, PNG и миниатюры проверены в Chrome. Реальные камера, отмена и разрешения Android/iPhone впереди. |
| C11–C12 | not_run | Реальный повтор ключа submit вернул исходный Job. Chrome прошёл submit-stay и submit-next. Отдельный полный сценарий потери ответа с двумя устройствами впереди. |
| C13–C14 | not_run | Unit проверил четыре комбинации фото и задач через K01/E_C01/M06, а также состояния worker по lifecycle. Browser проверил открытие готовой задачи. Полная матрица результатов на worker впереди. |
| C15–C16 | not_run | Unit проверил первую ошибку и исправление E_C01/M06, корректный K01, независимый вывод о незавершённости и безопасный текст. |
| C17–C18 | not_run | Chrome сохранил шесть независимых отзывов. API подтвердил изменение комментария без stale и смену state со stale. В браузере с перехватом HTTP подтверждён сохранённый локальный комментарий после 409 и новый ключ при явном повторе. |
| C19–C20 | not_run | На реальном API discard сохранил текущий результат и отзыв, submit новой версии опубликовал новые задачи без отзывов и сохранил соседний Bundle. Удаление одной задачи не удалило общее фото. Браузерная матрица замены и количества 2→3 отдельно не прогонялась. |
| C21–C22 | not_run | Unit проверил blocked/unknown/skipped. Неудачи и смешанные отчёты покрыты в processing; общая браузерная матрица впереди. |
| C23–C24 | not_run | Chrome прошёл обе стадии и получил сводку. На PostgreSQL повтор finalize вернул исходный AnalyticsJob, изменение состава после финала вернуло 409. Матрица всех blockers проверялась частями. |
| C25–C26 | not_run | UI проверил oracle и capabilities. Реальный API подтвердил stale и refresh с новым snapshot, а также fresh failed/retry без смены snapshot. Отдельные blocked/unknown состояния сводки проверены только по контрактным данным в UI и в processing. |
| C27 | not_run | Ранняя часть пройдена на реальном API: чужие Check/photo 404, анонимное фото 401, teacher history 403, staff history/photo 200 и staff mutation 403. Поздний staff UI ожидает REL-04. |
| C28 | not_run | Unit и Chrome с перехватом HTTP проверили старую ревизию и 409. Реальный worker выявил гонку перед загрузкой следующего черновика. Добавлена сверка актуальной версии и снимков перед загрузкой и после приёма submit. Исправление прошло с настоящим worker. |
| C29 | not_run | Реальный events endpoint вернул тот же accepted ID при повторе. Unit проверил форму, разные session_id и недоступную сеть. |
| C30 | not_run | Карточка разбора проверена в Chrome на 320 CSS px и при увеличении базового размера текста до 200%. Подтверждены отсутствие горизонтальной прокрутки страницы и минимальный размер кнопки отзыва. Физические устройства и остальные экраны при увеличении впереди. |
| C31 | pass | Два queued Job сохранились после закрытия браузера и перезапуска backend/worker с теми же volumes. В Chrome открыт тот же Check и получена сохранённая сводка. |
| C32 | not_run | Список файлов и SHA локальной сборки готовы. Требуется запись приёма release. |
| C33 | pass | Локальный общий путь на двух тетрадях пройден на реальном HTTP/PostgreSQL/worker, включая replay, reload, stale/refresh и fresh failed/retry того же snapshot. Кандидат release фиксируется отдельно. |
| C34 | pass | Fixture работает без ключа и явно подписан. Контейнер polza без ключа завершился на startup с отключённой сетью. Публичный signup и anonymous analyze отсутствуют в собранных entrypoints. |
| C35 | not_run | Unit проверил безопасный рендер и сохранённые intent-метаданные, API — ошибки доступа/файла. В журналах fixture backend/worker сверено отсутствие использованных реквизитов и текста отзыва. |

## Блокеры и передача

- **BLK-application-01 закрыт.** Processing из origin/main подключён. Compose, миграции, вход, приватные данные, Job и сводка проверены на общей базе. Настройки, миграции и generated DTO оставлены в версии processing.
- **BLK-application-02, Summary.created.** В замороженном Summary нет даты сохранения текущего результата, а teacher не имеет доступа к SummaryHistory. Дата в интерфейсе появится после согласованного поля DTO. Текущее время или дата проверки не подставляются. Локальный выбор сейчас — скрыть строку даты. Для unassessed_tasks использован существующий текст result.no_result и отдельное число, так как в общем каталоге нет отдельной подписи.
- **B4.** Общие frontend/backend entrypoints, Compose, Docker/infra, конфигурация, docs, browser/API smoke и два файла fixture seed остаются у application до зафиксированного приёма release. Точные пути описаны в [границах модулей](../shared/MODULE_BOUNDARIES.md). app/config.py принадлежит processing. Доказательства и команды для совместного запуска — в [интеграционном состоянии](../../../../docs/pilot/INTEGRATION_STATE.md).

Подготовленный список для записи приёма B4:

- Точки входа `app/main.py`, `app/pilot/router.py`, `src/App.tsx`, `src/main.tsx`.
- Сборка и конфигурация `compose.yaml`, `Dockerfile`, `app/Dockerfile`, `infra/pilot-python-constraints.txt`, `.env.example`, `.dockerignore`, `.gitignore`, `.github/workflows/application.yml`, `index.html`, `vite.config.ts`, `package.json`, `package-lock.json`, `tsconfig.json`, `tsconfig.app.json`, `tsconfig.node.json`.
- Seed `app/pilot/operations/__init__.py` и `app/pilot/operations/create_fixture_accounts.py`.
- Доказательства и команды `docs/pilot/BOOTSTRAP.md`, `docs/pilot/INTEGRATION_STATE.md`, `scripts/pilot/browser_smoke.mjs`, `scripts/pilot/browser_compose_smoke.mjs` и `scripts/pilot/smoke_application.py`.

Команды для независимого повторения локального прогона release находятся в [BOOTSTRAP](../../../../docs/pilot/BOOTSTRAP.md).
