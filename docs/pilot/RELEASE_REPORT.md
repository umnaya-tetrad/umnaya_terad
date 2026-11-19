# Отчёт локального выпуска

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
