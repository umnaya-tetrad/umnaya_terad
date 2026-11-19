# Bootstrap учительского пилота

- Источник SmartNoteLanding `d62f5ecb8c1c53b1c97faf06530b8d84e691f88d`, ветка `codex/direct-landing-experiment`. HEAD и чистая рабочая копия проверены до чтения blob.
- База целевого репозитория и снимок shared v1 / API 1.0.0 `1144c498b4aba1e4e4fe118abe7c3f6f1b940198`. Опубликованной ветки интеграции при старте не было.
- Импорт исключает `.git`, `.env*`, `node_modules`, venv, `dist`, кэши, `inputExamples`, benchmark/outputs, фото и ответы, а также всё `project-context/`. Старые рекламные инструменты, публичная регистрация, тарифы и тесты удаляемых HTTP endpoint остаются в источнике.
- В пилоте приватное хранение оригиналов, аккаунты и очередь принадлежат processing. Старые настройки/обработчики квот, signup и одиночного публичного анализа не активируются. Исходные миграции 001–007 переданы без правок.

## Manifest

Каждый путь слева берётся из указанного commit. Хеши отражают исходные blob до адаптации точек входа, Compose и стилей.

Старые src/styles.css и src/lib/useModal.ts после импорта заменены стилями пилота и нативным диалогом. Старый app/tests/conftest.py и test_security.py исключены из рабочей ветки после исходного прогона, поскольку проверяют снятые public endpoints и main старого продукта.

| Источник | Назначение | Git blob | Основание |
| --- | --- | --- | --- |
| `Dockerfile` | `Dockerfile` | `2e0292134507df01e1b5161c4b0b20ff7b5e3237` | Сборка и зависимости |
| `app/Dockerfile` | `app/Dockerfile` | `f068de18f4997e69a548caf4f3f628962d4a39b0` | Точка входа или backend-задел |
| `app/auth.py` | `app/auth.py` | `6a22279b1c78d2c93c1ec1bd4395d06a125ca5b0` | Точка входа или backend-задел |
| `app/config.py` | `app/config.py` | `aab2429986bd3e0499637f3fabc2890941eee9aa` | Точка входа или backend-задел |
| `app/image_validation.py` | `app/image_validation.py` | `4bc163162d4601d9e666118e7e4f990745c5ec2c` | Точка входа или backend-задел |
| `app/main.py` | `app/main.py` | `60ee64ef066a24827b9ceda06ccb540dfd2cfa77` | Точка входа или backend-задел |
| `app/migrations/001_daily_quota.sql` | `app/migrations/001_daily_quota.sql` | `aae08536e9e98d7d443554ba0f991cc0c00bdcfc` | История схемы |
| `app/migrations/002_authentication.sql` | `app/migrations/002_authentication.sql` | `302559889015b4d0b0d56a7070b3eb16ace8b7e2` | История схемы |
| `app/migrations/003_experiment.sql` | `app/migrations/003_experiment.sql` | `819277c77a8e342930ab569516992ceb052bf3f0` | История схемы |
| `app/migrations/004_quota_owners.sql` | `app/migrations/004_quota_owners.sql` | `dd9c19a39d7a3ad1eca06d8db01c50f4191a770b` | История схемы |
| `app/migrations/005_analysis_milestones.sql` | `app/migrations/005_analysis_milestones.sql` | `2103dabb9beaf88d789d8af62d696d8b1d133b04` | История схемы |
| `app/migrations/006_budget_admin_audit.sql` | `app/migrations/006_budget_admin_audit.sql` | `a879a32f54aa2409d2d2a8f82e572450d1e017d7` | История схемы |
| `app/migrations/007_site_availability.sql` | `app/migrations/007_site_availability.sql` | `ad5f689d275ace4536464329c2c72280bb2d2779` | История схемы |
| `app/model_catalog.py` | `app/model_catalog.py` | `d4f7a29ed10cce876ab60fd494d50f5ea01dd6ba` | Точка входа или backend-задел |
| `app/polza_client.py` | `app/polza_client.py` | `4245a2f7e93df303bc4622ddfd8d7113b97e7cc1` | Точка входа или backend-задел |
| `app/prompts.py` | `app/prompts.py` | `f146a500b91a4fbedba17d320a9510aca131050c` | Точка входа или backend-задел |
| `app/pytest.ini` | `app/pytest.ini` | `a635c5c031823148db0da62e63edb0c1f6e4a5f6` | Точка входа или backend-задел |
| `app/requirements.txt` | `app/requirements.txt` | `6799762f7750414afc8faa87ee46f897b134125b` | Точка входа или backend-задел |
| `app/schemas.py` | `app/schemas.py` | `56129fcc100559e53247a40dad59b22db4b5b090` | Точка входа или backend-задел |
| `app/security.py` | `app/security.py` | `dc9a10ad64625facafefbd66060d2afc4edc962b` | Точка входа или backend-задел |
| `app/tests/conftest.py` | `app/tests/conftest.py` | `949b9e9f373d8d86cf50d4ee2360ab0007eef6b6` | Проверки базовых модулей |
| `app/tests/test_auth.py` | `app/tests/test_auth.py` | `3dd1a92a36f49255185006af5a8de772ea33873c` | Проверки базовых модулей |
| `app/tests/test_model_catalog.py` | `app/tests/test_model_catalog.py` | `21fce8567b8f556f484719468237cb6ddc78330f` | Проверки базовых модулей |
| `app/tests/test_polza_client.py` | `app/tests/test_polza_client.py` | `1af8ec7a6262fd604d280ab2d791264c38bb8e6d` | Проверки базовых модулей |
| `app/tests/test_schemas.py` | `app/tests/test_schemas.py` | `9f326ea1e3b2c749a2b2e11b6fce056559c917d1` | Проверки базовых модулей |
| `app/tests/test_security.py` | `app/tests/test_security.py` | `01a9a2fce3025f2660132a398592617b19d54654` | Проверки базовых модулей |
| `compose.yaml` | `compose.yaml` | `ce5f1bb5fa21a3f7911faf49dfe49ab2c38f43e8` | Сборка и зависимости |
| `index.html` | `index.html` | `510be67e62f4a646960ccfe12756a78a426ec98d` | Сборка и зависимости |
| `package-lock.json` | `package-lock.json` | `54b9e508506807a3d406e8fee0107ff79f827541` | Сборка и зависимости |
| `package.json` | `package.json` | `6f9521e3624d32b7c8200c004940e1914afa2925` | Сборка и зависимости |
| `src/App.tsx` | `src/App.tsx` | `a021491d6482626e28c07603a291a02906bf8614` | Точка входа или UI-задел |
| `src/components/MathFormula.tsx` | `src/components/MathFormula.tsx` | `57669b0c972273c3057a76295e6890a77caf9a5d` | Точка входа или UI-задел |
| `src/lib/useModal.ts` | `src/lib/useModal.ts` | `698245c57b53bb638771c02ed0de59ff1a622b46` | Точка входа или UI-задел |
| `src/main.tsx` | `src/main.tsx` | `6ff8aaee695d139958394a13b42f738b6e33121e` | Точка входа или UI-задел |
| `src/styles.css` | `src/styles.css` | `da27cb5b1a91749994e2106d89c7e6926a6ca00b` | Точка входа или UI-задел |
| `tsconfig.app.json` | `tsconfig.app.json` | `68eb3628c549cd2213faa482132f4dc14fb20ece` | Сборка и зависимости |
| `tsconfig.json` | `tsconfig.json` | `1ffef600d959ec9e396d5a260bd3f5b927b2cef8` | Сборка и зависимости |
| `tsconfig.node.json` | `tsconfig.node.json` | `3950b4b1904b2932389e09ead72fd1324da88a3b` | Сборка и зависимости |
| `vite.config.ts` | `vite.config.ts` | `00829b20d0880f62ecbf350ae182cf1db898c07d` | Сборка и зависимости |

## Окружение и проверка

Контейнерные runtime закреплены по digest: Node 22.23.3 с npm 10.9.9, Python 3.12.14 и PostgreSQL 16.15. Версии JavaScript-пакетов сохранены из исходного lockfile. Ограничения Python зафиксированы в [pilot-python-constraints.txt](../../infra/pilot-python-constraints.txt). В Windows для старого исходного pytest понадобился пакет tzdata==2025.2.

Исходный checkout с отдельной PostgreSQL: npm test — 31 тест, npm run build — PASS, python -m pytest -q из app — 120 тестов. Временная БД PostgreSQL 16.15 запускалась на loopback с собственной базой smartnote_baseline_test. Checkout источника остался чистым.

Команды application из корня:

```sh
npm ci
npm test
npm run build
npm run test:browser
python -m pip install -c infra/pilot-python-constraints.txt -r app/requirements.txt jsonschema
cd app
python -m pytest tests/pilot/application -q
```

test:browser использует установленный Chrome и перехват API с синтетическими fixtures. HTTP-тесты используют ASGI и явные processing doubles. Они запускаются до передачи домена. В локальном Docker Desktop BuildKit не принял кириллицу в исходном пути, а backend и frontend успешно собраны из временной копии файлов с ASCII-путём.

## Старт совместного стека после B1b

Скопировать [.env.example](../../.env.example) в локальный .env. Выставить PILOT_TRANSPORT=fixture, случайный URL-safe POSTGRES_PASSWORD, VISITOR_COOKIE_SECRET длиной от 32 символов и отдельные реквизиты всех трёх fixture аккаунтов. Файлы с рабочими реквизитами хранить вне Git. Проверить, что ALLOWED_BROWSER_ORIGINS содержит точный origin браузера. Compose связывает PILOT_TRANSPORT и VITE_PILOT_TRANSPORT. Браузер открывает http://127.0.0.1:5173.

```sh
docker compose -f compose.yaml build
docker compose -f compose.yaml run --rm migrate
docker compose -f compose.yaml up -d --wait
docker compose -f compose.yaml exec backend python -m pilot.operations.create_fixture_accounts
docker compose -f compose.yaml ps
```

После B3 [smoke_application.py](../../scripts/pilot/smoke_application.py) выполняет вход, загрузку общего синтетического PNG, ожидание Job, отзывы, finalize с повтором ключа и чтение сохранённой сводки. Он проверяет fixture-режим целевого backend через Compose. Для smoke передать PILOT_FIXTURE_TEACHER_1_LOGIN и PILOT_FIXTURE_TEACHER_1_PASSWORD в окружение процесса, затем выполнить python scripts/pilot/smoke_application.py. Команда создаёт синтетическую проверку. Фактические результаты и недостающие порты описаны в [HANDOFF](../../project-context/pilot/planning/application/HANDOFF.md).
