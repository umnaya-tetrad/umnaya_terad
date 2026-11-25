import { actions, type PilotApi } from '../api/client'
import { ApiError, errorText } from '../api/errors'
import type { Mutation } from '../api/contract'
import { prepareUpload } from './compress'
import { readRecords, saveRecord, saveRecords, type UploadFile, type UploadRecord, type UploadSubmit } from './storage'

export class PhotoUploadQueue {
  private items: UploadRecord[] = []
  private listeners = new Set<() => void>()
  private active = true
  private draining = false
  private xhr?: XMLHttpRequest
  private channel?: BroadcastChannel
  private ready: Promise<void>
  private stateTail: Promise<unknown> = Promise.resolve()
  private cancelled = new Set<string>()
  private currentInput?: string
  private controllers = new Set<AbortController>()
  error = ''
  constructor(private api: PilotApi, readonly owner: string) {
    this.ready = this.load().catch(() => { this.error = 'Не удалось открыть хранилище фото на телефоне.'; this.changed() })
    if (typeof BroadcastChannel !== 'undefined') {
      this.channel = new BroadcastChannel('smartnote:photo-uploads:' + owner)
      this.channel.onmessage = () => { if (!this.draining) void this.load().then(() => this.kick()).catch(() => { this.error = 'Не удалось прочитать очередь фото. Повторите загрузку.'; this.changed() }) }
    }
    window.addEventListener('online', this.online)
    window.addEventListener('beforeunload', this.beforeUnload)
    void this.ready.then(() => this.kick())
  }
  private online = () => { this.kick() }
  private beforeUnload = (event: BeforeUnloadEvent) => {
    if (this.pending().length) { event.preventDefault(); event.returnValue = '' }
  }
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener) } }
  snapshot = () => this.items
  private changed() { this.items = [...this.items]; this.listeners.forEach(fn => fn()) }
  private async load() {
    const disk = await readRecords(this.owner)
    if (!this.active) return
    const volatile = this.items.filter(item => item.kind === 'photo' && item.volatile && !disk.some(x => x.id === item.id))
    this.items = [...disk, ...volatile].map(item => item.kind === 'photo' && ['uploading', 'saving', 'preparing'].includes(item.state)
      ? { ...item, state: 'queued' as const, progress: 0 } : item.kind === 'submit' && item.state === 'sending'
        ? { ...item, state: 'queued' as const } : item)
    this.changed()
  }
  private async put(item: UploadRecord) {
    await saveRecord(item)
    if (!this.active) return
    this.items = [...this.items.filter(old => old.id !== item.id), item].sort((a, b) => a.created - b.created)
    this.changed(); this.channel?.postMessage('changed')
  }
  private view(item: UploadRecord) { this.items = this.items.map(old => old.id === item.id ? item : old); this.changed() }
  pending(checkId?: string, notebookId?: string) {
    return this.items.filter(item => (!checkId || item.checkId === checkId) && (!notebookId || item.notebookId === notebookId)
      && (item.kind === 'photo' ? !['uploaded','cancelled'].includes(item.state) : !['done','cancelled'].includes(item.state)))
  }
  files(inputId: string) { return this.items.filter((item): item is UploadFile => item.kind === 'photo' && item.inputId === inputId && item.state !== 'cancelled') }
  sealed(inputId: string) { return this.items.some(item => item.kind === 'submit' && item.inputId === inputId && item.state !== 'cancelled') }
  private stateChange<T>(work: () => Promise<T>): Promise<T> {
    const execute = () => navigator.locks ? navigator.locks.request('smartnote-upload-state:' + this.owner, work) : work()
    const pending = this.stateTail.then(execute, execute)
    this.stateTail = pending.catch(() => {})
    return pending
  }
  enqueue(target: Pick<UploadFile, 'checkId' | 'notebookId' | 'bundleId' | 'inputId'>, files: File[]) {
    return this.stateChange(() => this.enqueueFiles(target, files))
  }
  private async enqueueFiles(target: Pick<UploadFile, 'checkId' | 'notebookId' | 'bundleId' | 'inputId'>, files: File[]) {
    await this.ready
    const disk = await readRecords(this.owner)
    if (!this.active || this.sealed(target.inputId) || disk.some(x => x.kind === 'submit' && x.inputId === target.inputId && x.state !== 'cancelled')) throw new Error('Этот комплект уже отправляется. Добавьте фото в новый комплект.')
    const batch = files.map((file, index): UploadFile => {
      const type = file.type || ({jpg:'image/jpeg',jpeg:'image/jpeg',png:'image/png',webp:'image/webp',heic:'image/heic',heif:'image/heif'}[file.name.split('.').at(-1)?.toLowerCase() ?? ''] ?? 'application/octet-stream')
      return { ...target, id: crypto.randomUUID(), kind: 'photo', owner: this.owner,
        created: Date.now() + index / 1000, name: file.name, type, originalBytes: file.size,
        blob: file.slice(0, file.size, type), prepared: false, state: 'queued', progress: 0, attempts: 0 }
    })
    try {
      await saveRecords(batch)
      this.error = ''
      this.items = [...this.items, ...batch]; this.changed(); this.channel?.postMessage('changed')
    } catch {
      this.items = [...this.items, ...batch.map(item => ({ ...item, state: 'error' as const, volatile: true, error: 'Фото не сохранено на телефоне. Освободите память и нажмите «Повторить».' }))]
      this.changed(); throw new Error('Фото пока не сохранено на телефоне. Не закрывайте приложение; освободите память и повторите загрузку.')
    }
    this.kick()
  }
  submit(target: Pick<UploadFile, 'checkId' | 'notebookId' | 'bundleId' | 'inputId'>, baselineIds: string[]) {
    return this.stateChange(() => this.freezeSubmit(target, baselineIds))
  }
  private async freezeSubmit(target: Pick<UploadFile, 'checkId' | 'notebookId' | 'bundleId' | 'inputId'>, baselineIds: string[]) {
    await this.ready
    const disk = await readRecords(this.owner)
    if (this.sealed(target.inputId) || disk.some(x => x.kind === 'submit' && x.inputId === target.inputId && x.state !== 'cancelled')) return
    const files = [...new Map([...disk, ...this.items].filter((x): x is UploadFile => x.kind === 'photo' && x.inputId === target.inputId && x.state !== 'cancelled').map(x => [x.id, x])).values()].sort((a,b) => a.created-b.created)
    if (files.some(file => file.volatile)) throw new Error('Сначала сохраните фото на телефоне: нажмите «Повторить загрузку».')
    if (!files.length && !baselineIds.length) throw new Error('Добавьте хотя бы одно фото.')
    await this.put({ ...target, id: crypto.randomUUID(), kind: 'submit', owner: this.owner,
      created: Date.now(), fileIds: files.filter(file => !file.serverId || !baselineIds.includes(file.serverId)).map(x => x.id), baselineIds,
      state: 'queued', attempts: 0 })
    this.kick()
  }
  async retry(id: string) {
    const item = this.items.find(x => x.id === id)
    if (item) { await this.put({ ...item, ...(item.kind === 'photo' ? { volatile: false } : {}), state: 'queued', error: undefined, attempts: 0 }); this.error = ''; this.changed(); this.kick() }
  }
  async resume() {
    try { await this.load(); this.error = ''; this.changed(); this.kick() }
    catch { this.error = 'Не удалось прочитать очередь на телефоне. Освободите память и повторите.'; this.changed() }
  }
  async forget(inputId: string, serverId?: string) {
    for (const item of this.items.filter(x => x.inputId === inputId && (serverId === undefined || (x.kind === 'photo' && x.serverId === serverId)))) {
      await this.put({ ...item, state: 'cancelled', ...(item.kind === 'photo' ? { blob: undefined } : {}) })
    }
  }
  async cancelInput(inputId: string) {
    const records = this.items.filter(x => x.inputId === inputId)
    const first = records[0]
    if (!first) return
    this.cancelled.add(inputId)
    if (this.currentInput === inputId) this.xhr?.abort()
    try {
      await this.checkOwner()
      for (let attempt = 0; attempt < 3; attempt++) {
        const check = await this.metadata(signal => this.api.getCheck(first.checkId, signal))
        const bundle = check.notebooks.flatMap(x => x.bundles).find(x => x.id === first.bundleId)
        if (bundle?.current_input?.id === inputId) throw new Error('Комплект уже передан в ИИ. Его можно открыть в разборах.')
        if (bundle?.draft?.id === inputId) {
          try { await this.metadata(signal => this.api.mutate(actions.discardDraft(inputId), { key: crypto.randomUUID(), revision: check.revision }, signal)) }
          catch (error) { if (error instanceof ApiError && error.status === 409 && attempt < 2) continue; throw error }
        }
        await this.forget(inputId)
        return
      }
    } catch (error) {
      for (const item of this.items.filter(x => x.inputId === inputId && !['uploaded','done','cancelled'].includes(x.state))) {
        const failed = { ...item, state: 'error' as const, error: error instanceof Error ? error.message : 'Отмена не подтверждена сервером. Повторите.' }
        try { await this.put(failed) } catch { this.view(failed) }
      }
      throw error
    } finally { this.cancelled.delete(inputId); this.kick() }
  }
  stop() {
    this.active = false; this.xhr?.abort(); this.channel?.close()
    this.controllers.forEach(controller => controller.abort())
    window.removeEventListener('online', this.online); window.removeEventListener('beforeunload', this.beforeUnload)
    this.changed()
  }
  private async metadata<T>(work: (signal: AbortSignal) => Promise<T>) {
    const controller = new AbortController(); this.controllers.add(controller)
    const timeout = setTimeout(() => controller.abort(), 30_000)
    try { return await work(controller.signal) }
    finally { clearTimeout(timeout); this.controllers.delete(controller) }
  }
  private async checkOwner() {
    if (!this.active) throw new ApiError(401)
    const session = await this.metadata(signal => this.api.getSession(signal))
    if (!this.active || session.user_id !== this.owner) { this.stop(); throw new ApiError(401) }
  }
  private upload(item: UploadFile): Promise<Mutation> {
    return new Promise((resolve, reject) => {
      if (!this.active || this.cancelled.has(item.inputId)) { reject(new ApiError(401)); return }
      const xhr = new XMLHttpRequest(); this.xhr = xhr
      xhr.open('POST', '/api/input-versions/' + encodeURIComponent(item.inputId) + '/queued-photos')
      xhr.withCredentials = true; xhr.timeout = 180_000
      xhr.setRequestHeader('Idempotency-Key', item.id)
      xhr.upload.onprogress = event => {
        if (this.active && event.lengthComputable) this.view({ ...item, state: event.loaded === event.total ? 'saving' : 'uploading', progress: event.loaded / event.total })
      }
      xhr.onload = () => {
        try {
          const value = JSON.parse(xhr.responseText)
          if (xhr.status >= 200 && xhr.status < 300) resolve(value)
          else reject(new ApiError(xhr.status, value?.error))
        } catch { reject(new Error('Ответ сервера не получен. Повтор безопасен.')) }
      }
      xhr.onerror = xhr.ontimeout = xhr.onabort = () => reject(new Error('Передача прервана. Фото сохранено на телефоне.'))
      const form = new FormData()
      form.set('file', item.blob!, item.blob!.type === 'image/jpeg' ? item.name.replace(/\.[^.]+$/, '') + '.jpg' : item.name)
      xhr.send(form)
    })
  }
  private async sendSubmit(item: UploadSubmit) {
    const files = item.fileIds.map(id => this.items.find((x): x is UploadFile => x.kind === 'photo' && x.id === id))
    if (files.some(file => !file || file.state !== 'uploaded')) return false
    const photoIds = item.photoIds ?? [...item.baselineIds, ...files.map(file => file!.serverId!)]
    const next = { ...item, photoIds, state: 'sending' as const }
    await this.put(next) // Freeze exact payload before dispatch, including reload/lost-ACK retries.
    await this.checkOwner()
    await this.metadata(async signal => {
      const response = await fetch('/api/bundles/' + encodeURIComponent(item.bundleId) + '/queued-submit', {
        method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': item.id },
        body: JSON.stringify({ input_version_id: item.inputId, photo_ids: photoIds }), signal,
      })
      const value = await response.json()
      if (!response.ok) throw new ApiError(response.status, value?.error)
    })
    if (this.active) await this.put({ ...next, state: 'done', error: undefined })
    return true
  }
  private kick() {
    if (!this.active || this.draining || !navigator.onLine) return
    this.draining = true
    const work = async () => {
      // Other tabs share durable keys and blobs. Web Locks prevents duplicate transfers.
      await this.load()
      while (this.active && navigator.onLine) {
        const item = this.items.find(x => !this.cancelled.has(x.inputId) && x.state === 'queued' && (x.kind === 'photo' || x.fileIds.every(id => this.items.some(f => f.id === id && f.state === 'uploaded'))))
        if (!item) break
        this.currentInput = item.inputId
        try {
          await this.checkOwner()
          if (item.kind === 'photo') {
            let prepared = item
            if (!item.prepared) {
              this.view({ ...item, state: 'preparing' })
              const blob = await prepareUpload(item.blob!)
              prepared = { ...item, blob, type: blob.type, prepared: true, state: 'queued' }
              await this.put(prepared)
            }
            if (prepared.blob!.size > 8_000_000) throw new ApiError(413, { code: 'invalid_input', message: 'Фото больше 8 MB. Выберите меньший снимок или переснимите.', current_revision: null })
            await this.checkOwner()
            if (this.cancelled.has(item.inputId) || this.items.find(x => x.id === item.id)?.state === 'cancelled') continue
            this.view({ ...prepared, state: 'uploading', progress: 0 })
            const result = await this.upload(prepared)
            if (!result.entity_id) throw new Error('Сервер не подтвердил сохранение фото.')
            if (this.active && !this.cancelled.has(item.inputId) && this.items.find(x => x.id === item.id)?.state !== 'cancelled') await this.put({ ...prepared, blob: undefined, state: 'uploaded', serverId: result.entity_id, progress: 1, error: undefined })
          } else await this.sendSubmit(item)
        } catch (error) {
          if (!this.active) break
          if (this.cancelled.has(item.inputId)) continue
          const latest = this.items.find(x => x.id === item.id) ?? item
          const transient = !(error instanceof ApiError) || error.status >= 500 || error.status === 429
          const attempts = latest.attempts + 1
          const retry = transient && attempts < 3
          const failed: UploadRecord = { ...latest, state: retry ? 'queued' : 'error', attempts,
            error: error instanceof ApiError ? errorText(error) : error instanceof Error ? error.message : 'Не удалось загрузить фото.' }
          try { await this.put(failed) } catch {
            this.view({ ...latest, state: 'error', error: 'Не удалось сохранить очередь на телефоне. Освободите память и повторите.' })
          }
          if (retry) await new Promise(resolve => setTimeout(resolve, attempts * 1500))
        }
      }
    }
    const locks = navigator.locks
    const promise = locks ? locks.request('smartnote-photo-uploads:' + this.owner, work) : work()
    void promise.catch(() => { this.error = 'Не удалось сохранить очередь. Не закрывайте приложение и повторите.'; this.changed() })
      .finally(() => {
        this.draining = false; this.currentInput = undefined
        if (!this.error && this.items.some(x => !this.cancelled.has(x.inputId) && x.state === 'queued' && (x.kind === 'photo' || x.fileIds.every(id => this.items.some(f => f.id === id && f.state === 'uploaded'))))) this.kick()
      })
  }
}
