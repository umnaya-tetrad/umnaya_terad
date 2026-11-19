import { useEffect, useRef, useState } from 'react'
import type { PilotApi } from '../api/client'
import type {
  BundleHistory, Check, CheckListItem, HistoryRun, SummaryHistory,
} from '../api/contract'
import { errorText } from '../api/errors'
import { copy } from '../copy'
import { JobStatus } from '../components/JobStatus'
import { PhotoThumbnail } from '../components/PhotoStrip'
import { PhotoViewer } from '../components/PhotoViewer'
import { MathText } from '../components/MathText'
import { TaskCard } from '../components/TaskCard'

const date = new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' })

/** Third-person review wording: the staff member never reviews on the teacher's behalf. */
export function reviewLabel(state: string | null | undefined) {
  if (state === 'confirmed') return copy('staff.review_confirmed')
  if (state === 'system_error') return copy('staff.review_system_error')
  return copy('staff.review_missing')
}

function Photos({ api, photos, open }: {
  api: PilotApi
  photos: Array<{ id: string }>
  open: (value: { id: string; label: string }) => void
}) {
  if (!photos.length) return null
  return <ul className="photo-strip plain">{photos.map((photo, index) => {
    const label = copy('capture.photo', { number: index + 1, total: photos.length })
    return <li key={photo.id}>
      <PhotoThumbnail api={api} photo={photo as never} label={label} open={() => open({ id: photo.id, label })} />
    </li>
  })}</ul>
}

export function StaffChecksScreen({ api, open }: {
  api: PilotApi; open: (check: CheckListItem) => void
}) {
  const [ownerLogin, setOwnerLogin] = useState('')
  const [filter, setFilter] = useState('')
  const [items, setItems] = useState<Array<{ owner: { login: string }; check: CheckListItem }>>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [pending, setPending] = useState(true)
  const [error, setError] = useState('')
  const controller = useRef<AbortController | null>(null)

  async function load(after?: string, login = filter) {
    controller.current?.abort()
    const request = new AbortController()
    controller.current = request
    setPending(true)
    setError('')
    try {
      const page = await api.listStaffChecks({
        ownerLogin: login.trim() || undefined, cursor: after, signal: request.signal,
      })
      if (request.signal.aborted) return
      setItems(previous => after
        ? [...new Map([...previous, ...page.items].map(item => [item.check.id, item])).values()]
        : page.items)
      setCursor(page.next_cursor)
    } catch (failure) {
      if (!request.signal.aborted) setError(errorText(failure))
    } finally {
      if (!request.signal.aborted) setPending(false)
    }
  }

  useEffect(() => {
    setFilter('')
    void load(undefined, '')
    return () => controller.current?.abort()
    // The list is mounted once per authenticated staff session.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api])

  return <section className="stack">
    <header className="sheet stack">
      <h1>{copy('staff.title')}</h1>
      <h2>{copy('staff.teachers')}</h2>
      <p className="phase">{copy('staff.readonly')}</p>
    </header>
    <form className="sheet stack" onSubmit={event => {
      event.preventDefault()
      setFilter(ownerLogin)
      void load(undefined, ownerLogin)
    }}>
      <label>{copy('staff.teacher_login')}
        <input maxLength={128} autoComplete="off" value={ownerLogin}
          onChange={event => setOwnerLogin(event.target.value)} />
      </label>
      <button type="submit" className="primary" disabled={pending}>{copy('staff.find')}</button>
    </form>
    {error && <div className="notice danger" role="alert"><p>{error}</p></div>}
    {pending && !items.length && <p role="status">{copy('common.loading')}</p>}
    {!pending && !items.length && !error && <p className="sheet">{copy('history.empty')}</p>}
    {!!items.length && <ul className="plain stack">{items.map(item => <li key={item.check.id}>
      <button className="row-card" onClick={() => open(item.check)}>
        <strong>{item.check.title}</strong>
        <span>{item.owner.login} · {date.format(new Date(item.check.created_at))} · {copy(`check.phase_${item.check.phase}`)}</span>
      </button>
    </li>)}</ul>}
    {cursor && <button disabled={pending} onClick={() => void load(cursor)}>{copy('common.more')}</button>}
  </section>
}

function HistoryRuns({ runs }: { runs: HistoryRun[] }) {
  const [openTask, setOpenTask] = useState<string>()
  if (!runs.length) return <p className="help">{copy('common.unavailable')}</p>
  return <div className="stack">
    {runs.map(run => <div className="stack" key={run.job.id}>
      <p className="phase">{run.job.kind} · {run.job.state}</p>
      {run.result && run.result.report.tasks.map((task, index) => {
        const stored = run.tasks.find(item => item.analysis.task_id === task.task_id)
        const key = `${run.job.id}:${task.task_id}`
        const shown = stored?.analysis ?? task
        return <div className="stack" key={key}>
          <p className="context">
            {copy('check.task', { number: index + 1 })} · {reviewLabel(stored?.review?.state)}
            {stored?.skipped ? ` · ${copy('task.skipped')}` : ''}
          </p>
          <button onClick={() => setOpenTask(value => value === key ? undefined : key)}>
            {openTask === key ? copy('common.close') : copy('result.title')}
          </button>
          {openTask === key && <TaskCard value={shown} photoCount={shown.evidence.length ? shown.evidence.length : 1} />}
          {stored?.review?.comment && <p className="help"><MathText text={stored.review.comment} /></p>}
        </div>
      })}
      {!!run.deleted_task_ids.length && <p className="help">
        {copy('delete.task')}: {run.deleted_task_ids.length}
      </p>}
    </div>)}
  </div>
}

export function StaffCheckScreen({ api, id, back }: { api: PilotApi; id: string; back: () => void }) {
  const [check, setCheck] = useState<Check>()
  const [owner, setOwner] = useState('')
  const [error, setError] = useState('')
  const [history, setHistory] = useState<BundleHistory>()
  const [summaryHistory, setSummaryHistory] = useState<SummaryHistory>()
  const [viewer, setViewer] = useState<{ id: string; label: string }>()
  const [loadingHistory, setLoadingHistory] = useState(false)

  useEffect(() => {
    const request = new AbortController()
    api.getStaffCheck(id, request.signal).then(result => {
      if (request.signal.aborted) return
      setCheck(result.check)
      setOwner(result.owner.login)
    }).catch(failure => {
      if (!request.signal.aborted) setError(errorText(failure))
    })
    return () => request.abort()
  }, [api, id])

  async function openHistory(bundleId: string) {
    setLoadingHistory(true)
    try {
      setHistory(await api.getBundleHistory(bundleId))
    } catch (failure) {
      setError(errorText(failure))
    } finally {
      setLoadingHistory(false)
    }
  }

  async function openSummaryHistory() {
    setLoadingHistory(true)
    try {
      setSummaryHistory(await api.getSummaryHistory(id))
    } catch (failure) {
      setError(errorText(failure))
    } finally {
      setLoadingHistory(false)
    }
  }

  if (error) return <section className="stack">
    <button className="back" onClick={back}>{copy('common.back')}</button>
    <p className="notice danger" role="alert">{error}</p>
  </section>
  if (!check) return <section className="stack">
    <button className="back" onClick={back}>{copy('common.back')}</button>
    <p role="status">{copy('common.loading')}</p>
  </section>

  return <section className="stack">
    <button className="back" onClick={back}>{copy('common.back')}</button>
    <header className="sheet stack">
      <p className="context">{owner}</p>
      <h1>{check.title}</h1>
      <p className="phase">{copy(`check.phase_${check.phase}`)}</p>
      <p className="phase">{copy('staff.readonly')}</p>
    </header>
    {check.notebooks.map(notebook => <div className="sheet stack" key={notebook.id}>
      <h2>{copy('check.notebook', { number: notebook.number })}</h2>
      {notebook.bundles.map(bundle => <div className="stack" key={bundle.id}>
        <JobStatus bundle={bundle} />
        {bundle.current_input && <Photos api={api} photos={bundle.current_input.photos}
          open={value => setViewer(value)} />}
        {bundle.tasks.map((task, index) => <div className="stack" key={task.task_id}>
          <p className="context">
            {copy('check.task', { number: index + 1 })} · {reviewLabel(task.review?.state)}
            {task.skipped ? ` · ${copy('task.skipped')}` : ''}
          </p>
          <TaskCard value={task.analysis} photoCount={bundle.current_input?.photos.length ?? 1} />
          {task.review?.comment && <p className="help"><MathText text={task.review.comment} /></p>}
        </div>)}
        {bundle.current_input && <button disabled={loadingHistory} onClick={() => void openHistory(bundle.id)}>
          {copy('check.ready_count', { count: 1 })}
        </button>}
      </div>)}
    </div>)}
    <button disabled={loadingHistory} onClick={() => void openSummaryHistory()}>{copy('check.summary')}</button>
    {history && <div className="sheet stack">
      <h2>{copy('check.task', { number: history.versions.length })}</h2>
      {history.versions.map((version, index) => <div className="stack" key={version.input.id}>
        <p className="phase">{copy('check.notebook', { number: index + 1 })}</p>
        <Photos api={api} photos={version.input.photos} open={value => setViewer(value)} />
        <HistoryRuns runs={version.runs} />
      </div>)}
    </div>}
    {summaryHistory && <div className="sheet stack">
      <h2>{copy('summary.title')}</h2>
      {summaryHistory.items.map(item => <div className="stack" key={`${item.summary.job_id}:${item.created_at}`}>
        <p className="phase">{date.format(new Date(item.created_at))}</p>
        <p className="help">{copy('summary.basis')}</p>
        {item.summary.result && <p className="phase">
          {copy('summary.with_errors')}: {item.summary.result.notebooks.with_errors} · {copy('summary.without_errors')}: {item.summary.result.notebooks.without_errors}
        </p>}
      </div>)}
      {!summaryHistory.items.length && <p className="help">{copy('summary.not_started')}</p>}
    </div>}
    {viewer && <PhotoViewer api={api} {...viewer} close={() => setViewer(undefined)} />}
  </section>
}
