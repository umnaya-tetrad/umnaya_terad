import { actions } from '../api/client'
import type { Check, Summary } from '../api/contract'
import { summaryStatus } from '../components/JobStatus'
import { copy } from '../copy'
import { skippedCounts, type Mutate, type Run } from '../state/flow'
import { MathText } from '../components/MathText'

const number = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 })

function Metric({ title, value, hint, tone }: {
  title: string; value: string | number; hint: string; tone: 'blue' | 'green' | 'red' | 'gold';
}) {
  return <article className={`summary-metric task-frame summary-metric--${tone}`}>
    <h2>{title}</h2>
    <p className="summary-metric-value">{value}</p>
    <p className="summary-hint">{hint}</p>
  </article>
}

export function SummaryScreen({ check, value, materials, busy, run, mutate }: {
  check: Check; value: Summary; materials: () => void; busy: boolean; run: Run; mutate: Mutate;
}) {
  const result = value.state === 'succeeded' && !value.stale ? value.result : null
  const status = summaryStatus(value)
  const basis = (result?.notebooks.with_errors ?? 0) + (result?.notebooks.without_errors ?? 0)
  const skipped = skippedCounts(check)
  const hasConfirmed = check.notebooks.some(notebook => notebook.bundles.some(bundle =>
    !bundle.skipped && bundle.tasks.some(task => !task.skipped && task.review?.state === 'confirmed'),
  ))
  const notes = result ? [
    { count: result.incomplete_tasks, label: copy('summary.note_incomplete'), hint: copy('summary.note_incomplete_hint'), tone: 'gold' },
    { count: result.disputed_tasks, label: copy('summary.note_disputed'), hint: copy('summary.note_disputed_hint'), tone: 'red' },
    { count: result.notebooks.partial, label: copy('summary.note_partial'), hint: copy('summary.note_partial_hint'), tone: 'gold' },
    { count: result.unassessed_tasks, label: copy('summary.note_unassessed'), hint: copy('summary.note_unassessed_hint'), tone: 'neutral' },
    { count: result.notebooks.empty, label: copy('summary.note_empty'), hint: copy('summary.note_empty_hint'), tone: 'neutral' },
    { count: skipped.skipped_tasks, label: copy('summary.note_skipped_tasks'), hint: copy('summary.note_skipped_tasks_hint'), tone: 'neutral' },
    { count: skipped.skipped_bundles, label: copy('summary.note_skipped_bundles'), hint: copy('summary.note_skipped_bundles_hint'), tone: 'neutral' },
  ].filter(item => item.count > 0) : []

  return <section className="summary-report stack">
    <button className="back summary-back" onClick={materials}>← {copy('summary.materials')}</button>
    <header className="summary-header task-frame">
      <p className="context">{check.title}</p>
      <h1>{copy('summary.title')}</h1>
    </header>
    {(status || value.stale || value.can_refresh || (value.can_retry && !value.stale)) && <section className="summary-state task-frame stack" role="status">
      {value.stale && <p>{copy('summary.stale')}</p>}
      {status && <p>{copy(status)}</p>}
      {value.can_refresh && <button className="primary" disabled={busy} onClick={() => void run(async () => {
        await mutate(actions.refreshSummary(check.id))
      })}>{copy('summary.refresh')}</button>}
      {value.can_retry && !value.stale && <button disabled={busy} onClick={() => void run(async () => {
        await mutate(actions.retrySummary(check.id))
      })}>{copy('summary.retry')}</button>}
    </section>}
    {result && <>
      <section className="summary-metrics">
        <Metric title={copy('summary.metric_total')} value={result.notebooks.total} hint={copy('summary.metric_total_hint')} tone="blue" />
        <Metric title={copy('summary.metric_clean')} value={result.notebooks.without_errors} hint={copy('summary.metric_clean_hint')} tone="green" />
        <Metric title={copy('summary.metric_errors')} value={result.notebooks.with_errors} hint={copy('summary.metric_errors_hint')} tone="red" />
        <Metric title={copy('summary.metric_average')}
          value={basis > 0 && result.average_errors_per_notebook !== null ? number.format(result.average_errors_per_notebook) : '—'}
          hint={basis > 0 ? copy('summary.metric_average_hint') : copy('summary.no_average')} tone="gold" />
      </section>
      <p className="summary-basis">{copy('summary.basis_short')} <strong>{basis} / {result.notebooks.total}</strong></p>
      <section className="summary-top stack">
        <h2>{copy('summary.top')}</h2>
        {result.top_errors.length ? <>
          <p className="summary-hint">{copy('summary.top_basis')}</p>
          <ol className="plain stack">{result.top_errors.slice(0, 3).map((item, index) =>
            <li className="summary-error-card task-frame" key={index}>
              <span className="summary-rank" aria-hidden="true">{index + 1}</span>
              <div className="stack">
                <h3><MathText text={item.rule} /></h3>
                <p className="summary-frequency">{copy('summary.frequency', { count: item.task_ids.length })}</p>
              </div>
            </li>,
          )}</ol>
        </> : <div className={`summary-empty task-frame${hasConfirmed ? ' summary-empty--success' : ''}`}>
          <span aria-hidden="true">{hasConfirmed ? '✓' : '—'}</span>
          <p>{copy(hasConfirmed ? 'summary.no_errors' : 'summary.no_data')}</p>
        </div>}
      </section>
      {notes.length > 0 && <section className="summary-notes stack">
        <h2>{copy('summary.notes_title')}</h2>
        <div className="task-frame summary-note-list">{notes.map(item => <article className={`summary-note summary-note--${item.tone}`} key={item.label}>
          <strong className="summary-note-count">{item.count}</strong>
          <div><h3>{item.label}</h3><p className="summary-hint">{item.hint}</p></div>
        </article>)}</div>
      </section>}
    </>}
  </section>
}
