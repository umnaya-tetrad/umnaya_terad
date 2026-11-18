# Умная тетрадь / SmartNote

Общая база знаний проекта и спецификация первого учительского пилота. После обычного git clone в репозитории доступны требования, решения, технический план, исследования и сохраненные демонстрационные материалы. История чата для чтения не нужна.

## Коллеге и новому агенту

Откройте репозиторий как рабочую папку и передайте агенту:

> Прочитай AGENTS.md, используй skill smartnote-pilot и восстанови текущий контекст проекта. Затем кратко объясни, какой пилот разрабатываем, что уже готово, какие ограничения согласованы и какой следующий шаг. После этого выполняй мою задачу.

Вход — [AGENTS.md](AGENTS.md). Вся документация — [project-context/](project-context/README.md). Текущий этап — [CURRENT_STATE.md](project-context/CURRENT_STATE.md).

## Три рабочих skill

| Skill | Назначение |
|---|---|
| [smartnote-pilot](.agents/skills/smartnote-pilot/SKILL.md) | Ввести нового агента в проект и текущий этап, выбрать документы для задачи |
| [smartnote-doc-sync](.agents/skills/smartnote-doc-sync/SKILL.md) | После изменений синхронизировать требования, техническое описание и фактический статус |
| [smartnote-preflight](.agents/skills/smartnote-preflight/SKILL.md) | Перед push/merge проверить код, документацию и результаты проверок; при расхождении вызвать doc-sync |

Назначения и условия вызова закреплены в AGENTS.md. Порядок работы и карта обновлений — [AGENT_WORKFLOW.md](project-context/AGENT_WORKFLOW.md). Для другого агента без поддержки skills достаточно попросить прочитать соответствующий SKILL.md как обычную инструкцию.

## Главные документы

- [Что разрабатываем](project-context/pilot/PRODUCT.md), [сценарий учителя](project-context/pilot/TEACHER_FLOW.md), [формулы сводки](project-context/pilot/SUMMARY_METRICS.md).
- [Решения владельца](project-context/pilot/DECISIONS.md), [итоговые статусы вопросов](project-context/pilot/QUESTIONS.md).
- [Архитектура и API](project-context/pilot/TECHNICAL_PLAN.md), [этапы реализации](project-context/pilot/IMPLEMENTATION_PLAN.md), [приемка](project-context/pilot/TRIAL_AND_ACCEPTANCE.md).
- [Роли/данные](project-context/pilot/DATA_AND_ACCESS.md), [логи и время](project-context/pilot/ANALYTICS.md).
- [Макеты, интерактивное демо и ролик](project-context/references/product-kit/START_HERE.html), [источники и ревизии](project-context/SOURCES.md).

Текущее состояние: спецификация 1.0 согласована по R01–R79. Рабочий учительский пилот в этом репозитории еще не реализован; HTML-демо не является приложением с ИИ. Формат письменного итога апробации пока отложен. Проверки окружения и фактической модели предстоят при реализации.

## Проверка комплекта

Из корня: python scripts/check_context.py. Проверка также запускается в GitHub на push/PR. Она находит структурные ошибки; актуальность смысла кода и документации дополнительно проверяет агент по smartnote-preflight.
