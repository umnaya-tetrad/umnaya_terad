import { useState } from 'react'
import { actions, type PilotApi } from '../api/client'
import type { Bundle, Check, Notebook } from '../api/contract'
import { ConfirmDialog, type Confirmation } from '../components/ConfirmDialog'
import { JobStatus } from '../components/JobStatus'
import { PhotoCapture } from '../components/PhotoCapture'
import { PhotoThumbnail } from '../components/PhotoStrip'
import { PhotoViewer } from '../components/PhotoViewer'
import { copy } from '../copy'
import { movePhoto } from '../photos'
import { notebookPhotoCount, skippable, tasksIn, type Mutate, type Run, type TaskLocation } from '../state/flow'
import type { Event } from '../api/contract'

export function NotebookScreen({ api, check, notebook, initialBundle, busy, run, mutate, back, next, review, emit }: {
  api: PilotApi; check: Check; notebook: Notebook; initialBundle?: string; busy: boolean; run: Run; mutate: Mutate;
  back: () => void; next: () => Promise<void>; review: (entry: TaskLocation) => void;
  emit: (name: Event['name'], entityId?: string) => void
}) {
  const [bundleId, setBundleId] = useState(initialBundle)
  const [replace, setReplace] = useState<string>()
  const [viewer, setViewer] = useState<{ id: string; label: string }>()
  const [confirmation, setConfirmation] = useState<Confirmation>()
  const [uploading, setUploading] = useState(false)
  const [accepted, setAccepted] = useState(false)
  const [unsent, setUnsent] = useState(false)
  const draftBundle = notebook.bundles.find(bundle => bundle.id === bundleId && bundle.draft)
    ?? notebook.bundles.find(bundle => bundle.draft?.photos.length && !bundle.current_input)
    ?? notebook.bundles.find(bundle => bundle.draft && !bundle.current_input)
    ?? notebook.bundles.find(bundle => bundle.draft?.photos.length)
  const draft = draftBundle?.draft
  const canEdit = check.phase !== 'finalized'
  const photos = draft?.photos ?? []
  const photoIds = photos.map(photo => photo.id)

  function sameDraft(current: Check) {
    const active = current.notebooks.find(item => item.id === notebook.id)
    if (!active || current.phase === 'finalized') return false
    if (!draft) return !active.bundles.some(bundle => bundle.draft && !bundle.current_input)
    const actual = active.bundles.find(bundle => bundle.id === draftBundle?.id)?.draft
    return actual?.id === draft.id && actual.photos.length === photoIds.length &&
      actual.photos.every((photo, index) => photo.id === photoIds[index])
  }

  function select(files: File[]) {
    emit('photo_selected', draftBundle?.id)
    void run(async refreshRevision => {
      setUploading(true)
      setAccepted(false)
      try {
        await refreshRevision(sameDraft)
        let draftId = draft?.id
        if (!draftId) {
          const made = await mutate(actions.createBundle(notebook.id), false)
          if (!made.entity_id) throw new Error('Missing bundle')
          setBundleId(made.entity_id)
          // createBundle returns the Bundle id; its draft comes from getCheck.
          const created = (current: Check) => current.notebooks.find(item => item.id === notebook.id)
            ?.bundles.find(item => item.id === made.entity_id)?.draft
          const current = await refreshRevision(value => value.phase !== 'finalized' && created(value)?.photos.length === 0)
          draftId = created(current)?.id
          if (!draftId) throw new Error('Missing draft')
        }
        if (replace) {
          const { entity_id: newPhoto } = await mutate(actions.uploadPhoto(draftId, files[0]), false)
          if (!newPhoto) throw new Error('Missing photo')
          await mutate(actions.deleteDraftPhoto(draftId, replace), false)
          await mutate(actions.reorderPhotos(draftId, { photo_ids: photoIds.map(id => id === replace ? newPhoto : id) }))
        } else {
          for (const [index, file] of files.entries()) {
            await mutate(actions.uploadPhoto(draftId, file), index === files.length - 1)
          }
        }
      } finally {
        setReplace(undefined)
        setUploading(false)
      }
    })
  }

  function confirmDelete(body: string, work: () => Promise<void>) {
    setConfirmation({
      title: copy('delete.title'), body: <p>{body}</p>, label: copy('delete.confirm'),
      destructive: true, confirm: () => { void run(work) },
    })
  }

  function discard() {
    if (!draft) return
    confirmDelete(copy('delete.draft'), async () => {
      await mutate(actions.discardDraft(draft.id))
      setBundleId(undefined)
      setUnsent(false)
    })
  }

  function submit(goNext: boolean) {
    if (!draft || !draftBundle || !photos.length || uploading) return
    void run(async refreshRevision => {
      await refreshRevision(sameDraft)
      await mutate(actions.submitBundle(draftBundle.id, { input_version_id: draft.id }), false)
      setAccepted(true)
      setUnsent(false)
      setBundleId(undefined)
      const current = await refreshRevision(value => value.phase !== 'finalized' &&
        !!value.notebooks.find(item => item.id === notebook.id)?.bundles.some(bundle =>
          bundle.id === draftBundle.id && bundle.current_input?.id === draft.id && !bundle.skipped,
        ))
      if (goNext) {
        await next()
      } else {
        if (current.notebooks.find(item => item.id === notebook.id)?.bundles.some(bundle => bundle.draft && !bundle.current_input)) return
        const made = await mutate(actions.createBundle(notebook.id))
        if (made.entity_id) setBundleId(made.entity_id)
      }
    })
  }

  function goBack() {
    if (photos.length) {
      setUnsent(true)
      return
    }
    back()
  }

  function retry(bundle: Bundle) {
    const input = bundle.current_input
    if (!input) return
    setConfirmation({
      title: copy('replace.title'), body: <p>{copy('replace.body')}</p>, label: copy('job.retry'),
      confirm: () => { void run(async () => { await mutate(actions.retryBundle(bundle.id, { input_version_id: input.id })) }) },
    })
  }

  function changePhotos(bundle: Bundle) {
    if (bundle.draft) {
      setBundleId(bundle.id)
      return
    }
    if (!bundle.current_input) return
    const current = bundle.current_input
    setConfirmation({
      title: copy('replace.title'), body: <p>{copy('replace.body')}</p>, label: copy('replace.confirm'),
      confirm: () => { void run(async () => {
        await mutate(actions.createInputVersion(bundle.id, { photo_ids: current.photos.map(photo => photo.id) }))
        setBundleId(bundle.id)
      }) },
    })
  }

  const tasks = tasksIn(notebook).sort((a, b) =>
    Number(a.task.analysis.result === 'not_assessed') - Number(b.task.analysis.result === 'not_assessed'),
  )
  const taskGroups = [
    { title: 'notebook.unreviewed', entries: tasks.filter(entry => !entry.task.review) },
    { title: 'notebook.reviewed', entries: tasks.filter(entry => !!entry.task.review) },
  ] as const
  return <section className="stack">
    <button className="back" disabled={busy} onClick={goBack}>{copy('common.back')}</button>
    <header className="sheet">
      <p className="context">{check.title}</p>
      <h1>{copy('check.notebook', { number: notebook.number })}</h1>
    </header>
    {accepted && <p className="notice success" role="status">{copy('capture.accepted')}</p>}
    {taskGroups.filter(group => group.entries.length > 0).map(group => <section className="stack" key={group.title}>
      <h2>{copy(group.title)}</h2>
      <ul className="plain stack">{group.entries.map(entry => {
        const state = entry.task.review?.state
        return <li key={entry.task.task_id}>
          <button className={`row-card task-review-card task-review-card--${state ?? 'unreviewed'}`} onClick={() => review(entry)}>
            <span className="task-review-heading">
              <strong>{copy('check.task', { number: entry.number })}</strong>
              {state && <span className="task-review-badge">
                <span aria-hidden="true">{state === 'confirmed' ? '✓' : '✕'}</span>
                {copy(state === 'confirmed' ? 'notebook.confirmed' : 'notebook.system_error')}
              </span>}
            </span>
            <span>{entry.task.skipped ? copy('task.skipped') : entry.task.analysis.locator}</span>
          </button>
        </li>
      })}</ul>
    </section>)}
    {canEdit && <div className="sheet stack">
      {notebook.bundles.filter(bundle => bundle.id !== draftBundle?.id && bundle.draft?.photos.length).map(bundle =>
        <button key={bundle.id} disabled={busy} onClick={() => { setReplace(undefined); setBundleId(bundle.id) }}>
          {copy('capture.preview')} · {bundle.draft?.photos.length}
        </button>,
      )}
      {!photos.length && <p>{copy('notebook.empty')}</p>}
      {!photos.length && <p className="help">{copy('capture.hint')}</p>}
      {!!photos.length && <h2>{copy('capture.preview')}</h2>}
      {!!photos.length && <ol className="photo-strip plain">{photos.map((photo, index) => {
        const label = copy('capture.photo', { number: index + 1, total: photos.length })
        return <li key={photo.id} className="photo-tile stack">
          <PhotoThumbnail api={api} photo={photo} label={label} open={() => setViewer({ id: photo.id, label })} />
          <div className="button-row compact">
            {([-1, 1] as const).map(delta => <button key={delta} disabled={busy || index + delta < 0 || index + delta >= photos.length}
              aria-label={label + (delta < 0 ? ' ↑' : ' ↓')} onClick={() => {
                if (draft) void run(async () => {
                  await mutate(actions.reorderPhotos(draft.id, { photo_ids: movePhoto(photoIds, photo.id, delta) }))
                })
              }}>{delta < 0 ? '↑' : '↓'}</button>)}
          </div>
          <button disabled={busy} aria-pressed={replace === photo.id} onClick={() => setReplace(photo.id)}>{copy('capture.replace')}</button>
          <button className="danger" disabled={busy} onClick={() => {
            if (draft) confirmDelete(copy('delete.photo', { number: index + 1 }), async () => {
              await mutate(actions.deleteDraftPhoto(draft.id, photo.id))
            })
          }}>{copy('capture.remove')}</button>
        </li>
      })}</ol>}
      {replace && <button disabled={busy} onClick={() => setReplace(undefined)}>{copy('common.cancel')}</button>}
      {!!photos.length && !replace && <h3>{copy('capture.add')}</h3>}
      <PhotoCapture select={select} opened={() => emit('capture_opened', draftBundle?.id)} busy={busy} single={!!replace} />
      {uploading && <p role="status">{copy('capture.uploading')}</p>}
      {unsent && !!photos.length && <p className="notice" role="alert">{copy('capture.unsent')}</p>}
      {photos.length ? <div className="stack">
        <button className="primary" disabled={busy} onClick={() => submit(false)}>{copy('capture.submit_stay')}</button>
        <button disabled={busy} onClick={() => submit(true)}>{copy('capture.submit_next')}</button>
        <button className="subtle danger" disabled={busy} onClick={discard}>{copy('capture.discard')}</button>
      </div> : notebookPhotoCount(notebook) > 0 && <button disabled={busy} onClick={() => void run(next)}>{copy('notebook.next')}</button>}
    </div>}
    {notebook.bundles.filter(bundle => bundle.current_input).map(bundle => <div className="stack" key={bundle.id}>
      <JobStatus bundle={bundle} />
      {!bundle.tasks.length && bundle.current_input && <ul className="photo-strip plain">
        {bundle.current_input.photos.map((photo, index, all) => {
          const label = copy('capture.photo', { number: index + 1, total: all.length })
          return <li key={photo.id}>
            <PhotoThumbnail api={api} photo={photo} label={label} open={() => setViewer({ id: photo.id, label })} />
          </li>
        })}
      </ul>}
      {canEdit && (bundle.job?.can_retry || bundle.skipped || skippable(bundle) || bundle.draft) && <div className="button-row">
        {bundle.job?.can_retry && <button disabled={busy} onClick={() => retry(bundle)}>{copy('job.retry')}</button>}
        {(bundle.skipped || skippable(bundle) || bundle.draft) && <button disabled={busy} onClick={() => changePhotos(bundle)}>{copy('result.change_photos')}</button>}
        {skippable(bundle) && <button disabled={busy} onClick={() => void run(async () => {
          if (bundle.current_input) await mutate(actions.skipBundle(bundle.id, { input_version_id: bundle.current_input.id }))
        })}>{copy('job.skip')}</button>}
      </div>}
    </div>)}
    {viewer && <PhotoViewer api={api} {...viewer} close={() => setViewer(undefined)} />}
    {confirmation && <ConfirmDialog value={confirmation} close={() => setConfirmation(undefined)} />}
  </section>
}
