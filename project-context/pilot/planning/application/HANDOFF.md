# Состояние application и передача

Направление: **application**. Статус: **planned**. Обновлено: 19.11.2026, 05:51 Asia/Yekaterinburg (UTC+05:00). Это состояние ТЗ; код приложения, ветки и runtime-проверки здесь не выполнены.

## Основание и ревизии

| Поле | Фактическое значение |
|---|---|
| Назначение | [README](README.md), [TASKS APP-01–15](TASKS.md), [ACCEPTANCE APP-C01–35](ACCEPTANCE.md) |
| База репозитория при подготовке ТЗ | `c4eed9a7b62b4e7b90fb77004d87fff75544aad4`; рабочая копия содержит общие незакоммиченные изменения, их не откатывать |
| Pinned source | SmartNoteLanding `d62f5ecb8c1c53b1c97faf06530b8d84e691f88d`; импорт **не выполнен** |
| Контракт | shared v1 / API1.0.0; [OpenAPI](../shared/api/openapi.json), [schema](../shared/api/schemas/domain.schema.json), [fixtures](../shared/api/fixtures/http.json), [lifecycle](../shared/api/fixtures/lifecycle.json), [LOCAL_ENV](../shared/LOCAL_ENV.md) |
| B0 contract commit | Не назначен; координатор фиксирует фактический SHA общего пакета перед реализацией |
| B1 baseline commit | Не создан; нужен объединенный B1a/B1b |
| Рабочая ветка/commit реализации | Не созданы; план `work/application` от опубликованного `integration/pilot-local` |
| Remote/PR/merge commit | Не зафиксированы этой задачей; публикация не выполнялась |
| Transport реализации | Не запущен; для приемки явно `PILOT_TRANSPORT=fixture`, обычный default polza без fallback |

Факт подготовки документов не означает статус ready для реализации. Кодовые пункты APP-01–15 и runtime APP-C01–35 пока **not_run**; будущий исполнитель заменяет строки реальными фактами, а не предполагает успех по существованию этого файла.

## Подготовлено

- Детальные задачи с целью/R/A, путями, входами B0/B1b, последовательностью и DoD; точные processing facade согласованы для тонких auth/CRUD routes.
- 35 приемочных сценариев и таблица всех 34 operationId; границы UI/HTTP/domain/staff/интеграционных проверок разделены.
- Ранний Compose/hooks/seed до B1 и порядок однократной передачи общих файлов/seed release в B4.
- Нормальная polza-конфигурация fail-closed и явный fixture с «Учебный режим», без нового HTTP DTO; Settings меняет processing, application проверяет wiring/совместимость.

Проверки общего пакета до этой реализации – [SHARED_REVIEW](../shared/SHARED_REVIEW.md). Они не являются APP-C pass. При подготовке этих четырех файлов 19.11.2026 механически проверены: 15 уникальных APP-задач, 35 уникальных APP-C, покрытие всех 34 operationId OpenAPI, существующие локальные ссылки, корректные CaseID и отсутствие пробельных хвостов – PASS. Повторно выполнен существующий `python project-context/pilot/planning/shared/check_shared.py` в изолированном dev-env – PASS: 158 UX-строк, 34 операции/44 HTTP/25 lifecycle, четыре пары аналитики и 73 офлайн-теста. Это документные/контрактные проверки, не APP-C и не runtime. Перекрестное ревью трех индивидуальных ТЗ выполняет координатор отдельно.

## Еще не реализовано

| Этап | Оставшийся результат | Кто продолжает |
|---|---|---|
| B1a | APP-01/02: manifest/pinned import, lock/runtime, hooks/Compose | application |
| B1b | Доменные модели/миграции/auth/storage/guard/services и fixture-worker | processing; application использует порты, не дублирует |
| B1a → B1 | APP-03: auth routes и минимальный create_fixture_accounts; код CLI в B1a, runtime на общей auth/schema до B1 | application, без ожидания release |
| B2 | APP-04–10: HTTP CRUD, teacher UI, сохраненные фото/разборы/отзывы/reload | application с API processing |
| B3/B4 | APP-11–14: реальный локальный путь финала/аналитики, тесты/передача | processing API; application UI+HTTP wiring |
| 18:00–21:00 | APP-15, независимая общая приемка и локальный кандидат | application fixes своего кода; release интеграция |

## Запуск и данные — создать при реализации

Все команды ниже **целевые**, их выполнение здесь не заявлено. Подробные параметры/ограничения – LOCAL_ENV и APP-02/03.

```text
docker compose -f compose.yaml build
docker compose -f compose.yaml run --rm migrate
docker compose -f compose.yaml up -d
docker compose -f compose.yaml exec backend python -m pilot.operations.create_fixture_accounts
npm test
npm run build
```

Backend application tests из `app/`: `python -m pytest tests/pilot/application -q`. Миграции/runner/worker предоставляет processing, собственные SQL здесь не создаются. Запуск не удаляет volumes. Для seed потребуются шесть env-имен, полностью перечисленных в APP-03 TASKS; без значений по умолчанию/печати паролей. `VISITOR_COOKIE_SECRET`, DATABASE_URL и остальные секреты только вне Git, не восстанавливать из предположений.

Плановые UI/media fixtures безопасные синтетические. Shared математические fixtures и frozen ответы read-only. Fixture transport не анализирует произвольную школьную фотографию и явно помечен; живые запросы/расходы, внешние устройства/сервер и школьная апробация не выполнены.

## Выполненные проверки реализации

| Проверка | Статус | Commit/результат/ограничение |
|---|---|---|
| Исходные npm/backend baseline | not_run | Импорт не выполнен |
| APP unit/build/HTTP tests | not_run | Код/runner предстоит создать |
| B1 Compose/миграции/seed | not_run | Нужны APP-01–04 и B1b |
| API smoke финала/аналитики | not_run | Обязателен B4 на реальной локальной DB/fixture-worker |
| Реальные Android/iPhone | not_run | Эмуляция/настоящее устройство фиксируются отдельно |
| Live LLM/платные расходы/deploy/апробация | not_run | В объем подготовки ТЗ не входят |

## Точные зависимости и блокеры

Новых продуктовых блокеров при подготовке ТЗ не выявлено. Непоставленные программные B1b-порты – плановая зависимость будущей работы, не доказательство дефекта processing. При реализации регистрировать фактический `BLK-application-NN`: severity; baseline/contract/code SHA; операция/fixture/команда; expected/actual; затронутые APP/A/C; владелец и следующий шаг. Не отмечать blocked из-за отсутствия встречи и не заменять отсутствующий domain локальным хранилищем.

Для следующего исполнения обязательно получить фактический B0 commit и B1b артефакты. Независимо можно начать manifest, fixture UI/client и тесты; auth/CRUD runtime проверяются после общей основы.

## Доказательство совместимости ядра на B4

Пока **not_run**. Заполнить: code/integration/contract commits, transport, test DB/provenance и команду APP-C33; ответы beginCompletion 200 → оценки → finalizeCheck 202 → AnalyticsJob → getSummary 200 с сохраненным result. Приложить replay финала, fresh failed retry, state-change stale/refresh и запрет refresh unknown/running. Проверить неизменность старых математических выводов/согласий вне затронутого комплекта. Prompt/schema без API-пути не считается полной передачей.

## Передача release в B4

Факт передачи: **не выполнена**. Отправитель application, получатель release; назначенное время 18:00, но владение меняется только по записанному commit и приему. Заполнить обе стороны, не проставлять SHA заранее:

```text
contract_commit:
baseline_commit:
application_code_commit:
handoff_commit:
accepted_by_release_commit:
accepted_at_with_timezone:
checks_and_limitations:
```

Передаваемый список: `app/main.py`, `app/pilot/router.py`, `src/App.tsx`, `src/main.tsx`, `compose.yaml`, `Dockerfile`, `app/Dockerfile`, package/lock/tsconfig/Vite/index/Playwright config, `.env.example`/ignore/CI, `infra/**`, `scripts/pilot/**`, `docs/pilot/**`, `app/pilot/operations/create_fixture_accounts.py`, `app/pilot/operations/__init__.py`. Реальный manifest уточняет конкретные существующие файлы, а не подразумевает все возможные wildcard. `app/config.py`, домен/SQL/worker/analytics/генерируемые DTO в этот переход не входят и остаются processing. Teacher-компоненты (кроме переданных shell entrypoint) и auth/CRUD application остаются application.

До передачи только application правит общие конфиги; после нее application передает reproduction release и правит свой UI/HTTP. Release вправе исправить известный дефект любого модуля по frozen contract, отдельным fix commit+тестом по протоколу. Вечер не зависит от синхронного возвращения автора processing.

## Завершение локального этапа

К 21:00 release фиксирует локального кандидата/команды/A01–A25. Application передает свои code commit, выполненные APP-C, pass/fail/not_run, дефекты и границы устройств/transport. Внешний выпуск и независимая апробация остаются отдельными этапами. HANDOFF не содержит паролей, ключей, реальных школьных фото, production-ответов, персональных условий участников или выдуманного экономического/математического успеха.

Явное уточнение manifest B4: вместе с app/main.py, app/pilot/router.py и Compose release принимает src/App.tsx и src/main.tsx. Teacher-компоненты в src/pilot остаются application; staff UI/list/get добавляет release после B4 без раннего отсутствующего импорта. app/config.py — processing и не входит в передачу bootstrap-файлов.
