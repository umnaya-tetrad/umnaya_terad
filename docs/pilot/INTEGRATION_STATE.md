# Состояние локальной интеграции пилота

Ветка application — локальная work/application. Контракт shared v1 / API 1.0.0 взят из 1144c498b4aba1e4e4fe118abe7c3f6f1b940198. При старте в origin был только main. У проекта пока нет объединённой базы B1 и принятой передачи B4. Актуальные доказательства и точные блокеры записаны в [HANDOFF application](../../project-context/pilot/planning/application/HANDOFF.md).

## Что подключает application

- FastAPI создаёт один asyncpg pool и Services в lifespan. app/pilot/router.py агрегирует auth/application/processing/events и монтируется один раз под /api. APP маршруты передают данные в общие порты. Общие обработчики ошибок устанавливаются один раз.
- PostgreSQL 16, одноразовый migrate, backend, worker, frontend и три именованных volume описаны в Compose. API и worker используют один приватный каталог через PILOT_STORAGE_ROOT. Для API используется /health, для worker — согласованный python -m pilot.processing.worker --healthcheck.
- Учительский UI использует относительный /api. Поставляемые с B1b сгенерированные DTO сравниваются с B0. Пока TS читает типы из зафиксированного shared, а ASGI-тесты загружают shared Python DTO только в тестовом процессе.
- В точках входа выделено место для подключения staff в REL-04. Ранний staff может войти, а teacher workspace для него закрыт.

## При появлении B1b и B3

1. Сверить shared revision и поставку processing по [HANDOFF processing](../../project-context/pilot/planning/processing/HANDOFF.md), особенно сигнатуры auth, revision, подготовку и приватную выдачу фото, Settings, worker health и путь storage.
2. В объединённом checkout выполнить [команды bootstrap](BOOTSTRAP.md) и сверить B1 с чистой PostgreSQL. Проверить seed дважды на тех же реквизитах, ACL двух учителей, фото и сохранённый Job при закрытии приложения.
3. На B3 исполнить smoke двухэтапного финала, повтор ключа, сохранённую сводку и сценарии перезапуска/конфликтов из [APP-C33](../../project-context/pilot/planning/application/ACCEPTANCE.md#app-c33-полный-b4-путь-и-вечерний-кандидат). Точный SHA интеграции, результат и владельцев принять в обоих HANDOFF.
