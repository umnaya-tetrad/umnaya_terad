# Карта знаний SmartNote

Текущая реализация processing и безопасное доказательство – [HANDOFF](../pilot/planning/processing/HANDOFF.md), [RUNTIME_REPORT](../pilot/planning/processing/RUNTIME_REPORT.md). Это каноничный результат 99 runtime tests/32 случаев; прежние source-аудиты сохраняют дату и не заменяют его.


Срез: 18.11.2026. Назначение – находить первоисточник и понимать, что именно он подтверждает. Общие инструкции: [AGENTS.md](../AGENTS.md). Технические выводы: [INTEGRATION_AUDIT.md](INTEGRATION_AUDIT.md).

Последующая предметная документация текущего мобильного учительского пилота: [pilot/README.md](../pilot/README.md). Там находятся подтвержденные ответы, продукт, сценарий, технический план, данные/доступ и приемка. Для подробных требований текущего пилота использовать ее согласованные уточнения; общие материалы ниже сохраняют роль контекста и основания.

## 1. Три слоя и их полномочия

**Итоговый слой текущего пилота, 18.11.2026:** [спецификация 1.0](../pilot/README.md), [R01–R79](../pilot/DECISIONS.md), [сценарий](../pilot/TEACHER_FLOW.md), [формулы](../pilot/SUMMARY_METRICS.md), [архитектура](../pilot/TECHNICAL_PLAN.md), [этапы реализации](../pilot/IMPLEMENTATION_PLAN.md) и [приемка](../pilot/TRIAL_AND_ACCEPTANCE.md). Требования этого слоя согласованы; код/испытания пока не выполнены. Исторические документы не возвращают закрытые вопросы, ученические ограничения для учителя или исключенные функции.

| Слой | Что из него берем | Чего он сам по себе не подтверждает |
|---|---|---|
| Корневая папка и `research-garden` | Решения команды, текущий этап, аудиторию, продуктовую ценность, школьный маршрут и исследовательские основания | Сегодняшнюю работоспособность кода и готовность всех заявленных функций |
| `product-kit` | Продуктовый сценарий в экранах, визуальный язык, интерактивный показ, ролик и исходную конкурсную концепцию | Настоящий ИИ, загрузку файлов, сервер, базу, качество и эффект |
| `SmartNoteLanding` | Реализацию анализа одной фотографии, HTTP/API, валидацию, отображение формул, лимит, тесты и исторические бенчмарки | Готовый учительский продукт, утвержденный тариф, полный предметный охват и школьное внедрение |

Продуктовые решения сопоставляем по дате и статусу, фактическое поведение – по коду и проверке. Несовпадение не устраняется выбором одного источника для всех вопросов: требование может быть актуальным, а код еще не соответствовать ему.

## 2. Канонические продуктовые материалы

| Источник | Содержание и способ использования |
|---|---|
| [PROJECT_CONTEXT.md](../PROJECT_CONTEXT.md) | Основной согласованный срез на 18 ноября; технические сообщения автора от 17 ноября. Два сценария, фокус школ, алгебра 7–9, CAS, команда, сроки и неизвестное. Новый осмотр кода описан отдельно в аудите |
| [SCHOOL_PROCESS.md](../SCHOOL_PROCESS.md) | Адресация директору/завучу, встреча с учителем, интервью, обучение, самостоятельная проба, итог, типы подтверждений. Последние договоренности уточняют ранние исследовательские предложения |
| [PRODUCT_DESCRIPTION.md](../PRODUCT_DESCRIPTION.md) | Исходная концепция 30 октября: боль, ценность, роли, оба сценария, границы, исследовательский задел, цели, экономика. Использовать с ноябрьскими поправками |
| [Конкурсная заявка DOCX](../references/product-kit/references/contest-project.docx) | Сохраненный первичный конкурсный артефакт. Сведения о нем пересказаны в продуктовом описании; в текущем обследовании DOCX заново не разбирался |
| [Решения](DECISIONS.md) | Компактный реестр принятых ориентиров и открытых развилок. Новые предложения не заменяют исходные решения автоматически |

В корневом продуктовом описании ссылка на исходный DOCX ведет в прежний соседний проект `PermKonkurs`. Доступная копия теперь находится по ссылке выше. Исходный текст сохранен; в передаваемой копии `product-kit/docs/PRODUCT_DESCRIPTION.md` ссылка уже адаптирована.

## 3. Интерфейс, демонстрация и питч

| Источник | Когда открывать |
|---|---|
| [README комплекта](../references/product-kit/README.md) и [его AGENTS](../references/product-kit/AGENTS.source.md) | Вход, установка, ограничения, локальные правила изменений |
| [START_HERE](../references/product-kit/START_HERE.html), [каталог](../references/product-kit/preview/index.html) | Быстро посмотреть комплект без установки зависимостей |
| [preview/app.html](../references/product-kit/preview/app.html) | Пройти интерактивный сценарий. Состояние только в памяти вкладки |
| [manifest.json](../references/product-kit/preview/manifest.json) и `preview/screens/` | Идентификаторы и отдельные HTML всех 28 состояний: 26 приложения и 2 камеры |
| [INTERFACE_GUIDE.md](../references/product-kit/docs/INTERFACE_GUIDE.md) | Карта действий учителя и ученика, статусы, границы макетов и визуальный стиль |
| [AppScreen.tsx](https://github.com/svn-re7/smartnote-product-kit/blob/d32870f32397eb63e9b2751bb7ab5738905c1b79/src/ui/AppScreen.tsx), [screens.css](https://github.com/svn-re7/smartnote-product-kit/blob/d32870f32397eb63e9b2751bb7ab5738905c1b79/src/ui/screens.css) | Визуальные компоненты, типы экранов, оформление и демонстрационные данные |
| [prototype.tsx](https://github.com/svn-re7/smartnote-product-kit/blob/d32870f32397eb63e9b2751bb7ab5738905c1b79/src/prototype.tsx) | Переходы, локальные классы/темы/работы, подтверждения и отклонения. Это сценарная оболочка |
| [IMPLEMENTATION.md](../references/product-kit/docs/IMPLEMENTATION.md) | Устройство экспорта, Vite и Remotion, куда вносить изменения |
| [STATUS.md](../references/product-kit/docs/STATUS.md) | Сообщенные проверки комплекта на 18 ноября и известные ограничения. Не новый прогон этой задачи |
| [Ролик v6](../references/product-kit/media/smart-notebook-v6.mp4), [VIDEO_V6.md](../references/product-kit/docs/VIDEO_V6.md) | Питч процесса: 135 секунд, учитель и ученик; исторические заметки о монтаже |
| [ActionVideo.tsx](https://github.com/svn-re7/smartnote-product-kit/blob/d32870f32397eb63e9b2751bb7ab5738905c1b79/src/scenes/video-v6/ActionVideo.tsx), [CameraCapture.tsx](https://github.com/svn-re7/smartnote-product-kit/blob/d32870f32397eb63e9b2751bb7ab5738905c1b79/src/scenes/video-v6/CameraCapture.tsx) | Исходники монтажа и иллюстрации камеры; реальную камеру не включают |

Демо учителя: классы → темы → работа → комплект → отчет → очередь → подтверждение/отклонение → дополнительное внимание → аналитика. `Manual` отмечает просмотр, полноценное редактирование математического вывода в нем не реализовано. Счетчики `12 / 7 / 3 / 2` иллюстративные.

Демо ученика: собственная попытка → камера → просмотр фото → анализ → правило → исправление в тетради → повторный снимок → успех. Ошибка и успех предопределены; фотографии заменены формулами и иллюстрациями.

## 4. Реализация лендинга

Корневого README в загруженной ревизии нет. Вместо него используем следующую навигацию.

| Источник | Что дает |
|---|---|
| [AGENTS.md](../references/SmartNoteLanding/AGENTS.source.md) | Локальная карта и правила FastAPI/PostgreSQL, данных и проверок |
| [frontend-demo.md](../references/SmartNoteLanding/docs/frontend-demo.md) | Публичная главная, `/pricing`, отключенный по умолчанию `/internal`, моки и импорт JSON |
| [backend-integration.md](../references/SmartNoteLanding/docs/backend-integration.md) | Путь фото → FastAPI → Polza → JSON → UI, настройка и лимит. Параметры сверять с кодом |
| [architecture.md](../references/SmartNoteLanding/docs/architecture.md) | Архитектурный замысел, поток, будущие сущности и аналитика. Не инвентаризация реализованных таблиц |
| [llm-contract.md](../references/SmartNoteLanding/docs/llm-contract.md) | Семантика версии 1.0, статусы, поля, инварианты. Широкая математика и исправленный шаг расходятся с нынешней школьной рамкой |
| [main.py](https://github.com/svn-re7/SmartNoteLanding/blob/b8423b01a5eb56601539e83d14c382d23eea1a61/app/main.py) | Текущие `/api/health`, `/api/quota`, `/api/analyze`, cookie, подключение БД и обработка ошибок |
| [schemas.py](https://github.com/svn-re7/SmartNoteLanding/blob/b8423b01a5eb56601539e83d14c382d23eea1a61/app/schemas.py), [analysis.ts](https://github.com/svn-re7/SmartNoteLanding/blob/b8423b01a5eb56601539e83d14c382d23eea1a61/src/types/analysis.ts) | Серверная и клиентская модели результата |
| [model_catalog.py](https://github.com/svn-re7/SmartNoteLanding/blob/b8423b01a5eb56601539e83d14c382d23eea1a61/app/model_catalog.py), [prompts.py](https://github.com/svn-re7/SmartNoteLanding/blob/b8423b01a5eb56601539e83d14c382d23eea1a61/app/prompts.py), [polza_client.py](https://github.com/svn-re7/SmartNoteLanding/blob/b8423b01a5eb56601539e83d14c382d23eea1a61/app/polza_client.py) | Фактическая модель, режим ответа, версия промпта и адаптер |
| [image_validation.py](https://github.com/svn-re7/SmartNoteLanding/blob/b8423b01a5eb56601539e83d14c382d23eea1a61/app/image_validation.py) | MIME, декодирование, размер и разрешение файла |
| [quota.py](https://github.com/svn-re7/SmartNoteLanding/blob/b8423b01a5eb56601539e83d14c382d23eea1a61/app/quota.py), [миграция](https://github.com/svn-re7/SmartNoteLanding/blob/b8423b01a5eb56601539e83d14c382d23eea1a61/app/migrations/001_daily_quota.sql) | PostgreSQL-лимит и резервации; это не база учительских работ |
| [PhotoAnalysis.tsx](https://github.com/svn-re7/SmartNoteLanding/blob/b8423b01a5eb56601539e83d14c382d23eea1a61/src/components/PhotoAnalysis.tsx), [AnalysisResult.tsx](https://github.com/svn-re7/SmartNoteLanding/blob/b8423b01a5eb56601539e83d14c382d23eea1a61/src/components/AnalysisResult.tsx), [MathFormula.tsx](https://github.com/svn-re7/SmartNoteLanding/blob/b8423b01a5eb56601539e83d14c382d23eea1a61/src/components/MathFormula.tsx) | Выбор и отправка файла, статусы, первый ошибочный шаг, исправление, KaTeX |
| [App.tsx](https://github.com/svn-re7/SmartNoteLanding/blob/b8423b01a5eb56601539e83d14c382d23eea1a61/src/App.tsx), [LandingPage.tsx](https://github.com/svn-re7/SmartNoteLanding/blob/b8423b01a5eb56601539e83d14c382d23eea1a61/src/components/LandingPage.tsx), [PricingPage.tsx](https://github.com/svn-re7/SmartNoteLanding/blob/b8423b01a5eb56601539e83d14c382d23eea1a61/src/components/PricingPage.tsx) | Маршруты и публичная оболочка; тарифные кнопки не подключены к оплате |
| [compose.yaml](https://github.com/svn-re7/SmartNoteLanding/blob/b8423b01a5eb56601539e83d14c382d23eea1a61/compose.yaml), [package.json](https://github.com/svn-re7/SmartNoteLanding/blob/b8423b01a5eb56601539e83d14c382d23eea1a61/package.json), [requirements.txt](https://github.com/svn-re7/SmartNoteLanding/blob/b8423b01a5eb56601539e83d14c382d23eea1a61/app/requirements.txt) | Реальные команды и зависимости трех сервисов разработки |

Переиспользовать прежде всего адаптер, валидацию, контракт, математический рендер и обработку ошибок. Учительские сущности, сохранение решения педагога и сводку предстоит реализовать поверх этого задела.

## 5. Качество, примеры и экономика

| Материал | Назначение и ограничения |
|---|---|
| [model-benchmark.md](../references/SmartNoteLanding/docs/model-benchmark.md) | Методика, планы gold-набора, задержка, стоимость, контракт и ограничения внешнего набора. Планируемый набор не считать уже размеченным |
| [benchmark-run-history.md](../references/SmartNoteLanding/docs/benchmark-run-history.md) | Исторические сентябрьские запуски и выбор модели. Доступность моделей и сегодняшние цены не подтверждает |
| [model-math-assessment.md](../references/SmartNoteLanding/docs/model-math-assessment.md) | 11 работ: входной фильтр на пяти и ручной оракул на шести. Не смешивать с сообщенными автором 20 тестами |
| [inputExamples/README.md](https://github.com/svn-re7/SmartNoteLanding/blob/b8423b01a5eb56601539e83d14c382d23eea1a61/inputExamples/README.md) | Пять синтетических PNG/SVG и ожидаемые результаты; `run_e2e_examples.py` вызывает настоящий API |
| [benchmark/README.md](https://github.com/svn-re7/SmartNoteLanding/blob/b8423b01a5eb56601539e83d14c382d23eea1a61/inputExamples/benchmark/README.md), [manifest.json](https://github.com/svn-re7/SmartNoteLanding/blob/b8423b01a5eb56601539e83d14c382d23eea1a61/inputExamples/benchmark/manifest.json) | Происхождение внешних фото и ограничения использования. README говорит о 10, фактически файлов JPG 11 – см. аудит |
| [benchmarkSnapshot.json](https://github.com/svn-re7/SmartNoteLanding/blob/b8423b01a5eb56601539e83d14c382d23eea1a61/src/data/benchmarkSnapshot.json) | Статический нормализованный срез для внутреннего UI, не новый запуск |
| `SmartNoteLanding/app/tests/`, тесты `src/` | Существующие проверки маршрута, контракта, адаптера, отображения и внутренних инструментов |
| [Экономическая таблица](https://github.com/svn-re7/SmartNoteLanding/blob/b8423b01a5eb56601539e83d14c382d23eea1a61/outputs/unit_economics_mvp_20260916/smartnote_unit_economics_mvp.xlsx), [генератор](https://github.com/svn-re7/SmartNoteLanding/blob/b8423b01a5eb56601539e83d14c382d23eea1a61/build_weekly_unit_economics.mjs) | Исторический расчет и превью в той же папке; содержание XLSX заново не анализировалось, текущий тариф из него не выводим |

НИРС на FERMAT, 20 примеров со слов автора, сентябрьский benchmark и будущий школьный набор – четыре разных основания. Числа, знаменатели, происхождение и ограничения собраны в аудите.

## 6. Исследовательский архив и школы

Вход: [research-garden/README.md](../research-garden/README.md). В каждой папке запуска находятся `plan.md`, `meta.json`, `report.md`, `audit.md`, реестры `sources-*.jsonl`, `claims-*.jsonl` и приложения. Ссылка вида `[#strand-sN]` в отчете указывает на источник в реестре. Уровень A может подтверждать заявление владельца сервиса, но сам по себе не доказывает эффективность.

| Запуск | Что искать |
|---|---|
| [30 октября: рынок и продуктовая ценность](../research-garden/runs/2026-10-30T10-19-14Z/report.md) | Аналоги, сравнение с мультимодальным чатом, роль учителя, Пермь, экономика. Приложения: [ценность](../research-garden/runs/2026-10-30T10-19-14Z/appendices/value-comparison.md), [конкуренты](../research-garden/runs/2026-10-30T10-19-14Z/appendices/competitors.md), [бизнес-модель](../research-garden/runs/2026-10-30T10-19-14Z/appendices/business-model.md) |
| Тот же запуск: аналоги | [Тьютор AI](../research-garden/runs/2026-10-30T10-19-14Z/appendices/tyutor-deep.md), [Сократ AI](../research-garden/runs/2026-10-30T10-19-14Z/appendices/sokrat-deep.md), [ручное сравнение](../research-garden/runs/2026-10-30T10-19-14Z/appendices/manual-competitor-test.md). Выводы датированы, личное испытание аналогов не заменены кабинетным поиском |
| Тот же запуск: доступ к пользователям | [Контакты Перми](../research-garden/runs/2026-10-30T10-19-14Z/appendices/perm-contacts.md), [интервью](../research-garden/runs/2026-10-30T10-19-14Z/appendices/interviews-and-outreach.md), [протокол сравнения](../research-garden/runs/2026-10-30T10-19-14Z/appendices/pilot-protocol.md). Кандидаты не являются партнерами |
| [17 ноября, 14:11:45Z: ФСИ](../research-garden/runs/2026-11-17T14-11-45Z/report.md) | Исследование заявки, конкурсных критериев и победителей: [чек-лист](../research-garden/runs/2026-11-17T14-11-45Z/appendices/application-checklist.md), [подтверждения](../research-garden/runs/2026-11-17T14-11-45Z/appendices/supporting-documents.md), [победители](../research-garden/runs/2026-11-17T14-11-45Z/appendices/winners-2025.md). Правила перед подачей перепроверять |
| [17 ноября, 14:52:58Z: школьный процесс](../research-garden/runs/2026-11-17T14-52-58Z/report.md) | [Воронка](../research-garden/runs/2026-11-17T14-52-58Z/appendices/school-funnel.md), [встреча](../research-garden/runs/2026-11-17T14-52-58Z/appendices/meeting-playbook.md), [меню пилота](../research-garden/runs/2026-11-17T14-52-58Z/appendices/pilot-menu.md), [формы](../research-garden/runs/2026-11-17T14-52-58Z/appendices/document-forms.md), [методики](../research-garden/runs/2026-11-17T14-52-58Z/appendices/frameworks.md) |
| [Письма, редакция 18 ноября](../research-garden/runs/2026-11-17T14-52-58Z/appendices/deputy-head-emails.md) | Три варианта обращения; ручная редактура первого сохранена. Подготовленный текст не означает отправку |
| [Визуальная схема школы](../research-garden/visuals/school-process-2026-11-17.png) | Иллюстрация; актуальные роли и развилки сверять с корневым `SCHOOL_PROCESS.md` |
| [next-steps-2026-10-30.md](../research-garden/next-steps-2026-10-30.md) | Исторические рекомендации; открытый ученический запуск и реклама из них сейчас отложены |

Ноябрьское уточнение отменяет жесткий лимит «одно письмо и две встречи», предложенный ранним отчетом: число контактов гибкое и зависит от школы. Ученический этап возможен отдельно; учительский достаточен для первого содержательного результата. Доказательство школьного опыта привязано к фактическим действиям, а не наличию положительного письма.

## 7. Копии и обновление

При первоначальном обследовании до последующих ответов по пилоту было установлено:

- `PROJECT_CONTEXT.md` и `SCHOOL_PROCESS.md` совпадают с копиями в `product-kit/docs/` после нормализации переводов строк.
- `PRODUCT_DESCRIPTION.md` отличается только адаптацией ссылки на конкурсный DOCX.
- Все 77 файлов корневого `research-garden` побайтно совпадают с `product-kit/docs/research-garden`.

Результат и ревизии: [SOURCE_SNAPSHOT.json](SOURCE_SNAPSHOT.json). Это исторический срез начального объединения, а не постоянно действующая гарантия совпадения. После уточнения пилота корневые контекст и школьный процесс получили новые дополнения; копии в product-kit намеренно не обновлялись и теперь отстают от этих ответов.

Обновлять так: сначала канонический корневой источник; затем общую сводку/решения; если передаем свежий продуктовый комплект – отдельно просмотреть diff и обновить его копии, сохранив локальные ссылки. Не переносить назад старую копию поверх оригинала. Новые исследования сохранять отдельным датированным запуском. Исторические результаты не переписывать под новые выводы.

Служебные `.playwright-mcp`, `.git`, зависимости и сборочные кэши не являются источниками продуктовых решений. Реальные школьные данные и секреты не должны попадать в общую документацию или Git.

Portable publication: source links have been relocated or pinned; the original sibling-workspace DOCX is included under project-context/references/product-kit/references/contest-project.docx. See ../SOURCES.md.
