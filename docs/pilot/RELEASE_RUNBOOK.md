# Runbook локального выпуска пилота

20.11.2026. Операторская инструкция для локальной сборки и восстановления. Внешний сервер, HTTPS и школьная выдача доступа здесь **не** описаны: это отдельный выпуск. Правила конфигурации — [LOCAL_ENV](../../project-context/pilot/planning/shared/LOCAL_ENV.md), проверенные команды — [BOOTSTRAP](BOOTSTRAP.md).

Все команды выполняются из корня репозитория `umnaya_terad`. Файл с реквизитами лежит **вне Git**, например `~/.config/smartnote/pilot.env` (права `600`), и передаётся Compose через `--env-file`. Значения не печатать и не коммитить.

## Переменные окружения

| Имя | Назначение |
|---|---|
| `COMPOSE_PROJECT_NAME` | Имя Compose-проекта. Рабочий — `smartnote-pilot`; приёмка — `smartnote-release-accept`; восстановление — `smartnote-restore-*` |
| `PILOT_FRONTEND_PORT` | Порт frontend на `127.0.0.1` (рабочий 5173, приёмка 5273) |
| `PILOT_TRANSPORT` | `fixture` для учебного режима, `polza` для реальной модели. Один источник для backend и frontend |
| `POSTGRES_PASSWORD`, `VISITOR_COOKIE_SECRET` | Обязательные секреты PostgreSQL и HMAC сессии (≥32 символа) |
| `ALLOWED_BROWSER_ORIGINS` | Точный список origin браузера; wildcard запрещён |
| `PILOT_FIXTURE_*_LOGIN/PASSWORD` | Три локальных аккаунта: два teacher и staff |
| `PILOT_ACCOUNT_PASSWORD` | Пароль для `manage_accounts`, только в окружении или скрытом вводе |
| `PILOT_OPERATOR_REF` | Кто выполняет привилегированную операцию (аудит) |
| `PILOT_ENV_FILE` | Путь к локальному env-файлу для скриптов `scripts/pilot/*` |
| `PILOT_BACKUP_PROJECT` | Проект, который бэкапит `backup_local.py` (по умолчанию `smartnote-pilot`) |
| `PILOT_COMPOSE_OVERRIDES` | Необязательные абсолютные пути к Compose override-файлам для backup/restore, разделенные `os.pathsep` (`:` на Linux, `;` на Windows). Те же файлы должны использоваться при запуске исходного проекта |

Обычный режим — `polza`; без ключа startup отказывает и не подменяется fixture. Учебная приёмка задаёт `fixture` явно и видит метку «Учебный режим».

Для `run.sh` несекретные параметры задаются через окружение: `MODE`, `PROJECT`, `PORT`, `LOGIN` (поддержаны также `PILOT_TRANSPORT`, `COMPOSE_PROJECT_NAME`, `PILOT_FRONTEND_PORT` и имена `PILOT_FIXTURE_*`). Например, `MODE=fixture PROJECT=smartnote-local-test PORT=5273 ./run.sh`. Без явного режима остается `polza`.

Пароли и `POLZA_API_KEY` задаются только в приватном `$PILOT_ENV_FILE` или окружении процесса. Не вписывать их в отслеживаемый `run.sh` или в аргументы команд. Прежние имена `PASSWORD`, `TEACHER2_PASSWORD`, `STAFF_PASSWORD`, `POLZA_KEY` поддерживаются как переменные окружения. При отсутствии паролей первый запуск генерирует их и сохраняет один раз; существующие логины и секреты читаются из приватного файла. Launcher передает пароли в `docker compose exec` через `-e ИМЯ`, без значений в argv хостового процесса.

Обычный `./run.sh` проверяет вход, но при несовпадении пароля отказывает без сброса. Для намеренной смены оператор сначала обновляет приватную конфигурацию, затем запускает `./run.sh reset`: команда использует trusted `manage_accounts`, сохраняет ID, роли и материалы, закрывает сессии только реально сброшенных аккаунтов. Остановка, status, restart, budget и pause доступны прежними командами; справка — `./run.sh help`.

## Запуск и проверка

```sh
export PILOT_ENV_FILE=~/.config/smartnote/pilot.env
docker compose --env-file "$PILOT_ENV_FILE" build
docker compose --env-file "$PILOT_ENV_FILE" run --rm migrate
docker compose --env-file "$PILOT_ENV_FILE" up -d --wait
docker compose --env-file "$PILOT_ENV_FILE" exec -T backend python -m pilot.operations.manage_accounts seed
docker compose --env-file "$PILOT_ENV_FILE" ps
```

Ожидается: `postgres`, `backend`, `worker`, `frontend` — `healthy`; `migrate` — `Exited (0)`; ровно три аккаунта (`2 teacher`, `1 staff`). Повторный `migrate` и повторный `seed` безопасны и ничего не сбрасывают.

Health без модели: `curl -fsS http://127.0.0.1:${PILOT_FRONTEND_PORT}/` (frontend) и health backend изнутри контейнера. Наружу порты backend/worker не публикуются; фото доступно только через авторизованный `/api/assets/{id}` с `Cache-Control: private, no-store`.

Остановка без потери данных: `docker compose stop`. **Не** использовать `down -v` в рабочем проекте: это удалит volumes с базой и фото. `down -v` допустим только для выделенного тестового проекта.

## Диагностика

```sh
python3 scripts/pilot/processing_control.py status
python3 scripts/pilot/processing_control.py --operator-ref release pause  --reason "provider issue"
python3 scripts/pilot/processing_control.py --operator-ref release resume --reason "provider restored"
docker compose --env-file "$PILOT_ENV_FILE" exec -T backend python -m pilot.processing.budget status
docker compose --env-file "$PILOT_ENV_FILE" exec -T backend python -m pilot.processing.budget set-limit --rub 500
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
docker compose -p smartnote-pilot --env-file "$PILOT_ENV_FILE" stop backend worker
python3 scripts/pilot/backup_local.py --destination ~/pilot-backups --project smartnote-pilot
docker compose -p smartnote-pilot --env-file "$PILOT_ENV_FILE" start backend worker
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
3. Вернуться к совместимому commit/image: `git checkout <совместимый commit>`, `docker compose build`, `up -d`.
4. Не выполнять downgrade SQL и не переписывать применённые миграции: исправление делается новой миграцией.
5. Снять паузу `resume` только после проверки health и очереди.

Восстановление из бэкапа — отдельная осознанная операция с чистыми volumes; обычный запуск его не делает.

## Приёмка

```sh
export PILOT_ACCEPTANCE_PROJECT=smartnote-release-accept PILOT_ACCEPTANCE_PORT=5273
export PILOT_ENV_FILE=~/.config/smartnote/pilot.env
python3 -m pytest tests/integration/pilot -q
npx playwright test tests/e2e/pilot
```

Приёмка сама поднимает свой проект с чистыми volumes и не трогает рабочий `smartnote-pilot`. Результаты и границы — в [RELEASE_REPORT](RELEASE_REPORT.md); реальные устройства и внешний сервер туда не входят.
