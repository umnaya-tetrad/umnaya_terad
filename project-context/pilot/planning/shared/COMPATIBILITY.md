# Совместимость и проверки общей базы

19.11.2026. **Спецификация для реализации.** Действующий контракт пакета описан в [API_CONTRACT](API_CONTRACT.md); границы — [MODULE_BOUNDARIES](MODULE_BOUNDARIES.md), порядок baseline — [HANDOFF_PROTOCOL](HANDOFF_PROTOCOL.md). Наличие спецификации не означает, что runtime или перечисленные будущие тесты уже существуют.

## Что фиксируется

B0 фиксирует одним commit: OpenAPI/JSON Schema/fixtures, prompt и response schema аналитики, схему событий, сигнатуры доменных сервисов и правила revision/idempotency. Замороженный checker `page-check/1.2` из `pilot/ai/` не меняется для удобства UI или группировки. Новая оболочка приложения не становится новой схемой checker. Клиентские `src/pilot/api/generated.ts` и серверные `app/pilot/contracts.py` генерируются processing из одного источника; ручное независимое переименование запрещено.

B1 фиксирует отдельно source SHA, manifest переноса, фактические lockfiles/версии runtime, цепочку миграций, имена Compose services/volumes, стабильные hooks подключения routers, entrypoints и команды проверок. Все направления обновляются до этого commit. Владение B1 не передает: application поддерживает main/router/Compose/packageconfigs и все bootstrap-конфиги до B4 в 18:00, затем передает их release вместе с account seed по commit/HANDOFF. Не следует обновлять версии пакетов под словом latest из старого package.json без lockfile. Старый source SHA фиксирует происхождение, а не успешность его проверки на новой машине.

Изменение после B0 классифицируется: исправление реализации по схеме — обычный fix; совместимое дополнение — новая документированная версия контракта с обновлением схем/fixtures/генерации и потребителей; изменение смысла enum, required-полей, URL, revision, финала или snapshot — несовместимое. Такое изменение не сливается по молчанию, требует координатора и, если меняет продукт, решения владельца продукта. Пакет одного PR включает все затронутые слои. До обновления baseline потребители остаются на прежнем contract commit.

## Offline gate сейчас и runtime gate после bootstrap

Контрактный gate не зависит от Docker, UI, провайдера и секретов. Он проверяет синтаксис OpenAPI, разрешение локальных `$ref`, валидацию каждого fixture по точной схеме, отрицательные fixtures, соответствие имен/enum/обязательных полей и неизменность checker. Команда и зависимости берутся из `api/README.md`; ее результат записывается отдельно от runtime. Если валидатор еще не создан или команда не выполнена, B0 имеет статус not_run, а не pass по ручному чтению.

Доступные уже в исходном комплекте проверки документации из корня umnaya_terad:

```powershell
python scripts/check_context.py
git diff --check
git diff --cached --check
```

Они не проверяют API сервера, worker, миграции или качество модели. Сами результаты прогонов фиксируются в HANDOFF, а не предполагаются этим документом.

После импорта source application воспроизводит исходные проверки: `npm test`, `npm run build`, backend `python -m pytest` из `app/` (с требуемой для тестов БД, если нужна), и записывает фактические результаты. Новые pilot contract/domain/integration/e2e тесты создаются по TASKS/ACCEPTANCE направлений; команды ниже — **целевой интерфейс будущих проверок**, они не объявлены существующими:

| Gate после появления кода | Целевая команда/исполнитель |
|---|---|
| Frontend unit/build | `npm test`, `npm run build` / application |
| Backend pilot, включая access/revision и lifecycle | из `app/`: `python -m pytest tests/pilot` / processing; application/staff наборы — их владельцы |
| DB/Compose/restart/funds/races | `python -m pytest tests/integration/pilot` / release из корня |
| Teacher+staff browser flow | `npx playwright test tests/e2e/pilot` / release |
| Полный локальный кандидат | документированная последовательность Compose + все применимые строки выше / release |

При создании тестов владельцы дают реальное расположение runner, зависимости и assertions; несовпадение с этим интерфейсом устраняется до B1/B4, а не оставляется коллеге угадывать cwd. Обычные проверки используют явный fixture transport и запрещают сетевой вызов модели. Live runner — отдельная opt-in команда с отдельно разрешенным бюджетом; обычный CI ее не включает.

Минимум совместимости: checked-in fixtures многозадачной страницы/продолжения/mixed Report; версия и отзыв после замены; общий фотоasset при удалении одной задачи; потерянный submit response; чужой ID/роль; два клиента и revision conflict; гонки финала с upload/review/worker; один retry/restart/неизвестный исход; reserve/funds/pause обоих типов Job; failed/stale analytics и поздний snapshot; события без дублей и без содержимого материалов. Числовые assertions сводки берутся из SUMMARY_METRICS и детальных ACCEPTANCE; изменение fixtures ради прохождения неправильного кода запрещено.

## Локальный запуск: задел и обязательный итог

Read-only осмотр исходного `compose.yaml` на SHA `d62f5ecb8c1c53b1c97faf06530b8d84e691f88d` обнаружил services `postgres`, `frontend`, `backend`, PostgreSQL 16, `npm run dev` и `uvicorn main:app --host 0.0.0.0 --port 8000 --reload`. Из этого файла следует команда `docker compose -f compose.yaml up --build` из корня источника; она **не выполнялась** и не доказывает готовый pilot startup. В source нет отдельного worker и приватного photo volume. Флаги регистрации/квот требуют переработки; старый Compose нельзя объявлять финальным запуском пилота.

Целевой Compose в корне umnaya_terad сохраняет имена `postgres`, `frontend`, `backend` и добавляет `worker` и одноразовый `migrate`. API: `uvicorn main:app --host 0.0.0.0 --port 8000` с workdir `/app`; worker: `python -m pilot.processing.worker` с тем же workdir и backend image; migrate: `python -m pilot.domain.migrate`. Worker/migrate entrypoints создает processing, API bootstrap — application; health не выполняет LLM-запрос. DB volume — `postgres_data`, приватные оригиналы — `pilot_photos`, frontend dependencies — `frontend_node_modules`; API и worker используют общий photo volume, веб-сервер не раздает его напрямую. DB healthy → migrate completed successfully → backend/worker healthy → frontend. Перезапуск не удаляет volumes; `down -v` в обычной инструкции запрещен.

Application до B1 подключает согласованные hooks main/router/Compose. Processing поставляет свои импортируемые routes и worker entrypoint, не меняя main/router; незавершенное содержимое модуля не должно ломать импорт ранней базы. Пустой router не закрывает приемку endpoint, неожиданные ImportError не скрываются. Обновления bootstrap-конфигов между B1 и B4 выполняет application без зависимости от release.

Целевая последовательность после реализации: безопасная локальная конфигурация без реального API-ключа → `docker compose -f compose.yaml build` → `docker compose -f compose.yaml run --rm migrate` → `docker compose -f compose.yaml up -d` → `docker compose -f compose.yaml exec backend python -m pilot.operations.create_fixture_accounts` → smoke. Ранний account seed и health/smoke команды application дает до B1 на общей auth/schema processing и записывает в `docs/pilot/BOOTSTRAP.md`; нет зависимости от поздней работы release. Account seed остается у application до B4; release после 18:00 принимает его по commit/HANDOFF и доводит account/операторские инструкции в `docs/pilot/RUNBOOK.md`. Пока модулей нет, команды не выдаются за выполненные. Уникальные секреты задаются локально вне Git; пример конфигурации не содержит действующих ключей или реквизитов доступа, CLI не принимает пароль через командную строку и не выводит его.

Роли приложения — только `teacher` и `staff`, последний читает материалы с аудитом. Ручная пауза не имеет HTTP admin endpoint: release запускает `scripts/pilot/processing_control.py` через локальный привилегированный доступ к Compose/БД; тот вызывает доменную функцию processing. Проверка паузы обоих видов Job и сохранности очереди/истории выполняется имитатором, без реального платного запроса.

Приемка после restart проверяет сохранение Check/Notebook/photos/jobs/reviews/summary и отсутствие двойного внешнего вызова на восстановлении. Два worker используют один PostgreSQL guard/reserve и fencing; рост числа контейнеров не меняет лимит retry или финансовые правила. Нельзя запускать одновременно старый in-request анализ и новый worker для одного pilot submit. Legacy register и публичный анализ без входа отключены на сервере, отсутствие кнопки в UI недостаточно. Worker не зависит от открытой вкладки. Повторный запуск migrate безопасно проверяет registry примененных миграций и не исполняет SQL дважды; конкурентные migration runners сериализуются.

## Границы доказательств

Green offline gate разрешает реализацию по одинаковым DTO; B1 runtime smoke разрешает ранний совместный цикл; B4 подтверждает переданный функциональный пакет; локальная приемка подтверждает только проверенные локальные случаи. Ни один из них сам по себе не доказывает скорость/качество на реальных школьных работах, live доступность модели, публичный HTTPS или школьную апробацию. Внешний выпуск выполняется отдельно после локального результата к 21:00.

## Staff без ранней зависимости

До B4 application подключает только существующие auth/application/processing/events routers; отсутствующий staff router/UI не импортируется. Ранние auth/asset/history ACL реализуют владельцы app/processing и проверяются до передачи. listStaffChecks/getStaffCheck и полный staff UI создает release в REL-04 после B4. src/App.tsx/src/main.tsx являются bootstrap entrypoint: application до B4, затем release, вместе с main/router/Compose. Application после B4 продолжает teacher-компоненты, не правит принятые shell entrypoint. Функция места подключения не является fake-success staff endpoint; неожиданные ImportError не скрываются.
