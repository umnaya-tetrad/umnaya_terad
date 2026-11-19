# Текущий этап проекта

Срез 19.11.2026. **Processing backend готов к интеграции и проверен локально; полная сборка приложения, сервер и школьная апробация не подтверждены.**

Учительский пилот: готовый личный аккаунт, именованная проверка, условные тетради без ФИО, совместный комплект фото, фоновый checker, отдельные отзывы. Два этапа завершения R84/R86: ожидание/просмотр с редактированием, затем окончательное согласие фиксирует состав и запускает LLM-сводку. Контракт Q49 закрыт shared v1; обязательных rule_id в checker нет.

## Что реализовано и проверено

[Processing HANDOFF](pilot/planning/processing/HANDOFF.md) – ready. Канонический прогон на `9d788953a298ff03b7e7903a6b3015cc83f3045d`, run ID `cbc35dd744f541238ce847df507546d4`: **99 PASS,0 failed,0 skipped;32/32 PROC-Cxx**,133,01 с. Python3.12.10/PostgreSQL16.15, настоящий ASGI и дочерние OS worker; чистые HEAD/tree в начале и конце. [Матрица 12 задач/32 случаев, точная команда и ограничения](pilot/planning/processing/RUNTIME_REPORT.md).

Реализованы SQL 001–015, auth/ACL/ревизии/идемпотентность, приватные durable фото, PostgreSQL queue/lease/fencing с 2 global slots, поколения/история/отзывы/skip/delete, двухэтапный финал/snapshot, отдельная аналитика/stale/retry/refresh, события/audit и safe diagnostics. Source SQL 001–007 совпадают с pinned `d62f5ecb8c1c53b1c97faf06530b8d84e691f88d`. В тестах application-owned auth/CRUD подключены test-only ASGI adapter; production processing/events/domain/worker настоящие.

R87: общий накопительный backend cap 500 RUB на все teacher /оба kind, PostgreSQL spent/holds; trusted `python -m pilot.processing.budget set-limit --rub 500` меняет cap без restart. Это не баланс Polza/месячный reset; walletinitialize/topup и отдельный pricing-файл не prerequisites. Валидный ответ с cost=null публикуется с финансовым hold; execution unknown не повторяется вслепую.

Независимое code review:99 PASS на 746504c и C01/C32 на 9d78895, no open P1/P2. Shared gate73 остается отдельной проверкой спецификаций/типов/fixtures/frozen. Документальное ревью и публикация выполняются после doc-sync; push/merge не объявляются фактом заранее.

## Отдельная живая аналитика

Prompt v1 без изменений: small6 тетрадей/7 задач и class30=120 повторенных public/synthetic benchmark Task прошли числа/refs и смысловые группы 17/11/6. Class30:81,832 с/5,06564076 RUB. Всего 3 платных text-only попытки/6,54385092 RUB: первый ответ потерян private bridge и сверен финансово, два вывода проверены. Unknown/holds0, все стоимости finalized; новых paid photo checks0. Это отдельный разрешенный smoke-бюджет 150 RUB, не runtime cap 500. [Подробности](pilot/planning/processing/RUNTIME_REPORT.md).

## Что остается not_run

- UI/teacher/staff screens и полный браузерный поток application/release.
- Docker Compose/контейнерные volumes/restart и сборка всего приложения: Docker daemon недоступен.
- Настоящие Android/iPhone, камера/галерея/HEIC в браузере.
- Внешний сервер/HTTPS/deploy/выдача школьного доступа.
- Самостоятельная учительская апробация, полезность и экономия полного времени.

Application/release HANDOFF остаются planned. Следующий шаг – принять processing по commit/контракту, интегрировать bootstrap/UI/Compose и выполнить их приемку; локальный кандидат R85 и внешний выпуск различаются. Архивные макеты, исследования и старый месячный ориентир 400 RUB не переопределяют R87 или фактический runtime-отчет. Организационные сведения школы – в SCHOOL_PROCESS; новых школьных результатов этим кодовым этапом не установлено.
