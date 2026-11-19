import { useEffect, useRef, useState } from 'react'
import { actions, type PilotApi } from '../api/client'
import type { Check, Notebook, Summary } from '../api/contract'
import { ApiError, errorText } from '../api/errors'
import type { Intents } from '../api/intents'
import { ConfirmDialog, type Confirmation } from '../components/ConfirmDialog'
import { copy } from '../copy'
import { CheckScreen } from '../screens/CheckScreen'
import { CompletionScreen } from '../screens/CompletionScreen'
import { NotebookScreen } from '../screens/NotebookScreen'
import { ReviewScreen } from '../screens/ReviewScreen'
import { SummaryScreen } from '../screens/SummaryScreen'
import type { Emit } from '../telemetry/useLifecycle'
import { reviewQueue, skippable, tasksIn, type Mutate, type Run, type TaskLocation } from './flow'
import { useCheckPolling } from './useCheckPolling'
import { WORKBENCH_ENABLED, type WorkbenchView } from '../dev/workbench'

type NotebookView = { page: 'notebook'; notebook: string; bundle?: string }
type OriginView = { page: 'check' | 'completion' } | NotebookView
type View = OriginView | { page: 'summary' } | { page: 'review'; task: string; origin: OriginView }

export function CheckWorkspace({ id, api, intents, setup, done, deleted, emit, initialWorkbenchView, workbenchContext }: {
  id: string; api: PilotApi; intents: Intents; setup: boolean; done: () => void; deleted: () => void; emit: Emit;
  initialWorkbenchView?: WorkbenchView;
  workbenchContext?: (notebookId?: string) => void;
}) {
  const { check, readError, refresh, store } = useCheckPolling(api, id)
  const [view, setView] = useState<View>()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [summaryRead, setSummaryRead] = useState<{ value: Summary; source: Check }>()
  const [confirm, setConfirm] = useState<Confirmation>()
  const pendingRevision = useRef<number | null>(null)
  const attemptedSetup = useRef(false)
  const appliedWorkbenchView = useRef(false)
  const onEvent = useRef(emit)
  onEvent.current = emit
  const screen = useRef<HTMLDivElement>(null)

  const activeView: View = view ?? { page: check?.phase === 'finalized' ? 'summary' : 'check' }
  const viewedTask = activeView.page === 'review' ? activeView.task : undefined
  const workbenchNotebook = activeView.page === 'notebook' ? activeView.notebook
    : activeView.page === 'review' ? check?.notebooks.find(notebook => tasksIn(notebook).some(entry => entry.task.task_id === activeView.task))?.id
      : undefined

  useEffect(() => {
    if (WORKBENCH_ENABLED) workbenchContext?.(workbenchNotebook)
  }, [workbenchContext, workbenchNotebook])

  useEffect(() => {
    if (!WORKBENCH_ENABLED || !initialWorkbenchView || !check || appliedWorkbenchView.current) return
    appliedWorkbenchView.current = true
    const requested = initialWorkbenchView
    if (requested.page === 'notebook') {
      const notebook = check.notebooks.find(item => item.id === requested.notebook) ?? check.notebooks[0]
      if (notebook) setView({ page: 'notebook', notebook: notebook.id })
    } else if (requested.page === 'review') {
      const entry = check.notebooks.flatMap(tasksIn).find(item => item.task.task_id === requested.task)
        ?? reviewQueue(check)[0]
      if (entry) setView({ page: 'review', task: entry.task.task_id, origin: { page: 'check' } })
    } else setView({ page: requested.page })
  }, [check, initialWorkbenchView])

  useEffect(() => {
    if (!viewedTask) return
    onEvent.current('result_opened', id, viewedTask)
    return () => onEvent.current('result_closed', id, viewedTask)
  }, [id, viewedTask])

  const focusKey = check ? [activeView.page, activeView.page === 'notebook' ? activeView.notebook : viewedTask].join(':') : ''
  useEffect(() => {
    const heading = screen.current?.querySelector('h1')
    if (heading) {
      heading.tabIndex = -1
      heading.focus({ preventScroll: true })
      window.scrollTo(0, 0)
    }
  }, [focusKey])

  const mutate: Mutate = async (action, reload = true) => {
    const expectedRevision = pendingRevision.current
    if (expectedRevision === null) throw new Error('Check mutation outside an active action')
    const result = await intents.send(action, id, expectedRevision)
    store.acknowledge(result.check_revision)
    pendingRevision.current = Math.max(expectedRevision, result.check_revision)
    if (reload) await refresh()
    return result
  }

  const run: Run = async work => {
    if (!check || pendingRevision.current !== null) return false
    // Polling updates the view, but must not silently rebase a choice that
    // started from an older revision. Follow-up writes use the last receipt.
    pendingRevision.current = check.revision
    setBusy(true)
    setError('')
    try {
      await work(async compatible => {
        const current = await refresh()
        if (!current) throw new Error('Unable to refresh the active check')
        if (!compatible(current)) throw new ApiError(409)
        pendingRevision.current = current.revision
        return current
      })
      return true
    } catch (failure) {
      setError(errorText(failure))
      await refresh()
      return false
    } finally {
      pendingRevision.current = null
      setBusy(false)
    }
  }

  function openNotebook(notebook: string, bundle?: string) {
    setView({ page: 'notebook', notebook, bundle })
  }

  async function addNotebook(createBundle = false) {
    const result = await mutate(actions.createNotebook(id), !createBundle)
    const notebook = result.entity_id
    if (!notebook) throw new Error('Missing notebook')
    openNotebook(notebook)
    if (createBundle) {
      const built = await mutate(actions.createBundle(notebook))
      openNotebook(notebook, built.entity_id ?? undefined)
    }
    return notebook
  }

  useEffect(() => {
    if (!setup || !check || check.phase === 'finalized' || attemptedSetup.current) return
    attemptedSetup.current = true
    if (check.notebooks.length) openNotebook(check.notebooks[0].id)
    else void run(async () => { await addNotebook(true) })
  })

  useEffect(() => {
    if (activeView.page !== 'summary') return
    const controller = new AbortController()
    const source = store.current
    if (source) api.getSummary(id, controller.signal).then(value => {
      if (!controller.signal.aborted && store.current === source) setSummaryRead({ value, source })
    }).catch(failure => {
      if (!controller.signal.aborted) setError(errorText(failure))
    })
    return () => controller.abort()
  }, [activeView.page, api, id, store])

  function remove(body: string, work: () => Promise<void>) {
    setConfirm({
      title: copy('delete.title'), body: <p>{body}</p>, label: copy('delete.confirm'),
      destructive: true, confirm: () => { void run(work) },
    })
  }

  if (!check) return <div className="stack">
    <button className="back" onClick={done}>{copy('common.back')}</button>
    <p className="notice" role="status">{readError || copy('common.loading')}</p>
    {readError && <button onClick={() => void refresh()}>{copy('common.refresh')}</button>}
  </div>

  function review(entry: TaskLocation, origin: OriginView) {
    setView({ page: 'review', task: entry.task.task_id, origin })
  }

  async function nextNotebook(current: Notebook) {
    const following = (store.current?.notebooks ?? []).filter(notebook => notebook.number > current.number)
      .sort((a, b) => a.number - b.number)[0]
    if (following) {
      openNotebook(following.id)
      if (!following.bundles.some(bundle => bundle.draft)) {
        const made = await mutate(actions.createBundle(following.id))
        openNotebook(following.id, made.entity_id ?? undefined)
      }
    } else {
      await addNotebook(true)
    }
  }

  function pickFirst(files: File[]) {
    onEvent.current('photo_selected', id)
    void run(async () => {
      const existing = store.current?.notebooks[0]
      const notebookId = existing?.id ?? await addNotebook()
      const reusable = existing?.bundles.find(bundle => bundle.draft && !bundle.current_input)
      const bundleId = reusable?.id ?? (await mutate(actions.createBundle(notebookId))).entity_id
      const draft = store.current?.notebooks.find(notebook => notebook.id === notebookId)
        ?.bundles.find(bundle => bundle.id === bundleId)?.draft
      openNotebook(notebookId, bundleId ?? undefined)
      if (!draft) throw new Error('Missing draft')
      for (const file of files) await mutate(actions.uploadPhoto(draft.id, file))
    })
  }

  let content
  if (activeView.page === 'summary' || (activeView.page === 'completion' && check.phase === 'finalized')) {
    content = <SummaryScreen check={check} value={summaryRead?.source === check ? summaryRead.value : check.summary}
      materials={() => setView({ page: 'check' })} busy={busy} run={run} mutate={mutate} />
  } else if (activeView.page === 'completion') {
    const first = reviewQueue(check, true)[0] ?? reviewQueue(check)[0]
    const unresolvedTask = check.notebooks.flatMap(tasksIn).find(entry => !entry.task.skipped && entry.task.analysis.result === 'not_assessed')
    const unresolvedBook = check.notebooks.find(notebook => notebook.bundles.some(skippable))
    const unsent = check.notebooks.find(notebook => notebook.bundles.some(bundle => bundle.draft?.photos.length))
    const unsentBundle = unsent?.bundles.find(bundle => bundle.draft?.photos.length)
    content = <CompletionScreen check={check} busy={busy} materials={() => setView({ page: 'check' })}
      ready={first && (() => review(first, { page: 'completion' }))}
      unresolved={unresolvedTask ? () => review(unresolvedTask, { page: 'completion' })
        : unresolvedBook && (() => openNotebook(unresolvedBook.id))}
      draft={unsent && (() => openNotebook(unsent.id, unsentBundle?.id))}
      cameraOpened={() => onEvent.current('capture_opened', id)} photo={pickFirst}
      finalized={() => void run(async () => { await mutate(actions.finalizeCheck(id)); setView({ page: 'summary' }) })} />
  } else if (activeView.page === 'notebook') {
    const notebook = check.notebooks.find(item => item.id === activeView.notebook)
    content = notebook ? <NotebookScreen key={notebook.id + (activeView.bundle ?? '')} api={api} check={check}
      notebook={notebook} initialBundle={activeView.bundle} busy={busy} run={run} mutate={mutate}
      back={() => setView({ page: 'check' })} next={() => nextNotebook(notebook)}
      review={entry => review(entry, activeView)} emit={(name, entityId) => onEvent.current(name, id, entityId)} />
      : <Unavailable back={() => setView({ page: 'check' })} />
  } else if (activeView.page === 'review') {
    const entry = check.notebooks.flatMap(tasksIn).find(item => item.task.task_id === activeView.task)
    const queue = reviewQueue(check)
    const index = queue.findIndex(item => item.task.task_id === activeView.task)
    const following = queue[index + 1]
    content = entry ? <ReviewScreen key={entry.task.analysis_id} api={api} check={check} entry={entry} busy={busy}
      run={run} mutate={mutate} back={() => setView(activeView.origin)}
      next={following && (() => review(following, activeView.origin))}
      report={entry.task.review && check.completion.unreviewed_tasks === 0 ? () => {
        if (check.phase === 'finalized') { setView({ page: 'summary' }); return }
        void run(async () => {
          if (check.phase === 'editing') await mutate(actions.beginCompletion(id))
          setView({ page: 'completion' })
        })
      } : undefined}
      replacement={bundleId => openNotebook(entry.notebook.id, bundleId)} />
      : <Unavailable back={() => setView(activeView.origin)} />
  } else {
    content = <CheckScreen check={check} busy={busy} back={done}
      add={() => void run(async () => { await addNotebook(true) })} open={notebook => openNotebook(notebook.id)}
      review={entry => review(entry, { page: 'check' })}
      finish={() => void run(async () => {
        if (check.phase === 'editing') await mutate(actions.beginCompletion(id))
        setView({ page: 'completion' })
      })}
      summary={() => setView({ page: 'summary' })}
      remove={() => remove(copy('delete.check', { title: check.title }), async () => {
        await mutate(actions.deleteCheck(id), false)
        deleted()
      })}
      removeNotebook={notebook => remove(copy('delete.notebook', { number: notebook.number }), async () => {
        await mutate(actions.deleteNotebook(notebook.id))
      })} />
  }

  return <div className="stack" ref={screen}>
    {(error || readError) && <div className="notice danger" role="alert">
      <p>{error || readError}</p><button onClick={() => void refresh().then(value => { if (value) setError('') })}>
        {copy('common.refresh')}
      </button>
    </div>}
    {content}
    {confirm && <ConfirmDialog value={confirm} close={() => setConfirm(undefined)} />}
  </div>
}

function Unavailable({ back }: { back: () => void }) {
  return <div className="sheet stack">
    <p role="status">{copy('common.unavailable')}</p><button onClick={back}>{copy('common.back')}</button>
  </div>
}
