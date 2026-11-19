import { strict as assert } from 'node:assert'
import { execFileSync } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { chromium, request } from 'playwright'

const origin = process.env.PILOT_FOLLOWUPS_ORIGIN
const project = process.env.COMPOSE_PROJECT_NAME
assert.ok(origin && /^http:\/\/127\.0\.0\.1:\d+$/.test(origin), 'Set PILOT_FOLLOWUPS_ORIGIN to a local loopback origin.')
assert.ok(project && project !== 'smartnote-pilot', 'Use an isolated Compose project.')
const compose = (...args) => execFileSync('docker', ['compose', ...args], { encoding: 'utf8' })
assert.equal(compose('exec', '-T', 'backend', 'printenv', 'PILOT_TRANSPORT').trim(), 'fixture')
assert.equal(compose('port', 'frontend', '5173').trim(), new URL(origin).host)
assert.equal(compose('exec', '-T', 'worker', 'printenv', 'PILOT_TRANSPORT').trim(), 'fixture')

function credentials(account) {
  const login = process.env[`PILOT_FIXTURE_${account}_LOGIN`]
  const password = process.env[`PILOT_FIXTURE_${account}_PASSWORD`]
  assert.ok(login && password, `Set the fixture credentials for ${account}.`)
  return { login, password }
}

const firstTeacher = credentials('TEACHER_1')
const secondTeacher = credentials('TEACHER_2')
const api = await request.newContext({ baseURL: origin, extraHTTPHeaders: { Origin: origin } })
const browser = await chromium.launch({ channel: 'chrome', headless: true })
let workerStopped = false

async function json(client, method, path, status, data, headers) {
  const response = await client.fetch(`/api${path}`, { method, data, headers })
  assert.equal(response.status(), status, `${method} ${path}${response.status() === status ? '' : ': ' + await response.text()}`)
  return status === 204 ? null : response.json()
}

function write(revision) {
  const headers = { 'Idempotency-Key': randomUUID() }
  if (revision !== undefined) headers['If-Match'] = '"' + revision + '"'
  return headers
}

const runUnknown = `
import asyncio
from pathlib import Path
import asyncpg
from config import get_settings
from pilot.domain.services import create_services
from pilot.processing.worker import run_once

async def main():
    settings = get_settings()
    async with asyncpg.create_pool(settings.database_url) as pool:
        svc = create_services(pool, Path(settings.pilot_storage_root), settings)
        assert svc.mode == "fixture"
        svc.fixture_scenario = "unknown"
        assert await run_once(svc)

asyncio.run(main())
`

function budget() {
  return JSON.parse(compose('exec', '-T', 'backend', 'python', '-m', 'pilot.processing.budget', 'status'))
}

async function login(page, credential) {
  await page.getByLabel('Логин').fill(credential.login)
  await page.getByLabel('Пароль').fill(credential.password)
  await page.getByRole('button', { name: 'Войти', exact: true }).click()
  await page.getByRole('heading', { name: 'Мои проверки', exact: true }).waitFor()
}

async function openReview(page, title, credential = firstTeacher) {
  await page.goto(origin)
  await login(page, credential)
  await page.getByText(title, { exact: true }).click()
  await page.getByRole('button', { name: 'Посмотреть разборы', exact: true }).click()
  await page.getByRole('heading', { name: /Разбор задачи/ }).waitFor()
}

async function waitForReady(path) {
  const deadline = Date.now() + 20000
  while (Date.now() < deadline) {
    const snapshot = await json(api, 'GET', path, 200)
    if (snapshot.notebooks[0].bundles[0].tasks.length) return
    await new Promise(resolve => setTimeout(resolve, 300))
  }
  throw new Error('Replacement fixture job did not publish its result.')
}

const persistedEvents = `
import asyncio, sys
from uuid import UUID
import asyncpg
from config import get_settings

async def main():
    con = await asyncpg.connect(get_settings().database_url)
    try:
        actor = UUID(sys.argv[1])
        ids = [UUID(value) for value in sys.argv[2:]]
        rows = await con.fetch("SELECT actor_id, id FROM pilot_events WHERE id=ANY($1::uuid[])", ids)
        assert len(rows) == len(ids) and all(row["actor_id"] == actor for row in rows)
    finally:
        await con.close()

asyncio.run(main())
`

try {
  const user = await json(api, 'POST', '/auth/login', 200, firstTeacher)
  const title = 'Синтетическая проверка доработок ' + randomUUID().slice(0, 8)
  const initial = await json(api, 'POST', '/checks', 201, { title }, write())
  const checkPath = '/checks/' + initial.check_id
  const notebook = await json(api, 'POST', checkPath + '/notebooks', 201, undefined, write(initial.check_revision))
  const bundle = await json(api, 'POST', '/notebooks/' + notebook.entity_id + '/bundles', 201, undefined, write(notebook.check_revision))
  const bundlePath = '/bundles/' + bundle.entity_id
  const read = () => json(api, 'GET', checkPath, 200)
  const select = check => check.notebooks[0].bundles.find(value => value.id === bundle.entity_id)
  let current = await read()
  const originalDraft = select(current).draft.id

  compose('stop', 'worker')
  workerStopped = true
  const upload = await api.post('/api/input-versions/' + originalDraft + '/photos', {
    headers: write(current.revision),
    multipart: { file: {
      name: 'synthetic.png', mimeType: 'image/png',
      buffer: await readFile('src/pilot/__fixtures__/media/synthetic-page.png'),
    } },
  })
  assert.equal(upload.status(), 201)
  const uploaded = await upload.json()
  const submitted = await json(api, 'POST', bundlePath + '/submit', 202, { input_version_id: originalDraft }, write(uploaded.check_revision))
  compose('run', '--rm', '--no-deps', 'worker', 'python', '-c', runUnknown)
  current = await read()
  assert.equal(select(current).job.state, 'unknown')
  const held = budget().held_rub
  assert.ok(Number(held) > 0)
  await json(api, 'POST', bundlePath + '/skip', 200, { input_version_id: originalDraft }, write(current.revision))
  const skipped = select(await read())
  assert.ok(skipped.skipped)
  assert.equal(skipped.job.can_retry, false)

  const replacementContext = await browser.newContext()
  const replacementPage = await replacementContext.newPage()
  await replacementPage.goto(origin)
  await login(replacementPage, firstTeacher)
  await replacementPage.getByText(title, { exact: true }).click()
  await replacementPage.getByRole('button', { name: /^Тетрадь 1/ }).click()
  const change = replacementPage.getByRole('button', { name: 'Изменить фото комплекта', exact: true })
  const dialog = replacementPage.getByRole('dialog')
  async function createDraft() {
    await change.click()
    await dialog.getByText(/Прежние оценки проверки всех его задач будут сняты/).waitFor()
    const response = replacementPage.waitForResponse(result =>
      result.request().method() === 'POST' && new URL(result.url()).pathname === '/api' + bundlePath + '/versions',
    )
    await dialog.getByRole('button', { name: 'Изменить фото', exact: true }).click()
    assert.equal((await response).status(), 201)
    await replacementPage.getByText('Фото перед отправкой', { exact: true }).waitFor()
    const current = select(await read())
    assert.ok(current.skipped)
    assert.deepEqual(current.current_input, skipped.current_input)
    assert.deepEqual(current.result, skipped.result)
    assert.deepEqual(current.draft.photos, skipped.current_input.photos)
    assert.equal(current.job.id, submitted.job.id)
  }
  await createDraft()
  await replacementPage.getByRole('button', { name: 'Удалить черновик', exact: true }).click()
  const discarded = replacementPage.waitForResponse(result =>
    result.request().method() === 'DELETE' && new URL(result.url()).pathname.startsWith('/api/input-versions/'),
  )
  await dialog.getByRole('button', { name: 'Удалить', exact: true }).click()
  assert.equal((await discarded).status(), 200)
  await replacementPage.getByText('Фото перед отправкой', { exact: true }).waitFor({ state: 'hidden' })
  assert.deepEqual(select(await read()), skipped)
  assert.equal(budget().held_rub, held)
  await createDraft()
  const replaced = replacementPage.waitForResponse(result =>
    result.request().method() === 'POST' && new URL(result.url()).pathname === '/api' + bundlePath + '/submit',
  )
  await replacementPage.getByRole('button', { name: 'Отправить на проверку', exact: true }).click()
  assert.equal((await replaced).status(), 202)
  const latest = select(await read())
  assert.equal(latest.skipped, false)
  assert.notEqual(latest.current_input.id, originalDraft)
  assert.notEqual(latest.job.id, submitted.job.id)
  assert.equal(latest.job.state, 'queued')
  assert.equal(budget().held_rub, held)
  await replacementContext.close()
  compose('start', 'worker')
  workerStopped = false
  await waitForReady(checkPath)
  console.log('PASS APP-F01: skipped unknown bundle can create, discard, and submit a replacement; its original financial hold survived.')

  const observed = await browser.newContext()
  const page = await observed.newPage()
  const order = []
  page.on('response', response => {
    const path = new URL(response.url()).pathname
    if (path === '/api/events') order.push('events')
    if (path === '/api/auth/logout') order.push('logout')
  })
  await openReview(page, title)
  assert.deepEqual(order, [])
  const eventResponse = page.waitForResponse(response => new URL(response.url()).pathname === '/api/events')
  const logoutResponse = page.waitForResponse(response => new URL(response.url()).pathname === '/api/auth/logout')
  await page.getByRole('button', { name: 'Выйти', exact: true }).click()
  const accepted = await eventResponse
  assert.equal(accepted.status(), 202)
  assert.equal((await logoutResponse).status(), 204)
  await page.getByRole('heading', { name: 'Вход в Умную тетрадь' }).waitFor()
  assert.deepEqual(order, ['events', 'logout'])
  const events = accepted.request().postDataJSON().events
  const ids = events.map(event => event.id)
  assert.equal(new Set(ids).size, ids.length)
  assert.deepEqual((await accepted.json()).accepted_ids, ids)
  assert.equal(events.filter(event => event.name === 'app_visible').length, 1)
  assert.equal(events.filter(event => event.name === 'result_opened').length, 1)
  assert.equal(events.filter(event => event.name === 'result_closed').length, 1)
  compose('exec', '-T', 'backend', 'python', '-c', persistedEvents, user.user_id, ...ids)
  await observed.close()

  for (const mode of ['offline', 'hung']) {
    const isolated = await browser.newContext()
    const failing = await isolated.newPage()
    let resume
    let attempts = 0
    await isolated.route(url => url.pathname === '/api/events', async route => {
      attempts++
      if (mode === 'hung') await new Promise(resolve => { resume = resolve })
      await route.abort().catch(() => {})
    })
    await openReview(failing, title)
    await failing.getByRole('button', { name: 'Выйти', exact: true }).click()
    await failing.getByRole('heading', { name: 'Вход в Умную тетрадь' }).waitFor({ timeout: 5000 })
    assert.equal(attempts, 1)
    resume?.()
    await login(failing, secondTeacher)
    assert.equal(await failing.getByText(title, { exact: true }).count(), 0)
    await isolated.close()
  }

  const retryLogout = await browser.newContext()
  const retryPage = await retryLogout.newPage()
  const observedBatches = []
  await retryLogout.route(url => url.pathname === '/api/events', async route => {
    observedBatches.push(route.request().postDataJSON().events)
    if (observedBatches.length === 1) await route.abort()
    else await route.continue()
  })
  await retryLogout.route(url => url.pathname === '/api/auth/logout',
    route => route.fulfill({ status: 503, json: { error: { code: 'unavailable' } } }), { times: 1 })
  await openReview(retryPage, title)
  await retryPage.getByRole('button', { name: 'Выйти', exact: true }).click()
  await retryPage.getByRole('alert').getByText(/Не удалось/).waitFor()
  await retryPage.getByRole('button', { name: 'Выйти', exact: true }).click()
  await retryPage.getByRole('heading', { name: 'Вход в Умную тетрадь' }).waitFor()
  const dropped = new Set(observedBatches[0].map(event => event.id))
  assert.ok(observedBatches.slice(1).flat().every(event => !dropped.has(event.id)))
  await retryLogout.close()

  const tabs = await browser.newContext()
  const previous = await tabs.newPage()
  const currentTab = await tabs.newPage()
  await currentTab.goto(origin)
  await currentTab.getByRole('heading', { name: 'Вход в Умную тетрадь' }).waitFor()
  await openReview(previous, title)
  await login(currentTab, secondTeacher)
  await previous.getByRole('heading', { name: 'Вход в Умную тетрадь' }).waitFor()
  const updatedActorEvents = currentTab.waitForResponse(response => new URL(response.url()).pathname === '/api/events')
  await currentTab.getByRole('button', { name: 'Выйти', exact: true }).click()
  const updatedActorBatch = await updatedActorEvents
  assert.equal(updatedActorBatch.status(), 202)
  assert.ok(updatedActorBatch.request().postDataJSON().events.every(event => !event.check_id && !event.entity_id))
  await tabs.close()

  for (const name of ['visibilitychange', 'pagehide']) {
    const lifecycle = await browser.newContext()
    const lifecyclePage = await lifecycle.newPage()
    await lifecyclePage.goto(origin)
    await login(lifecyclePage, firstTeacher)
    const delivered = lifecyclePage.waitForResponse(response => new URL(response.url()).pathname === '/api/events')
    await lifecyclePage.evaluate(name => {
      if (name === 'visibilitychange') {
        Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true })
        document.dispatchEvent(new Event(name))
      } else {
        window.dispatchEvent(new PageTransitionEvent(name))
      }
    }, name)
    const response = await delivered
    assert.equal(response.status(), 202)
    assert.deepEqual(response.request().postDataJSON().events.map(event => event.name), ['app_visible', 'app_hidden'])
    await lifecycle.close()
  }
  console.log('PASS APP-F03: events under the original actor before logout; offline/hung delivery, failed logout and cross-tab account change.')
} finally {
  await browser.close()
  await api.dispose()
  if (workerStopped) compose('start', 'worker')
}
