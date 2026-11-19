# Состояние application и передача

Направление **application**. Срез 19.11.2026, статус **in_progress**. Код application собран локально. Полная приемка пилота зависит от B1b/B3 и остаётся **not_run**.

## Ревизии

| Артефакт | Факт |
| --- | --- |
| Цель | [TASKS APP-01–15](TASKS.md), [ACCEPTANCE APP-C01–35](ACCEPTANCE.md) |
| Pinned source | SmartNoteLanding d62f5ecb8c1c53b1c97faf06530b8d84e691f88d. Импорт и проверка blob описаны в [BOOTSTRAP](../../../../docs/pilot/BOOTSTRAP.md). |
| База и контракт B0 | 1144c498b4aba1e4e4fe118abe7c3f6f1b940198 на origin/main. Shared v1, API 1.0.0. |
| Application | Локальная work/application. Код 77cdbbddef6510a0a977936f75028c363ec3e2fe. |
| B1 / B4 / B5 | Объединённые commit и приемка **not_run**. Ветки integration/pilot-local на origin на момент начала работы ещё не было. |
| Transport | Браузерная подмена HTTP и ASGI doubles использованы явно. Реальный fixture-worker и polza **not_run**. |

## Что поставлено

- APP-01: импорт выбранных blob, исходные npm/build/pytest и проверяемый манифест.
- APP-02–04: Dockerfiles и Compose, API lifespan и router hooks, auth cookie и exact Origin, seed CLI, CRUD и приватное фото через processing.
- APP-05–13: мобильный учительский сценарий, HTTP-клиент с revision и ключами, фото и фоновые состояния, отдельный отзыв, замена/skip/retry, два шага финала, актуальная сводка и телеметрия. Сквозной код smoke подготовлен для совместного fixture-стека.
- APP-14: результаты и границы проверки зафиксированы ниже. B4 приём и APP-15 после B4 остаются в плане (planned).

## Фактические команды и результаты

| Проверка | Результат |
| --- | --- |
| Исходный npm test и npm run build из pinned SmartNoteLanding | PASS, 31 тест и сборка. Предупреждение Vite о чанке больше 500 КБ. |
| Исходный python -m pytest -q из pinned app с отдельной PostgreSQL 16.15 | PASS, 120 тестов. Первый запуск дал 6 ошибок ZoneInfo на Windows, после установки tzdata==2025.2 на временное окружение — PASS. |
| npm test и npm run build | PASS, 16 unit-тестов и сборка на Windows. Production build также прошёл внутри frontend-образа с отключённой сетью. Предупреждение Vite о чанке больше 500 КБ. |
| python -m pytest -q из app | PASS, 22 теста, включая 11 ASGI тестов с явными doubles. Starlette предупреждает о будущем отказе от httpx в TestClient. |
| npm run test:browser | PASS, Chrome на Windows, headless mobile 320 CSS px, перехват HTTP. Вход, история, открытие задачи/zoom, отдельный отзыв, reload, загрузка PNG из галереи и submit-next, выход. |
| docker compose -f compose.yaml config -q с синтетическими значениями | PASS. |
| docker compose -f compose.yaml build backend frontend | PASS из проверенной копии файлов в ASCII-пути. Из исходного кириллического пути локальный BuildKit завершился ошибкой gRPC о непечатаемых ASCII в заголовке сессии. |
| python scripts/check_context.py, shared/check_shared.py, planning/check_tasks.py и git diff --check | Проверки структуры и контракта. Shared gate прошёл 73 офлайн-теста. |
| Real Android/iPhone, полный B1/B4, Polza, внешний выпуск | **not_run**. |

## APP-C01–35

Статус в таблице относится к критериям кейса целиком. Выполненная проверка компонента записана отдельно от полного кейса. Для DB/e2e ожидаются реальные processing-порты и совместный стек.

| Кейсы | Статус | Текущее доказательство |
| --- | --- | --- |
| C01 | pass | Манифест, базовые npm/build и PostgreSQL pytest. |
| C02 | not_run | Compose config/образы и проверка параметров seed прошли. Миграции/пул/seed и Job требуют B1b. |
| C03 | not_run | ASGI double проверил cookie/exact Origin/session/logout; browser проверил вход и выход. |
| C04–C05 | not_run | ASGI double проверил названия, ETag, cursor и вызов создания тетради. Browser mock проверил навигацию по истории. Проверка двух аккаунтов и пагинации на БД впереди. |
| C06 | not_run | Начальный draft и submit-next упражнялись в browser mock. |
| C07–C09 | not_run | ASGI double проверил один multipart file, HEIC Content-Type и приватную бинарную выдачу. Unit проверил порядок. Транзакции и серверная нормализация форматов впереди. |
| C10 | not_run | Галерея, PNG и миниатюры проверены в Chrome. Реальные камера, отмена и разрешения Android/iPhone впереди. |
| C11–C12 | not_run | Unit воспроизвёл потерянный ответ и одинаковый ключ. Browser mock проверил submit-next. Реальный Job и restart впереди. |
| C13–C14 | not_run | Unit проверил continuation и состояния worker по lifecycle, browser — открытие готовой задачи. Полная матрица результатов на worker впереди. |
| C15–C16 | not_run | Unit проверил независимый вывод о незавершенности и безопасный текст. В браузере показана первая ошибка E_C01. |
| C17–C18 | not_run | ASGI double проверил точный analysis_id и пустой комментарий. Browser mock сохранил конкретный отзыв и перечитал проверку. |
| C19–C20 | not_run | UI отправляет отдельные guarded mutation; устойчивость поколений и сохранение соседнего фото проверяются на B1b/B3. |
| C21–C22 | not_run | Unit проверил разные статусы blocked/unknown/skipped. Модель поколений, worker и финансовые guards ожидают processing. |
| C23–C24 | not_run | Unit проверил ожидание, пустой сценарий, can_finalize и key replay. Сохранённый AnalyticsJob проверяется на B3. |
| C25–C26 | not_run | Unit проверил oracle 4 тетради, знаменатель, 0,5, частоты и stale UI. API свежести/refresh/retry проверяется на B3. |
| C27 | not_run | ASGI double проверил ранние auth/private photo/staff-only history. Staff UI и полные ACL ожидают REL-04 и общую БД. |
| C28 | not_run | Unit проверил защиту store от позднего GET и новый ключ после 409. Доменные гонки ожидают processing. |
| C29 | not_run | Unit проверил стабильность event ID на повторе, форму payload и разные session_id. Реальный ingest впереди. |
| C30 | not_run | Браузерный тест 320 CSS px без горизонтального overflow и визуальная проверка карточки. Физические устройства и масштабирование 200% впереди. |
| C31 | not_run | Browser mock проверил reload без повторного PUT. Перезапуск контейнеров/долговечность проверяются на B1. |
| C32–C33 | not_run | Commit B4, общий smoke и приём release ожидают B1b/B3. |
| C34 | not_run | Compose использует один источник transport; browser показывает учебную метку. Реальный запуск без ключа ждёт B1b. |
| C35 | not_run | Unit проверил отсутствие комментария в сохраняемых intent-метаданных, ASGI — ошибки входа/ACL и cookie; журнал processing проверяется в интеграции. |

## Блокеры и передача

- **BLK-application-01, B1b/B3.** В текущем checkout отсутствуют pilot.domain.*, pilot.contracts, pilot.routes.processing, pilot.routes.events и worker/migration runner. Импорт main упирается в pilot.domain. Без совместимой поставки невозможно запустить живые APP endpoints, проверить миграции/seed, приватность между аккаунтами, сохранённые Job и сводку. Источник app/config.py по-прежнему не принимает POLZA_TIMEOUT_SECONDS=300 и MIN_IMAGE_EDGE=32. Владелец портов и Settings — processing.
- **BLK-application-02, Summary.created.** В замороженном Summary нет даты сохранения текущего результата, а teacher не имеет доступа к SummaryHistory. Дата в интерфейсе появится после согласованного поля DTO. Текущее время или дата проверки не подставляются. Локальный выбор сейчас — скрыть строку даты. Для unassessed_tasks использован существующий текст result.no_result и отдельное число, так как в общем каталоге нет отдельной подписи.
- **B4.** Общие frontend/backend entrypoints, Compose, Docker/infra, конфигурация, docs, browser/API smoke и два файла fixture seed остаются у application до зафиксированного приёма release. Точные пути описаны в [границах модулей](../shared/MODULE_BOUNDARIES.md). app/config.py принадлежит processing. Доказательства и команды для совместного запуска — в [интеграционном состоянии](../../../../docs/pilot/INTEGRATION_STATE.md).

Критерий полного B4 остаётся прежним: begin → отдельные отзывы → finalize с replay → сохранённая summary на PostgreSQL и fixture-worker. Условия для следующего прогона описаны в [BOOTSTRAP](../../../../docs/pilot/BOOTSTRAP.md).
