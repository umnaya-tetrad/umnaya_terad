import { useEffect, useRef, useState } from 'react'
import type { PilotApi } from '../api/client'
import type { CheckListItem } from '../api/contract'
import { errorText } from '../api/errors'
import { copy } from '../copy'

const date = new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium' })

export function ChecksScreen({ api, open, create }: {
  api: PilotApi; open: (item: CheckListItem) => void; create: () => void
}) {
  const [items, setItems] = useState<CheckListItem[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [pending, setPending] = useState(true)
  const [error, setError] = useState('')
  const controller = useRef<AbortController | null>(null)

  async function load(after?: string) {
    controller.current?.abort()
    const request = new AbortController()
    controller.current = request
    setPending(true)
    setError('')
    try {
      const page = await api.listChecks(after, request.signal)
      if (request.signal.aborted) return
      setItems(previous => after ? [...new Map([...previous, ...page.items].map(item => [item.id, item])).values()] : page.items)
      setCursor(page.next_cursor)
    } catch (failure) {
      if (!request.signal.aborted) setError(errorText(failure))
    } finally {
      if (!request.signal.aborted) setPending(false)
    }
  }

  useEffect(() => {
    void load()
    return () => controller.current?.abort()
    // A history screen is mounted per authenticated teacher.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api])

  return (
    <section className="stack">
      <div className="section-header">
        <h1>{copy('history.title')}</h1>
        <button className="primary" onClick={create}>{copy('history.new')}</button>
      </div>
      {error && <div className="notice danger" role="alert">
        <p>{error}</p><button onClick={() => void load()}>{copy('common.refresh')}</button>
      </div>}
      {pending && !items.length && <p role="status">{copy('common.loading')}</p>}
      {!items.length && !pending && !error && <p className="sheet">{copy('history.empty')}</p>}
      {!!items.length && <ul className="plain stack">{items.map(item => (
        <li key={item.id}>
          <button className="row-card" onClick={() => open(item)}>
            <strong>{item.title}</strong>
            <span>{date.format(new Date(item.created_at))} · {copy(`check.phase_${item.phase}`)}</span>
          </button>
        </li>
      ))}</ul>}
      {cursor && <button disabled={pending} onClick={() => void load(cursor)}>{copy('common.more')}</button>}
    </section>
  )
}
