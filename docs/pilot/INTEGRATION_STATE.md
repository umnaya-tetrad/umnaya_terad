# Состояние локальной интеграции пилота

Локальная work/application объединена с origin/main 0f8460df6465612a815810b77eb2f60a72376350. Контракт shared v1 / API 1.0.0 взят из 1144c498b4aba1e4e4fe118abe7c3f6f1b940198. Локальный B1 и учительский путь до сохранённой сводки проверены. Приём B4 остаётся за release. [HANDOFF application](../../project-context/pilot/planning/application/HANDOFF.md)

## Что подключает application

- FastAPI создаёт один asyncpg pool и Services в lifespan. app/pilot/router.py агрегирует auth/application/processing/events и монтируется один раз под /api. APP маршруты передают данные в общие порты. Общие обработчики ошибок устанавливаются один раз.
- PostgreSQL 16, одноразовый migrate, backend, worker, frontend и три именованных volume описаны в Compose. API и worker используют один приватный каталог через PILOT_STORAGE_ROOT. Для API используется /health, для worker — согласованный python -m pilot.processing.worker --healthcheck.
- Учительский UI использует относительный /api и сгенерированные типы processing. Сгенерированные Python/TS DTO побайтово совпадают с B0. HTTP-адаптеры вызывают общий валидатор processing.
- В точках входа выделено место для подключения staff в REL-04. Ранний staff может войти, а teacher workspace для него закрыт.

## Проверено в совместном стеке

1. Чистая PostgreSQL 16.15, SQL 001–015, повторный мигратор и seed, healthy API/worker/frontend. Использованы [команды bootstrap](BOOTSTRAP.md).
2. В реальном API прошли доступ двух учителей и staff, приватные фото, пять форматов, повторы ключей, сохранённая сводка и refresh после изменения оценки.
3. В Chrome прошли два комплекта, шесть отзывов, двухэтапный финал и чтение результата после reload. Отдельный запуск остановил worker, оставил два принятых Job в очереди, закрыл браузер и подтвердил сохранность после перезапуска backend и worker.
