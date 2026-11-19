import { execFileSync } from 'node:child_process'
import { readFile } from 'node:fs/promises'
import { randomUUID } from 'node:crypto'
import { expect, test } from '@playwright/test'
import type { Check } from '../../../src/pilot/api/contract'

// REL-C07: the closed staff surface is read-only and speaks in the third person.
// Only the local Compose fixture stack is used; no model call and no school data.
const compose = (...args: string[]) => execFileSync('docker', ['compose', ...args], { encoding: 'utf8' })

const staffLogin = process.env.PILOT_FIXTURE_STAFF_LOGIN
const staffPassword = process.env.PILOT_FIXTURE_STAFF_PASSWORD
const teacherLogin = process.env.PILOT_FIXTURE_TEACHER_1_LOGIN
const teacherPassword = process.env.PILOT_FIXTURE_TEACHER_1_PASSWORD

const MUTATION_LABELS = [
  'Согласен с проверкой', 'Ошибка в проверке ИИ', 'Пропустить', 'Повторить',
  'Удалить задачу', 'Завершить проверку', 'Завершить и создать сводку',
  'Обновить сводку', 'Повторить сводку', 'Сохранить',
]

test.beforeAll(() => {
  expect(compose('exec', '-T', 'backend', 'printenv', 'PILOT_TRANSPORT').trim()).toBe('fixture')
  expect(staffLogin, 'PILOT_FIXTURE_STAFF_LOGIN').toBeTruthy()
  expect(staffPassword, 'PILOT_FIXTURE_STAFF_PASSWORD').toBeTruthy()
  expect(teacherLogin, 'PILOT_FIXTURE_TEACHER_1_LOGIN').toBeTruthy()
  expect(teacherPassword, 'PILOT_FIXTURE_TEACHER_1_PASSWORD').toBeTruthy()
})

test('REL-C07 staff UI is read-only, third-person and without teacher mutations', async ({ page, browser }) => {
  const pageErrors: string[] = []
  const writes: Array<{ path: string; method: string }> = []
  page.on('pageerror', error => pageErrors.push(error.message))
  page.on('request', request => {
    const path = new URL(request.url()).pathname
    if (path.startsWith('/api/') && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method())) {
      writes.push({ path, method: request.method() })
    }
  })

  await page.goto('/')
  await page.getByLabel('Логин').fill(staffLogin!)
  await page.getByLabel('Пароль').fill(staffPassword!)
  await page.getByRole('button', { name: 'Войти', exact: true }).click()

  await expect(page.getByRole('heading', { name: 'Раздел команды', exact: true })).toBeVisible()
  await expect(page.getByText('Только просмотр. Отзывы учителя менять нельзя.', { exact: true })).toBeVisible()

  const firstRow = page.locator('button.row-card').first()
  await expect(firstRow).toBeVisible()
  await expect(firstRow.locator('span').first()).not.toBeEmpty()

  await page.getByLabel('Логин учителя').fill(teacherLogin!)
  await page.getByRole('button', { name: 'Найти проверки', exact: true }).click()
  await expect(page.locator('button.row-card').first()).toBeVisible()

  for (const label of MUTATION_LABELS) {
    await expect(page.getByRole('button', { name: label, exact: true })).toHaveCount(0)
  }

  await page.locator('button.row-card').first().click()
  await expect(page.getByText('Только просмотр. Отзывы учителя менять нельзя.', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()

  await expect(page.getByText('Вы согласились', { exact: false })).toHaveCount(0)
  for (const label of MUTATION_LABELS) {
    await expect(page.getByRole('button', { name: label, exact: true })).toHaveCount(0)
  }

  const staffWrites = writes.filter(item =>
    !item.path.startsWith('/api/events') &&
    !item.path.startsWith('/api/auth/') &&
    !item.path.startsWith('/api/staff/'))
  expect(staffWrites, 'Staff browsing must not perform teacher mutations').toEqual([])
  expect(pageErrors).toEqual([])

  // A teacher session must not reach the closed staff area.
  const teacherContext = await browser.newContext()
  const teacherPage = await teacherContext.newPage()
  await teacherPage.goto('/')
  await teacherPage.getByLabel('Логин').fill(teacherLogin!)
  await teacherPage.getByLabel('Пароль').fill(teacherPassword!)
  await teacherPage.getByRole('button', { name: 'Войти', exact: true }).click()
  await expect(teacherPage.getByRole('button', { name: 'Новая проверка', exact: true })).toBeVisible()
  await expect(teacherPage.getByRole('heading', { name: 'Раздел команды', exact: true })).toHaveCount(0)
  await teacherContext.close()
})

test('REL-C07 staff histories retain each version photo count and summary denominator', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel('Логин').fill(teacherLogin!)
  await page.getByLabel('Пароль').fill(teacherPassword!)
  await page.getByRole('button', { name: 'Войти', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Мои проверки' })).toBeVisible()
  const origin = new URL(page.url()).origin
  async function mutate(method: 'POST' | 'PUT', path: string, status: number, data?: unknown, revision?: number) {
    const response = await page.request.fetch(`/api${path}`, {
      method, data, headers: {
        Origin: origin, 'Idempotency-Key': randomUUID(),
        ...(revision === undefined ? {} : { 'If-Match': `"${revision}"` }),
      },
    })
    expect(response.status(), await response.text()).toBe(status)
    return response.json()
  }
  const title = `Staff history regression ${randomUUID().slice(0, 8)}`
  const made = await mutate('POST', '/checks', 201, { title })
  const checkPath = `/checks/${made.check_id}`
  const read = async (): Promise<Check> => (await page.request.get(`/api${checkPath}`)).json()
  const notebook = await mutate('POST', `${checkPath}/notebooks`, 201, undefined, made.check_revision)
  const bundle = await mutate('POST', `/notebooks/${notebook.entity_id}/bundles`, 201, undefined, notebook.check_revision)
  const png = await readFile('src/pilot/__fixtures__/media/synthetic-page.png')
  async function upload(draftId: string, revision: number) {
    const response = await page.request.post(`/api/input-versions/${draftId}/photos`, {
      headers: { Origin: origin, 'Idempotency-Key': randomUUID(), 'If-Match': `"${revision}"` },
      multipart: { file: { name: 'synthetic.png', mimeType: 'image/png', buffer: png } },
    })
    expect(response.status(), await response.text()).toBe(201)
    return response.json()
  }
  async function settle(jobId: string) {
    await expect.poll(async () => {
      const current = await read()
      const active = current.notebooks[0].bundles[0]
      return active.job?.id === jobId && active.job.state === 'succeeded' && active.tasks.length === 3
    }).toBe(true)
  }
  async function confirmTasks() {
    let current = await read()
    for (const task of current.notebooks[0].bundles[0].tasks) {
      await mutate('PUT', `/tasks/${task.task_id}/review`, 200,
        { analysis_id: task.analysis_id, state: 'confirmed', comment: '' }, current.revision)
      current = await read()
    }
    return current
  }
  let current = await read()
  const firstInput = current.notebooks[0].bundles[0].draft!.id
  const firstPhoto = await upload(firstInput, current.revision)
  const firstJob = await mutate('POST', `/bundles/${bundle.entity_id}/submit`, 202,
    { input_version_id: firstInput }, firstPhoto.check_revision)
  await settle(firstJob.job.id)
  current = await confirmTasks()
  const version = await mutate('POST', `/bundles/${bundle.entity_id}/versions`, 201,
    { photo_ids: current.notebooks[0].bundles[0].current_input!.photos.map(photo => photo.id) }, current.revision)
  const secondPhoto = await upload(version.entity_id, version.check_revision)
  const secondJob = await mutate('POST', `/bundles/${bundle.entity_id}/submit`, 202,
    { input_version_id: version.entity_id }, secondPhoto.check_revision)
  await settle(secondJob.job.id)
  current = await confirmTasks()
  const begun = await mutate('POST', `${checkPath}/begin-completion`, 200, undefined, current.revision)
  await mutate('POST', `${checkPath}/finalize`, 202, undefined, begun.check_revision)
  await expect.poll(async () => (await read()).summary.state).toBe('succeeded')
  current = await read()
  const task = current.notebooks[0].bundles[0].tasks[0]
  const disputed = await mutate('PUT', `/tasks/${task.task_id}/review`, 200,
    { analysis_id: task.analysis_id, state: 'system_error', comment: '' }, current.revision)
  await mutate('POST', `${checkPath}/summary/refresh`, 202, undefined, disputed.check_revision)
  await expect.poll(async () => {
    const value = (await read()).summary
    return value.state === 'succeeded' && !value.stale
  }).toBe(true)
  const beforeStaff = await read()

  await page.getByRole('button', { name: 'Выйти', exact: true }).click()
  await page.getByLabel('Логин').fill(staffLogin!)
  await page.getByLabel('Пароль').fill(staffPassword!)
  await page.getByRole('button', { name: 'Войти', exact: true }).click()
  await page.getByText(title, { exact: true }).click()
  await page.getByRole('button', { name: 'Готово разборов: 1', exact: true }).click()
  const historicalCards = page.getByRole('button', { name: 'Разбор задачи', exact: true })
  await expect(historicalCards).toHaveCount(6)
  await historicalCards.first().click()
  await historicalCards.nth(2).click() // first card of the other input version
  const historyCards = page.getByRole('button', { name: 'Закрыть', exact: true }).locator('..')
  await expect(historyCards).toHaveCount(2)
  const historicalLabels = await historyCards.locator('ol.evidence small, .first-error small').allTextContents()
  expect(historicalLabels).toContain('Фото 1 из 1')
  expect(historicalLabels).toContain('Фото 1 из 2')
  expect(historicalLabels).not.toContain('Фото 1 из 4')

  await page.getByRole('button', { name: 'Открыть сводку', exact: true }).click()
  const summaries = page.getByRole('region', { name: 'Сводка проверки', exact: true })
  await expect(summaries.locator('article')).toHaveCount(2)
  await expect(summaries).not.toContainText(/\{(?:count|value|date)\}/)
  await expect(summaries).toContainText('В расчете полностью подтвержденных тетрадей: 1')
  await expect(summaries).toContainText('В расчете полностью подтвержденных тетрадей: 0')
  await expect(summaries).toContainText('Нет полностью подтвержденных тетрадей для среднего.')
  await expect(page.getByRole('button', { name: /Согласен|Ошибка в проверке|Удалить|Завершить|Обновить сводку/ })).toHaveCount(0)
  const afterStaff = await (await page.request.get(`/api/staff/checks/${made.check_id}`)).json()
  expect(afterStaff.check.revision).toBe(beforeStaff.revision)
  expect(afterStaff.check.data_revision).toBe(beforeStaff.data_revision)
})
