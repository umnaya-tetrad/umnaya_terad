import type { Check, Notebook } from '../api/contract'
import { bundleStatus } from '../components/JobStatus'
import { copy } from '../copy'
import { notebookPhotoCount, reviewQueue, type TaskLocation } from '../state/flow'

export function CheckScreen({ check, busy, back, add, open, review, finish, summary, remove, removeNotebook, localCounts = {} }: {
  localCounts?: Record<string, number>; check: Check; busy: boolean; back: () => void; add: () => void; open: (notebook: Notebook) => void;
  review: (task: TaskLocation) => void; finish: () => void; summary: () => void;
  remove: () => void; removeNotebook: (notebook: Notebook) => void
}) {
  const canEdit = check.phase !== 'finalized'
  const ready = reviewQueue(check)
  return <section className="stack">
    <button className="back" onClick={back}>{copy('common.back')}</button>
    <div className="sheet">
      <h1>{check.title}</h1>
      <p className="phase">{copy(`check.phase_${check.phase}`)}</p>
      {!!ready.length && <div className="button-row">
        <button className="primary" onClick={() => review(ready.find(entry => !entry.task.review) ?? ready[0])}>
          {copy('check.open_ready')}
        </button>
        <span>{copy('check.ready_count', { count: ready.length })}</span>
      </div>}
    </div>
    <div className="section-header">
      <h2>{copy('check.notebooks')}</h2>
      {canEdit && <button disabled={busy} onClick={add}>{copy('check.add_notebook')}</button>}
    </div>
    <ul className="plain stack">
      {check.notebooks.map(notebook => {
        const localCount = localCounts[notebook.id] ?? 0
        const photoCount = notebookPhotoCount(notebook) + localCount
        const statuses = [...new Set(notebook.bundles.map(bundleStatus).filter(label => label !== undefined))]
        return <li key={notebook.id} className={`sheet notebook-row notebook-row--${photoCount ? 'uploaded' : 'empty'}`}>
          <button className="row-link" onClick={() => open(notebook)}>
            <strong>{copy('check.notebook', { number: notebook.number })}</strong>
            <span>{copy(photoCount ? 'notebook.photo_count' : 'notebook.no_photos', { count: photoCount })}</span>
            {localCount > 0 && <span>Ожидает загрузки фото: {localCount}</span>}
            {statuses.map(status => <span key={status}>{copy(status)}</span>)}
          </button>
          {canEdit && <button className="subtle" disabled={busy} onClick={() => removeNotebook(notebook)}>
            {copy('notebook.delete')}
          </button>}
        </li>
      })}
    </ul>
    <div className="button-row">
      {canEdit ? <button className="primary" disabled={busy} onClick={finish}>{copy('check.finish')}</button>
        : <button className="primary" onClick={summary}>{copy('check.summary')}</button>}
      <button className="subtle danger" disabled={busy} onClick={remove}>{copy('check.delete')}</button>
    </div>
  </section>
}
