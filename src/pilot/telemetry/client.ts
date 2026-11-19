import type { PilotApi } from '../api/client'
import type { Event } from '../api/contract'
import { ApiError } from '../api/errors'

export class Telemetry {
  readonly sessionId = crypto.randomUUID()
  private queue: Event[] = []
  private readonly requests = new AbortController()
  private inFlight?: Promise<boolean>
  private finishing?: Promise<void>
  private view?: { checkId?: string; entityId?: string }
  private visibility?: 'app_visible' | 'app_hidden'

  constructor(
    private readonly api: PilotApi,
    private readonly now = () => new Date(),
    private readonly canSend = () => true,
  ) {}

  track(name: Event['name'], checkId?: string, entityId?: string) {
    if (this.finishing || this.requests.signal.aborted) return
    if (name === 'app_visible' || name === 'app_hidden') {
      if (this.visibility === name) return
      this.visibility = name
    }
    if (name === 'result_opened') this.view = { checkId, entityId }
    if (name === 'result_closed') {
      if (!this.view || this.view.checkId !== checkId || this.view.entityId !== entityId) return
      this.view = undefined
    }
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

  discard() {
    this.requests.abort()
    this.queue = []
    this.view = undefined
  }

  flush(keepalive = false): Promise<boolean> {
    if (!this.canSend()) this.discard()
    if (this.requests.signal.aborted || !this.queue.length) return Promise.resolve(false)
    if (this.inFlight) return this.inFlight
    const events = this.queue.slice(0, 100)
    this.inFlight = this.send(events, keepalive).finally(() => { this.inFlight = undefined })
    return this.inFlight
  }

  private async send(events: Event[], keepalive: boolean) {
    function remaining(queue: Event[], ids: string[]) {
      const accepted = new Set(ids)
      return queue.filter(event => !accepted.has(event.id))
    }
    try {
      const accepted = await this.api.events({ events }, keepalive, this.requests.signal)
      const before = this.queue.length
      this.queue = remaining(this.queue, accepted.accepted_ids)
      return this.queue.length < before
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 401) this.discard()
      if (failure instanceof ApiError && failure.status < 500 && failure.status !== 429) {
        // The server rejects a batch atomically when a referenced entity vanished.
        this.queue = remaining(this.queue, events.map(event => event.id))
        return true
      }
      return false
    }
  }

  finish() {
    if (this.finishing) return this.finishing
    if (this.view) this.track('result_closed', this.view.checkId, this.view.entityId)
    const drain = async () => {
      // Join an in-flight batch first. The remaining batches keep the same IDs.
      if (this.inFlight) await this.inFlight
      while (this.queue.length && await this.flush(true)) { /* drain remaining events */ }
    }
    let timer: ReturnType<typeof setTimeout>
    const deadline = new Promise<void>(resolve => { timer = setTimeout(resolve, 1000) })
    this.finishing = Promise.race([drain(), deadline]).finally(() => {
      clearTimeout(timer)
      this.discard()
    })
    return this.finishing
  }
}
