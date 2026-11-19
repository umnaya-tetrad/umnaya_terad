# Состояние и передача processing

status: **ready**

19.11.2026. Готов backend-пакет для интеграции application/release. Полная локальная сборка UI/Compose, сервер и школьная апробация этим статусом не объявляются.

| Поле | Факт |
|---|---|
| Ветка / проверенный code commit | `processing` / `9d788953a298ff03b7e7903a6b3015cc83f3045d` |
| База реализации | `1144c498b4aba1e4e4fe118abe7c3f6f1b940198` |
| Source | SmartNoteLanding `d62f5ecb8c1c53b1c97faf06530b8d84e691f88d`; SQL 001–007 точные pinned bytes |
| SQL | `app/migrations/001–015`, checksum registry и upgrade проверены; примененный SQL неизменяем |
| Контракты | shared v1 / OpenAPI1.0.0; page-check/1.2; summary-input/1; class-summary/1 |
| Canonical run | `cbc35dd744f541238ce847df507546d4`, 2026-11-19T11:35:43Z–11:37:56Z, чистый HEAD start=end |
| Runtime | Python3.12.10 / PostgreSQL16.15 / Windows10;99 PASS/133,01 с;32/32 PROC-Cxx PASS |
| Доказательство | [RUNTIME_REPORT.md](RUNTIME_REPORT.md), [runtime-results.json](runtime-results.json):12 задач/32 случая, точная команда, assertions и ограничения |
| Независимое code review | Собственный 99 PASS на 746504c и C01/C32 на 9d78895; no open P1/P2; документальное ревью перед публикацией отдельно |

## Готовые порты и эксплуатация

Services/auth/access/revision/errors/storage/mutations/queries, processing/events routers, snapshot/validator/LLM builders, SQL/worker/events/diagnostics реализованы. Router paths без `/api`; application подключает prefix один раз. Factory не запускает сеть или миграции. Entrypoints из `app`/PYTHONPATH app:

```text
python -m pilot.domain.migrate
python -m pilot.processing.worker
python -m pilot.processing.worker --healthcheck
python -m pilot.processing.budget status
python -m pilot.processing.budget set-limit --rub 500
```

Одна PostgreSQL очередь с 2 global slots для обоих kind/всех teacher; lease60 с, heartbeat10 с, stale health30 с. Фото original/normalized долговечны и приватны; общий storage root передается API/worker. Поколения, отзывы и двухэтапное завершение не меняются из-за результата старого worker. Safe usage/time/error diagnostics сохраняются отдельно от private raw material.

R87: общий накопительный cap 500 RUB в PostgreSQL, без walletinitialize/topup/pricing-file prerequisite; hot-change CLI без restart. Встроенный conservative model/route profile – `processing/pricing.py`. `spent_rub` и active holds не обнуляются изменением cap; fixture/polza изолированы. Валидный ответ при cost=null публикуется, slot освобождается, billing hold сохраняется до trusted сверки. Execution unknown не resend; late evidence не подменяет current generation. Ручная pause и reconciliation вызывают общий service, без HTTP admin/SQL-дубликата.

`PILOT_TRANSPORT=polza` обычный; без ключа fail-closed, fixture fallback отсутствует. Explicit fixture дает mock technical cycle для синтетических входов; арифметический mock и literal-rule grouping не проверяют смысловую группировку LLM. Настройки и ограничения – [LOCAL_ENV](../shared/LOCAL_ENV.md).

## Живой text-only smoke

Два сохраненных результата аналитики проверены по числам и смысловым Task groups; третий первый ответ потерян в private bridge и финансово сверился по finalized history. Всего 6,54385092 RUB/3 paid calls, unknown/holds0; class30=120 повторенных benchmark dev Task,81,832 с/5,06564076 RUB. Promptv1 unchanged, новых paid photo checks0. Подробности/ограничения – RUNTIME_REPORT. Новых paid calls передача не разрешает.

## Дальше и ограничения

PROC-01–PROC-12 и матрица принятого объема представлены в отчете. Push/merge этой записью не выполнены; публикация после отдельного ревью doc-sync по уже полученному разрешению владельца. Точные commit публикации/интеграции фиксируются фактом после операции.

UI, полный application bootstrap, Compose/container restart, настоящие мобильные устройства, HTTPS/deploy и самостоятельная апробация – **not_run**. Auth/CRUD в приемке подключались через test-only ASGI adapter; production processing/events/domain/PG/OS worker проверены. Прежний статус planned относится к подготовке ТЗ и заменен этим handoff; старый план часов B1–B4 не является новым результатом измерений.
