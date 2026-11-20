import { useLayoutEffect, useRef, useState } from 'react'
import type { Review, ReviewWrite } from '../api/contract'
import { copy } from '../copy'

export function ReviewControls({ review, busy, save }: {
  review: Review | null; busy: boolean; save: (state: ReviewWrite['state'], comment: string) => Promise<boolean>
}) {
  const [local, setLocal] = useState<string>()
  const [notice, setNotice] = useState(false)
  const comment = local ?? review?.comment ?? ''
  const actions = useRef<HTMLDivElement>(null)

  useLayoutEffect(() => {
    const bar = actions.current
    if (!bar) return
    const updateHeight = () => document.documentElement.style.setProperty('--review-actions-height', `${bar.getBoundingClientRect().height}px`)
    updateHeight()
    const observer = new ResizeObserver(updateHeight)
    observer.observe(bar)
    return () => {
      observer.disconnect()
      document.documentElement.style.removeProperty('--review-actions-height')
    }
  }, [])

  async function submit(state: ReviewWrite['state']) {
    setNotice(false)
    if (await save(state, comment)) {
      setLocal(undefined)
      setNotice(true)
    }
  }

  return <section className="sheet stack">
    <p>{copy('review.help')}</p>
    {review?.state !== 'confirmed' && <p className="phase">{copy(review ? `review.${review.state}` : 'review.unreviewed')}</p>}
    <div className="review-actions" ref={actions} role="group" aria-label={copy('review.help')}>
      <div className="review-actions-inner">
        <button className="success" disabled={busy} aria-pressed={review?.state === 'confirmed'}
          onClick={() => void submit('confirmed')}>✓ {copy('review.agree')}</button>
        <button className="danger" disabled={busy} aria-pressed={review?.state === 'system_error'}
          onClick={() => void submit('system_error')}>✕ {copy('review.disagree')}</button>
      </div>
    </div>
    <label>{copy('review.comment_label')}
      <textarea rows={3} maxLength={4000} disabled={busy} value={comment} placeholder={copy('review.comment_placeholder')}
        onChange={event => { setLocal(event.target.value); setNotice(false) }} />
    </label>
    {review && local !== undefined && local !== review.comment &&
      <button disabled={busy} onClick={() => void submit(review.state)}>{copy('common.save')}</button>}
    {notice && <p role="status">{copy('review.saved')}</p>}
  </section>
}
