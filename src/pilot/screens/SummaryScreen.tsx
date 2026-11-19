import { actions } from '../api/client'
import type { Check, Summary } from '../api/contract'
import { summaryStatus } from '../components/JobStatus'
import { copy } from '../copy'
import { skippedCounts, type Mutate, type Run } from '../state/flow'

const number = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 4 })

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
  return <section className="stack">
    <button className="back" onClick={materials}>{copy('common.back')}</button>
    <div className="sheet stack">
      <p className="context">{check.title}</p>
      <h1>{copy('summary.title')}</h1>
      <p>{copy('summary.locked')}</p>
      {status && <p className="notice" role="status">{copy(status)}</p>}
      {value.stale && <p className="notice" role="status">{copy('summary.stale')}</p>}
      {value.can_refresh && <button className="primary" disabled={busy} onClick={() => void run(async () => {
        await mutate(actions.refreshSummary(check.id))
      })}>{copy('summary.refresh')}</button>}
      {value.can_retry && !value.stale && <button disabled={busy} onClick={() => void run(async () => {
        await mutate(actions.retrySummary(check.id))
      })}>{copy('summary.retry')}</button>}
      <button onClick={materials}>{copy('summary.materials')}</button>
    </div>
    {result && <>
      <section className="sheet stack">
        <p><strong>{copy('summary.total', { count: result.notebooks.total })}</strong></p>
        <ul className="plain metrics">
          <li>{copy('summary.with_errors', { count: result.notebooks.with_errors })}</li>
          <li>{copy('summary.without_errors', { count: result.notebooks.without_errors })}</li>
          <li>{copy('summary.basis', { count: basis })}</li>
          <li>{basis && result.average_errors_per_notebook !== null
            ? copy('summary.average', { value: number.format(result.average_errors_per_notebook) })
            : copy('summary.no_average')}</li>
          <li>{copy('summary.partial', { count: result.notebooks.partial })}</li>
          <li>{copy('summary.empty', { count: result.notebooks.empty })}</li>
          <li>{copy('summary.incomplete', { count: result.incomplete_tasks })}</li>
          <li>{copy('summary.disputed', { count: result.disputed_tasks })}</li>
          <li>{copy('result.no_result')} · {number.format(result.unassessed_tasks)}</li>
        </ul>
      </section>
      <section className="sheet stack">
        <h2>{copy('summary.top')}</h2>
        {result.top_errors.length ? <>
          <p className="help">{copy('summary.top_basis')}</p>
          <ol className="stack">{result.top_errors.slice(0, 3).map((item, index) =>
            <li key={index}><strong>{item.rule}</strong><p>{copy('summary.frequency', { count: item.task_ids.length })}</p></li>,
          )}</ol>
        </> : <p>{copy(hasConfirmed ? 'summary.no_errors' : 'summary.no_data')}</p>}
      </section>
    </>}
    <div className="sheet metrics">
      <p>{copy('summary.skipped_tasks', { count: skipped.skipped_tasks })}</p>
      <p>{copy('summary.skipped_bundles', { count: skipped.skipped_bundles })}</p>
    </div>
  </section>
}
