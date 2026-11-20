# Live на VPS

20.11.2026. Проверено развертывание на `root@135.106.216.99`, приложение доступно по [https://umnaya-tetrad.ru](https://umnaya-tetrad.ru). Исходники на сервере: `/root/projects/umnaya_terad`, commit `4bd90426461368e5c4b342cf8110b51f8cd9d56c`. Это отдельный внешний результат; исторические локальные отчеты не заменяют его.

## Что запущено

- Compose project `smartnote-pilot`: PostgreSQL, backend, worker и frontend — healthy; `restart=unless-stopped`. Миграции завершились успешно. Другой проект `smartnote-staging` не изменялся.
- Host nginx принимает HTTPS, перенаправляет HTTP на HTTPS и проксирует на `127.0.0.1:5173`. БД и backend наружу не опубликованы.
- Frontend — собранная статика в `smartnote-pilot-frontend:4bd9042-static`, nginx вместо Vite dev. Артефакты взяты из локального live, собранного на `419c3d3`: перед переносом подтвержден пустой diff к `4bd9042` по `src`, Vite config, зависимостям, index и app/node tsconfig. Это использование готового эквивалентного артефакта, не новая сборка TypeScript на VPS.
- Runtime nginx base закреплен digest `nginx@sha256:a8b39bd9cf0f83869a2162827a0caf6137ddf759d50a171451b335cecc87d236`. Файлы frontend-релиза и source metadata: `/root/.config/smartnote/vps-release/4bd9042/`.
- `PILOT_TRANSPORT=polza`, `google/gemini-3.8-flash`, `google-ai-studio/flex`; сохранен существующий ключ сервера. Учебная панель и fixture transport выключены. Лимит backend 500 RUB сохранен; в момент проверки spent/held = 0.
- `VISITOR_COOKIE_SECURE=true`; разрешенные origins: `https://umnaya-tetrad.ru,https://www.umnaya-tetrad.ru`.

## Приватные файлы и обслуживание

На VPS используются `/root/.config/smartnote/pilot.env` и `/root/.config/smartnote/compose.vps-live.yaml`; права 600. Они находятся вне Git. Точный состав выпуска записан в `/root/.config/smartnote/vps-live-deployment.json`.

Все команды ниже выполняются на VPS. Для этого выпуска всегда указывайте оба Compose-файла и этот env: обычный `run.sh` предназначен для другого launcher-профиля и не воспроизводит данный static/HTTPS override.

```bash
cd /root/projects/umnaya_terad
docker compose -p smartnote-pilot --env-file /root/.config/smartnote/pilot.env -f compose.yaml -f /root/.config/smartnote/compose.vps-live.yaml ps
docker compose -p smartnote-pilot --env-file /root/.config/smartnote/pilot.env -f compose.yaml -f /root/.config/smartnote/compose.vps-live.yaml up -d --no-build --wait
docker compose -p smartnote-pilot --env-file /root/.config/smartnote/pilot.env -f compose.yaml -f /root/.config/smartnote/compose.vps-live.yaml logs --tail 100 backend worker
```

Изменение лимита без restart:

```bash
docker exec smartnote-pilot-backend-1 python -m pilot.processing.budget set-limit --rub 500
```

Аккаунты созданы штатным `pilot.operations.manage_accounts create` без паролей в argv: `admin-test` / `staff` и `teacher-test` / `teacher`. `staff` — существующий закрытый раздел команды с просмотром проверок, а не новая роль суперпользователя. Добавление следующих аккаунтов не требует restart: [RELEASE_RUNBOOK](RELEASE_RUNBOOK.md). Пароли переданы владельцу отдельно; приватная копия — `/root/.config/smartnote/vps-test-accounts.json`, локально `C:/Users/User/.config/smartnote/vps-test-accounts.json`. Пароли в документацию и Git не включены.

До изменения конфигурации создан backup `/root/.config/smartnote/vps-backups/20261120T002148Z/`: SQL dump, фото, env и host nginx config. Существующие volumes, аккаунты и настройки Polza не сбрасывались. До выпуска проверок и jobs в этой БД не было. Восстановление backup этой задачей не выполнялось.

## Проверка Playwright

Использован Playwright MCP; Browser plugin отсутствует. Проверен реальный HTTPS-домен, без подмены API и без fixture:

| Проверка | Результат |
| --- | --- |
| Вход `teacher-test` через форму | PASS: экран «Мои проверки», session 200, role=teacher |
| Вход `admin-test` через форму | PASS: «Раздел команды» / «Проверки учителей», session 200, role=staff |
| Обновление страницы для обеих ролей | PASS: сохраняются сессия и соответствующий экран |
| Выход из обоих аккаунтов | PASS: возвращается форма; после выхода staff session 401 |
| Cookie приложения | Secure, HttpOnly, SameSite=Lax |
| Frontend | Статические assets, нет `@vite` scripts и HMR; после перезагрузки staff console errors/warnings = 0 |
| Инфраструктура | 4 healthy, nginx config test PASS |

Начальный 401 `/api/auth/session` без авторизации — ожидаемое поведение. До замены frontend наблюдались ошибки Vite WebSocket; после замены их нет. Локальные screenshots: `.cache/vps-live/teacher-login.png`, `.cache/vps-live/admin-login.png` в общей рабочей папке, вне Git; паролей на них нет.

Границы: проверены вход/выход и сессии в браузере. Платные запросы checker/analytics, загрузка реальных работ, физические Android/iPhone, полный внешний E2E, нагрузка, reboot VPS и школьная апробация в этом выпуске **not_run**. Наличие ключа и healthy worker не является новым подтверждением качества ИИ.

SSH из текущей Windows-сети удалось установить прямым socket через Ethernet, обходя активный TUN; системные маршруты и VPN не изменялись. Этот машинный обход не нужен для работы самого приложения на VPS.
