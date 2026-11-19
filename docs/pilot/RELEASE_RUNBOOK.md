# Runbook локального выпуска пилота

20.11.2026. Операторская инструкция для локальной сборки и восстановления. Внешний сервер, HTTPS и школьная выдача доступа здесь **не** описаны: это отдельный выпуск. Начните с [ENVIRONMENT](ENVIRONMENT.md): какие файлы реально существуют, кто их читает и как подготовить приватный env на Bash/PowerShell. Спецификация параметров — [LOCAL_ENV](../../project-context/pilot/planning/shared/LOCAL_ENV.md), происхождение сборки — [BOOTSTRAP](BOOTSTRAP.md).

Все команды выполняются из корня `umnaya_terad`. Сначала подготовьте приватный файл по ENVIRONMENT; default-путь сам по себе не означает наличие файла. Для прямого Compose всегда указывайте один и тот же project, `-f` и `--env-file` (и исходные overrides, если они были). `PILOT_ENV_FILE` сам Docker Compose не читает. Значения секретов не печатать и не коммитить.

## Переменные окружения

| Имя | Назначение |
|---|---|
| `COMPOSE_PROJECT_NAME` | Имя выбранного Compose-проекта; default `smartnote-pilot`, приемка `smartnote-release-accept`, restore `smartnote-restore-*`. Текущие локальные стенды перечислены в ENVIRONMENT |
| `PILOT_FRONTEND_PORT` | Порт frontend на `127.0.0.1` (default 5173, приемка 5273) |
| `PILOT_TRANSPORT` | `fixture` для учебного режима, `polza` для реальной модели. Один источник для backend и frontend |
| `POSTGRES_PASSWORD`, `VISITOR_COOKIE_SECRET` | Пароль PostgreSQL и случайный HMAC-секрет сессии; `VISITOR_COOKIE_SECRET` от 32 символов |
| `ALLOWED_BROWSER_ORIGINS` | Точный список origin браузера; wildcard запрещён |
| `PILOT_FIXTURE_*_LOGIN/PASSWORD` | Начальный seed двух teacher и staff; не реестр действующих аккаунтов |
| `PILOT_ACCOUNT_PASSWORD` | Пароль для `manage_accounts`, только в окружении или скрытом вводе |
| `PILOT_OPERATOR_REF` | Кто выполняет привилегированную операцию (аудит) |
| `PILOT_ENV_FILE` | Путь для launcher и поддерживающих его Python wrappers/harness; точные различия и legacy-исключения — ENVIRONMENT |
| `PILOT_BACKUP_PROJECT` | Проект, который бэкапит `backup_local.py` (по умолчанию `smartnote-pilot`) |
| `PILOT_COMPOSE_OVERRIDES` | Необязательные абсолютные пути к Compose override-файлам для backup/restore, разделенные `os.pathsep` (`:` на Linux, `;` на Windows). Поддерживается также integration harness; не поддерживается `run.sh`, control/reconcile wrappers. Те же файлы нужны при прямом запуске исходного проекта |

Обычный режим — `polza`; без ключа startup отказывает и не подменяется fixture. Учебная приёмка задаёт `fixture` явно и видит метку «Учебный режим».

Для `run.sh` несекретные параметры задаются через окружение: `MODE`, `PROJECT`, `PORT`, `LOGIN` (поддержаны также `PILOT_TRANSPORT`, `COMPOSE_PROJECT_NAME`, `PILOT_FRONTEND_PORT` и имена `PILOT_FIXTURE_*`). Например, `MODE=fixture PROJECT=smartnote-local-test PORT=5273 ./run.sh`. Без явного режима остается `polza`.

Пароли и `POLZA_API_KEY` задаются только в приватном `$PILOT_ENV_FILE` или окружении процесса. Не вписывать их в отслеживаемый `run.sh` или в аргументы команд. Прежние имена `PASSWORD`, `TEACHER2_PASSWORD`, `STAFF_PASSWORD`, `POLZA_KEY` поддерживаются как переменные окружения. При отсутствии паролей первый запуск генерирует их и сохраняет один раз; существующие логины и секреты читаются из приватного файла. Launcher передает пароли в `docker compose exec` через `-e ИМЯ`, без значений в argv хостового процесса.

Обычный `./run.sh` проверяет вход, но при несовпадении пароля отказывает без сброса. Для намеренной смены оператор сначала обновляет приватную конфигурацию, затем запускает `./run.sh reset`: команда использует trusted `manage_accounts`, сохраняет ID, роли и материалы, закрывает сессии только реально сброшенных аккаунтов. Остановка, status, restart, budget и pause доступны прежними командами; справка — `./run.sh help`.

## Запуск и проверка

```sh
export PILOT_ENV_FILE="$HOME/.config/smartnote/pilot.env"
export COMPOSE_PROJECT_NAME=smartnote-local
export PILOT_FRONTEND_PORT=5173
docker compose -p "$COMPOSE_PROJECT_NAME" -f compose.yaml --env-file "$PILOT_ENV_FILE" build
docker compose -p "$COMPOSE_PROJECT_NAME" -f compose.yaml --env-file "$PILOT_ENV_FILE" run --rm migrate
docker compose -p "$COMPOSE_PROJECT_NAME" -f compose.yaml --env-file "$PILOT_ENV_FILE" up -d --wait
docker compose -p "$COMPOSE_PROJECT_NAME" -f compose.yaml --env-file "$PILOT_ENV_FILE" exec -T backend python -m pilot.operations.manage_accounts seed
docker compose -p "$COMPOSE_PROJECT_NAME" -f compose.yaml --env-file "$PILOT_ENV_FILE" ps
```

Ожидается: `postgres`, `backend`, `worker`, `frontend` — `healthy`; `migrate` — `Exited (0)`. В новой БД seed создаст 2 teacher и 1 staff; дополнительные существующие аккаунты не удаляются. Повторный `migrate`/`seed` не сбрасывает данные или пароли. Полный эквивалент startup для PowerShell:

```powershell
docker compose -p $env:COMPOSE_PROJECT_NAME -f compose.yaml --env-file $env:PILOT_ENV_FILE build
docker compose -p $env:COMPOSE_PROJECT_NAME -f compose.yaml --env-file $env:PILOT_ENV_FILE run --rm migrate
docker compose -p $env:COMPOSE_PROJECT_NAME -f compose.yaml --env-file $env:PILOT_ENV_FILE up -d --wait
docker compose -p $env:COMPOSE_PROJECT_NAME -f compose.yaml --env-file $env:PILOT_ENV_FILE exec -T backend python -m pilot.operations.manage_accounts seed
docker compose -p $env:COMPOSE_PROJECT_NAME -f compose.yaml --env-file $env:PILOT_ENV_FILE ps
```

Переменные `$env:PILOT_ENV_FILE`, `$env:COMPOSE_PROJECT_NAME`, `$env:PILOT_FRONTEND_PORT` заранее задаются по PowerShell-примеру ENVIRONMENT.

Health без модели: `curl -fsS http://127.0.0.1:${PILOT_FRONTEND_PORT}/` (frontend) и health backend изнутри контейнера. Наружу порты backend/worker не публикуются; фото доступно только через авторизованный `/api/assets/{id}` с `Cache-Control: private, no-store`.

Остановка без потери данных: `docker compose -p "$COMPOSE_PROJECT_NAME" -f compose.yaml --env-file "$PILOT_ENV_FILE" stop`. **Не** использовать `down -v` в рабочем проекте: это удалит volumes с базой и фото. `down -v` допустим только для выделенного тестового проекта.

## Изменение настроек и аккаунтов

Правка приватного файла не меняет running container; простой `docker compose restart` тоже не применяет новый env. Для runtime-настроек при том же project/file/наборе overrides:

```bash
docker compose -p "$COMPOSE_PROJECT_NAME" -f compose.yaml --env-file "$PILOT_ENV_FILE" up -d --force-recreate --wait
```

Это не смена пароля уже инициализированной PostgreSQL: `POSTGRES_PASSWORD` в файле сам пароль БД не обновляет. Для custom env не используйте launcher `restart`: он предварительно переписывает файл своим preset.

Чтобы добавить учителя, env менять и контейнеры пересоздавать не нужно:

```bash
docker compose -p "$COMPOSE_PROJECT_NAME" -f compose.yaml --env-file "$PILOT_ENV_FILE" exec backend python -m pilot.operations.manage_accounts create --login teacher-3 --role teacher
```

Пароль вводится скрыто в терминале, если `PILOT_ACCOUNT_PASSWORD` не задан; иначе берется из этой переменной. `-T` здесь не используется. Источник аккаунтов — `users` в БД; повторный seed не сбрасывает пароль, явный `manage_accounts reset --login ...` сохраняет ID/материалы и отзывает сессии аккаунта. Общий cap/pause меняются trusted CLI без recreate.

## Диагностика

```sh
python3 scripts/pilot/processing_control.py status
python3 scripts/pilot/processing_control.py --operator-ref release pause  --reason "provider issue"
python3 scripts/pilot/processing_control.py --operator-ref release resume --reason "provider restored"
docker compose -p "$COMPOSE_PROJECT_NAME" -f compose.yaml --env-file "$PILOT_ENV_FILE" exec -T backend python -m pilot.processing.budget status
docker compose -p "$COMPOSE_PROJECT_NAME" -f compose.yaml --env-file "$PILOT_ENV_FILE" exec -T backend python -m pilot.processing.budget set-limit --rub 500
```

- `status` показывает `paused`, `available_rub`, `held_rub`, `unknown_attempt_ids`, `mode`.
- Пауза блокирует только новые dispatch; queued Jobs, вход, история и чтение сохраняются. Минимальная пауза — `pause`, возврат — `resume`; причина обязательна и попадает в аудит.
- Cap — общий накопительный расход (500 RUB по умолчанию, не баланс Polza и не месячная квота). `set-limit` действует без restart и не сбрасывает `spent`/`held`.
- HTTP admin endpoint для паузы и денег не существует.

Сверка неизвестного исхода: положить evidence-файл **вне Git**

```json
{ "reference": "provider-receipt-...", "actual_cost_rub": "1.2345", "provider_request_id": "optional" }
```

и выполнить

```sh
python3 scripts/pilot/reconcile_attempt.py --attempt-id <uuid> --outcome settled \
  --evidence-file ~/evidence/receipt.json --operator-ref release
```

`--outcome rejected` требует доказанного отсутствия списания (`0` или `null`). Повтор того же `request_id` и evidence — no-op; иное evidence — конфликт с ненулевым кодом. Сырой файл не попадает в контейнер, лог или аудит: передаётся только SHA-256.

## Backup

Бэкап возможен только при остановленных писателях, иначе скрипт откажется: несогласованный дамп хуже отказа. Каталог должен быть вне репозитория и приватным.

```sh
docker compose -p "$COMPOSE_PROJECT_NAME" -f compose.yaml --env-file "$PILOT_ENV_FILE" stop backend worker
python3 scripts/pilot/backup_local.py --destination ~/pilot-backups --project "$COMPOSE_PROJECT_NAME"
docker compose -p "$COMPOSE_PROJECT_NAME" -f compose.yaml --env-file "$PILOT_ENV_FILE" start backend worker
```

Результат: каталог `pilot-backup-<UTC>/` с `database.dump` (`pg_dump -Fc`), `photos.tar.gz` и `manifest.json`. Права каталога `700`. Бэкапы не коммитить и не хранить рядом с `.env` в Git.

`--project` выбирает один проект для всех операций (проверка писателей, дамп, фото, метаданные), с явным `docker compose -p`; чужой `COMPOSE_PROJECT_NAME` его не переопределяет. Без флага используется `PILOT_BACKUP_PROJECT`, затем `smartnote-pilot`. Остановить писателей нужно именно выбранного проекта. Ошибки команд выводятся без сырого stderr, который может содержать секреты конфигурации.

## Restore

Восстановление идет **только в новый отдельный проект** `smartnote-restore-*` с новыми volumes. До первого `up/cp/pg_restore` скрипт проверяет Compose-конфигурацию и Docker inventory: любые контейнеры проекта, включая остановленные, его volumes или сеть означают отказ. Volumes, оставшиеся после `down`, и совпадение имени volume без Compose-метки также защищены. Ошибка проверки Docker означает отказ, а не пустую цель. Исходный проект и его писатели не затрагиваются.

```sh
python3 scripts/pilot/restore_local.py --bundle ~/pilot-backups/pilot-backup-<UTC> \
  --project smartnote-restore-rehearsal-20261120
```

Выбирать ранее не использованное имя; при отказе не удалять существующую цель ради повторения. Обхода защиты и destructive override нет. Пользовательские/shared/external volumes, включая устаревший `--target-photos-volume`, отклоняются. Тестовый override может менять image/окружение, но effective mounts `postgres/backend/worker/migrate` должны совпадать с базовой схемой: `postgres_data:/var/lib/postgresql/data`, `pilot_photos:/var/lib/smartnote/photos` у backend/worker, без mounts у migrate. Bind mounts, `volumes_from`, дополнительные/перенаправленные mounts, нестандартные volume drivers и `driver_opts` запрещены до запуска цели; допустим обычный local volume без опций с именем нового проекта.

Скрипт поднимает `postgres`, копирует дамп, делает `pg_restore --exit-on-error --clean --if-exists`, прогоняет migrate (сверка checksums), распаковывает фото в приватный volume и поднимает `postgres/backend/worker` с `--wait`. Код каждой операции и итоговые счетчики проверяются; при ошибке выполнение прекращается с ненулевым exit, JSON успеха не печатается. Частично созданная цель остается для диагностики; новый прогон требует нового имени. Frontend не стартует: второй экземпляр потребовал бы еще один порт, а факт восстановления проверяется по базе, файлам и worker.

Обязательные проверки после restore: `pilot_migrations` = 15, пользователи = 3, число `pilot_checks` не меньше источника, каждый `pilot_photo_assets.normalized_path` существует в volume, `pilot_attempts.state='unknown'` остаётся `unknown`, активные резервы совпадают с источником. Исходный проект не должен измениться.

## Rollback

1. `pause` dispatch.
2. Убедиться, что unknown-попытки и их резервы сохранены; не свершать их «на глаз».
3. Вернуться к совместимому commit/image в отдельном checkout; build/up выполнять с теми же явными project/env/overrides по разделу запуска, не менять пользовательские dirty-файлы.
4. Не выполнять downgrade SQL и не переписывать применённые миграции: исправление делается новой миграцией.
5. Снять паузу `resume` только после проверки health и очереди.

Восстановление из бэкапа — отдельная осознанная операция с чистыми volumes; обычный запуск его не делает.

## Приемка

Для Python integration harness сначала подготовить отдельный приватный synthetic env по ENVIRONMENT с `PILOT_TRANSPORT=fixture`; файл не создается самим тестом. Все операции harness направляет в `PILOT_ACCEPTANCE_PROJECT`, исходный пользовательский проект не используется.

```sh
export PILOT_ACCEPTANCE_PROJECT=smartnote-release-accept PILOT_ACCEPTANCE_PORT=5273
export PILOT_ENV_FILE="$HOME/.config/smartnote/acceptance.env"
python3 -m pytest tests/integration/pilot -q
```

Приемка поднимает свой изолированный проект с чистыми volumes; имя должно быть выделено только для synthetic тестов. Browser E2E — отдельный маршрут: `tests/e2e/pilot` читает реквизиты из process env, а встроенные Compose-вызовы teacher flow не передают `--env-file`. Для него нужны реквизиты и полная Compose-подстановка в окружении процесса, согласованные project/port/base URL; один `PILOT_ENV_FILE` этого не обеспечивает. Исторические браузерные команды и результаты с отдельно подготовленным окружением — [RELEASE_REPORT](RELEASE_REPORT.md). Реальные устройства и внешний сервер локальной приемкой не подтверждаются.
