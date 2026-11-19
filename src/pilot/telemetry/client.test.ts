import { expect, test, vi } from 'vitest'
import { PilotApi } from '../api/client'
import { Telemetry } from './client'

test('APP-C29 telemetry keeps event ids on retry and distinguishes independent sessions', async () => {
  const transport = vi.fn<typeof fetch>()
    .mockRejectedValueOnce(new TypeError('offline'))
    .mockResolvedValue(Response.json({ accepted_ids: [] }))
  const api = new PilotApi(transport)
  const first = new Telemetry(api, () => new Date('2026-11-19T12:00:00Z'))
  first.track('photo_selected', 'check', 'bundle')
  await first.flush()
  await first.flush()
  const other = new Telemetry(api)
  other.track('app_visible')
  await other.flush()
  const sent = transport.mock.calls.map(([, options]) => JSON.parse(String(options?.body)).events[0])
  expect(sent[0]).toEqual(sent[1])
  expect(sent[0].session_id).not.toBe(sent[2].session_id)
  expect(sent[0]).toMatchObject({ name: 'photo_selected', occurred_at: '2026-11-19T12:00:00.000Z', check_id: 'check', entity_id: 'bundle' })
  expect(Object.keys(sent[0]).sort()).toEqual(['check_id', 'entity_id', 'id', 'name', 'occurred_at', 'session_id'])
})

test('APP-F03 joins a periodic batch and sends the result close once before finishing', async () => {
  let completeFirst: (response: Response) => void = () => {}
  const transport = vi.fn<typeof fetch>()
    .mockImplementationOnce(() => new Promise(resolve => { completeFirst = resolve }))
    .mockImplementation(async (_url, options) => {
      const data = JSON.parse(String(options?.body))
      return Response.json({ accepted_ids: data.events.map((event: { id: string }) => event.id) })
    })
  const telemetry = new Telemetry(new PilotApi(transport))
  for (let i = 0; i < 100; i++) telemetry.track('heartbeat')
  const first = telemetry.flush()
  telemetry.track('result_opened', 'check', 'task')
  const finishing = telemetry.finish()
  telemetry.track('result_closed', 'check', 'task')
  expect(transport).toHaveBeenCalledTimes(1)
  const original = JSON.parse(String(transport.mock.calls[0][1]?.body)).events
  completeFirst(Response.json({ accepted_ids: original.map((event: { id: string }) => event.id) }))
  await first
  await finishing
  const remaining = JSON.parse(String(transport.mock.calls[1][1]?.body)).events
  expect(remaining.map((event: { name: string }) => event.name)).toEqual(['result_opened', 'result_closed'])
  expect(remaining[0].session_id).toBe(original[0].session_id)
  expect(new Set([...original, ...remaining].map(event => event.id)).size).toBe(102)
  await telemetry.flush()
  expect(transport).toHaveBeenCalledTimes(2)
})

test('APP-F03 ending is bounded even when the network never settles', async () => {
  vi.useFakeTimers()
  try {
    const transport = vi.fn<typeof fetch>().mockImplementation(() => new Promise(() => {}))
    const telemetry = new Telemetry(new PilotApi(transport))
    telemetry.track('app_visible')
    const finishing = telemetry.finish()
    await vi.advanceTimersByTimeAsync(1000)
    await finishing
    expect(transport.mock.calls[0][1]?.signal?.aborted).toBe(true)
    telemetry.track('app_visible')
    await telemetry.flush()
    expect(transport).toHaveBeenCalledTimes(1)
  } finally {
    vi.useRealTimers()
  }
})

test('APP-F03 rejects a previous cookie version and discards events after 401', async () => {
  let current = true
  const transport = vi.fn<typeof fetch>().mockResolvedValue(Response.json({}, { status: 401 }))
  const older = new Telemetry(new PilotApi(transport), undefined, () => current)
  older.track('heartbeat')
  current = false
  await older.finish()
  expect(transport).not.toHaveBeenCalled()

  const expired = new Telemetry(new PilotApi(transport))
  expired.track('app_visible')
  await expired.flush()
  expired.track('heartbeat')
  await expired.finish()
  expect(transport).toHaveBeenCalledTimes(1)
})
