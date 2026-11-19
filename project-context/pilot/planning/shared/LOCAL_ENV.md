# Минимальная конфигурация локальной сборки

20.11.2026. Конфигурация реализованной локальной сборки. Рабочие env-файлы не входят в Git. Каноническая инструкция по файлам, loader/приоритетам, Bash/PowerShell и локальным проектам — [ENVIRONMENT](../../../../docs/pilot/ENVIRONMENT.md), команды — [RELEASE_RUNBOOK](../../../../docs/pilot/RELEASE_RUNBOOK.md). Фактические потребители: [app/config.py](../../../../app/config.py), [compose.yaml](../../../../compose.yaml), [run.sh](../../../../run.sh); происхождение Settings сохраняется в [BOOTSTRAP](../../../../docs/pilot/BOOTSTRAP.md). Имена ниже имеют конкретного потребителя, другие knobs не переносятся автоматически.

## Два явных режима

`PILOT_TRANSPORT=polza|fixture` — один источник режима для API/worker и клиентской сборки. Нормальный режим по умолчанию `polza`: нужен действующий серверный ключ и проверенная финансовая конфигурация. Если ключ/профиль отсутствуют, реальный transport не подменяется учебным; запуск или dispatch безопасно отказывает с диагностикой.

Офлайн-приемка явно задает `PILOT_TRANSPORT=fixture`; никаких внешних запросов. Compose передает это же значение frontend как `VITE_PILOT_TRANSPORT`, а UI показывает короткую метку «Учебный режим». Согласованность режимов проверяется в bootstrap/приемке. Отдельно вручную выставлять два независимых режима нельзя. Признак относится к dev-конфигурации и не требует нового поля учительского HTTP DTO.

Fixture transport возвращает предопределенный mock-разбор фото; default analytics mock строит арифметику и literal-rule группы для произвольного синтетического snapshot. Named oracle/mixed/synonyms/zero-denominator профили фиксированы и проверяют совпадение содержимого. Это технический тест, не распознавание произвольного реального фото и не проверка смысловой группировки LLM. Реальные ученические материалы не отправляются в него с обещанием анализа; контрольный live smoke выполняется отдельно и явно, в выделенном бюджете. Автотест не может случайно включить polza только из-за наличия ключа в окружении.

## Параметры и потребители

| Имя | Потребитель / правило |
|---|---|
| PILOT_TRANSPORT | Фабрика backend transport и fixture/live приемка; default polza, fixture только явный |
| VITE_PILOT_TRANSPORT | Только frontend build/dev; значение поступает из того же PILOT_TRANSPORT в Compose; показывает учебную метку |
| POSTGRES_PASSWORD / DATABASE_URL | Compose PostgreSQL и asyncpg pool. DATABASE_URL формируется локально, не публикуется с реквизитами |
| VISITOR_COOKIE_SECRET | Сохраненное имя source Settings: HMAC непрозрачной auth-сессии, случайный секрет вне Git. Название не означает возвращение анонимных квот |
| VISITOR_COOKIE_SECURE | false только для локального HTTP; при внешнем HTTPS отдельный выпуск устанавливает true |
| ALLOWED_BROWSER_ORIGINS | Явный список локальных origin; клиент обращается к относительному /api через proxy, wildcard с cookie запрещен |
| VITE_BACKEND_URL | Серверная настройка Vite proxy до backend service; браузеру нельзя предлагать адрес контейнера вместо относительного /api |
| REQUIRE_AUTH_FOR_ANALYSIS | true в пилотном окружении; все новые pilot routes защищены независимо от старого feature flag |
| POLZA_API_KEY / POLZA_BASE_URL / POLZA_MODEL / POLZA_PROVIDER | Только backend/worker в polza; источники defaults — [ai/.env.example](../../ai/.env.example). Не VITE-переменные |
| POLZA_MAX_COMPLETION_TOKENS / POLZA_TIMEOUT_SECONDS / POLZA_CONNECT_TIMEOUT_SECONDS | Runtime Settings принимает25000/300/15; прежний max180 обновлен. Text-only аналитика проверена отдельно с этим профилем; новый photo-checker live-прогон25k не выполнялся |
| POLZA_MAX_PRICE_PROMPT / POLZA_MAX_PRICE_COMPLETION / POLZA_MAX_PRICE_IMAGE | Ценовые фильтры маршрута; не стоимость запроса и не баланс. Профиль/доступность проверяются перед реальным запуском |
| MAX_IMAGE_BYTES / MAX_IMAGE_PIXELS / MIN_IMAGE_EDGE | Общая политика upload/worker: 8000000 байт, 36000000 пикселей, короткая сторона от 32. Runtime min edge32 согласован с domain validator; PNG fixture64x64 проходит проверку. Это техническая валидация, не учительская квота |

Старые DAILY_FREE_ANALYSES, RECURRING_DAILY_FREE_ANALYSES, NETWORK_HOURLY_SENDS и QUOTA_RESERVATION_SECONDS не становятся ограничениями учителя или новой очередью. Старые register/анонимный analyze отключаются серверно. Метрика/рекламные внутренние инструменты не активируются автоматически переносом исходников.

## Деньги, локальные аккаунты и внутренние настройки

По [R87](../../DECISIONS.md) действует общий накопительный расходной cap 500 RUB в PostgreSQL: `pilot_processing_budget` хранит limit/spent/held/paused. Это не остаток счета Polza, не 500 RUB на учителя и не месячный автоматический сброс. До отправки атомарно проверяется `spent+held+request_bound<=limit` для обоих kind и всех учителей. Режимы fixture/polza изолированы. Изменение cap не сбрасывает spent/holds и не отменяет running.

Trusted CLI из окружения app: `python -m pilot.processing.budget status`; `python -m pilot.processing.budget set-limit --rub 500`. Изменение вступает в силу без restart. Walletinitialize/topup и отдельный pricing-файл больше не требуются для dispatch; прежние требования подтвержденного wallet balance superseded R87. Встроенный консервативный профиль – `app/pilot/processing/pricing.py`, RUB ceilings50/250/50 и контекст 1048576; bound соответствует фактическому request/cap, не средней цене benchmark.

Execution и billing unknown различаются: валидный ответ с cost=null публикуется, worker slot освобожден, финансовый hold сохранен. Потерянный исход исполнения остается unknown без blind retry. Trusted reconciliation с evidence может позднее уточнить actual cost и снять hold один раз. Обычный ключ Polza остается обязательным, без fallback в fixture.

Рабочие slots, lease/heartbeat, reservation policy и recovery фиксируются кодом/документацией processing; выпуск не придумывает независимые значения. По общему API стартовая глобальная конкурентность двух типов Job —2. Настройки не появляются в учительском UI. Локальные CLI вызывают доменные функции без собственной схемы SQL и не принимают пароли/ключи через командную строку.

`manage_accounts seed` получает начальные тестовые реквизиты из окружения backend и использует общий auth; legacy `create_fixture_accounts` остается отдельным fixture-only seed. Источник аккаунтов — PostgreSQL `users`; `PILOT_FIXTURE_*` не является реестром пользователей. Повторный seed не меняет действующие пароли. Дополнительный `manage_accounts create` не требует изменения env/restart; пароль берется скрытым вводом или из `PILOT_ACCOUNT_PASSWORD`, без argv. Доступы передаются вне Git.

Корневой [.env.example](../../../../.env.example) — полный шаблон Compose, а [ai/.env.example](../../ai/.env.example) — reference-профиль адаптера. Это разные шаблоны, не готовые приватные файлы. Приложение не задает `Settings.env_file` и самостоятельно их не читает; Compose получает выбранный файл через явный `--env-file`, а process env имеет приоритет при подстановке. Launcher создает/переписывает свой preset при `up/restart/reset`, но не загружает все произвольные настройки из файла. Точные границы — в ENVIRONMENT. Редактирование env не меняет running container: для новых runtime env нужен recreate, простой restart недостаточен; аккаунты и cap меняются отдельно через SQL-backed CLI.

Settings в `app/config.py` принадлежит processing; передача общих файлов/Compose от application к release зафиксирована в [release HANDOFF](../release/HANDOFF.md). Второй validator не создается. Поддержка HEIC/HEIF/EXIF и оригиналов определена API_CONTRACT: допустимый файл должен дать нормализованный asset в той же границе 8m/36m/32 до подтверждения приема; при невозможности 422.
