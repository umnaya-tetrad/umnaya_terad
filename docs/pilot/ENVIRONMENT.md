# Какие env-файлы используются

20.11.2026. Сверено с кодом `e9154ec`: [run.sh](../../run.sh), [Compose](../../compose.yaml), [Settings](../../app/config.py) и host wrappers. Это описание локального окружения; серверная конфигурация и deploy им не подтверждаются. Секретные значения не читались и здесь не публикуются.

`pilot.env` — имя приватного файла по умолчанию, не файл из Git; на этой машине он не создан. Текущие стенды используют свои `compose.env`. Шаблон — корневой `.env.example`. Добавлять учителей в env не требуется: аккаунты хранятся в БД.

## Файлы и потребители

| Файл / механизм | Что реально происходит |
| --- | --- |
| Корневой [.env.example](../../.env.example) | Полный шаблон локальной Compose-конфигурации с пустыми секретами. Сам по себе не загружается и не является готовым env-файлом |
| [project-context/pilot/ai/.env.example](../../project-context/pilot/ai/.env.example) | Reference-профиль AI-адаптера. Не содержит всей конфигурации приложения/БД/аккаунтов и не заменяет корневой шаблон |
| Приватный файл по `PILOT_ENV_FILE` | Путь выбирает launcher или поддерживающий его wrapper. Сам Docker Compose эту переменную не обрабатывает: прямому вызову нужен `--env-file` |
| `~/.config/smartnote/pilot.env` | Default `run.sh`; backup/restore/control/reconcile используют его только если он уже существует. Наличие такого файла не следует из наличия документации |
| [app/config.py](../../app/config.py) | `SettingsConfigDict(extra="ignore")`, без `env_file`. Приложение читает окружение процесса, самостоятельно файл `.env`/`pilot.env` не открывает |

В Git есть только два указанных `.env.example`, без рабочих секретов. Реальные env-файлы хранятся вне checkout. В Compose значения файла служат для подстановки в YAML; в контейнер попадают только переменные из `services.*.environment`, а не весь файл. Например, fixture-реквизиты передаются backend, но не frontend. `PILOT_ENV_FILE` не монтирует файл в контейнер и не задает имя Compose-проекта.

## Срез этой Windows-машины

Пути ниже относятся к конкретной машине и не появятся у коллеги после clone. У проектов отдельные БД/volumes. Live использует настоящую Polza, остальные демонстрационные проекты — synthetic fixture; это локальные стенды, не внешний сервер. Значения файлов не раскрываются.

| Назначение / порт | Compose project | Приватный путь / состояние на 20.11.2026 |
| --- | --- | --- |
| Default launcher, порт по умолчанию 5173 | default `smartnote-pilot` | `C:/Users/User/.config/smartnote/pilot.env` **не существует**; это ожидаемый default-путь, а не текущая конфигурация демонстрации |
| Активный live с Polza, 5173 | `smartnote-pilot-live` | `C:/Users/User/.config/smartnote/pilot-live.env`; UI собирается из текущей ветки с отдельным `pilot-live-ui.compose.yaml`, backend/data сохранены |
| Приостановленный UX-стенд | `smartnote-ux-workbench` | `C:/Users/User/.config/smartnote/ux-workbench.env`; контейнеры остановлены, данные сохранены. На 5173 сейчас live |
| Старая активная демонстрация, 5183 | `smartnote-main-audit-729b717` | `C:/Users/User/Desktop/3_year/SmartNote/.cache/main-audit-729b717/runtime/compose.env`; путь подтвержден Compose env-file label контейнера |
| Активный исправленный preview, 5484 | `smartnote-release-ui-fixes` | `C:/Users/User/Desktop/3_year/SmartNote/.cache/release-fixes/ui/compose.env`; путь подтвержден приватным UI run context |
| Завершенный runtime-прогон, 5483 | `smartnote-release-fix-focus` | `C:/Users/User/Desktop/3_year/SmartNote/.cache/release-fixes/runtime/compose.env` остался на диске, сервисы остановлены |

У тестовых проектов были также отдельные Compose override-файлы. Таблица указывает происхождение env, а не команду для их пересоздания: без исходного набора `-f` не воспроизводить эти проекты. Эта документационная работа их не меняла.

## Два способа настройки

### Прямой Compose: полный контроль над приватным файлом

Из корня репозитория подготовьте собственный файл вне Git. Копия шаблона еще требует заполнения: случайный URL-safe `POSTGRES_PASSWORD`, случайный `VISITOR_COOKIE_SECRET` от 32 символов, три разных fixture-логина/пароля для первоначального seed. Для бесплатной локальной проверки задайте `PILOT_TRANSPORT=fixture`; `POLZA_API_KEY` тогда не нужен. `ALLOWED_BROWSER_ORIGINS` должен совпадать с выбранным портом. Секреты вводите в приватном редакторе, без значений в командной строке.

Bash / Git Bash:

```bash
export PILOT_ENV_FILE="$HOME/.config/smartnote/pilot.env"
export COMPOSE_PROJECT_NAME=smartnote-local
export PILOT_FRONTEND_PORT=5173
umask 077
mkdir -p "$(dirname "$PILOT_ENV_FILE")"
test -e "$PILOT_ENV_FILE" || cp .env.example "$PILOT_ENV_FILE"
chmod 700 "$(dirname "$PILOT_ENV_FILE")"
chmod 600 "$PILOT_ENV_FILE"
# Заполнить выбранный файл в приватном редакторе, затем:
docker compose -p "$COMPOSE_PROJECT_NAME" -f compose.yaml --env-file "$PILOT_ENV_FILE" config --quiet
```

PowerShell:

```powershell
$env:PILOT_ENV_FILE = Join-Path $HOME '.config/smartnote/pilot.env'
$env:COMPOSE_PROJECT_NAME = 'smartnote-local'
$env:PILOT_FRONTEND_PORT = '5173'
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $env:PILOT_ENV_FILE) | Out-Null
if (-not (Test-Path -LiteralPath $env:PILOT_ENV_FILE)) {
    Copy-Item -LiteralPath .env.example -Destination $env:PILOT_ENV_FILE
}
# Ограничить доступ к файлу своим Windows-аккаунтом и заполнить в приватном редакторе.
docker compose -p $env:COMPOSE_PROJECT_NAME -f compose.yaml --env-file $env:PILOT_ENV_FILE config --quiet
```

Копирование не перезаписывает уже существующий файл. `config --quiet` проверяет конфигурацию без вывода подставленных секретов, не запускает контейнеры/модель. Сборка, запуск и команды для того же project/env — [RELEASE_RUNBOOK](RELEASE_RUNBOOK.md). Не используйте полный `docker compose config` для публикации диагностики: в нем могут оказаться секреты.

### `run.sh`: готовый локальный preset

Launcher на Bash сам создает/переписывает выбранный файл при `up` (включая вызов без команды), `restart` и `reset`; перед перезаписью существующего файла делает одну копию `.bak`. `stop`, `status`, `logs` и прочие команды управления файл не создают. Пустые пароли при записи генерируются; не нужно вписывать их в tracked `run.sh`.

```bash
PILOT_ENV_FILE="$HOME/.config/smartnote/launcher.env" \
MODE=fixture PROJECT=smartnote-launcher PORT=5173 ./run.sh
```

Этот пример запускает новый выбранный проект; в текущей документационной проверке он не выполнялся. На Windows нужен Bash/Git Bash, это не PowerShell-скрипт.

| Параметр launcher | Приоритет |
| --- | --- |
| Файл | `PILOT_ENV_FILE` процесса, затем `$HOME/.config/smartnote/pilot.env` |
| Режим | `MODE`, затем `PILOT_TRANSPORT` **процесса**, затем `polza` |
| Порт | `PORT`, затем `PILOT_FRONTEND_PORT` процесса, затем `5173` |
| Проект | `PROJECT`, затем `COMPOSE_PROJECT_NAME` процесса, затем `smartnote-pilot` |
| Логины/секреты | Поддерживаемый alias/`PILOT_FIXTURE_*` из процесса, затем выбранные `KEY=value` из файла, затем default логина/генерация пароля. Для Polza ключ не генерируется |

`run.sh` не загружает весь dotenv. `stored()` читает простое `KEY=value` через awk: без `export`, кавычек и интерполяции; проверяемые секреты/логины с кавычками, `$`, `#` или переводом строки отклоняются. `MODE/PORT/PROJECT` и `POLZA_MODEL/POLZA_PROVIDER` не восстанавливаются из сохраненного файла. Например, один `PILOT_TRANSPORT=fixture` внутри файла не переключит default launcher из `polza`.

Совместимые secret aliases процесса — `PASSWORD`, `TEACHER2_PASSWORD`, `STAFF_PASSWORD`, `POLZA_KEY`; также поддержаны соответствующие `PILOT_FIXTURE_*_PASSWORD`, `POLZA_API_KEY`, `POSTGRES_PASSWORD`, `VISITOR_COOKIE_SECRET`. Это не совет вписывать значения в tracked файл или аргументы команд.

Запись идет фиксированным preset-набором: HTTP origins вычисляются из `PORT`, model/provider берутся из process env/defaults, остальные параметры профиля могут быть перезаписаны. Произвольные добавленные строки не сохраняются. Сгенерированный файл не содержит `COMPOSE_PROJECT_NAME`/`PILOT_FRONTEND_PORT`; для прямых Compose-команд custom project/port задаются отдельно, как выше. Для индивидуального env используйте прямой Compose, а не повторную запись launcher.

## Приоритеты и остальные скрипты

Для Compose подстановка из **окружения вызвавшего процесса выше `--env-file`**; затем действуют defaults YAML. Поэтому старые экспортированные `POLZA_*`/`PILOT_FIXTURE_*` могут перекрыть отредактированный файл, в том числе после записи launcher. Его выбор/перезапись файла и итоговая Compose-подстановка — разные этапы. Наш маршрут всегда задает `-p`/`-f`/`--env-file` явно; default-поиск `.env` самим Compose не нужен.

| Инструмент | Что он читает |
| --- | --- |
| `backup_local.py`, `restore_local.py` | `PILOT_ENV_FILE` или существующий default; `PILOT_COMPOSE_OVERRIDES`; явный `--project` (backup также имеет свой default) |
| `processing_control.py`, `reconcile_attempt.py` | `PILOT_ENV_FILE` или существующий default; project из `COMPOSE_PROJECT_NAME` процесса. `PILOT_COMPOSE_OVERRIDES` не поддерживают |
| `tests/integration/pilot/conftest.py` | Требует явный существующий `PILOT_ENV_FILE`, поддерживает overrides; для реквизитов process env выше файла, project/port берутся из `PILOT_ACCEPTANCE_PROJECT/PORT` |
| Legacy `smoke_application.py`, `browser_compose_smoke.mjs`, `browser_followups_compose.mjs` | Не читают `PILOT_ENV_FILE` и не передают `--env-file`; credentials берут из process env. Один export пути их не настраивает. Актуальный explicit-env harness — integration tests |

Browser E2E `tests/e2e/pilot` тоже требует реквизиты в process env; его teacher-flow Compose calls не передают `--env-file`. Не путать его подготовку с Python integration harness.

Host wrappers и test harness из таблицы не создают приватный env-файл вместо оператора; это делает только описанный выше launcher при записи preset. `PILOT_COMPOSE_OVERRIDES` — механизм указанных Python helpers/tests, не общая настройка Compose или `run.sh`.

## Когда нужен restart и где живут аккаунты

Редактирование файла не меняет окружение уже запущенного контейнера. Для новых runtime env-параметров нужен recreate выбранных сервисов с теми же project/file/overrides; обычный `docker compose restart` не применяет их. Команды — в runbook. Изменение `POSTGRES_PASSWORD` в файле/recreate не меняет пароль уже инициализированной БД; это отдельная операция PostgreSQL.

Источник аккаунтов — PostgreSQL `users`, а `PILOT_FIXTURE_*` — реквизиты первоначального seed/launcher, не реестр пользователей. Повторный seed не меняет пароль существующего пользователя. `manage_accounts create --login ... --role teacher|staff` добавляет аккаунт через текущий backend без правки env и без restart; пароль приходит скрытым вводом или из `PILOT_ACCOUNT_PASSWORD`, не argv. Reset — отдельная явная операция, сохраняющая ID/материалы и отзывающая сессии этого аккаунта. Cap/pause также живут в PostgreSQL и меняются trusted CLI без recreate; изменение env не сбрасывает их.
