import { execFileSync } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { expect, test, type Page } from '@playwright/test'

// REL-C27 automatic part: viewport widths, 200% text, no horizontal page scroll,
// reachable actions, formula scrolling inside its block and photo zoom.
// The real Android/iPhone steps stay manual and are recorded separately.
const ACCEPTANCE_PROJECT = process.env.PILOT_ACCEPTANCE_PROJECT || 'smartnote-release-accept'
const compose = (...args: string[]) =>
  execFileSync('docker', ['compose', '-f', 'compose.yaml', ...args], {
    encoding: 'utf8',
    env: { ...process.env, COMPOSE_PROJECT_NAME: ACCEPTANCE_PROJECT },
  })

const teacherLogin = process.env.PILOT_FIXTURE_TEACHER_1_LOGIN
const teacherPassword = process.env.PILOT_FIXTURE_TEACHER_1_PASSWORD
const PNG = 'src/pilot/__fixtures__/media/synthetic-page.png'

test.beforeAll(() => {
  expect(compose('exec', '-T', 'backend', 'printenv', 'PILOT_TRANSPORT').trim()).toBe('fixture')
  expect(teacherLogin, 'PILOT_FIXTURE_TEACHER_1_LOGIN').toBeTruthy()
  expect(teacherPassword, 'PILOT_FIXTURE_TEACHER_1_PASSWORD').toBeTruthy()
})

async function openCheck(page: Page) {
  await page.goto('/')
  await page.getByLabel('Логин').fill(teacherLogin!)
  await page.getByLabel('Пароль').fill(teacherPassword!)
  await page.getByRole('button', { name: 'Войти', exact: true }).click()
  await page.getByRole('button', { name: 'Новая проверка', exact: true }).click()
  await page.getByLabel('Название проверки').fill('REL-C27 ' + randomUUID().slice(0, 8))
  await page.getByRole('button', { name: 'Создать проверку', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Тетрадь 1', exact: true })).toBeVisible()
}

async function noHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(() => {
    const root = document.documentElement
    const offenders: string[] = []
    for (const element of Array.from(document.querySelectorAll('body *'))) {
      const rect = element.getBoundingClientRect()
      if (rect.width === 0) continue
      if (rect.right > root.clientWidth + 1 || rect.left < -1) {
        const style = getComputedStyle(element)
        if (style.overflowX === 'auto' || style.overflowX === 'scroll') continue
        offenders.push(`${element.tagName}.${element.className}`.slice(0, 80))
      }
    }
    return {
      pageOverflow: root.scrollWidth - root.clientWidth,
      offenders: [...new Set(offenders)].slice(0, 5),
    }
  })
  expect(overflow.pageOverflow, `page scrolls horizontally: ${overflow.offenders.join(', ')}`).toBeLessThanOrEqual(1)
}

async function tapTargetsAreLargeEnough(page: Page) {
  const tooSmall = await page.evaluate(() => {
    const small: string[] = []
    for (const element of Array.from(document.querySelectorAll('button'))) {
      const rect = element.getBoundingClientRect()
      if (rect.width === 0 || rect.height === 0) continue
      if (rect.height < 44 || rect.width < 32) {
        small.push(`${(element.textContent || '').trim().slice(0, 24)}:${Math.round(rect.width)}x${Math.round(rect.height)}`)
      }
    }
    return small
  })
  expect(tooSmall, `tap targets below 44px height: ${tooSmall.join(', ')}`).toEqual([])
}

for (const width of [320, 360, 390, 430]) {
  test(`REL-C27 layout at ${width} CSS px keeps every action reachable`, async ({ page }) => {
    await page.setViewportSize({ width, height: 780 })
    await openCheck(page)
    await noHorizontalScroll(page)
    await tapTargetsAreLargeEnough(page)

    const choosing = page.waitForEvent('filechooser')
    await page.getByRole('button', { name: 'Выбрать из галереи', exact: true }).click()
    await (await choosing).setFiles(PNG)
    await expect(page.getByText(/Фото 1 из 1/).first()).toBeVisible()
    await noHorizontalScroll(page)
    await tapTargetsAreLargeEnough(page)

    for (const label of [
      'Отправить на проверку',
      'Отправить и перейти к следующей тетради',
      'Снять фото',
      'Выбрать из галереи',
    ]) {
      const target = page.getByRole('button', { name: label, exact: true })
      await expect(target).toBeVisible()
      const box = await target.boundingBox()
      expect(box, label).not.toBeNull()
      expect(box!.x).toBeGreaterThanOrEqual(-1)
      expect(box!.x + box!.width).toBeLessThanOrEqual(width + 1)
    }
  })
}

test('REL-C27 200% text keeps content readable and actions usable', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 780 })
  await page.addInitScript(() => {
    // Emulate the browser "text only" zoom at 200%.
    const style = document.createElement('style')
    style.textContent = 'html { font-size: 36px !important; }'
    document.addEventListener('DOMContentLoaded', () => document.head.appendChild(style))
  })
  await openCheck(page)
  await noHorizontalScroll(page)
  const font = await page.evaluate(() => getComputedStyle(document.documentElement).fontSize)
  expect(font).toBe('36px')

  const choosing = page.waitForEvent('filechooser')
  await page.getByRole('button', { name: 'Выбрать из галереи', exact: true }).click()
  await (await choosing).setFiles(PNG)
  await expect(page.getByText(/Фото 1 из 1/).first()).toBeVisible()
  await noHorizontalScroll(page)

  const submit = page.getByRole('button', { name: 'Отправить на проверку', exact: true })
  await expect(submit).toBeVisible()
  await submit.click()
  await expect(page.getByText('Комплект принят. Можно снимать дальше или закрыть приложение.', { exact: false })).toBeVisible()
  await noHorizontalScroll(page)
})

test('REL-C27 dialogs, formula scrolling and photo zoom stay usable', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 780 })
  await openCheck(page)

  const choosing = page.waitForEvent('filechooser')
  await page.getByRole('button', { name: 'Выбрать из галереи', exact: true }).click()
  await (await choosing).setFiles(PNG)
  await expect(page.getByText(/Фото 1 из 1/).first()).toBeVisible()

  await page.getByRole('button', { name: 'Удалить фото', exact: true }).first().click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toBeVisible()
  const dialogBox = await dialog.boundingBox()
  expect(dialogBox!.width).toBeLessThanOrEqual(320)
  await page.getByRole('button', { name: 'Отмена', exact: true }).click()
  await expect(dialog).toBeHidden()

  await page.getByRole('button', { name: /Фото 1 из 1/ }).first().click()
  const viewer = page.getByRole('dialog')
  await expect(viewer).toBeVisible()
  await page.getByRole('button', { name: 'Увеличить фото', exact: true }).click()
  const zoomed = await page.locator('.photo-viewport img').getAttribute('class')
  expect(zoomed).toContain('zoomed')
  await page.getByRole('button', { name: 'Увеличить фото', exact: true }).click()
  await page.getByRole('button', { name: 'Закрыть', exact: true }).click()
  await expect(viewer).toBeHidden()

  await page.getByRole('button', { name: 'Отправить на проверку', exact: true }).click()
  await expect(page.getByText('Комплект принят. Можно снимать дальше или закрыть приложение.', { exact: false })).toBeVisible()
  await expect(page.getByRole('button', { name: /Задача 1/ }).first()).toBeVisible()
  await page.getByRole('button', { name: /Задача 1/ }).first().click()

  const formula = page.locator('.formula').first()
  if (await formula.count()) {
    const scrollable = await formula.evaluate(element => ({
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
      overflowX: getComputedStyle(element).overflowX,
    }))
    expect(['auto', 'scroll']).toContain(scrollable.overflowX)
  }
  await noHorizontalScroll(page)
})
