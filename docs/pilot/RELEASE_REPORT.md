# Отчёт локального выпуска

Отдельный внешний выпуск 20.11.2026: [VPS_LIVE](VPS_LIVE.md) — HTTPS, четыре healthy-сервиса, Playwright-вход teacher/staff и сохранение сессий. Исторические not_run ниже относятся к тем локальным прогонам; полный внешний E2E и платные AI-проверки в новом выпуске также не проводились.

## Повторная проверка после аудита main, 20.11.2026

**Статус: локальная fixture-приемка исправлений завершена.** База аудита — main `a7a74548336348b4e5da5386ea777ce682b623ef`; исправления ведутся в отдельной `fix/release-audit`. Зафиксированный code/test HEAD — `261bb6e2740e168d3cbc27a74462b03b692b8015`: production fixes до `9980048`, браузерные regressions `d88db12`, усиленные integration-тесты `261bb6e`. Исторические PASS от 19.11 ниже сохранены как прежние результаты и не выданы за новый прогон. Внешний выпуск/развертывание приложения — not_run; платных запросов в этой работе нет.

Во время финальных runtime-прогонов HEAD кода/тестов зафиксирован; незакоммиченными оставались только 9 файлов doc-sync. Поэтому checkout не объявляется чистым: `working_tree_clean=false`. Processing run `e801c0690ca94853885ca244f9fa7b1c` завершился с exit 0 и неизменным start/end commit `261bb6e`; source/image parity зафиксирована отдельно. Run `0a2b712e7dc74cbda850d2a0ec1fbcf3` относится к staff 8, а не ко второму полному processing-прогону.

Формальный HANDOFF release остается `in_progress`: gate для `ready` требует собственные `RUNTIME_REPORT.md`/`runtime-results.json` с clean-tree metadata; такой формат этой задачей не создавался и фактическое `false` не переписано на `true`. Это не открытый дефект или pending code/tests: локальные исправления проверены, все 193 backend/integration-теста прошли. Общая готовность пилота не заявляется.

### Исправления и границы

| Дефект аудита | Исправление и ревизия |
| --- | --- |
| Restore перезаписывал существующий остановленный target | `f67c188`: отказ при любых прежних контейнерах, volumes или сети, включая stopped/detached; ошибка inventory означает отказ до `up/cp/pg_restore`. Проверяются коды каждой операции, migrate, health и итоговые счетчики; JSON успеха только после проверки |
| Backup игнорировал `--project`, manifest мог указывать иной источник | `f67c188`: один явный `-p` и согласованный `COMPOSE_PROJECT_NAME` во всех Compose-вызовах; metadata относится к выбранному проекту |
| Launcher помещал пароли в argv и предлагал редактировать tracked-файл | `19114a1`: `-e ИМЯ` с передачей через окружение, секреты в приватном env/окружении; несовпадение пароля при обычном startup не запускает reset, явный `./run.sh reset` остается trusted-операцией |
| Staff history считала evidence как количество фото | `6d1c68d`: количество фото берется из InputVersion выбранного поколения, отдельно от числа evidence |
| Staff summary history показывала `{count}` без числовой основы | `6d1c68d`: числа исторического result, знаменатель, `null` среднего, partial/stale отображаются явно |
| Галерейный HEIC с пустым/общим MIME мог не загрузиться | `f3b7812`: MIME hint нормализуется по имени до Intent и на API boundary; исходные bytes/name/lastModified сохраняются |
| Дополнительный P1 независимого ревью: override обходил restore-защиту через mounts | `9980048`: проверяется effective storage `postgres/backend/worker/migrate`; bind/shared/extra/redirected mounts, `volumes_from`, tmpfs, external/nonlocal/driver_opts отклоняются до создания цели. Допустимы только ожидаемые named mounts и новые обычные local volumes проекта |

Runtime-тесты усилены отдельно: REL-C24 теперь отправляет фото и обрабатывает 60 тетрадей/240 задач. Прежний тест фактически создавал 58 тетрадей (29 на учителя), без upload/submit/processing; его исторический PASS не доказывал требуемую нагрузку. REL-C15 теперь проверяет настоящий POST→429→retry через production worker, строгий лимит двух попыток и restart. Синтетический поставщик реализован только в `tests/integration/pilot/fixture_worker.py` через `httpx.MockTransport`; production домен, очередь, worker, транспортная сериализация, settlement и публикация результата настоящие. Изменений SQL, HTTP-схем, frozen checker/analytics prompt или cap 500 RUB нет.

### Новые прогоны

Команды ниже выполняются в корне checkout, кроме строк с явным `app/`; `<private-cache>` означает приватный каталог evidence вне Git. Для integration/E2E нужны отдельные synthetic project/env/image, как в [RELEASE_RUNBOOK](RELEASE_RUNBOOK.md): runtime `smartnote-release-fix-focus` на 5483 с `PILOT_ENV_FILE`/`PILOT_COMPOSE_OVERRIDES`/`PILOT_BASE_URL`/`PILOT_EVIDENCE_DIR`, UI — `smartnote-release-ui-fixes` на 5484. Секреты не передаются в argv и не входят в отчет. В Windows использовался существующий Python 3.12.10 env `<SmartNote>/.cache/processing-env/Scripts/python.exe`; команда `python` в таблице обозначает этот интерпретатор. Processing использовал `PILOT_TRANSPORT=fixture` и отдельный `PILOT_TEST_DATABASE_URL` на loopback PostgreSQL 16.15/56436; Docker runtime — Server 29.8.0, Python 3.12.14/PostgreSQL 16.15 в контейнерах.

| Команда/проверка | Фактический результат и границы |
| --- | --- |
| `python -m pytest tests/unit/pilot -q` | PASS, 63 теста; собственный прогон 8,57 с, независимый повтор 15,93 с. Bash/argv проверяются через Docker stub, отрицательные ветви inventory/mounts — через subprocess stub. Guard/launcher regressions включены в существующий CI job |
| `python -m pytest tests/unit/pilot/test_recovery_guards.py -k real_resolved_compose -q` | Дополнительно отдельно выполнены 2 positive с настоящим read-only `docker compose config`: базовая конфигурация и image/env override. Оба входят также в общий набор 63; нужен Compose CLI, но не Docker mutations/работающий daemon/модель |
| `bash -n run.sh` | PASS |
| `npm test` | PASS, 43 теста /7 файлов; независимый повтор 1,70 с Vitest duration |
| `npm run build` | PASS; это сборка frontend, не внешний выпуск |
| `python -m pytest tests/integration/pilot/test_events_load.py tests/integration/pilot/test_lifecycle_recovery.py -k "rel_c24 or rel_c15_one" -q --tb=short --basetemp=<private-cache>/runtime/focused-pytest --junitxml=<private-cache>/runtime/focused.xml` | PASS, 3 теста/13 deselected, 140,610 с. REL-C24: 2 teacher по 30 тетрадей, циклически 3/4/5 задач, всего 240; 60 POST, 60 settlements, 0,60 synthetic RUB, два одновременно занятых global slots, владельцы/входы/результаты не смешаны. REL-C15: 429→success ровно 2 POST; 429 дважды — ровно 2 POST и terminal failure, третьего нет после restart |
| `npm run test:e2e -- --output <private-cache>/ui/e2e-final-results --reporter=list,junit` | Финальный набор PASS, 15 тестов, 73,572 с; после rebuild проверено совпадение SHA256 `client.ts`, `StaffScreens.tsx`, `pilot.css` между source и frontend image. Frontend image `sha256:50feba6a8779d67d5c04bf8cba4bb1b1dc352252fec5e8de45452586f7af794b`, backend/worker `sha256:93e5aaf6daf38d7398ee78a2a05ca3017d18b789c19f82354667b155dd5d38f3`. Предыдущий 15 PASS/70,845 с — отдельный промежуточный прогон |
| Дополнительная реальная браузерная проверка HEIC | PASS на изолированном local fixture: 3320 байт native HEIC, `File.type=''`, upload 201; PNG и HEIC сохранены как 2 фото, submit содержит оба. Это Chromium/Playwright, не настоящее iPhone/Android |
| Staff histories и responsive | PASS: одна фотография/4 evidence показана как «1 из 1»; исторические summary показывают basis 1/0, среднее `null`, partial/stale, без literal `{count}`. 30 responsive проверок на локальном браузере; физические устройства не проверялись |
| `python -m pytest tests/integration/pilot -q --tb=short --basetemp=<private-cache>/runtime/final-pytest --junitxml=<private-cache>/runtime/integration-final.xml` | PASS, 51 тест, 609,321 с по JUnit, 0 failed/errors/skipped, code/test HEAD `261bb6e`. Actual Docker: конфликт `--project`/`COMPOSE_PROJECT_NAME` выбирает правильный источник; остановленная существующая restore-цель отклонена, marker/cap/container IDs неизменны; fresh restore сохраняет photo SHA256, graph/reviews/summary IDs и unknown/reserve. Источник не изменен. Усиленные C24/C15 входят также в этот полный набор |
| `python -m pytest --confcutdir tests/pilot/application tests/pilot/application -q --junitxml=<private-cache>/runtime/application-final.xml` из `app/` | PASS, 24 теста, 2,359 с; новый прогон на `261bb6e`, реальные route adapters с service doubles |
| `python -m pytest tests/pilot/staff -q --junitxml=<private-cache>/runtime/staff-final.xml` из `app/` | PASS, 8 тестов, 2,669 с; новый прогон на `261bb6e`, реальные staff routes с query/auth doubles |
| `python -m pytest --confcutdir tests tests/test_auth.py tests/test_model_catalog.py tests/test_polza_client.py tests/test_schemas.py -q --junitxml=<private-cache>/runtime/source-final.xml` из `app/` | PASS, 11 тестов, 2,533 с; новый прогон на `261bb6e`, legacy module regressions (это не тесты CLI) |
| `python -m pytest tests/pilot/processing tests/pilot/domain tests/pilot/analytics tests/pilot/events tests/pilot/source -q --junitxml=<private-cache>/runtime/processing-final.xml` из `app/` | PASS, 99 тестов, 299,119 с; 0 failed/errors/skipped, run `e801c0690ca94853885ca244f9fa7b1c`, start/end commit `261bb6e`, exit 0. Production domain/processing/events и дочерние OS workers, test ASGI adapters/mock provider; paid network отсутствует |
| `python project-context/pilot/planning/shared/check_shared.py` | PASS, 73 офлайн-теста, финальный повтор 3,50 с; 159 UX-строк, references/placeholders, frozen checker, API/fixtures/analytics. Это gate спецификаций, без live-запросов |
| `python project-context/pilot/planning/check_tasks.py` | PASS, 39 задач/95 случаев; целостность ТЗ, без runtime-проверки |
| `python scripts/check_context.py` | PASS, structural gate документации; не заменяет смысловое ревью и тесты приложения |
| `git diff a7a7454 --check`, `git diff --check`, `git diff --cached --check` | PASS; состав diff проверен на отсутствие приватных env, бинарных outputs/cache и непредусмотренных артефактов. Поиск типовых credential patterns в добавленных строках совпадений не дал; он не доказывает отсутствие любого возможного секрета |
| Независимое ревью production/test diff | Подтверждено закрытие дополнительного mount P1 на `9980048`; code/test HEAD `261bb6e` и полный runtime/browser proof прочитаны, открытых P1/P2 нет. Doc-sync draft прочитан; контроль его зафиксированного commit выполняется перед Git-передачей |

Дополнительные JSON/XML/скриншоты хранятся вне Git в `<SmartNote>/.cache/release-fixes/runtime/` (`final-report.json`, JUnit XML, case evidence), `ui/` (`validation-report.json`, `candidate-parity.json`, screenshots) и `review.md`; переносимые доказательства — тесты репозитория и приведенные здесь результаты. Длительности пяти финальных backend/integration-наборов и E2E взяты из JUnit `testsuite.time`; stdout elapsed включает overhead runner и может отличаться. Браузерные и runtime-проекты изолированы; существующая демонстрация на 5183 и исходный пользовательский worktree не изменялись.

**Не проверено этой работой:** платная модель/Gemini и качество ее новых ответов, реальные Android/iPhone и камера/галерея на них, полный интерактивный `run.sh up` на Windows с настоящим Docker (Bash/Docker-stub и read-only config этого не доказывают), внешний сервер/HTTPS/deploy, школьная апробация и экономия полного времени учителя. Отдельный прежний text-only smoke processing описан в его отчете и не является новым release-прогоном.

## Исторический результат от 19.11.2026

19.11.2026. Локальная сборка проверена на этой машине. Внешний сервер, публикация и школьная апробация **not_run**: этот отчёт их не подтверждает.

## Кандидат

| Поле | Факт |
| --- | --- |
| Ветка | `release_tasks` от `002d814de6bab3b946208e0155e54e65c035cb27` |
| Кандидатный commit | `942bcb1` (REL-11) + коммит REL-12 с этой матрицей; финальный SHA — `git log -1` |
| Контракт | shared v1 / OpenAPI 1.0.0, `1144c498b4aba1e4e4fe118abe7c3f6f1b940198` |
| Source | SmartNoteLanding `d62f5ecb8c1c53b1c97faf06530b8d84e691f88d` |
| Processing | `9d788953a298ff03b7e7903a6b3015cc83f3045d`, влит как `0f8460df6465612a815810b77eb2f60a72376350` |
| Transport приёмки | `PILOT_TRANSPORT=fixture`, внешних вызовов модели нет |
| Приёмочный проект | `smartnote-release-accept`, frontend `127.0.0.1:5273`; рабочий `smartnote-pilot` не затрагивается |
| Платформа проверки | macOS (darwin), Docker 29.4.3, Chrome 156 (Playwright 1.64.1), PostgreSQL 16.15, Python 3.12.14 в контейнере |

## Итоговые прогоны

| Проверка | Результат |
| --- | --- |
| `python project-context/pilot/planning/shared/check_shared.py` | PASS, 73 офлайн-теста |
| `python scripts/check_context.py` | PASS, 512 файлов, 996 локальных ссылок |
| `npm test` | PASS, 7 файлов / 28 тестов |
| `npm run build`, `npx tsc -b` | PASS (предупреждение Vite о чанке ~550 КБ) |
| `pytest --confcutdir tests/pilot/application tests/pilot/application -q` из `app/` | PASS, 24 теста |
| `pytest tests/pilot/staff -q` из `app/` | PASS, 8 тестов |
| `pytest tests/integration/pilot -q` | PASS, 49 тестов (238,9 с) |
| `npx playwright test tests/e2e/pilot` | PASS, 14 тестов; восемь полных прогонов подряд зелёные |
| `ruff check` по затронутым Python-файлам | PASS |
| `git diff --check` | PASS |

## Матрица A01–A25

Статус относится к локальной интеграционной проверке release. Отдельно указано, что осталось за пределами этой среды.

| A-ID | Release cases | Статус | Доказательство |
| --- | --- | --- | --- |
| A01 | C05/C06/C26 | pass | Готовые аккаунты, вход/выход, нет регистрации; `test_acl_staff.py -k rel_c05/rel_c06`, `teacher_flow.spec.ts --grep REL-C26` |
| A02 | C08/C27 | pass (эмуляция) | Загрузка PNG/JPEG/HEIC, отказ PDF 415, приватный asset; `--grep REL-C08`, `mobile_layout.spec.ts`. Реальная камера — not_run |
| A03 | C09/C11 | pass | Сообщения о нехватке условия/нечитаемости приходят из контракта, не как ошибка ученика; `--grep REL-C09/C11` |
| A04 | C09/C10/C13 | pass | Один submit — все фото; продолжение на втором фото; новая версия входа |
| A05 | C09/C11/C15 | pass (fixture) | Компактный разбор ≤4 evidence и первый неверный шаг с правилом; качество живой модели не проверялось |
| A06 | C09/C27 | pass (эмуляция) | Четыре ширины, текст 200%, отсутствие горизонтальной прокрутки; устройства not_run |
| A07 | C11 | pass | Отдельный отзыв на задачу, соседние оценки независимы |
| A08 | C11/C22/C23 | pass | Красная отметка не запускает retry; спорное вне подтверждённой математики |
| A09 | C13/C16 | pass | Замена входа снимает согласия; old analysis не принимает отзыв; fencing |
| A10 | C11/C15/C19 | pass | Skip только неоценимой задачи, один автоповтор, блокеры финала |
| A11 | C15/C16 | pass | Не более двух попыток; unknown удерживает резерв, нет blind resend |
| A12 | C04/C05/C27/C28 | pass (эмуляция) | Restart сохраняет данные; reset аккаунта; мобильная вёрстка; backup/restore. Реальные устройства not_run |
| A13 | C12 | pass | Идемпотентный повтор, конфликт payload, stale guard |
| A14 | C13/C19/C20 | pass | Поколение 2→3, двухэтапный финал, закрытый состав |
| A15 | C14/C20 | pass | Удаление задачи сохраняет общее фото; удаление проверки в работе |
| A16 | C19/C20/C21/C22 | pass | GET не запускает, retry того же snapshot, stale/refresh, закрытый состав |
| A17 | C23 | pass (контракт) | `validate_pair` на четырёх парах; числа oracle 4/1/1/1/1, avg 0,5. Смысловая группировка живой модели — not_run |
| A18 | C09/C23 | pass (контракт) | Незавершённость отдельно, не увеличивает ошибки; `mixed` и `synonyms` |
| A19 | C02/C10/C24 | pass (fixture) | Один transport-source, фон, 60 тетрадей двух учителей; реальная модель not_run |
| A20 | C06/C07 | pass | Staff read-only, аудит, отказ teacher и staff-mutation |
| A21 | C07/C25 | pass | События с серверной атрибуцией, без частичного приёма, без утечек в журнал |
| A22 | C01/C25/C28 | pass | Приём B4, безопасные журналы, backup/restore в отдельный проект |
| A23 | C16/C17/C28 | pass (fixture) | Unknown/fencing, общий cap с hot-change, неизменность резервов |
| A24 | C18 | pass | Pause останавливает только новые dispatch, resume продолжает |
| A25 | C01/C23/C26/C27 | pass (локально) | Контракт, валидатор, отсутствие исключённых функций, адаптивная вёрстка. Сервер и апробация not_run |

## REL-C01–C28

| Case | Статус | Где доказательство |
| --- | --- | --- |
| C01 | pass | Приём B4: HANDOFF, сверка SHA, DTO и SQL |
| C02 | pass | Compose, transport-source, health, fail-closed polza |
| C03 | pass | `test_compose_backup.py -k rel_c03*`, сериализация и checksum |
| C04 | pass | `test_compose_persistence.py -k rel_c04` + browser `--restart` |
| C05 | pass | `test_acl_staff.py -k rel_c05*` |
| C06 | pass | `test_acl_staff.py -k rel_c06` |
| C07 | pass | `test_staff_readonly.py`, `staff_readonly.spec.ts` |
| C08 | pass | `teacher_flow.spec.ts --grep REL-C08` |
| C09 | pass | `--grep REL-C09` |
| C10 | pass | `--grep REL-C10`; тест проходит документированный 409-путь через «Обновить страницу» |
| C11 | pass | `--grep REL-C11` |
| C12 | pass | `test_lifecycle_recovery.py -k rel_c12*` |
| C13 | pass | `-k rel_c13*` |
| C14 | pass | `-k rel_c14*` |
| C15 | pass | `-k rel_c15*` |
| C16 | pass | `-k rel_c16*` |
| C17 | pass | `test_funds_control.py -k rel_c17*` |
| C18 | pass | `-k rel_c18*` |
| C19 | pass | `test_analytics_finalization.py -k rel_c19*`, `--grep REL-C19` |
| C20 | pass | `-k rel_c20` |
| C21 | pass | `-k rel_c21*` |
| C22 | pass | `-k rel_c22*` |
| C23 | pass | `-k rel_c23*` |
| C24 | pass | `test_events_load.py -k rel_c24` |
| C25 | pass | `-k rel_c25*` |
| C26 | pass | `test_compose_persistence.py -k rel_c26`, `--grep REL-C26` |
| C27 | pass (авто) | `mobile_layout.spec.ts`; реальные устройства not_run |
| C28 | pass | `test_compose_backup.py -k rel_c28*` |

## Мобильная приёмка (REL-C27)

| Шаг | Как проверено | Результат |
| --- | --- | --- |
| Ширины 320/360/390/430 CSS px | `npx playwright test tests/e2e/pilot/mobile_layout.spec.ts` | PASS: нет горизонтальной прокрутки, все действия внутри области, кнопки ≥44 px |
| Текст 200% | тот же прогон, `html { font-size: 36px }` | PASS: заголовки и действия видимы, загрузка фото и submit работают |
| Диалоги | тот же прогон | PASS: диалог вписан в 320 px, отмена возвращает экран |
| Увеличение фото | тот же прогон | PASS: просмотр и `zoomed` работают |
| Длинная формула | тот же прогон | PASS: `overflow-x: auto` у блока формулы |
| Готовность не закрывает съёмку | `--grep REL-C10` | PASS |
| Негативный контроль детектора | временный элемент шириной 900 px | PASS: переполнение обнаруживается |

Ручные шаги на настоящем Android и iPhone (камера, галерея, HEIC, отказ в разрешении, сворачивание, возврат, второй вход) **not_run**: устройств нет, эмуляция их не заменяет.

## Ограничения и следующий шаг

- Реальная модель Polza, её качество и стоимость в release не проверялись: платных вызовов не было. Отдельный text-only smoke выполнен processing-направлением и здесь не переоткрывается.
- Внешний HTTPS/домен, reverse proxy и школьная выдача аккаунтов не выполнялись — отдельный внешний выпуск.
- Скорость проверки задачи и экономия времени учителя не измерялись; длительность прогона тестов не является этими показателями.
- Восстановление из бэкапа другим человеком по runbook — организационная отметка, а не автоматическая проверка.
- Следующий шаг: внешний деплой на существующий сервер с резервной копией и откатом, затем самостоятельная апробация учителя.
