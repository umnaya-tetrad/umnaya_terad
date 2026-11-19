import type { PilotApi } from '../api/client'
import type { Event } from '../api/contract'
import { ApiError } from '../api/errors'

export class Telemetry {
  private readonly sessionId = crypto.randomUUID()
  private queue: Event[] = []
  private inFlight = false

  constructor(private readonly api: PilotApi, private readonly now = () => new Date()) {}

  track(name: Event['name'], checkId?: string, entityId?: string) {
    if (this.queue.length >= 300) return
    this.queue.push({
      id: crypto.randomUUID(),
      session_id: this.sessionId,
      occurred_at: this.now().toISOString(),
      name,
      check_id: checkId ?? null,
      entity_id: checkId ? entityId ?? null : null,
    })
  }

  async flush(keepalive = false) {
    if (this.inFlight || !this.queue.length) return
    this.inFlight = true
    const events = this.queue.slice(0, 100)
    const remove = (ids: string[]) => {
      const accepted = new Set(ids)
      this.queue = this.queue.filter(event => !accepted.has(event.id))
    }
    try {
      const accepted = await this.api.events({ events }, keepalive)
      remove(accepted.accepted_ids)
    } catch (failure) {
      if (failure instanceof ApiError && failure.status < 500 && failure.status !== 429) {
        // The server rejects a batch atomically when a referenced entity vanished.
        remove(events.map(event => event.id))
      }
    } finally {
      this.inFlight = false
    }
  }
}
