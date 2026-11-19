import { execFileSync } from 'node:child_process'
import { expect, test } from '@playwright/test'

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
