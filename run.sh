#!/usr/bin/env bash
# Локальный запуск пилота «Умная тетрадь».
#
# Всё, что обычно нужно менять, — в блоке НАСТРОЙКИ ниже. Остальное трогать не нужно.
# Скрипт не хранит секретов в репозитории: пароли и ключ попадают в локальный файл
# окружения вне Git (~/.config/smartnote/pilot.env, права 600).
#
# Быстрый старт:
#   ./run.sh            # поднять стек и проверить вход
#   ./run.sh logs       # смотреть логи
#   ./run.sh stop       # остановить, данные сохраняются
#   ./run.sh help       # все команды

set -euo pipefail

# ============================== НАСТРОЙКИ ==============================
# Режим: fixture — учебный (без обращений к модели, бесплатно)
#        polza   — реальная модель Gemini через Polza (тратит деньги)
MODE=polza

# Логин и пароль учителя, под которым вы входите.
# Пустой пароль = «взять сохранённый, а если его нет — сгенерировать и запомнить».
LOGIN=teacher1
PASSWORD=

# Необязательные дополнительные аккаунты (нужны, чтобы проверить изоляцию
# двух учителей и закрытый раздел команды). Тоже можно оставить пустыми.
TEACHER2_LOGIN=teacher2
TEACHER2_PASSWORD=
STAFF_LOGIN=staff
STAFF_PASSWORD=

# Ключ Polza. Нужен только при MODE=polza. Не коммитить и не передавать в VITE_*.
POLZA_KEY=

# Модель и маршрут Polza (менять обычно не требуется).
POLZA_MODEL=google/gemini-3.8-flash
POLZA_PROVIDER=google-ai-studio/flex

# Порт интерфейса на 127.0.0.1 и имя Compose-проекта.
PORT=5173
PROJECT=smartnote-pilot

# Файл окружения. Лежит вне репозитория: внутри .env отклоняется проверкой контекста.
ENV_FILE="${PILOT_ENV_FILE:-$HOME/.config/smartnote/pilot.env}"
# ======================================================================

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$ROOT/compose.yaml"

die() { printf 'ошибка: %s\n' "$*" >&2; exit 1; }
note() { printf '%s\n' "$*"; }

command -v docker >/dev/null 2>&1 || die "не найден docker"
docker info >/dev/null 2>&1 || die "Docker не запущен. Откройте Docker Desktop и повторите."
[ -f "$COMPOSE_FILE" ] || die "не найден $COMPOSE_FILE"

# Значение из уже сохранённого env-файла (без выполнения кода из него).
stored() {
  [ -f "$ENV_FILE" ] || return 0
  awk -v key="$1" '
    index($0, key "=") == 1 { print substr($0, length(key) + 2); exit }
  ' "$ENV_FILE"
}

# Случайная строка без символов, ломающих env-файл.
random_string() {
  local length="$1" raw=""
  if command -v openssl >/dev/null 2>&1; then
    raw="$(openssl rand -base64 $(( length * 3 )) 2>/dev/null || true)"
  elif command -v python3 >/dev/null 2>&1; then
    raw="$(python3 -c 'import secrets,sys;print(secrets.token_urlsafe(int(sys.argv[1])))' "$length" 2>/dev/null || true)"
  fi
  [ -n "$raw" ] || die "нет openssl/python3 для генерации пароля — задайте пароль в блоке НАСТРОЙКИ"
  raw="$(printf '%s' "$raw" | LC_ALL=C tr -dc 'A-Za-z0-9' || true)"
  [ ${#raw} -ge "$length" ] || die "не удалось сгенерировать пароль нужной длины"
  printf '%s' "${raw:0:$length}"
}

# Секрет: приоритет — значение из блока НАСТРОЙКИ, затем сохранённое, затем новый.
# Результат печатается; ничего не логируется. length=0 означает «не генерировать».
secret() {
  local chosen="$1" key="$2" length="${3:-24}"
  if [ -n "$chosen" ]; then printf '%s' "$chosen"; return; fi
  local previous
  previous="$(stored "$key")"
  if [ -n "$previous" ]; then printf '%s' "$previous"; return; fi
  if [ "$length" -le 0 ]; then return; fi
  random_string "$length"
}

# Compose env-файл чувствителен к кавычкам, '#', '$' и переводам строк.
check_value() {
  local name="$1" value="$2"
  case "$value" in
    *'
'*) die "$name содержит перевод строки — так нельзя" ;;
    *'"'*|*"'"*) die "$name содержит кавычку — уберите её" ;;
    *'$'*) die "$name содержит \$ — compose подставит переменную; уберите символ" ;;
    *'#'*) die "$name содержит # — в env-файле это начало комментария" ;;
  esac
}

case "$MODE" in
  fixture|polza) ;;
  *) die "MODE должен быть fixture или polza, сейчас: '$MODE'" ;;
esac

# Ключ обязателен только для запуска в режиме polza. Останавливать стек и смотреть
# логи можно и без него: иначе забытый MODE=polza блокировал бы управление.
require_polza_key() {
  [ "$MODE" = "polza" ] || return 0
  [ -n "$POLZA_KEY" ] || [ -n "$(stored POLZA_API_KEY)" ] || die \
    "MODE=polza требует POLZA_KEY. Впишите ключ в блок НАСТРОЙКИ или в $ENV_FILE"
}

POSTGRES_PASSWORD="$(secret '' POSTGRES_PASSWORD 32)"
VISITOR_COOKIE_SECRET="$(secret '' VISITOR_COOKIE_SECRET 48)"
POLZA_KEY="$(secret "$POLZA_KEY" POLZA_API_KEY 0)"
PASSWORD="$(secret "$PASSWORD" PILOT_FIXTURE_TEACHER_1_PASSWORD 20)"
TEACHER2_PASSWORD="$(secret "$TEACHER2_PASSWORD" PILOT_FIXTURE_TEACHER_2_PASSWORD 20)"
STAFF_PASSWORD="$(secret "$STAFF_PASSWORD" PILOT_FIXTURE_STAFF_PASSWORD 20)"

[ ${#VISITOR_COOKIE_SECRET} -ge 32 ] || die "VISITOR_COOKIE_SECRET должен быть не короче 32 символов"
[ -n "$PASSWORD" ] && [ -n "$TEACHER2_PASSWORD" ] && [ -n "$STAFF_PASSWORD" ] || die "не удалось подготовить пароли аккаунтов"

ORIGINS="http://localhost:$PORT,http://127.0.0.1:$PORT"
ENV_BACKUP=""

write_env() {
  for pair in \
    "PILOT_TRANSPORT=$MODE" \
    "POSTGRES_PASSWORD=$POSTGRES_PASSWORD" \
    "VISITOR_COOKIE_SECRET=$VISITOR_COOKIE_SECRET" \
    "POLZA_API_KEY=$POLZA_KEY" \
    "PILOT_FIXTURE_TEACHER_1_LOGIN=$LOGIN" \
    "PILOT_FIXTURE_TEACHER_1_PASSWORD=$PASSWORD" \
    "PILOT_FIXTURE_TEACHER_2_LOGIN=$TEACHER2_LOGIN" \
    "PILOT_FIXTURE_TEACHER_2_PASSWORD=$TEACHER2_PASSWORD" \
    "PILOT_FIXTURE_STAFF_LOGIN=$STAFF_LOGIN" \
    "PILOT_FIXTURE_STAFF_PASSWORD=$STAFF_PASSWORD"; do
    check_value "${pair%%=*}" "${pair#*=}"
  done

  mkdir -p "$(dirname "$ENV_FILE")"
  chmod 700 "$(dirname "$ENV_FILE")" 2>/dev/null || true
  if [ -f "$ENV_FILE" ] && [ -z "$ENV_BACKUP" ]; then
    ENV_BACKUP="$ENV_FILE.bak"
    cp "$ENV_FILE" "$ENV_BACKUP"
    chmod 600 "$ENV_BACKUP"
  fi
  umask 077
  cat > "$ENV_FILE" <<EOF
# Автоматически создано run.sh. Не коммитить: файл содержит пароли и ключи.
PILOT_TRANSPORT=$MODE
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
VISITOR_COOKIE_SECRET=$VISITOR_COOKIE_SECRET
VISITOR_COOKIE_SECURE=false
ALLOWED_BROWSER_ORIGINS=$ORIGINS

POLZA_API_KEY=$POLZA_KEY
POLZA_BASE_URL=https://polza.ai/api/v1
POLZA_MODEL=$POLZA_MODEL
POLZA_PROVIDER=$POLZA_PROVIDER
POLZA_MAX_COMPLETION_TOKENS=25000
POLZA_TIMEOUT_SECONDS=300
POLZA_CONNECT_TIMEOUT_SECONDS=15
POLZA_MAX_PRICE_PROMPT=50
POLZA_MAX_PRICE_COMPLETION=250
POLZA_MAX_PRICE_IMAGE=50

PILOT_FIXTURE_TEACHER_1_LOGIN=$LOGIN
PILOT_FIXTURE_TEACHER_1_PASSWORD=$PASSWORD
PILOT_FIXTURE_TEACHER_2_LOGIN=$TEACHER2_LOGIN
PILOT_FIXTURE_TEACHER_2_PASSWORD=$TEACHER2_PASSWORD
PILOT_FIXTURE_STAFF_LOGIN=$STAFF_LOGIN
PILOT_FIXTURE_STAFF_PASSWORD=$STAFF_PASSWORD
EOF
  chmod 600 "$ENV_FILE"
}

compose() {
  # Compose публикует frontend на PILOT_FRONTEND_PORT, а не на PORT напрямую.
  PILOT_FRONTEND_PORT="$PORT" docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" -p "$PROJECT" "$@"
}

backend_python() {
  compose exec -T backend python "$@"
}

# Вход через настоящий HTTP. Возвращает 0 при 200, 1 при 401, 2 при прочих сбоях.
login_status() {
  local login="$1" password="$2"
  compose exec -T -e LOGIN="$login" -e PASSWORD="$password" -e ORIGIN="http://127.0.0.1:$PORT" \
    backend python -c '
import json, os, sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

body = json.dumps({"login": os.environ["LOGIN"], "password": os.environ["PASSWORD"]}).encode()
request = Request(
    "http://localhost:8000/api/auth/login",
    data=body,
    method="POST",
    headers={"Content-Type": "application/json", "Origin": os.environ["ORIGIN"]},
)
try:
    with urlopen(request, timeout=10) as response:
        sys.exit(0 if response.status == 200 else 2)
except HTTPError as exc:
    sys.exit(1 if exc.code in (401, 403) else 2)
except Exception:
    sys.exit(2)
' >/dev/null 2>&1
}

reset_password() {
  local login="$1" password="$2"
  compose exec -T -e PILOT_ACCOUNT_PASSWORD="$password" backend \
    python -m pilot.operations.manage_accounts --operator-ref run.sh reset --login "$login" \
    >/dev/null
}

# Аккаунт мог быть создан раньше с другим паролем: seed в этом случае ничего не меняет.
ensure_login() {
  local login="$1" password="$2" label="$3" status=0
  login_status "$login" "$password" || status=$?
  case "$status" in
    0) return 0 ;;
    1) note "  $label: пароль отличается от сохранённого — обновляю"
       reset_password "$login" "$password" || die "не удалось обновить пароль $login"
       login_status "$login" "$password" || die "после сброса вход $login не работает" ;;
    *) die "backend не отвечает на вход $login. Смотрите: ./run.sh logs backend" ;;
  esac
}

wait_health() {
  local timeout="${1:-180}" waited=0 state
  while [ "$waited" -lt "$timeout" ]; do
    state="$(compose ps --format '{{.Service}} {{.Health}}' 2>/dev/null || true)"
    if ! printf '%s\n' "$state" | grep -q "starting"; then
      if printf '%s\n' "$state" | grep -q "unhealthy"; then
        printf '%s\n' "$state" >&2
        die "сервис перешёл в unhealthy"
      fi
      if printf '%s\n' "$state" | grep -q healthy; then return 0; fi
    fi
    sleep 3
    waited=$((waited + 3))
  done
  compose ps >&2 || true
  die "сервисы не стали healthy за ${timeout}s"
}

cmd_up() {
  require_polza_key
  write_env
  note "Проект:     $PROJECT"
  note "Режим:      $MODE$( [ "$MODE" = fixture ] && printf ' (учебный, без вызовов модели)' )"
  note "Адрес:      http://127.0.0.1:$PORT"
  note "Логин:      $LOGIN"
  note "Env-файл:   $ENV_FILE"
  [ -n "$ENV_BACKUP" ] && note "Резервная копия env: $ENV_BACKUP"
  note ""

  compose build
  compose run --rm migrate
  compose up -d --wait
  wait_health

  compose exec -T backend python -m pilot.operations.manage_accounts seed >/dev/null 2>&1 \
    || die "не удалось подготовить аккаунты. Смотрите: ./run.sh logs backend"

  ensure_login "$TEACHER2_LOGIN" "$TEACHER2_PASSWORD" "второй учитель"
  ensure_login "$STAFF_LOGIN" "$STAFF_PASSWORD" "сотрудник"
  ensure_login "$LOGIN" "$PASSWORD" "учитель"

  note "Готово. Откройте http://127.0.0.1:$PORT и войдите как $LOGIN."
  if [ "$MODE" = fixture ]; then
    note "Сверху будет метка «Учебный режим»: разборы имитируются, деньги не тратятся."
  else
    note "Режим polza: реальные запросы тратят деньги в пределах общего лимита."
    note "Проверить расход: ./run.sh budget"
  fi
}

cmd_status() {
  [ -f "$ENV_FILE" ] || die "ещё нет $ENV_FILE — выполните ./run.sh"
  note "Проект $PROJECT, режим $(stored PILOT_TRANSPORT)"
  compose ps
  note ""
  note "Лимит и расход:"
  compose exec -T backend python -m pilot.processing.budget status 2>/dev/null || note "  (backend не запущен)"
}

cmd_logs() {
  [ -f "$ENV_FILE" ] || die "ещё нет $ENV_FILE — выполните ./run.sh"
  compose logs --tail=200 -f "$@"
}

cmd_stop() {
  [ -f "$ENV_FILE" ] || die "ещё нет $ENV_FILE"
  compose stop
  note "Остановлено. База и фото сохранены."
}

cmd_down() {
  [ -f "$ENV_FILE" ] || die "ещё нет $ENV_FILE"
  if [ "${1:-}" = "--wipe" ]; then
    note "ВНИМАНИЕ: удаляю volumes проекта $PROJECT — база, фото и аккаунты будут потеряны."
    printf 'Подтвердите, введя имя проекта (%s): ' "$PROJECT"
    read -r answer
    [ "$answer" = "$PROJECT" ] || die "отменено"
    compose down -v
    note "Проект удалён вместе с данными."
    return
  fi
  compose down
  note "Контейнеры удалены, данные сохранены. Полная очистка: ./run.sh down --wipe"
}

cmd_restart() {
  [ -f "$ENV_FILE" ] || die "ещё нет $ENV_FILE"
  require_polza_key
  write_env
  compose up -d --force-recreate
  wait_health
  note "Перезапущено с текущими настройками из блока НАСТРОЙКИ."
}

cmd_reset() {
  [ -f "$ENV_FILE" ] || die "ещё нет $ENV_FILE — выполните ./run.sh"
  require_polza_key
  write_env
  ensure_login "$LOGIN" "$PASSWORD" "учитель"
  ensure_login "$TEACHER2_LOGIN" "$TEACHER2_PASSWORD" "второй учитель"
  ensure_login "$STAFF_LOGIN" "$STAFF_PASSWORD" "сотрудник"
  note "Пароли в базе совпадают с блоком НАСТРОЙКИ. Старые сессии сброшенных аккаунтов закрыты."
}

cmd_budget() {
  [ -f "$ENV_FILE" ] || die "ещё нет $ENV_FILE"
  compose exec -T backend python -m pilot.processing.budget status
}

cmd_pause() {
  [ -f "$ENV_FILE" ] || die "ещё нет $ENV_FILE"
  case "${1:-}" in
    resume) compose exec -T backend python -m pilot.operations.processing_cli resume \
              --operator-ref run.sh --reason "resume via run.sh" ;;
    "")     compose exec -T backend python -m pilot.operations.processing_cli pause \
              --operator-ref run.sh --reason "pause via run.sh" ;;
    *) die "использование: ./run.sh pause [resume]" ;;
  esac
}

cmd_doctor() {
  note "docker:        $(docker --version)"
  note "compose:       $(docker compose version --short 2>/dev/null || echo '?')"
  [ -f "$ENV_FILE" ] && note "env-файл:      $ENV_FILE ($(ls -l "$ENV_FILE" | awk '{print $1}'))" || note "env-файл:      ещё не создан"
  note "режим:         $( [ -f "$ENV_FILE" ] && stored PILOT_TRANSPORT || echo "$MODE")"
  if [ -f "$ENV_FILE" ] && [ -n "$(stored POLZA_API_KEY)" ]; then
    note "ключ polza:    задан"
  else
    note "ключ polza:    пуст"
  fi
  if [ -f "$ENV_FILE" ]; then
    note "backend:       $(compose ps --format '{{.Service}} {{.State}}' 2>/dev/null | tr '\n' ' ')"
  fi
}

cmd_help() {
  cat <<'EOF'
Запуск пилота «Умная тетрадь».

  ./run.sh                собрать, применить миграции, поднять и проверить вход
  ./run.sh up             то же самое (явно)
  ./run.sh restart        пересоздать контейнеры с новыми настройками из блока НАСТРОЙКИ
  ./run.sh stop           остановить, данные сохранить
  ./run.sh down           удалить контейнеры, данные сохранить
  ./run.sh down --wipe    удалить контейнеры и volumes (база, фото) — с подтверждением
  ./run.sh reset          привести пароли аккаунтов к значениям из блока НАСТРОЙКИ
  ./run.sh status         состояние сервисов и расход
  ./run.sh logs [сервис]  логи (backend, worker, frontend, postgres)
  ./run.sh budget         общий лимит и расход модели
  ./run.sh pause          приостановить новые запросы к модели
  ./run.sh pause resume   возобновить
  ./run.sh doctor         окружение, режим, наличие ключа
  ./run.sh help           эта справка

Что менять: блок НАСТРОЙКИ в самом начале файла (MODE, LOGIN, PASSWORD, POLZA_KEY, PORT).
Пароли и ключ сохраняются в локальный файл вне Git; в репозиторий они не попадают.
Пустой PASSWORD означает «использовать сохранённый или сгенерировать один раз».
EOF
}

command="${1:-up}"
[ $# -gt 0 ] && shift || true
case "$command" in
  up)      cmd_up ;;
  restart) cmd_restart ;;
  reset)   cmd_reset ;;
  stop)    cmd_stop ;;
  down)    cmd_down "$@" ;;
  status)  cmd_status ;;
  logs)    cmd_logs "$@" ;;
  budget)  cmd_budget ;;
  pause)   cmd_pause "$@" ;;
  doctor)  cmd_doctor ;;
  help|-h|--help) cmd_help ;;
  *) die "неизвестная команда '$command'. Справка: ./run.sh help" ;;
esac
