import { useEffect, useState, useSyncExternalStore } from 'react'
import type { PhotoUploadQueue } from './queue'
import type { UploadFile } from './storage'

export function useUploads(queue: PhotoUploadQueue) {
  return useSyncExternalStore(queue.subscribe, queue.snapshot, queue.snapshot)
}
function LocalPhoto({ item }: { item: UploadFile }) {
  const [url, setUrl] = useState('')
  useEffect(() => {
    if (!item.blob) return
    const next = URL.createObjectURL(item.blob); setUrl(next)
    return () => URL.revokeObjectURL(next)
  }, [item.blob])
  return url ? <img src={url} alt="Фото в очереди загрузки" style={{ maxWidth: 150, maxHeight: 180, objectFit: 'contain' }} /> : null
}
export function UploadStatus({ queue, checkId, notebookId, compact = false, open }: {
  queue: PhotoUploadQueue; checkId?: string; notebookId?: string; compact?: boolean; open?: (id: string) => void
}) {
  useUploads(queue)
  const items = queue.pending(checkId, notebookId)
  if (!items.length && !queue.error) return null
  if (compact) return <aside className="notice" aria-label="Очередь загрузки">
    <p>Фото загружаются в фоне: {items.filter(x => x.kind === 'photo').length}. Можно продолжать съемку.</p>
    {queue.error && <><p role="alert">{queue.error}</p><button onClick={() => void queue.resume()}>Повторить загрузку</button></>}
    {open && [...new Set(items.map(x => x.checkId))].map(id => <button key={id} onClick={() => open(id)}>Открыть загрузки</button>)}
  </aside>
  return <section className="sheet stack" aria-label="Фото на телефоне">
    <h2>Загрузка фото</h2>
    <p className="help">Можно снимать дальше и переходить к другим тетрадям. До отправки всех фото не закрывайте приложение.</p>
    {queue.error && <><p role="alert">{queue.error}</p><button onClick={() => void queue.resume()}>Повторить загрузку</button></>}
    {items.map(item => <article className="notice stack" key={item.id}>
      {item.kind === 'photo' ? <>
        <LocalPhoto item={item} />
        <p>{item.state === 'queued' ? 'Фото сохранено на телефоне. Ожидает загрузки.'
          : item.state === 'preparing' ? 'Подготавливаем фото'
          : item.state === 'saving' ? 'Фото передано. Сохраняем на сервере…'
          : item.state === 'uploading' ? `Загружаем фото: ${Math.round(item.progress * 100)}%` : item.error}</p>
        {['uploading', 'saving'].includes(item.state) && <progress max={1} value={item.progress} aria-label="Прогресс загрузки фото" />}
      </> : <p>{item.state === 'error' ? item.error : 'Комплект отправится на проверку после загрузки всех фото.'}</p>}
      {item.state === 'error' && <button onClick={() => void queue.retry(item.id).catch(() => {})}>Повторить загрузку</button>}
    </article>)}
    {[...new Set(items.map(x => x.inputId))].map(inputId => <button className="danger" key={inputId} onClick={() => {
      if (window.confirm('Отменить загрузку этого комплекта? Все его фото будут убраны из черновика. Уже отправленный в ИИ комплект удалить здесь нельзя.')) void queue.cancelInput(inputId).catch(error => window.alert(error instanceof Error ? error.message : 'Отменить не удалось.'))
    }}>Отменить загрузку комплекта</button>)}
  </section>
}
