import { useState } from 'react'
import type { Check } from '../api/contract'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { JobStatus } from '../components/JobStatus'
import { PhotoCapture } from '../components/PhotoCapture'
import { copy } from '../copy'
import { skippedCounts } from '../state/flow'

export function CompletionScreen({ check, busy, finalized, materials, ready, unresolved, draft, photo, cameraOpened }: {
  check: Check; busy: boolean; finalized: () => void; materials: () => void; ready?: () => void;
  unresolved?: () => void; draft?: () => void; photo: (files: File[]) => void; cameraOpened: () => void;
}) {
  const [confirm, setConfirm] = useState(false)
  const completion = check.completion
  const bundles = check.notebooks.flatMap(notebook => notebook.bundles)
  const empty = !completion.can_finalize && !completion.pending_jobs && !completion.unreviewed_tasks &&
    !completion.unresolved_tasks && !completion.unresolved_bundles && !completion.unsent_drafts &&
    !bundles.some(bundle => bundle.current_input && !bundle.skipped)
  return <section className="stack">
    <button className="back" onClick={materials}>{copy('common.back')}</button>
    <div className="sheet stack">
      <p className="context">{check.title}</p>
      <h1>{copy('finish.title')}</h1>
      {completion.pending_jobs > 0 && <>
        <p>{copy('finish.pending', { count: completion.pending_jobs })}</p>
        {bundles.filter(bundle => ['queued', 'running', 'retry_wait'].includes(bundle.job?.state ?? ''))
          .map(bundle => <JobStatus key={bundle.id} bundle={bundle} />)}
      </>}
      {completion.unreviewed_tasks > 0 && <p>{copy('finish.unreviewed', { count: completion.unreviewed_tasks })}</p>}
      {ready && <button onClick={ready}>{copy('check.open_ready')}</button>}
      {(completion.unresolved_tasks > 0 || completion.unresolved_bundles > 0) && <div className="notice">
        <p>{copy('finish.unresolved')}</p>
        {unresolved && <button onClick={unresolved}>{copy('finish.open_materials')}</button>}
      </div>}
      {completion.unsent_drafts > 0 && <div className="notice">
        <p>{copy('finish.drafts', { count: completion.unsent_drafts })}</p>
        {draft && <button onClick={draft}>{copy('finish.open_materials')}</button>}
      </div>}
      {empty && <>
        <p className="notice">{copy('finish.empty')}</p>
        <PhotoCapture busy={busy} opened={cameraOpened} select={photo} />
      </>}
      <button onClick={materials}>{copy('finish.open_materials')}</button>
      {completion.can_finalize && <button className="primary" disabled={busy} onClick={() => setConfirm(true)}>
        {copy(busy ? 'finish.finalizing' : 'finish.finalize')}
      </button>}
    </div>
    {confirm && completion.can_finalize && <ConfirmDialog close={() => setConfirm(false)} value={{
      title: copy('finish.confirm_title'), label: copy('finish.confirm'), confirm: finalized,
      body: <><p>{copy('finish.confirm_body')}</p><p>{copy('finish.excluded', skippedCounts(check))}</p></>,
    }} />}
  </section>
}
