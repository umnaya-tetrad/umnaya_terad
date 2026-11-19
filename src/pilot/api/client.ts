import type {
  AnalysisTarget, Check, Checks, Events, EventsAccepted, InputTarget, Job, Login, Mutation,
  PhotoOrder, ReviewWrite, Session, Submit, Summary, Title, VersionCreate,
} from './contract'
import { ApiError } from './errors'

type Payload = AnalysisTarget | InputTarget | PhotoOrder | ReviewWrite | Submit | Title | VersionCreate
export type Action = { method: 'POST' | 'PATCH' | 'DELETE' | 'PUT'; path: string; body?: Payload | File }
export type Guard = { key: string; revision: number | null }

const checks = '/checks'
const path = (root: string, id: string) => `/${root}/${encodeURIComponent(id)}`
const check = (id: string) => path('checks', id)
const notebook = (id: string) => path('notebooks', id)
const bundle = (id: string) => path('bundles', id)
const draft = (id: string) => path('input-versions', id)
const task = (id: string) => path('tasks', id)
const post = (path: string, body?: Payload | File): Action => ({ method: 'POST', path, body })
const remove = (path: string): Action => ({ method: 'DELETE', path })

export const actions = {
  createCheck: (body: Title) => post(checks, body),
  deleteCheck: (id: string) => remove(check(id)),
  createNotebook: (id: string) => post(`${check(id)}/notebooks`),
  deleteNotebook: (id: string) => remove(notebook(id)),
  createBundle: (id: string) => post(`${notebook(id)}/bundles`),
  deleteBundle: (id: string) => remove(bundle(id)),
  createInputVersion: (id: string, body: VersionCreate) => post(`${bundle(id)}/versions`, body),
  reorderPhotos: (id: string, body: PhotoOrder): Action => ({ method: 'PATCH', path: draft(id), body }),
  discardDraft: (id: string) => remove(draft(id)),
  uploadPhoto: (id: string, file: File) => post(`${draft(id)}/photos`, file),
  deleteDraftPhoto: (id: string, photoId: string) => remove(`${draft(id)}/photos/${encodeURIComponent(photoId)}`),
  submitBundle: (id: string, body: Submit) => post(`${bundle(id)}/submit`, body),
  retryBundle: (id: string, body: InputTarget) => post(`${bundle(id)}/retry`, body),
  skipBundle: (id: string, body: InputTarget) => post(`${bundle(id)}/skip`, body),
  deleteTask: (id: string) => remove(task(id)),
  saveReview: (id: string, body: ReviewWrite): Action => ({ method: 'PUT', path: `${task(id)}/review`, body }),
  skipTask: (id: string, body: AnalysisTarget) => post(`${task(id)}/skip`, body),
  beginCompletion: (id: string) => post(`${check(id)}/begin-completion`),
  finalizeCheck: (id: string) => post(`${check(id)}/finalize`),
  refreshSummary: (id: string) => post(`${check(id)}/summary/refresh`),
  retrySummary: (id: string) => post(`${check(id)}/summary/retry`),
}

export class PilotApi {
  constructor(private readonly transport: typeof fetch = fetch, private readonly onUnauthorized?: () => void) {}

  private async request(path: string, init?: RequestInit, quiet401 = false) {
    const response = await this.transport.call(globalThis, `/api${path}`, { credentials: 'same-origin', cache: 'no-store', ...init })
    if (response.ok) return response

    if (response.status === 401 && !quiet401) this.onUnauthorized?.()
    const detail = await response.json().catch(() => null)
    throw new ApiError(response.status, detail?.error)
  }

  private async json<T>(path: string, init?: RequestInit, quiet401?: boolean): Promise<T> {
    return (await this.request(path, init, quiet401)).json()
  }

  login(body: Login) {
    return this.json<Session>('/auth/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    }, true)
  }

  getSession() { return this.json<Session>('/auth/session', undefined, true) }

  async logout() { await this.request('/auth/logout', { method: 'POST' }) }

  listChecks(cursor?: string, signal?: AbortSignal) {
    const params = new URLSearchParams({ limit: '30' })
    if (cursor) params.set('cursor', cursor)
    return this.json<Checks>(`${checks}?${params}`, { signal })
  }

  async getCheck(id: string, signal?: AbortSignal): Promise<Check> {
    const response = await this.request(check(id), { signal })
    const result: Check = await response.json()
    const tag = response.headers.get('ETag')
    if (tag !== `"${result.revision}"`) throw new ApiError(502)
    return result
  }

  getJob(id: string, signal?: AbortSignal) { return this.json<Job>(path('jobs', id), { signal }) }

  getSummary(id: string, signal?: AbortSignal) {
    return this.json<Summary>(`${check(id)}/summary`, { signal })
  }

  async getPhoto(id: string, signal?: AbortSignal) {
    return (await this.request(path('assets', id), { signal })).blob()
  }

  events(events: Events, keepalive: boolean, signal?: AbortSignal) {
    return this.json<EventsAccepted>('/events', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(events), keepalive, signal,
    }, true)
  }

  mutate(action: Action, guard: Guard) {
    const headers = new Headers({ 'Idempotency-Key': guard.key })
    if (guard.revision !== null) headers.set('If-Match', `"${guard.revision}"`)
    let body: BodyInit | undefined
    if (action.body instanceof File) {
      const form = new FormData()
      form.set('file', action.body)
      body = form
    } else if (action.body !== undefined) {
      headers.set('Content-Type', 'application/json')
      body = JSON.stringify(action.body)
    }
    return this.json<Mutation>(action.path, { method: action.method, headers, body })
  }
}
