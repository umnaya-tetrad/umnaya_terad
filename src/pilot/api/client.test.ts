import { describe, expect, test, vi } from 'vitest'
import { fixtureByName, fixtureTransport } from '../__fixtures__/transport'
import { actions, PilotApi } from './client'
import { ApiError } from './errors'
import { Intents } from './intents'

function localStorageDouble(): Storage {
  const entries = new Map<string, string>()
  return {
    get length() { return entries.size },
    clear: () => entries.clear(),
    getItem: key => entries.get(key) ?? null,
    key: index => [...entries.keys()][index] ?? null,
    removeItem: key => { entries.delete(key) },
    setItem: (key, value) => { entries.set(key, value) },
  }
}

describe('application API', () => {
  test('APP-C03 login, session and logout use the contract endpoints', async () => {
    const api = new PilotApi(fixtureTransport('login', 'getSession', 'logout'))
    const credentials = fixtureByName('login').request.body as { login: string; password: string }
    expect(await api.login(credentials)).toEqual(await api.getSession())
    await expect(api.logout()).resolves.toBeUndefined()
  })

  test('APP-C08 multipart attaches exactly one file and quotes the revision', async () => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(Response.json({}))
    const api = new PilotApi(fetch)
    await api.mutate(actions.uploadPhoto('version', new File(['test'], 'test.heic', { type: 'image/heic' })), {
      key: 'intent', revision: 11,
    })
    const [path, init] = fetch.mock.calls[0]
    expect(path).toBe('/api/input-versions/version/photos')
    expect(init?.credentials).toBe('same-origin')
    expect(new Headers(init?.headers).get('If-Match')).toBe('"11"')
    expect(new Headers(init?.headers).has('Content-Type')).toBe(false)
    expect([...(init?.body as FormData).keys()]).toEqual(['file'])
  })

  test.each([
    ['page.HEIC', '', 'image/heic'],
    ['page.heif', 'application/octet-stream', 'image/heif'],
    ['page.heic', 'application/octet-stream', 'image/heic'],
    ['page.jpg', '', 'image/jpeg'],
    ['page.png', '', 'image/png'],
    ['page.webp', 'application/octet-stream', 'image/webp'],
    ['page.heic', 'image/heic', 'image/heic'],
    ['page.pdf', 'application/pdf', 'application/pdf'],
    ['page.heic', 'application/pdf', 'application/pdf'],
    ['page.heic.exe', '', ''],
    ['heic', '', ''],
  ])('APP-C08 gallery MIME hint %s (%s) preserves original bytes and metadata', async (name, type, expected) => {
    const file = new File([new Uint8Array([0, 255, 3, 128])], name, { type, lastModified: 123456 })
    const transport = vi.fn<typeof globalThis.fetch>().mockResolvedValue(Response.json({}))
    await new PilotApi(transport).mutate(actions.uploadPhoto('version', file), { key: 'upload', revision: 1 })
    const sent = (transport.mock.calls[0][1]?.body as FormData).get('file') as File
    expect(sent.type).toBe(expected)
    expect(sent.name).toBe(file.name)
    expect(sent.lastModified).toBe(file.lastModified)
    expect(new Uint8Array(await sent.arrayBuffer())).toEqual(new Uint8Array(await file.arrayBuffer()))
  })

  test('APP-C11 inferred and explicit gallery MIME replay the same original upload intent', async () => {
    const storage = localStorageDouble()
    const transport = vi.fn<typeof globalThis.fetch>()
      .mockRejectedValueOnce(new TypeError('lost upload reply'))
      .mockResolvedValueOnce(Response.json({ check_revision: 2 }))
    const api = new PilotApi(transport)
    const native = new File(['unchanged original'], 'page.heic', { type: '' })
    const explicit = new File([native], native.name, { type: 'image/heic' })
    await expect(new Intents(api, 'teacher', storage).send(actions.uploadPhoto('version', native), 'check', 1))
      .rejects.toThrow('lost upload reply')
    await new Intents(api, 'teacher', storage).send(actions.uploadPhoto('version', explicit), 'check', 2)
    const [initial, replay] = transport.mock.calls.map(([, init]) => init!)
    expect(new Headers(replay.headers).get('Idempotency-Key')).toBe(new Headers(initial.headers).get('Idempotency-Key'))
    expect(new Headers(replay.headers).get('If-Match')).toBe('"1"')
    expect((replay.body as FormData).get('file')).toMatchObject({ name: native.name, type: 'image/heic', size: native.size })
    expect(storage.length).toBe(0)
  })

  test('APP-C08 the image size guard still rejects an oversized inferred-MIME upload before dispatch', async () => {
    const transport = vi.fn<typeof globalThis.fetch>()
    const file = new File([new Uint8Array(8_000_001)], 'large.heic')
    await expect(new Intents(new PilotApi(transport), 'teacher', localStorageDouble())
      .send(actions.uploadPhoto('version', file), 'check', 1)).rejects.toMatchObject({ status: 413 })
    expect(transport).not.toHaveBeenCalled()
  })

  test.each([
    actions.submitBundle('bundle', { input_version_id: 'sealed' }),
    actions.finalizeCheck('check'),
  ])('APP-C11 APP-C24 reload and concurrent clicks replay the original key', async (action) => {
    const storage = localStorageDouble()
    const transport = vi.fn<typeof globalThis.fetch>()
      .mockRejectedValueOnce(new TypeError('lost response'))
      .mockResolvedValueOnce(Response.json({ check_revision: 10 }))
    const api = new PilotApi(transport)
    await expect(new Intents(api, 'teacher', storage).send(action, 'check', 9)).rejects.toThrow('lost response')
    const reloaded = new Intents(api, 'teacher', storage)
    await Promise.all([reloaded.send(action, 'check', 10), reloaded.send(action, 'check', 10)])
    expect(transport).toHaveBeenCalledTimes(2)
    const [initial, replay] = transport.mock.calls.map(([, init]) => init)
    expect(new Headers(replay?.headers).get('Idempotency-Key')).toBe(new Headers(initial?.headers).get('Idempotency-Key'))
    expect(new Headers(replay?.headers).get('If-Match')).toBe('"9"')
    expect(replay?.body).toBe(initial?.body)
    expect(storage.length).toBe(0)
  })

  test('APP-C28 a conflict clears the old intent and never resends automatically', async () => {
    const transport = vi.fn<typeof globalThis.fetch>()
      .mockResolvedValueOnce(Response.json({ error: { code: 'revision_conflict', current_revision: 12 } }, { status: 409 }))
      .mockResolvedValueOnce(Response.json({ check_revision: 13 }))
    const intents = new Intents(new PilotApi(transport), 'teacher', localStorageDouble())
    const action = actions.finalizeCheck('check')
    await expect(intents.send(action, 'check', 11)).rejects.toBeInstanceOf(ApiError)
    expect(transport).toHaveBeenCalledTimes(1)
    await intents.send(action, 'check', 12)
    const keys = transport.mock.calls.map(([, init]) => new Headers(init?.headers).get('Idempotency-Key'))
    expect(keys[1]).not.toBe(keys[0])
  })

  test('APP-C35 a changed account uses neither the old action nor its metadata', async () => {
    const storage = localStorageDouble()
    const transport = vi.fn<typeof globalThis.fetch>()
      .mockRejectedValueOnce(new TypeError('lost response'))
      .mockResolvedValueOnce(Response.json({}))
    const api = new PilotApi(transport)
    const old = new Intents(api, 'original', storage)
    const action = actions.saveReview('task', { analysis_id: 'analysis', state: 'confirmed', comment: 'local text' })
    await expect(old.send(action, 'check', 20)).rejects.toThrow()
    expect(storage.getItem(storage.key(0)!)).not.toContain('local text')
    old.expire()
    await expect(old.send(action, 'check', 20)).rejects.toMatchObject({ status: 401 })
    expect(storage.length).toBe(0)
    expect(transport).toHaveBeenCalledTimes(1)
  })
})
