import type { Action, Guard, PilotApi } from './client'
import type { Mutation } from './contract'
import { ApiError } from './errors'

const prefix = 'smartnote:intent:'

function canonicalBody(action: Action) {
  return action.body && Object.entries(action.body).sort(([a], [b]) => a.localeCompare(b))
}

async function digest(value: BufferSource) {
  const bytes = new Uint8Array(await crypto.subtle.digest('SHA-256', value))
  return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('')
}

async function fingerprint(action: Action, checkId: string | null) {
  const { method, path, body } = action
  const payload = body instanceof File
    ? [body.type, await digest(await body.arrayBuffer())]
    : canonicalBody(action)
  return digest(new TextEncoder().encode(JSON.stringify([checkId, method, path, payload])))
}

export function resetIntentStorage(storage: Storage) {
  try {
    for (let index = storage.length - 1; index >= 0; index--) {
      const key = storage.key(index)
      if (key?.startsWith(prefix)) storage.removeItem(key)
    }
  } catch { /* storage unavailable */ }
}

export class Intents {
  private readonly outstanding = new Map<string, Guard>()
  private readonly sending = new Map<string, Promise<Mutation>>()
  private readonly uploadIds = new WeakMap<File, string>()
  private active = true

  constructor(private readonly api: PilotApi, private readonly ownerId: string, private readonly storage: Storage) {}

  expire() {
    this.active = false
    this.outstanding.clear()
    resetIntentStorage(this.storage)
  }

  send(action: Action, checkId: string | null, revision: number | null) {
    let body
    if (action.body instanceof File) {
      if (action.body.size > 8_000_000) return Promise.reject(new ApiError(413))
      body = this.uploadIds.get(action.body) ?? crypto.randomUUID()
      this.uploadIds.set(action.body, body)
    } else {
      body = canonicalBody(action)
    }
    const pendingKey = JSON.stringify([checkId, action.method, action.path, body])
    const pending = this.sending.get(pendingKey)
    if (pending) return pending
    const result = this.sendIntent(action, checkId, revision).finally(() => this.sending.delete(pendingKey))
    this.sending.set(pendingKey, result)
    return result
  }

  private async sendIntent(action: Action, checkId: string | null, revision: number | null) {
    const hash = await fingerprint(action, checkId)
    if (!this.active) throw new ApiError(401)
    const slot = `${prefix}${this.ownerId}:${hash}`
    let stored: Guard | undefined
    try {
      const raw = this.storage.getItem(slot)
      if (raw) stored = JSON.parse(raw)
    } catch {
      // In-memory single-flight handling also works when storage is disabled.
    }
    const guard = this.outstanding.get(slot) ?? stored ?? { key: crypto.randomUUID(), revision }
    this.outstanding.set(slot, guard)
    try { this.storage.setItem(slot, JSON.stringify(guard)) } catch { /* storage unavailable */ }

    const forget = () => {
      this.outstanding.delete(slot)
      try { this.storage.removeItem(slot) } catch { /* storage unavailable */ }
    }
    return this.api.mutate(action, guard).then(mutation => {
      forget()
      if (!this.active) throw new ApiError(401)
      return mutation
    }).catch(error => {
      if (error instanceof ApiError && error.status < 500) forget()
      throw error
    })
  }
}
