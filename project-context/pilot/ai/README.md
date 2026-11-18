# Переносимый пакет проверки страниц

19.11.2026. Этот каталог сохраняет точный проверенный промпт, схему и небольшой серверный reference adapter. Это **не готовое приложение**: аккаунты, очередь, хранение, интерфейс и аналитика остаются задачами реализации. Начать с [AI_INTEGRATION.md](../AI_INTEGRATION.md), затем [TOKEN_POLICY.md](TOKEN_POLICY.md). Направление сводки — [AI_ANALYTICS.md](../AI_ANALYTICS.md).

## Что брать в код

| Файл | Назначение |
|---|---|
| [checker-v2.txt](checker-v2.txt) | Точный system prompt финального прогона, не переписывать при переносе |
| [response-schema-v1.2.json](response-schema-v1.2.json), [contract.py](contract.py) | Полный контракт и локальные инварианты |
| [wire-schema-1-photo.json](wire-schema-1-photo.json), [wire-schema-2-photo.json](wire-schema-2-photo.json) | Сохраненные примеры схемы, отправляемой провайдеру |
| [adapter.py](adapter.py) | Один нестриминговый POST, валидация фото/JSON, диагностика и usage |
| [.env.example](.env.example) | Имена переменных без ключа |
| [requirements.txt](requirements.txt) | Зависимости reference-примера; это диапазоны, не production lockfile |
| [provenance.json](provenance.json) | Происхождение, хеши, проверенные и рекомендуемые параметры |
| [examples/provenance.json](examples/provenance.json) | Происхождение реальных dev-ответов в examples |
| [EVIDENCE.md](EVIDENCE.md) | Результаты эксперимента и ограничения переноса |
| [tests/test_adapter.py](tests/test_adapter.py) | Офлайн-проверки контракта и запроса, без платных вызовов |
| [capture-flow.puml](capture-flow.puml), [capture-async.puml](capture-async.puml) | UX и предлагаемая асинхронная последовательность; рядом PNG/SVG |

## Environment сервера

```dotenv
POLZA_API_KEY=<секрет из окружения сервера>
POLZA_BASE_URL=https://polza.ai/api/v1
POLZA_MODEL=google/gemini-3.8-flash
POLZA_PROVIDER=google-ai-studio/flex
POLZA_MAX_COMPLETION_TOKENS=25000
POLZA_TIMEOUT_SECONDS=300
POLZA_CONNECT_TIMEOUT_SECONDS=15
POLZA_MAX_PRICE_PROMPT=50
POLZA_MAX_PRICE_COMPLETION=250
POLZA_MAX_PRICE_IMAGE=50
```

`AdapterConfig.from_env()` читает `os.environ`, **не загружает .env автоматически**. Секрет внедряет существующий процесс запуска сервера. Не копировать ключи в репозиторий или клиент. Имена и defaults данного пакета не следует путать со старыми Settings лендинга: при интеграции намеренно обновить его валидаторы и конфигурацию. Числа max_price — датированные RUB/млн фильтры маршрута из опыта, не teacher quotas. Для checker-v2.txt, response-schema-v1.2.json и examples/*.response.json в корневом .gitattributes заданы исключения `-text`, сохраняющие исходные байты и хеши при clone.

## Минимальный вызов

Из каталога ai либо после включения перенесенного модуля в Python path:

```python
from pathlib import Path
from adapter import AdapterConfig, PolzaAdapter

adapter = PolzaAdapter(AdapterConfig.from_env())
result = adapter.analyze([Path("page-1.jpg"), Path("page-2.jpg")])
metadata = result.safe_metadata()
if result.status == "ok":
    report = result.report
    # Сохранить разбор с исходными notebook/input_version/job ID.
else:
    # Сохранить ошибку попытки; не создавать успешный математический итог.
    pass
```

Этот пример является **платным сетевым вызовом при наличии ключа**. Для офлайн-проверки из ai выполнить `python -m pytest tests -q`; тесты используют подставной transport. Установку зависимостей и запуск проводить в выбранном dev-окружении, не менять системный Python без необходимости. При переносе модулей в package адаптировать локальные импорты вместе с тестами.

Адаптер кодирует исходные изображения в data URL и строит `messages=[system, user]`. User content содержит текст нумерации и упорядоченные `image_url` с `detail=high`. System content — замороженный текст. Остальные поля: `response_format.type=json_schema`, имя `SmartNotePage`, `strict=true`, динамическая упрощенная schema, `reasoning.effort=medium`, `media_resolution=MEDIA_RESOLUTION_HIGH`, `temperature=0`, `max_completion_tokens`, provider only/fallbacks/max_price. Авторитетен исполняемый builder в adapter.py; примеры wire-schema относятся только к числу вложений в имени файла.

Результат содержит status, elapsed, HTTP/provider ID, finish reason, usage/cost, error class/code, валидированный report и raw content. `safe_metadata()` исключает секрет, фото и полный ответ. Полный report/raw content хранить в защищенном хранилище материалов, а не безусловно печатать в логи. Наличие transport status ok не отменяет `report.status=uncheckable` или `task.result=not_assessed`.

Внутри нет автоматического retry, durable queue, идемпотентности приема, подсчета общего бюджета, проверки системного сетевого маршрута и управления версиями. Эти обязанности описаны в [AI_INTEGRATION.md](../AI_INTEGRATION.md). Тесты сборки запроса не доказывают качество новой конфигурации 25k/300 s на живой модели.

## Выполненная проверка пакета

19.11.2026: `python -m pytest tests -q` из ai — **30 passed**, только MockTransport. `python scripts/check_context.py` из корня репозитория — PASS; обе проверки `git diff --check` и `git diff --cached --check` прошли. Независимое чтение документации выявило и помогло исправить описание нормированного времени, единицу размера фото и риск нормализации хешируемых файлов Git.

Для промпта, схемы и трех примеров проверены SHA256 исходных файлов и Git blobs после clean filter: все совпали с provenance. Дополнительно проверено точное совпадение с исходным checker финального эксперимента и хеш фактического текста system message. Диаграммы отрисованы локально PlantUML и просмотрены. На этапе подготовки пакета эти проверки не обращались к платному API и не выполняли commit/push или развертывание. История последующей публикации фиксируется коммитами репозитория.
