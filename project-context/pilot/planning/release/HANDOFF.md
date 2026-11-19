# Состояние и передача release

19.11.2026, Asia/Yekaterinburg. **status: planned.** Подготовлено индивидуальное ТЗ; приложение этим действием не реализовано. Работа release начинается в 18:00. Документ не подтверждает наличие кодовых коммитов или результаты runtime-приемки.

| Поле | Текущее фактическое значение |
|---|---|
| Плановая рабочая ветка | `work/release`, создание/фактическая ветка пока не подтверждены |
| Интеграционная ветка | `integration/pilot-local`, фактический remote/baseline SHA еще не передан |
| B0 contract commit | Не передан; общий пакет API 1.0.0 указан в shared, SHA зафиксировать при B4 |
| B1 runtime baseline commit | Не передан; запуск приложения release не проверял |
| B4 application/processing commits | Не переданы; не подменять HEAD документационного репозитория |
| Source provenance | SmartNoteLanding `d62f5ecb8c1c53b1c97faf06530b8d84e691f88d`; pinned источник будущего bootstrap, не сборка пилота |
| Candidate 20:15 / final 21:00 | Не созданы/не проверены |
| Transport / live расходы | Runtime не запускался; будущая приемка явно fixture. Платных запросов этой задачей нет |

## Готово

Специфицированы [REL-01–REL-12](TASKS.md), [REL-C01–REL-C28 и A01–A25](ACCEPTANCE.md). Это документы, а не выполненные задачи приложения. Основа — [shared v1](../shared/README.md); фактические офлайн-проверки общего пакета отдельно в [SHARED_REVIEW](../shared/SHARED_REVIEW.md), не записываются как runtime-прогон release.

## Еще не готово

Все REL-01–REL-12 planned; все REL-C01–REL-C28 not_run. Не получены исполняемый B4, миграционный upgrade, аккаунты/сессия, полный analytics smoke с commit, локальная сборка и реальные мобильные результаты. Это ожидаемые входы реализации, не доказательство блокировки после начала работы.

## Что принять в 18:00

Application: реальный branch/commit, BOOTSTRAP manifest, B1 smoke, main/router/Compose/packageconfigs/infra/scripts/docs/account seed, UI/CRUD и известные дефекты. Processing: модели/guards/миграции/runner, worker/queue/funds/events/pause/reconcile facade, fund_wallet initialize/topup и проверка профиля, полные checker+analytics, сигнатуры Services и результаты API smoke begin→finalize→summary, duplicate/failed/retry/state-change/refresh. Проверить включенные коммиты, затем однократно принять владение B4; повторный импорт source не выполнять.

Результат передачи заполнить: `application_commit`, `processing_commit`, `contract_commit`, `baseline_commit`, `integration_commit`, принятые пути, последовательность миграций, транспорт, команды/результаты. До получения оставить «не передан», SHA не угадывать.

## Запуск и данные

Будущие команды в [ACCEPTANCE](ACCEPTANCE.md) должны быть созданы/проверены при реализации; release еще их не выполнял. Понадобятся Docker Compose, frontend/backend dev dependencies, private local env, общая БД и приватный photo volume. `PILOT_TRANSPORT=fixture` задается явно, frontend `VITE_PILOT_TRANSPORT` из того же source; при polza нужен реальный ключ и отдельная авторизация платного smoke. Значения ключей/паролей в HANDOFF не записывать.

Имена local seed env без значений: `PILOT_FIXTURE_TEACHER_1_LOGIN`, `PILOT_FIXTURE_TEACHER_1_PASSWORD`, `PILOT_FIXTURE_TEACHER_2_LOGIN`, `PILOT_FIXTURE_TEACHER_2_PASSWORD`, `PILOT_FIXTURE_STAFF_LOGIN`, `PILOT_FIXTURE_STAFF_PASSWORD`. Defaults отсутствуют, повтор seed не сбрасывает пароль молча; поздний reset — отдельная привилегированная CLI. Основные Settings в `app/config.py` принадлежат processing и не становятся sharedconfig release на B4.

Accounts первоначально дает application до B1; release после B4 принимает seed и reset CLI. Итоговые команды startup/migrate/accounts/pause/reconcile/funds/backup/restore и зависимости записать в `docs/pilot/RELEASE_RUNBOOK.md`, `RUNBOOK.md` оставить вход-ссылкой. Restart без удаления volumes; unknown хранит резерв до безопасной сверки. Политика env/профиля — [LOCAL_ENV](../shared/LOCAL_ENV.md): реальные средства не seed400, баланс/резерв и evidence подтверждаются отдельно, fixture wallet изолирован.

## Выполненные проверки release

Runtime, Compose, PostgreSQL, браузер, настоящие Android/iPhone, модель, server deploy — **не выполнялись** при подготовке ТЗ. После реализации здесь записать каждую команду, cwd, commit, fixture/режим, actual результат и ограничения. Документационные проверки подготовки ТЗ записывать отдельно после их фактического выполнения; их результат не переводит runtime-кейсы в pass.

Проверка подготовки ТЗ 19.11.2026: `python project-context/pilot/planning/shared/check_shared.py` через подготовленное dev-окружение Python 3.12 — PASS, 73 офлайн-теста; 34 HTTP-операции, 44 HTTP fixtures, 25 lifecycle snapshots, четыре пары analytics. `git diff --check` и `git diff --cached --check` — PASS. Это сверка спецификации, без live LLM/сервера/приложения. Полный `check_context.py` повторяется координатором после появления параллельных файлов и итогового TASK_REVIEW; промежуточно фиксировал еще отсутствующие создаваемые документы, а не runtime-дефект.

## Блокеры и исправления

Активные runtime-блокеры пока не установлены, поскольку реализация не начата. При обнаружении: `BLK-release-NN / severity / contract+A-ID / commit / fixture+команда / actual / expected / next action`. Известный контракт интегратор исправляет в любом модуле с fix commit и регрессией без ожидания автора. Новый продукт/несовместимое API передается координатору, молчание не согласие.

## Финальная передача

Заполнить к 21:00: candidate/final commit, included/fix commits, проверенные миграции/volumes/accounts, результаты REL-C01–REL-C28 и одной A01–A25 матрицы, report/runbook paths, оставшиеся failed/not_run и шаг восстановления. Реальная модель/расходы, настоящие устройства, внешнее развертывание и школьная апробация — отдельные факты. Фраза «локальная сборка готова» допустима только в пределах явно выполненной приемки.
