# Проверка runtime processing · 19.11.2026

Код проверен локально: **99 PASS, 0 failed, 0 skipped; PROC-C01–PROC-C32: 32/32 PASS**, 133,01 с. Это backend-пакет для интеграции, не готовность всего учительского приложения. Переносимый безопасный результат – [runtime-results.json](runtime-results.json); состояние передачи – [HANDOFF](HANDOFF.md).

## Зафиксированный прогон

- Ветка `processing`, code commit `9d788953a298ff03b7e7903a6b3015cc83f3045d`; source `d62f5ecb8c1c53b1c97faf06530b8d84e691f88d`.
- Run ID `cbc35dd744f541238ce847df507546d4`; начало `2026-11-19T11:35:43.056583Z`, окончание `2026-11-19T11:37:56.050271Z`. HEAD одинаков в начале/конце; рабочая копия чистая в обеих точках.
- Windows10, Python3.12.10, PostgreSQL16.15; версии пакетов сохранены в безопасном JSON.
- Настоящие PG транзакции/несколько соединений, ASGI HTTP, дочерние OS worker и перезапуски. Для application-owned auth/CRUD использован test-only ASGI adapter; production processing/events routers и domain/storage/worker настоящие.
- Явный fixture/mock gateway, сеть модели запрещена. `provider_post_count` в JSON означает вызовы имитатора, не оплаченные обращения Polza.

Точная команда канонического прогона, cwd – корень репозитория; пути среды и изолированная DSN заменены переносимыми обозначениями:

```powershell
$env:PYTHONPATH=(Resolve-Path 'app').Path
$env:PYTHONPYCACHEPREFIX='<private-cache>/processing-bytecode'
$env:PILOT_TEST_DATABASE_URL='<isolated PostgreSQL16 URL with pilot_test_* database>'
& <venv>/Scripts/python.exe -m pytest app/tests/pilot -q --tb=short -p no:cacheprovider --basetemp <private-cache>/processing-final --junitxml=<private-cache>/processing-final.xml
```

Зависимости – `app/requirements.txt`. Harness требует отдельную `pilot_test_*` БД и не очищает рабочую БД. Не размещать DSN/пароли в Git. Локальные JUnit/run/case artifacts хранятся приватно; JSON выше содержит только разрешенные агрегаты и выполненные assertions.

## Матрица задач

| Задача | Статус | Проверенный объем | Случаи PROC- |
|---|---|---|---|
| PROC-01 | Реализовано и проверено локально | Миграции001–015, source001–007, constraints | C01/C02 |
| PROC-02 | Реализовано и проверено локально | Auth/ACL/session/reset, revision/intent | C03/C04/C06/C24 |
| PROC-03 | Реализовано и проверено локально | Приватные durable фото, форматы и порядок | C05/C07/C08 |
| PROC-04 | Реализовано и проверено локально | Поколения, Task/review, skip/delete/history | C09–C14 |
| PROC-05 | Реализовано и проверено локально | PG очередь, lease/fencing, два global slots, один retry | C15–C18/C30 |
| PROC-06 | Реализовано и проверено локально | Frozen checker, общий transport, безопасная диагностика | C09/C19 |
| PROC-07 | Реализовано и проверено локально | Накопительный cap500, pause, execution/billing unknown | C17/C18/C27–C29 |
| PROC-08 | Реализовано и проверено локально | Двухэтапный finalize и неизменяемый snapshot | C20–C22 |
| PROC-09 | Реализовано и проверено локально | Отдельная аналитика, oracle, stale/retry/refresh | C25/C26/C31 |
| PROC-10 | Реализовано и проверено локально | Events, dedupe, audit/outbox | C23/C24 |
| PROC-11 | Реализовано и проверено локально | Production processing/events routers и API-only цикл | C32 |
| PROC-12 | Реализовано и проверено локально | Исправления, независимое ревью, doc-sync и передача | C01–C32; этот отчет/HANDOFF |

PROC-12 включает настоящий doc-sync/preflight; последующая публикация и слияние выполняются отдельно после ревью документации. Время B1–B4 старого плана не является измерением фактической продолжительности этой работы.

## Матрица 32 случаев

PASS означает выполненные assertions этой строки, а не все возможные проверки соответствующего продукта. Дополнительные ограничения перечислены ниже и в machine report.

| Случай | Результат | Точный pytest node | Фактически проверено |
|---|---|---|---|
| PROC-C01 | PASS | `app/tests/pilot/domain/test_proc_contract.py::test_proc_c01` | Чистая PG и upgrade 001–007 с сохраненными user/session hashes; checksum tamper; SQL unique/immutable/finite. |
| PROC-C02 | PASS | `app/tests/pilot/domain/test_proc_contract.py::test_proc_c02` | Уникальные router hooks, совпадение DTO, реальный worker health CLI: live/expired/PG unavailable. |
| PROC-C03 | PASS | `app/tests/pilot/domain/test_proc_contract.py::test_proc_c03` | Сессии/роли/ACL, пароль/reset/revoke/expiry, HttpOnly/SameSite, Origin и staff read-only. |
| PROC-C04 | PASS | `app/tests/pilot/domain/test_proc_contract.py::test_proc_c04` | Реальный потерянный ACK после committed submit, intent replay перед revision, один Job/outbox. |
| PROC-C05 | PASS | `app/tests/pilot/processing/test_proc_contract.py::test_proc_c05` | Два запуска дочернего ASGI и перезапуск worker на тех же PG/storage; один provider dispatch. |
| PROC-C06 | PASS | `app/tests/pilot/domain/test_proc_contract.py::test_proc_c06` | Конфликт двух отзывов, точный revision/data_revision, comment-only/no-op, stale analysis. |
| PROC-C07 | PASS | `app/tests/pilot/domain/test_proc_contract.py::test_proc_c07` | Реальный upload/private bytes/ACL, corrupt/type/min edge и committed upload ACK loss. |
| PROC-C08 | PASS | `app/tests/pilot/domain/test_proc_contract.py::test_proc_c08` | Порядок фото, некорректная перестановка, sealed guard, replacement draft/discard. |
| PROC-C09 | PASS | `app/tests/pilot/processing/test_proc_contract.py::test_proc_c09` | Четыре multi/continuation сценария, invalid response, correct-but-incomplete. |
| PROC-C10 | PASS | `app/tests/pilot/domain/test_proc_contract.py::test_proc_c10` | Пересегментация 2→3 с новыми ID, снятие старых согласий и immutable reports. |
| PROC-C11 | PASS | `app/tests/pilot/domain/test_proc_contract.py::test_proc_c11` | Retry того же input, tombstone, история runs и сохраненный старый confirmed review. |
| PROC-C12 | PASS | `app/tests/pilot/domain/test_proc_contract.py::test_proc_c12` | Mixed not_assessed skip, соседний review, обе Task в серверном snapshot. |
| PROC-C13 | PASS | `app/tests/pilot/domain/test_proc_contract.py::test_proc_c13` | Общее фото после delete, delete последней Task→empty/null-average, номера 1/3. |
| PROC-C14 | PASS | `app/tests/pilot/domain/test_proc_contract.py::test_proc_c14` | Удаление queued Check, закрытые Check/Job, replay удаления и отсутствие dispatch. |
| PROC-C15 | PASS | `app/tests/pilot/processing/test_proc_contract.py::test_proc_c15` | Два OS worker на один Job; fencing/recovery; три OS worker на три Job разных kind при двух глобальных slots. |
| PROC-C16 | PASS | `app/tests/pilot/processing/test_proc_contract.py::test_proc_c16` | Ровно две попытки с actual worker process restart между ними; success/failure, третьего POST нет. |
| PROC-C17 | PASS | `app/tests/pilot/processing/test_proc_contract.py::test_proc_c17` | Actual worker kill после dispatch, page и analytics: unknown/restart/no-resend, сохраненные snapshot и budget holds. |
| PROC-C18 | PASS | `app/tests/pilot/processing/test_proc_contract.py::test_proc_c18` | Skip unknown→partial finalized summary→late callback без current publish→trusted cost reconciliation ровно один раз. |
| PROC-C19 | PASS | `app/tests/pilot/processing/test_proc_contract.py::test_proc_c19` | Frozen checker request/prompt, порядок реальных image parts/high; fixture без внешней сети. |
| PROC-C20 | PASS | `app/tests/pilot/domain/test_proc_contract.py::test_proc_c20` | Editing/empty и пять completion blockers; red/skip; frozen composition после finalize. |
| PROC-C21 | PASS | `app/tests/pilot/domain/test_proc_contract.py::test_proc_c21` | Review/upload/publish против finalize в обоих порядках с настоящим Check lock и barriers. |
| PROC-C22 | PASS | `app/tests/pilot/domain/test_proc_contract.py::test_proc_c22` | Двойной finalize/replay, один immutable snapshot, GET summary не создает jobs. |
| PROC-C23 | PASS | `app/tests/pilot/events/test_proc_contract.py::test_proc_c23` | Events replay/conflict, 101/extra fields, mixed foreign batch без частичного приема. |
| PROC-C24 | PASS | `app/tests/pilot/domain/test_proc_contract.py::test_proc_c24` | Staff history/material audit с реальной ролью, private photo ACL, безопасные общие логи. |
| PROC-C25 | PASS | `app/tests/pilot/analytics/test_proc_contract.py::test_proc_c25` | Четыре oracle snapshot/result через PG worker; invalid counts/refs/JSON/top/null average не публикуются. |
| PROC-C26 | PASS | `app/tests/pilot/analytics/test_proc_contract.py::test_proc_c26` | Fresh summary retry, stale/refresh, comment-only, новый snapshot. |
| PROC-C27 | PASS | `app/tests/pilot/processing/test_proc_contract.py::test_proc_c27` | Последнее решение: default cap500, оба kind/teachers, atomic reserves, live CLI cap change, same Job/worker IDs, без wallet initialization. |
| PROC-C28 | PASS | `app/tests/pilot/processing/test_proc_contract.py::test_proc_c28` | Manual pause при running, запрет новых dispatch, settlement/read доступны, resume без HTTP admin. |
| PROC-C29 | PASS | `app/tests/pilot/processing/test_proc_contract.py::test_proc_c29` | Последнее решение: валидные page/summary с cost=null публикуются; execution/billing раздельны; holds и неизвестная стоимость не равны нулю; trusted reconciliation/dedupe. |
| PROC-C30 | PASS | `app/tests/pilot/processing/test_proc_contract.py::test_proc_c30` | 60 тетрадей/180 Task/два worker; >100 stale кандидатов не голодают свежие page/analytics и не расходуют средства. |
| PROC-C31 | PASS | `app/tests/pilot/analytics/test_proc_contract.py::test_proc_c31` | Refresh-first/claim-first и все 14 summary guards с реальными Attempt rows. |
| PROC-C32 | PASS | `app/tests/pilot/analytics/test_proc_contract.py::test_proc_c32` | Полный ASGI+PG+worker API цикл до saved summary; повтор с обычным default fixture без transport override. |

## Независимое ревью и дополнительные gates

Независимый агент выполнил собственный полный прогон: 99 PASS за156,96 с на `746504c`, затем C01/C32 – 2 PASS на `9d78895`; открытых P1/P2 не осталось. Проверены shared gate73, frozen assets, CLI и context. Это агентное инженерное ревью, не независимая педагогическая экспертиза. Финальный полный прогон выше выполнен после этих исправлений на одной чистой ревизии.

SQL001–007 побайтово совпадают с закрепленным source. Миграции008–015 принадлежат пилоту; примененный SQL не переписывается. Code commit включает `6c3ae3c` runtime и `6d55027` source tests. HTTP/DTO shared v1, checker `page-check/1.2`, analytics `summary-input/1`/`class-summary/1` не изменены.

## Отдельная живая проверка аналитики

Использованы сохраненные **onepass v2/direct_v2** ответы public/synthetic benchmark; staged не использовался. Новый запрос содержал только текстовый JSON, без фотографий, комментариев или эталона. Runtime analytics prompt v1 не менялся; checker не вызывался платно заново. Профиль: `google/gemini-3.8-flash`, only `google-ai-studio/flex`, fallback=false, medium, completion cap25000, phase timeout300 с/connect15 с.

| Попытка | Время | RUB | Результат |
|---|---:|---:|---|
| Первый small | 20,55 с | 0,78419458 | Содержимое потеряно из-за double-decode в приватном Windows bridge; качество неизвестно, стоимость сверена по finalized provider history |
| Small:6 тетрадей/7 задач | 21,946 с | 0,69401558 | Числа/ссылки и обе смысловые группы PASS; среднее0,5 |
| Class30:30 тетрадей/120 задач, по3–5 | 81,832 с | 5,06564076 | Числа/ссылки и точные смысловые группы17/11/6 PASS |

Всего **6,54385092 RUB**, неизвестных списаний и активных резервов0; все три стоимости finalized, по одной provider attempt. Это отдельный разрешенный экспериментальный бюджет150 RUB; его журнал не является состоянием runtime cap500 в PostgreSQL и не обнуляет прежние benchmark расходы.

Class30:14 тетрадей с ошибками,6 без,10 частичных; среднее1,4; незавершенных10, спорных10, неоценимых6. Топ: вычитание большего числа из меньшего17, квадрат разности11, недопустимое сложение/вычитание под корнем6. Четвертая группа дискриминанта2 верно исключена. Проверены исходные первые ошибочные шаги и наборы wrapper Task ID; ошибка partial входит в топ, но не в среднее. Малый oracle включает пустую/неразрешенную работу и неоценимую задачу. Отказы явно смоделированы, задачи класса повторяют подготовленные benchmark примеры; это не120 уникальных школьных решений.

Опциональный bridge задавал Ethernet if4 до connect и проверял TLS socket. Его double-decode исправлен отдельной gzip-регрессией; production HTTPX не зависит от Windows bridge. `trust_env=False` отключает proxy окружения, но само по себе не доказывает обход системного TUN. Linux/server route этим экспериментом не проверен. Live-оценка смысла выполнена агентом, не учителем; повторов для статистической оценки качества не было.

## Не выполнено этим пакетом

| Область | Статус |
|---|---|
| UI/teacher frontend/staff screen, браузерный общий путь | not_run |
| Docker Compose/контейнерный restart/volume/сборка полного приложения | not_run: Docker daemon недоступен |
| Настоящие Android/iPhone, камера/галерея/HEIC через браузер | not_run |
| Внешний сервер/HTTPS/deploy/выдача школьного доступа | not_run |
| Самостоятельная учительская апробация и экономия полного времени | not_run |

Синтетический fixture/mock дает проверяемую арифметику и технический цикл; его literal-rule grouping не доказывает смысловое качество LLM. Отдельные text-only live результаты не подтверждают приложение на сегодняшнем сервере, качество всех тем алгебры или достижение целевых5–15 с.
