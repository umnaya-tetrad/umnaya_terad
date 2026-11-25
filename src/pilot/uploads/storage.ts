export type UploadFile = {
  id: string; kind: 'photo'; owner: string; checkId: string; notebookId: string; bundleId: string; inputId: string;
  created: number; name: string; type: string; originalBytes: number; blob?: Blob; prepared: boolean;
  state: 'queued' | 'preparing' | 'uploading' | 'saving' | 'uploaded' | 'error' | 'cancelled';
  progress: number; serverId?: string; error?: string; attempts: number; volatile?: boolean;
}
export type UploadSubmit = {
  id: string; kind: 'submit'; owner: string; checkId: string; notebookId: string; bundleId: string; inputId: string;
  created: number; fileIds: string[]; baselineIds: string[]; photoIds?: string[];
  state: 'queued' | 'sending' | 'done' | 'error' | 'cancelled'; error?: string; attempts: number;
}
export type UploadRecord = UploadFile | UploadSubmit

let opening: Promise<IDBDatabase> | undefined
function database() {
  return opening ??= new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open('smartnote-photo-uploads', 2)
    request.onupgradeneeded = () => {
      const store = request.result.objectStoreNames.contains('items') ? request.transaction!.objectStore('items') : request.result.createObjectStore('items', { keyPath: 'id' })
      if (!store.indexNames.contains('owner')) store.createIndex('owner', 'owner')
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => { opening = undefined; reject(request.error) }
    request.onblocked = () => { opening = undefined; reject(new Error('Хранилище фото занято другой вкладкой.')) }
  })
}
export async function saveRecord(item: UploadRecord) {
  return saveRecords([item])
}
export async function saveRecords(items: UploadRecord[]) {
  const db = await database()
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction('items', 'readwrite')
    for (const item of items) tx.objectStore('items').put(item)
    tx.oncomplete = () => resolve()
    tx.onerror = tx.onabort = () => reject(tx.error ?? new Error('Фото не удалось сохранить на телефоне.'))
  })
}
export async function readRecords(owner: string): Promise<UploadRecord[]> {
  const db = await database()
  return new Promise((resolve, reject) => {
    const request = db.transaction('items').objectStore('items').index('owner').getAll(owner)
    request.onsuccess = () => resolve((request.result as UploadRecord[]).sort((a, b) => a.created - b.created))
    request.onerror = () => reject(request.error)
  })
}
