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
