import { execFileSync } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { expect, test, type Page } from '@playwright/test'

// REL-C08..C11, C13, C19, C26 on the real local stack: real HTTP, PostgreSQL and
// the fixture worker. Only the fixture transport is used; no model call.
const ACCEPTANCE_PROJECT = process.env.PILOT_ACCEPTANCE_PROJECT || 'smartnote-release-accept'

const compose = (...args: string[]) =>
  execFileSync('docker', ['compose', '-f', 'compose.yaml', ...args], {
    encoding: 'utf8',
    env: { ...process.env, COMPOSE_PROJECT_NAME: ACCEPTANCE_PROJECT },
  })

const teacherLogin = process.env.PILOT_FIXTURE_TEACHER_1_LOGIN
const teacherPassword = process.env.PILOT_FIXTURE_TEACHER_1_PASSWORD

const PNG = 'src/pilot/__fixtures__/media/synthetic-page.png'
const JPG = 'src/pilot/__fixtures__/media/synthetic-page.jpg'
const HEIC = 'src/pilot/__fixtures__/media/synthetic-page.heic'

test.beforeAll(() => {
  expect(compose('exec', '-T', 'backend', 'printenv', 'PILOT_TRANSPORT').trim()).toBe('fixture')
  expect(teacherLogin, 'PILOT_FIXTURE_TEACHER_1_LOGIN').toBeTruthy()
  expect(teacherPassword, 'PILOT_FIXTURE_TEACHER_1_PASSWORD').toBeTruthy()
})

type Harness = {
  page: Page
  writes: Array<{ path: string; method: string; status: number }>
  errors: string[]
  checkId: () => string
}

async function signIn(page: Page) {
  await page.getByLabel('Логин').fill(teacherLogin!)
  await page.getByLabel('Пароль').fill(teacherPassword!)
  await page.getByRole('button', { name: 'Войти', exact: true }).click()
}

async function openHarness(page: Page): Promise<Harness> {
  const writes: Array<{ path: string; method: string; status: number }> = []
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('response', response => {
    const path = new URL(response.url()).pathname
    if (path.startsWith('/api/') && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(response.request().method())) {
      writes.push({ path, method: response.request().method(), status: response.status() })
    }
  })
  let checkId = ''
  await page.goto('/')
  await expect(page.getByText('Учебный режим', { exact: false })).toBeVisible()
  await signIn(page)
  await page.getByRole('button', { name: 'Новая проверка', exact: true }).click()
  const title = 'Приёмка REL-06 ' + randomUUID().slice(0, 8)
  await page.getByLabel('Название проверки').fill(title)
  await page.getByRole('button', { name: 'Создать проверку', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Тетрадь 1', exact: true })).toBeVisible()
  const url = new URL(page.url())
  checkId = url.searchParams.get('check') || ''
  expect(checkId).not.toBe('')
  return { page, writes, errors, checkId: () => checkId }
}

async function toCheckScreen(page: Page) {
  await page.getByRole('button', { name: /Назад$/ }).click()
  await expect(page.getByRole('button', { name: 'Завершить проверку', exact: true })).toBeVisible()
}

/**
 * Submit the current draft and tolerate the documented 409 path.
 *
 * Polling can advance the revision while a submit is in flight; the UI then
 * shows "Данные проверки изменились" with a refresh action (ux-flows, S06).
 * Acceptance follows that documented recovery instead of assuming a silent win.
 */
async function submitDraft(page: Page, label: string) {
  const conflict = page.getByRole('button', { name: 'Обновить страницу', exact: true })
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    await page.getByRole('button', { name: label, exact: true }).click()
    const settled = await Promise.race([
      page.getByText('Комплект принят. Можно снимать дальше или закрыть приложение.', { exact: false })
        .waitFor({ timeout: 8_000 }).then(() => 'accepted').catch(() => undefined),
      conflict.waitFor({ timeout: 8_000 }).then(() => 'conflict').catch(() => undefined),
    ])
    if (settled === 'accepted') return
    if (settled === 'conflict') {
      await conflict.click()
      await page.getByRole('button', { name: label, exact: true }).waitFor()
      continue
    }
  }
  throw new Error('Submit did not reach an accepted or documented conflict state')
}

/**
 * Click an action that may lose a revision race with polling.
 *
 * When the documented 409 appears (ux-flows: "Данные проверки изменились"),
 * the test follows the offered refresh and retries the same intent. This is the
 * specified recovery path, not a silent retry of an unconfirmed write.
 */
async function act(page: Page, label: string | RegExp, exact = true, timeout = 12_000) {
  const conflict = page.getByRole('button', { name: 'Обновить страницу', exact: true })
  const target = page.getByRole('button', { name: label, exact })
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    if (await conflict.count()) {
      await conflict.click()
      await expect(conflict).toHaveCount(0, { timeout })
    }
    await target.click()
    const settled = await Promise.race([
      target.waitFor({ state: 'detached', timeout }).then(() => 'moved').catch(() => undefined),
      conflict.waitFor({ timeout }).then(() => 'conflict').catch(() => undefined),
      page.waitForTimeout(timeout).then(() => 'timeout'),
    ])
    if (settled !== 'conflict' && settled !== 'timeout') return
  }
  throw new Error(`Action ${String(label)} kept conflicting with the current revision`)
}

/**
 * Upload one page, following the documented 409 recovery when polling advanced
 * the revision while the upload was in flight (ux-flows, S04/S05).
 */
async function upload(page: Page, file = PNG) {
  const conflict = page.getByRole('button', { name: 'Обновить страницу', exact: true })
  const gallery = page.getByRole('button', { name: 'Выбрать из галереи', exact: true })
  const photo = page.getByText(/Фото \d+ из \d+/).first()

  for (let attempt = 1; attempt <= 3; attempt += 1) {
    if (await conflict.count()) {
      await conflict.click()
      await gallery.waitFor()
    }
    const choosing = page.waitForEvent('filechooser')
    await gallery.click()
    await (await choosing).setFiles(file)
    const settled = await Promise.race([
      photo.waitFor({ timeout: 10_000 }).then(() => 'ok').catch(() => undefined),
      conflict.waitFor({ timeout: 10_000 }).then(() => 'conflict').catch(() => undefined),
    ])
    if (settled === 'ok') return
  }
  throw new Error('Upload did not reach the saved state or the documented conflict recovery')
}

test('REL-C26 excluded surfaces stay absent in the assembled UI', async ({ page }) => {
  const harness = await openHarness(page)
  for (const label of [
    'Класс', 'Тема', 'Вариант', 'Экспорт', 'Оценка', 'Тариф', 'Купить',
    'Зарегистрироваться', 'Чат поддержки', 'Корзина', 'Скачать',
  ]) {
    await expect(page.getByRole('button', { name: label, exact: false })).toHaveCount(0)
    await expect(page.getByRole('link', { name: label, exact: false })).toHaveCount(0)
  }
  for (const path of ['/api/auth/register', '/api/analyze', '/analyze']) {
    const response = await page.request.post(path, { data: { login: 'x', password: 'y' } })
    expect([404, 405], `${path} answered ${response.status()}`).toContain(response.status())
  }
  expect(harness.errors).toEqual([])
})

test('REL-C08 uploads a page and rejects an unsupported file', async ({ page }) => {
  const harness = await openHarness(page)
  await upload(page, JPG)
  await expect(page.getByText(/Фото 1 из 1/).first()).toBeVisible()

  const current = await (await page.request.get(`/api/checks/${harness.checkId()}`)).json()
  const rejected = await page.request.post(
    `/api/input-versions/${current.notebooks[0].bundles[0].draft.id}/photos`,
    {
      headers: {
        Origin: new URL(page.url()).origin,
        'Idempotency-Key': randomUUID(),
        'If-Match': `"${current.revision}"`,
      },
      multipart: { file: { name: 'fake.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4 synthetic') } },
    },
  )
  expect(rejected.status(), await rejected.text()).toBe(415)

  const photos = await page.request.get(`/api/checks/${harness.checkId()}`)
  const check = await photos.json()
  const draft = check.notebooks[0].bundles[0].draft
  expect(draft.photos.length).toBe(1)
  const asset = await page.request.get(`/api/assets/${draft.photos[0].id}`)
  expect(asset.status()).toBe(200)
  expect(asset.headers()['cache-control']).toBe('private, no-store')
  expect(harness.writes.filter(item => item.status >= 400).length).toBeLessThanOrEqual(1)
})

test('REL-C09 one page can yield several tasks; two photos can be one task', async ({ page }) => {
  const harness = await openHarness(page)
  await upload(page)
  await upload(page, HEIC)
  await submitDraft(page, 'Отправить на проверку')

  const check = await waitForCheck(page, harness.checkId())
  const bundle = check.notebooks[0].bundles[0]
  expect(bundle.current_input.photos.length).toBe(2)
  expect(bundle.tasks.length).toBeGreaterThan(0)
  for (const task of bundle.tasks) {
    const analysis = task.analysis
    expect(analysis.evidence.length).toBeLessThanOrEqual(4)
    for (const line of analysis.evidence) {
      expect(line.photo_index).toBeGreaterThanOrEqual(1)
      expect(line.photo_index).toBeLessThanOrEqual(2)
    }
    if (analysis.result === 'first_error_found') {
      expect(analysis.first_error.corrected_latex).toBeTruthy()
      expect(analysis.first_error.rule).toBeTruthy()
    }
  }
})

test('REL-C10 both send actions work and results do not wait for the camera', async ({ page }) => {
  const harness = await openHarness(page)
  const beforeSubmit = await page.request.get(`/api/checks/${harness.checkId()}`)
  expect((await beforeSubmit.json()).notebooks[0].bundles[0].job).toBeNull()

  await upload(page)
  await page.getByRole('button', { name: 'Отправить и перейти к следующей тетради', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Тетрадь 2', exact: true })).toBeVisible()

  const afterNext = await page.request.get(`/api/checks/${harness.checkId()}`)
  const submitted = await afterNext.json()
  expect(submitted.notebooks[0].bundles[0].job).not.toBeNull()
  expect(submitted.notebooks[0].bundles[0].current_input.photos.length).toBe(1)

  await upload(page)
  await submitDraft(page, 'Отправить на проверку')

  const busy = await waitForCheck(page, harness.checkId())
  const submittedBundles = busy.notebooks
    .flatMap((notebook: any) => notebook.bundles)
    .filter((bundle: any) => bundle.current_input)
  expect(submittedBundles.length).toBe(2)
  for (const bundle of submittedBundles) {
    expect(bundle.job).not.toBeNull()
    expect(bundle.tasks.length).toBeGreaterThan(0)
  }
  // Both sends use one submit each; the draft holder below carries no Job.
  const submits = harness.writes.filter(item => item.path.endsWith('/submit'))
  expect(submits.length).toBe(2)
  expect(submits.every(item => item.status === 202)).toBe(true)
  expect(busy.notebooks[0].bundles[0].current_input.photos.length).toBe(1)
  expect(busy.notebooks[1].bundles[0].current_input.photos.length).toBe(1)
})

test('REL-C11 reviews are per-task and the red state does not retry', async ({ page }) => {
  const harness = await openHarness(page)
  await upload(page)
  await page.getByRole('button', { name: 'Отправить на проверку', exact: true }).click()
  await expect(page.getByText('Комплект принят. Можно снимать дальше или закрыть приложение.', { exact: false })).toBeVisible()

  const ready: any = await waitForCheck(page, harness.checkId())
  const tasks = ready.notebooks[0].bundles[0].tasks
  expect(tasks.length).toBeGreaterThan(0)
  const reviewable = tasks.filter((task: any) => task.analysis.result !== 'not_assessed')
  expect(reviewable.length).toBeGreaterThan(0)

  await toCheckScreen(page)
  await page.getByRole('button', { name: 'Посмотреть разборы', exact: true }).click()
  await expect(page.getByRole('heading', { name: /^Разбор задачи/ }).first()).toBeVisible()

  const first = reviewable[0]
  await page.getByRole('button', { name: /Согласен с проверкой/ }).click()
  await expect(page.getByText('Отзыв сохранен', { exact: true })).toBeVisible()

  const afterAgree = await (await page.request.get(`/api/checks/${harness.checkId()}`)).json()
  const stored = afterAgree.notebooks[0].bundles[0].tasks.find(
    (task: { task_id: string }) => task.task_id === first.task_id,
  )
  expect(stored.review.state).toBe('confirmed')
  expect(afterAgree.notebooks[0].bundles[0].job.state).toBe('succeeded')

  if (reviewable.length > 1) {
    const second = reviewable[1]
    await page.getByRole('button', { name: 'Следующий разбор', exact: true }).click()
    await page.getByRole('button', { name: /Ошибка в проверке ИИ/ }).click()
    await expect(page.getByText('Отзыв сохранен', { exact: true })).toBeVisible()
    const afterRed = await (await page.request.get(`/api/checks/${harness.checkId()}`)).json()
    const red = afterRed.notebooks[0].bundles[0].tasks.find(
      (task: { task_id: string }) => task.task_id === second.task_id,
    )
    expect(red.review.state).toBe('system_error')
    expect(afterRed.notebooks[0].bundles[0].job.state).toBe('succeeded')
    expect(harness.writes.filter(item => item.path.endsWith('/retry')).length).toBe(0)
  }
  expect(harness.errors).toEqual([])
})

test('REL-C19 two-step finish blocks unresolved work and creates a summary', async ({ page }) => {
  const harness = await openHarness(page)
  await upload(page)
  await submitDraft(page, 'Отправить на проверку')

  await toCheckScreen(page)
  await act(page, 'Завершить проверку')
  await expect(page.getByRole('heading', { name: 'Просмотр перед завершением', exact: true })).toBeVisible()

  const pending = await (await page.request.get(`/api/checks/${harness.checkId()}`)).json()
  expect(pending.phase).toBe('review')
  expect(pending.summary.state).toBe('not_started')

  const blocked = await page.request.post(`/api/checks/${harness.checkId()}/finalize`, {
    headers: {
      Origin: new URL(page.url()).origin,
      'Idempotency-Key': randomUUID(),
      'If-Match': `"${pending.revision}"`,
    },
  })
  expect(blocked.status()).toBe(409)

  await page.getByRole('button', { name: 'Посмотреть разборы', exact: true }).click()

  // Review every ready card. The queue shrinks after each save, so the loop is
  // bounded by the actual task count read from the API, not by a UI guess.
  const ready = await (await page.request.get(`/api/checks/${harness.checkId()}`)).json()
  const total = ready.notebooks
    .flatMap((notebook: any) => notebook.bundles)
    .flatMap((bundle: any) => bundle.tasks)
    .filter((task: any) => !task.skipped).length
  expect(total).toBeGreaterThan(0)

  for (let index = 0; index < total; index += 1) {
    const agree = page.getByRole('button', { name: /Согласен с проверкой/ })
    if (await agree.count() === 0) break
    await agree.first().click()
    await expect(page.getByText('Отзыв сохранен', { exact: true })).toBeVisible({ timeout: 15_000 })
    const next = page.getByRole('button', { name: 'Следующий разбор', exact: true })
    if (await next.count() === 0) break
    await next.click()
    await expect(page.getByRole('heading', { name: /^Разбор задачи/ }).first()).toBeVisible()
  }
  await page.getByRole('button', { name: /Назад$/ }).click()
  await act(page, 'Завершить и создать сводку')
  await act(page, 'Да, завершить', false)

  const finalized = await waitForFinalized(page, harness.checkId())
  expect(finalized.phase).toBe('finalized')
  expect(finalized.summary.state).toBe('succeeded')
  expect(finalized.summary.result).not.toBeNull()
  expect(harness.writes.filter(item => item.path.endsWith('/finalize') && item.status === 202).length).toBe(1)
  expect(harness.errors).toEqual([])
})

test('REL-C13 a new input generation drops old reviews', async ({ page }) => {
  const harness = await openHarness(page)
  await upload(page)
  await submitDraft(page, 'Отправить на проверку')

  const ready = await waitForCheck(page, harness.checkId())
  const task = ready.notebooks[0].bundles[0].tasks.find(
    (item: { analysis: { result: string } }) => item.analysis.result !== 'not_assessed',
  )
  expect(task).toBeTruthy()

  const review = await page.request.put(`/api/tasks/${task.task_id}/review`, {
    headers: {
      Origin: new URL(page.url()).origin,
      'Idempotency-Key': randomUUID(),
      'If-Match': `"${ready.revision}"`,
    },
    data: { analysis_id: task.analysis_id, state: 'confirmed', comment: '' },
  })
  expect(review.status()).toBe(200)
  const confirmed = await review.json()

  const bundle = ready.notebooks[0].bundles[0]
  const newInput = await page.request.post(`/api/bundles/${bundle.id}/versions`, {
    headers: {
      Origin: new URL(page.url()).origin,
      'Idempotency-Key': randomUUID(),
      'If-Match': `"${confirmed.check_revision}"`,
    },
    data: { photo_ids: bundle.current_input.photos.map((photo: { id: string }) => photo.id) },
  })
  expect(newInput.status()).toBe(201)
  const created = await newInput.json()

  const submit = await page.request.post(`/api/bundles/${bundle.id}/submit`, {
    headers: {
      Origin: new URL(page.url()).origin,
      'Idempotency-Key': randomUUID(),
      'If-Match': `"${created.check_revision}"`,
    },
    data: { input_version_id: created.entity_id },
  })
  expect(submit.status()).toBe(202)

  const next = await waitForCheck(page, harness.checkId())
  for (const item of next.notebooks[0].bundles[0].tasks) {
    expect(item.review).toBeNull()
  }
  expect(next.notebooks[0].bundles[0].current_input.id).toBe(created.entity_id)
  expect(next.notebooks[0].bundles[0].current_input.id).not.toBe(bundle.current_input.id)
  expect(harness.errors).toEqual([])
})

async function draftId(page: Page): Promise<string> {
  const url = new URL(page.url())
  const id = url.searchParams.get('check')
  const response = await page.request.get(`/api/checks/${id}`)
  const check = await response.json()
  return check.notebooks[0].bundles[0].draft.id
}

async function waitForCheck(page: Page, checkId: string, timeout = 60_000) {
  const deadline = Date.now() + timeout
  let last: any
  while (Date.now() < deadline) {
    const response = await page.request.get(`/api/checks/${checkId}`)
    last = await response.json()
    const bundles = last.notebooks.flatMap((book: any) => book.bundles)
    const busy = bundles.some((bundle: any) => ['queued', 'running', 'retry_wait'].includes(bundle.job?.state))
    const analysed = bundles.every((bundle: any) => !bundle.current_input || bundle.tasks.length > 0)
    if (!busy && analysed) return last
    await page.waitForTimeout(500)
  }
  throw new Error(`Check did not settle: ${JSON.stringify(last?.notebooks?.map((b: any) => b.bundles.map((x: any) => x.job?.state)))}`)
}

async function waitForFinalized(page: Page, checkId: string, timeout = 60_000) {
  const deadline = Date.now() + timeout
  let last: any
  while (Date.now() < deadline) {
    const response = await page.request.get(`/api/checks/${checkId}`)
    last = await response.json()
    if (last.phase === 'finalized' && last.summary.state === 'succeeded') return last
    await page.waitForTimeout(500)
  }
  throw new Error(`Check did not finalize: phase=${last?.phase} summary=${last?.summary?.state}`)
}
