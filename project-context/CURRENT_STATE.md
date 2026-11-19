# Текущий этап проекта

Срез 20.11.2026. **Application, processing и release первоначально объединены в main `a7a7454` (база аудита); локальный учительский путь до сохраненной сводки реализован. После независимого аудита в изолированной `fix/release-audit` исправлены recovery/launcher, HEIC и staff history; повторная локальная fixture-приемка исправлений завершена.** Точные ревизии, команды, результаты и границы проверки — в [RELEASE_REPORT](../docs/pilot/RELEASE_REPORT.md).

Учительский пилот: готовый личный аккаунт, именованная проверка, условные тетради без ФИО, совместный комплект фото, фоновый checker, отдельные отзывы. Два этапа завершения R84/R86: ожидание/просмотр с редактированием, затем окончательное согласие фиксирует состав и запускает LLM-сводку. Контракт Q49 закрыт shared v1; обязательных rule_id в checker нет.

## Что реализовано и проверено

[Application HANDOFF](pilot/planning/application/HANDOFF.md) фиксирует общую сборку из processing в main `0f8460d`, миграции, seed, проверку доступа, приватные фото и браузерный прогон двух тетрадей до сохранённой сводки. [BOOTSTRAP](../docs/pilot/BOOTSTRAP.md) содержит команды воспроизведения.

[Processing HANDOFF](pilot/planning/processing/HANDOFF.md) – ready. Канонический прогон на `9d788953a298ff03b7e7903a6b3015cc83f3045d`, run ID `cbc35dd744f541238ce847df507546d4`: **99 PASS,0 failed,0 skipped;32/32 PROC-Cxx**,133,01 с. Python3.12.10/PostgreSQL16.15, настоящий ASGI и дочерние OS worker; чистые HEAD/tree в начале и конце. [Матрица 12 задач/32 случаев, точная команда и ограничения](pilot/planning/processing/RUNTIME_REPORT.md).

Реализованы SQL 001–015, auth/ACL/ревизии/идемпотентность, приватные durable фото, PostgreSQL queue/lease/fencing с 2 global slots, поколения/история/отзывы/skip/delete, двухэтапный финал/snapshot, отдельная аналитика/stale/retry/refresh, события/audit и safe diagnostics. Source SQL 001–007 совпадают с pinned `d62f5ecb8c1c53b1c97faf06530b8d84e691f88d`. В тестах application-owned auth/CRUD подключены test-only ASGI adapter; production processing/events/domain/worker настоящие.

R87: общий накопительный backend cap 500 RUB на все teacher /оба kind, PostgreSQL spent/holds; trusted `python -m pilot.processing.budget set-limit --rub 500` меняет cap без restart. Это не баланс Polza/месячный reset; walletinitialize/topup и отдельный pricing-файл не prerequisites. Валидный ответ с cost=null публикуется с финансовым hold; execution unknown не повторяется вслепую.

Независимое code review:99 PASS на 746504c и C01/C32 на 9d78895, no open P1/P2. Shared gate73 остается отдельной проверкой спецификаций/типов/fixtures/frozen. Документальное ревью и публикация выполняются после doc-sync; push/merge не объявляются фактом заранее.

## Отдельная живая аналитика

Prompt v1 без изменений: small6 тетрадей/7 задач и class30=120 повторенных public/synthetic benchmark Task прошли числа/refs и смысловые группы 17/11/6. Class30:81,832 с/5,06564076 RUB. Всего 3 платных text-only попытки/6,54385092 RUB: первый ответ потерян private bridge и сверен финансово, два вывода проверены. Unknown/holds0, все стоимости finalized; новых paid photo checks0. Это отдельный разрешенный smoke-бюджет 150 RUB, не runtime cap 500. [Подробности](pilot/planning/processing/RUNTIME_REPORT.md).

## Что остается not_run

- Настоящие Android/iPhone, камера/галерея/HEIC в браузере (`mobile_layout` проходит только в эмуляции).
- Внешний сервер/HTTPS/deploy/выдача школьного доступа.
- Реальная модель Polza в release-прогоне и платные вызовы.
- Интерактивный полный `run.sh up` на Windows: Bash/Docker-stub regressions и read-only Compose config прошли, фактический launcher startup этим не подтвержден.
- Самостоятельная учительская апробация, полезность и экономия полного времени.

## Локальный выпуск (REL-01–REL-12)

Историческая приемка `release_tasks` от 19.11.2026 (49 integration /14 E2E /28 frontend /24 application /8 staff) сохранена в [RELEASE_REPORT](../docs/pilot/RELEASE_REPORT.md). Она не заменяет повторную проверку после аудита main.

20.11.2026: 63 ops-теста, 43 frontend-теста и build — PASS. Усиленные REL-C24/C15: 3 PASS, настоящая очередь/worker с синтетической HTTP-границей поставщика; 60 тетрадей/240 задач, точные два запроса при временном сбое, сохранение retry через restart. Финальный браузерный набор на пересобранном image — 15 PASS, совпадение source/image SHA256 проверено. На code/test HEAD `261bb6e` application 24/staff 8/legacy 11 — PASS; backend processing 99 и полный integration 51 — PASS. Новых платных запросов нет. Публичный API, SQL, AI-промпты и общий cap 500 RUB не менялись.

B4 принят release 19.11.2026: [HANDOFF](pilot/planning/release/HANDOFF.md). Формальный статус передачи release остается `in_progress`: отдельный формат runtime-evidence с clean-tree metadata этой задачей не создавался; это не отменяет фактические PASS локальных исправлений. Общая готовность пилота не заявляется. Операторские команды — [RELEASE_RUNBOOK](../docs/pilot/RELEASE_RUNBOOK.md); секреты только в приватном env/окружении, обычный запуск не сбрасывает пароли. Организационные сведения школы описаны в SCHOOL_PROCESS.
