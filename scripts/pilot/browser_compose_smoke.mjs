import { strict as assert } from 'node:assert'
import { execFileSync } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { chromium } from 'playwright'

// The application smoke only uses the local Compose fixture stack.
const compose = (...args) => execFileSync('docker', ['compose', ...args], { encoding: 'utf8' })
const mode = compose('exec', '-T', 'backend', 'printenv', 'PILOT_TRANSPORT')
assert.equal(mode.trim(), 'fixture')
const verifyRestart = process.argv.includes('--restart')
const login = process.env.PILOT_FIXTURE_TEACHER_1_LOGIN
const password = process.env.PILOT_FIXTURE_TEACHER_1_PASSWORD
assert.ok(login && password, 'Set the local fixture teacher credentials in the process environment.')

const origin = 'http://127.0.0.1:5173'
const browser = await chromium.launch({ channel: 'chrome', headless: true })
let workerStopped = false
try {
  const mobileOptions = { viewport: { width: 320, height: 760 }, isMobile: true, hasTouch: true }
  let mobile = await browser.newContext(mobileOptions)
  const pageErrors = []
  const writeStatuses = []
  async function newPage() {
    const tab = await mobile.newPage()
    tab.setDefaultTimeout(20_000)
    tab.on('pageerror', error => pageErrors.push(error.message))
    tab.on('response', response => {
      const path = new URL(response.url()).pathname
      if (path.startsWith('/api/') && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(response.request().method())) {
        writeStatuses.push({ path, status: response.status() })
      }
    })
    return tab
  }
  let page = await newPage()
  let acceptedJobIds = []

  const button = (name, exact = true) => page.getByRole('button', { name, exact })
  const sameText = (name) => page.getByText(name, { exact: true })
  async function signIn() {
    await page.getByLabel('Логин').fill(login)
    await page.getByLabel('Пароль').fill(password)
    await button('Войти').click()
  }
  await page.goto(origin)
  await sameText('Учебный режим').waitFor()
  await signIn()
  await button('Новая проверка').click()
  const title = 'Синтетический браузерный smoke ' + randomUUID().slice(0, 8)
  await page.getByLabel('Название проверки').fill(title)
  await button('Создать проверку').click()

  const png = 'src/pilot/__fixtures__/media/synthetic-page.png'
  async function upload() {
    const choosing = page.waitForEvent('filechooser')
    await button('Выбрать из галереи').click()
    await (await choosing).setFiles(png)
    await sameText('Фото 1 из 1').waitFor()
  }

  await page.getByRole('heading', { name: 'Тетрадь 1', exact: true }).waitFor()
  const checkId = new URL(page.url()).searchParams.get('check')
  assert.ok(checkId)
  const checkUrl = origin + '/api/checks/' + checkId
  if (verifyRestart) {
    compose('stop', 'worker')
    workerStopped = true
  }
  await upload()
  await button(/Назад$/).click()
  await sameText('В комплекте есть неотправленные фото. Отправьте их или удалите черновик.').waitFor()
  await sameText('Фото 1 из 1').waitFor()
  await button('Отправить и перейти к следующей тетради').click()
  await page.getByRole('heading', { name: 'Тетрадь 2', exact: true }).waitFor()
  await upload()
  await button('Отправить на проверку').click()
  await sameText('Комплект принят. Можно снимать дальше или закрыть приложение.').waitFor()
  if (verifyRestart) {
    const before = await (await mobile.request.get(checkUrl)).json()
    const jobs = before.notebooks.flatMap(book => book.bundles.map(bundle => bundle.job).filter(Boolean))
    assert.equal(jobs.length, 2)
    assert.ok(jobs.every(job => job.state === 'queued'))
    acceptedJobIds = jobs.map(job => job.id).sort()
    await mobile.close()
    compose('restart', 'backend', 'worker')
    workerStopped = false
    compose('up', '-d', '--no-build', '--no-recreate', '--wait', '--wait-timeout', '45')
    mobile = await browser.newContext(mobileOptions)
    page = await newPage()
    await page.goto(origin)
    await signIn()
    await button(new RegExp('^' + title)).click()
  } else {
    await button(/Назад$/).click()
  }
  await sameText('Готово разборов: 6').waitFor()

  await button('Завершить проверку').click()
  await page.getByRole('heading', { name: 'Просмотр перед завершением', exact: true }).waitFor()
  await button('Посмотреть разборы').click()
  for (let index = 0; index < 6; index++) {
    await button(/Согласен с проверкой/).click()
    await sameText('Отзыв сохранен').waitFor()
    if (index < 5) await button('Следующий разбор').click()
  }
  await button(/Назад$/).click()
  await button('Завершить и создать сводку').click()
  await button('Да, завершить').click()
  await sameText('Тетрадей в проверке: 2').waitFor()
  await page.reload()
  await sameText('Тетрадей в проверке: 2').waitFor()
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), 320)

  const response = await mobile.request.get(checkUrl)
  assert.equal(response.status(), 200)
  const check = await response.json()
  assert.equal(check.phase, 'finalized')
  assert.equal(check.summary.state, 'succeeded')
  assert.equal(check.notebooks.length, 2)
  const bundles = check.notebooks.flatMap(book => book.bundles)
  assert.equal(bundles.flatMap(bundle => bundle.tasks)
    .filter(task => task.review?.state === 'confirmed').length, 6)
  if (verifyRestart) assert.deepEqual(bundles.flatMap(bundle => bundle.job ? [bundle.job.id] : []).sort(), acceptedJobIds)
  const photoIds = bundles.flatMap(bundle => bundle.current_input?.photos.map(photo => photo.id) ?? [])
  assert.equal(photoIds.length, 2)
  for (const photoId of photoIds) {
    const photo = await mobile.request.get(origin + '/api/assets/' + photoId)
    assert.equal(photo.status(), 200)
    assert.equal(photo.headers()['cache-control'], 'private, no-store')
    assert.ok((await photo.body()).length > 0)
  }
  assert.equal(writeStatuses.filter(({ path, status }) => path.endsWith('/submit') && status === 202).length, 2)
  assert.equal(writeStatuses.filter(({ path, status }) => path.endsWith('/finalize') && status === 202).length, 1)
  assert.deepEqual(writeStatuses.filter(({ status }) => status >= 400), [])
  assert.deepEqual(pageErrors, [])
  console.log('PASS: Chrome at 320 CSS px, real local HTTP/PostgreSQL/worker, two notebooks, six reviews, finalize and saved summary after reload.')
  if (verifyRestart) console.log('PASS: identical jobs and private photos survived with a fresh session after restarting backend and worker.')
} finally {
  await browser.close()
  if (workerStopped) compose('start', 'worker')
}
