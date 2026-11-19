import { useState } from 'react'
import { actions, type PilotApi } from '../api/client'
import type { Check } from '../api/contract'
import { ConfirmDialog, type Confirmation } from '../components/ConfirmDialog'
import { PhotoThumbnail } from '../components/PhotoStrip'
import { PhotoViewer } from '../components/PhotoViewer'
import { ReviewControls } from '../components/ReviewControls'
import { TaskCard } from '../components/TaskCard'
import { copy } from '../copy'
import { type Mutate, type Run, type TaskLocation } from '../state/flow'

export function ReviewScreen({ api, check, entry, busy, run, mutate, back, next, report, replacement }: {
  api: PilotApi; check: Check; entry: TaskLocation; busy: boolean; run: Run; mutate: Mutate;
  back: () => void; next?: () => void; report?: () => void; replacement: (bundleId: string) => void
}) {
  const { notebook, bundle, task, number } = entry
  const [photo, setPhoto] = useState<{ id: string; label: string }>()
  const [confirm, setConfirm] = useState<Confirmation>()
  const editable = check.phase !== 'finalized'
  const input = bundle.current_input
  const photos = input?.photos ?? []
  const eligible = !task.skipped && task.analysis.result !== 'not_assessed'

  return <section className="stack">
    <button className="back" onClick={back}>{copy('common.back')}</button>
    <div className="sheet">
      <p className="context">{check.title} · {copy('check.notebook', { number: notebook.number })}</p>
      <h1>{copy('result.title')} · {copy('check.task', { number })}</h1>
    </div>
    {task.analysis.photo_indices.length > 0 && <ul className="photo-strip plain">{task.analysis.photo_indices.map(index => {
      const item = photos[index - 1]
      const label = copy('capture.photo', { number: index, total: photos.length })
      return item && <li key={item.id}><PhotoThumbnail api={api} photo={item} label={label} open={() => setPhoto({ id: item.id, label })} /></li>
    })}</ul>}
    <TaskCard value={task.analysis} photoCount={photos.length} />
    {task.skipped && <p className="notice">{copy('task.skipped')}</p>}
    {eligible && <ReviewControls key={task.analysis_id} busy={busy} review={task.review} save={(state, comment) => run(async () => {
      await mutate(actions.saveReview(task.task_id, { analysis_id: task.analysis_id, state, comment }))
    })} />}
    {next && <button className={report ? undefined : 'primary'} onClick={next}>{copy('review.next')}</button>}
    {report && <button className="primary" disabled={busy} onClick={report}>{copy('review.report')}</button>}
    {editable && <div className="button-row">
      {!eligible && !task.skipped && <button disabled={busy} onClick={() => void run(async () => {
        await mutate(actions.skipTask(task.task_id, { analysis_id: task.analysis_id }))
      })}>{copy('task.skip')}</button>}
      {input && <button disabled={busy} onClick={() => setConfirm({
        title: copy('replace.title'), body: <p>{copy('replace.body')}</p>, label: copy('replace.confirm'),
        confirm: () => { void run(async () => {
          if (!bundle.draft) await mutate(actions.createInputVersion(bundle.id, { photo_ids: photos.map(photo => photo.id) }))
          replacement(bundle.id)
        }) },
      })}>{copy('result.change_photos')}</button>}
      {input && bundle.job?.can_retry && <button disabled={busy} onClick={() => setConfirm({
        title: copy('replace.title'), body: <p>{copy('replace.body')}</p>, label: copy('job.retry'),
        confirm: () => { void run(async () => {
          await mutate(actions.retryBundle(bundle.id, { input_version_id: input.id }))
          back()
        }) },
      })}>{copy('job.retry')}</button>}
      <button className="danger" disabled={busy} onClick={() => setConfirm({
        title: copy('delete.title'), body: <p>{copy('delete.task', { number, notebook: notebook.number })}</p>,
        label: copy('delete.confirm'), destructive: true,
        confirm: () => { void run(async () => { await mutate(actions.deleteTask(task.task_id)); (next ?? back)() }) },
      })}>{copy('task.delete')}</button>
    </div>}
    {photo && <PhotoViewer api={api} {...photo} close={() => setPhoto(undefined)} />}
    {confirm && <ConfirmDialog value={confirm} close={() => setConfirm(undefined)} />}
  </section>
}
