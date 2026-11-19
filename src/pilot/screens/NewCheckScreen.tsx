import { useRef, useState, type FormEvent } from 'react'
import { actions } from '../api/client'
import { errorText } from '../api/errors'
import type { Intents } from '../api/intents'
import { copy } from '../copy'

export function NewCheckScreen({ intents, open, back }: {
  intents: Intents; open: (id: string) => void; back: () => void
}) {
  const [title, setTitle] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const sending = useRef(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (sending.current) return
    const value = title.trim()
    if (!value) {
      setError(copy('check.title_required'))
      input.current?.focus()
      return
    }
    sending.current = true
    setBusy(true)
    setError('')
    try {
      const result = await intents.send(actions.createCheck({ title: value }), null, null)
      open(result.check_id)
    } catch (failure) {
      setError(errorText(failure))
    } finally {
      sending.current = false
      setBusy(false)
    }
  }

  return (
    <section className="sheet stack">
      <button className="back" disabled={busy} onClick={back}>{copy('common.back')}</button>
      <h1>{copy('history.new')}</h1>
      <form className="stack" onSubmit={submit}>
        <label>{copy('check.title_label')}
          <input ref={input} maxLength={200} placeholder={copy('check.title_placeholder')} value={title}
            onChange={event => setTitle(event.target.value)} aria-invalid={!!error && !title.trim()} />
        </label>
        <button className="primary" disabled={busy}>{copy('check.create')}</button>
      </form>
      {error && <p className="notice danger" role="alert">{error}</p>}
    </section>
  )
}
