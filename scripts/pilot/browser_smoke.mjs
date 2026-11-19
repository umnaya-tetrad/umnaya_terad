import { spawn } from 'node:child_process'
import { readFile } from 'node:fs/promises'
import { chromium } from 'playwright'
import { strict as assert } from 'node:assert'
import { randomUUID } from 'node:crypto'
import { createServer } from 'node:http'

const base = 'http://127.0.0.1:5193'
const fixtures = JSON.parse(await readFile('project-context/pilot/planning/shared/api/fixtures/http.json', 'utf8'))
const lifecycle = JSON.parse(await readFile('project-context/pilot/planning/shared/api/fixtures/lifecycle.json', 'utf8'))
const fixture = name => fixtures.find(item => item.name === name).response
const session = fixture('login').body
const check = fixture('getCheck').body
check.phase = 'editing'
const photo = await readFile('project-context/pilot/planning/shared/api/fixtures/synthetic-photo.png')
// A pagehide keepalive request can outlive Playwright's browser route.
const fallback = createServer((request, response) => {
  const events = request.method === 'POST' && request.url === '/api/events'
  response.writeHead(events ? 202 : 404, { 'Content-Type': 'application/json' })
  response.end(events ? '{"accepted_ids":[]}' : '{}')
})
await new Promise(resolve => fallback.listen(0, '127.0.0.1', resolve))
const server = spawn(process.execPath, ['node_modules/vite/bin/vite.js', 'dev', '--host', '127.0.0.1', '--port', '5193', '--strictPort'], {
  stdio: 'inherit', env: {
    ...process.env,
    VITE_PILOT_TRANSPORT: 'fixture',
    VITE_BACKEND_URL: 'http://127.0.0.1:' + fallback.address().port,
  },
})
let browser
try {
  for (let i = 0; i < 50; ++i) {
    try { if ((await fetch(base)).ok) break } catch {}
    await new Promise(resolve => setTimeout(resolve, 100))
  }
  browser = await chromium.launch({ channel: 'chrome', headless: true })
  const context = await browser.newContext({ viewport: { width: 320, height: 760 }, isMobile: true, hasTouch: true })
  const page = await context.newPage()
  page.setDefaultTimeout(6500)
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  let signedIn = false
  let reportReads = 0
  const mutations = []
  let submitted = 0
  let finalized = 0
  let rejectedDelete = false
  const replyMutation = (route, status, entity_id, job = null) => {
    const headers = route.request().headers()
    assert.equal(headers['if-match'], '"' + check.revision + '"')
    assert.match(headers['idempotency-key'], /^[0-9a-f-]{36}$/)
    check.revision++
    return route.fulfill({ status, json: { check_id: check.id, check_revision: check.revision, entity_id, job } })
  }
  await context.route(url => url.origin === base && url.pathname.startsWith('/api/'), async route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    const method = request.method()
    if (path === '/api/auth/session') return route.fulfill(signedIn ? { json: session } :
      { status: 401, json: { error: { code: 'unauthenticated', message: '', current_revision: null } } })
    if (path === '/api/auth/login' && method === 'POST') {
      signedIn = true
      return route.fulfill({ json: session })
    }
    if (path === '/api/auth/logout' && method === 'POST') {
      signedIn = false
      return route.fulfill({ status: 204 })
    }
    if (path === '/api/events' && method === 'POST') {
      const { events } = request.postDataJSON()
      return route.fulfill({ status: 202, json: { accepted_ids: events.map(event => event.id) } })
    }
    if (path === '/api/checks' && method === 'GET') return route.fulfill({ json: fixture('listChecks').body })
    if (path === '/api/checks/' + check.id && method === 'GET') {
      reportReads++
      return route.fulfill({ headers: { ETag: '"' + check.revision + '"' }, json: check })
    }
    if (path === '/api/checks/' + check.id + '/summary' && method === 'GET') {
      return route.fulfill({ json: check.summary })
    }
    if (path === '/api/checks/' + check.id + '/begin-completion' && method === 'POST') {
      check.phase = 'review'
      check.completion = lifecycle['completion-waits-checker'].completion
      return replyMutation(route, 200, check.id)
    }
    if (path === '/api/checks/' + check.id + '/finalize' && method === 'POST') {
      assert.equal(check.phase, 'review')
      assert.equal(check.completion.can_finalize, true)
      check.phase = 'finalized'
      check.completion = lifecycle['finalize-queues-analytics'].completion
      check.summary = lifecycle['finalize-queues-analytics'].summary
      finalized++
      return replyMutation(route, 202, null, fixture('finalizeCheck').body.job)
    }
    if (path.startsWith('/api/assets/') && method === 'GET') return route.fulfill({ contentType: 'image/png', body: photo })
    if (path.includes('/review') && method === 'PUT') {
      mutations.push(path)
      const body = request.postDataJSON()
      const task = check.notebooks.flatMap(book => book.bundles).flatMap(bundle => bundle.tasks)
        .find(task => task.analysis_id === body.analysis_id)
      assert.ok(task)
      task.review = { state: body.state, comment: body.comment }
      return replyMutation(route, 200, task.task_id)
    }
    if (method === 'POST' && path === '/api/checks/' + check.id + '/notebooks') {
      assert.equal(request.postData(), null)
      const book = { id: randomUUID(), number: Math.max(...check.notebooks.map(item => item.number), 0) + 1, bundles: [] }
      check.notebooks.push(book)
      return replyMutation(route, 201, book.id)
    }
    if (method === 'POST' && /^\/api\/notebooks\/[^/]+\/bundles$/.test(path)) {
      const book = check.notebooks.find(item => item.id === path.split('/')[3])
      assert.ok(book)
      const bundle = {
        id: randomUUID(), draft: { id: randomUUID(), state: 'draft', photos: [] },
        current_input: null, job: null, result: null, tasks: [], skipped: false,
      }
      book.bundles.push(bundle)
      return replyMutation(route, 201, bundle.id)
    }
    if (method === 'POST' && /^\/api\/input-versions\/[^/]+\/photos$/.test(path)) {
      assert.match(request.headers()['content-type'], /^multipart\/form-data; boundary=/)
      const id = path.split('/')[3]
      const draft = check.notebooks.flatMap(item => item.bundles).find(bundle => bundle.draft?.id === id)?.draft
      assert.ok(draft)
      const item = { id: randomUUID(), media_type: 'image/png' }
      draft.photos.push(item)
      return replyMutation(route, 201, item.id)
    }
    if (method === 'POST' && /^\/api\/bundles\/[^/]+\/submit$/.test(path)) {
      const bundle = check.notebooks.flatMap(item => item.bundles).find(item => item.id === path.split('/')[3])
      assert.ok(bundle?.draft?.photos.length)
      assert.deepEqual(request.postDataJSON(), { input_version_id: bundle.draft.id })
      bundle.current_input = { ...bundle.draft, state: 'sealed' }
      bundle.draft = null
      bundle.job = { ...fixture('submitBundle').body.job, id: randomUUID(), input_id: bundle.current_input.id, state: 'queued' }
      submitted++
      return replyMutation(route, 202, bundle.id, bundle.job)
    }
    if (method === 'DELETE' && /^\/api\/notebooks\/[^/]+$/.test(path)) {
      const revision = request.headers()['if-match']
      if (revision !== '"' + check.revision + '"') {
        assert.equal(revision, '"' + (check.revision - 1) + '"')
        rejectedDelete = true
        return route.fulfill({ status: 409, json: {
          error: { code: 'revision_conflict', message: 'Synthetic conflict', current_revision: check.revision },
        } })
      }
      throw new Error('The old confirmation was silently rebased after polling')
    }
    errors.push('unexpected ' + method + ' ' + path)
    return route.fulfill({ status: 404 })
  })
  const first = await page.goto(base)
  try {
    await page.getByText('Учебный режим', { exact: true }).waitFor()
  } catch (failure) {
    console.error(first.status(), await page.locator('body').innerText(), errors)
    throw failure
  }
  await page.getByLabel('Логин').fill('synthetic_teacher')
  await page.getByLabel('Пароль').fill('synthetic-fixture-only')
  await page.getByRole('button', { name: 'Войти', exact: true }).click()
  await page.getByRole('heading', { name: 'Мои проверки' }).waitFor()
  await page.getByRole('button', { name: new RegExp(check.title) }).click()
  await page.getByRole('button', { name: 'Посмотреть разборы' }).click()
  await page.getByRole('heading', { name: /Разбор задачи/ }).waitFor()
  await page.getByRole('button', { name: /Увеличить фото/ }).first().click()
  await page.getByRole('dialog').waitFor()
  await page.getByRole('button', { name: 'Увеличить фото', exact: true }).click()
  await page.getByRole('button', { name: 'Закрыть', exact: true }).click()
  await page.getByLabel('Комментарий – необязательно').fill('Синтетический отзыв')
  await page.getByRole('button', { name: /Согласен с проверкой/ }).click()
  await page.getByText('Отзыв сохранен').waitFor()
  assert.equal(mutations.length, 1)
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), 320)
  const zoom = await page.addStyleTag({ content: 'html { font-size: 36px !important; }' })
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), 320)
  assert.ok((await page.getByRole('button', { name: /Согласен с проверкой/ }).boundingBox()).height >= 48)
  await zoom.evaluate(element => element.remove())
  await page.reload()
  await page.getByRole('heading', { name: check.title }).waitFor()
  assert.equal(mutations.length, 1)
  assert.ok(reportReads >= 3)
  const number = Math.max(...check.notebooks.map(item => item.number), 0) + 1
  await page.getByRole('button', { name: 'Добавить тетрадь' }).click()
  await page.getByRole('heading', { name: 'Тетрадь ' + number }).waitFor()
  await page.getByRole('button', { name: 'Выбрать из галереи' }).waitFor()
  await page.locator('input[type=file]').last().setInputFiles('src/pilot/__fixtures__/media/synthetic-page.png')
  await page.getByText('Фото 1 из 1', { exact: true }).waitFor()
  await page.getByRole('button', { name: 'Отправить и перейти к следующей тетради' }).click()
  await page.getByRole('heading', { name: 'Тетрадь ' + (number + 1) }).waitFor()
  assert.equal(submitted, 1)
  await page.getByRole('button', { name: /Назад$/ }).click()
  await page.getByRole('button', { name: 'Удалить тетрадь', exact: true }).last().click()
  check.revision++
  await page.waitForResponse(response =>
    response.request().method() === 'GET' && new URL(response.url()).pathname === '/api/checks/' + check.id &&
    response.headers().etag === '"' + check.revision + '"',
  )
  await page.getByRole('dialog').getByRole('button', { name: 'Удалить', exact: true }).click()
  await page.getByText('Данные проверки изменились.', { exact: false }).waitFor()
  assert.ok(rejectedDelete)
  await page.getByRole('button', { name: 'Тетрадь ' + (number + 1), exact: true }).waitFor()

  await page.getByRole('button', { name: 'Завершить проверку', exact: true }).click()
  await page.getByText('Еще обрабатываются комплекты:', { exact: false }).waitFor()
  assert.equal(finalized, 0)
  const ready = lifecycle['red-resolves-review-excluded-from-math']
  Object.assign(check, { notebooks: ready.notebooks, completion: ready.completion, revision: check.revision + 1 })
  const finish = page.getByRole('button', { name: 'Завершить и создать сводку', exact: true })
  await finish.click()
  await page.getByRole('dialog').getByRole('button', { name: 'Отмена', exact: true }).click()
  assert.equal(finalized, 0)
  await finish.click()
  await page.getByRole('button', { name: 'Да, завершить', exact: true }).click()
  await page.getByText('Готовим сводку.', { exact: false }).waitFor()
  assert.equal(finalized, 1)
  check.summary = lifecycle['saved-analytics'].summary
  check.revision++
  await page.getByText('Тетрадей в проверке: 1', { exact: true }).waitFor()
  await page.getByRole('button', { name: 'Открыть материалы', exact: true }).click()
  await page.getByRole('button', { name: 'Открыть сводку', exact: true }).waitFor()
  assert.equal(await page.getByRole('button', { name: 'Добавить тетрадь', exact: true }).count(), 0)
  await page.getByRole('button', { name: 'Выйти' }).click()
  await page.getByRole('heading', { name: 'Вход в Умную тетрадь' }).waitFor()
  assert.deepEqual(errors, [])
  console.log('PASS browser mock: 320 CSS px, text 200%, auth/history, review/photo zoom and reload, upload/submit-next, revision conflict, completion and saved summary')
} finally {
  await browser?.close()
  server.kill()
  fallback.close()
}
