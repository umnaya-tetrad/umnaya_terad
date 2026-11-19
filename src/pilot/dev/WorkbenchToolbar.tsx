import { useEffect, useRef, useState } from 'react'
import { actions, type Action, type PilotApi } from '../api/client'
import type { CheckListItem, Notebook } from '../api/contract'
import { ApiError, errorText } from '../api/errors'
import type { Intents } from '../api/intents'
import {
  WORKBENCH_ENABLED, parseManifest, scenarioCheck, selectTask, workbenchAsset,
  type Manifest, type Scenario, type TaskFilter, type WorkbenchView,
} from './workbench'
import './workbench.css'

type Screen = 'scenario' | 'history' | 'new' | 'capture' | 'queue' | 'review' | 'correct' | 'error' | 'incomplete' | 'unassessed' | 'completion' | 'summary' | 'stale'
const messageFor = (failure: unknown) => failure instanceof ApiError ? errorText(failure)
  : failure instanceof Error ? failure.message : errorText(failure)

export default function WorkbenchToolbar({ api, intents, currentId, currentNotebookId, selectNotebook, open, history, create }: {
  api: PilotApi; intents: Intents; currentId: string | null;
  currentNotebookId?: string; selectNotebook: (id?: string) => void;
  open: (id: string, view: WorkbenchView) => void; history: () => void; create: () => void;
}) {
  const [expanded, setExpanded] = useState(true)
  const [catalog, setCatalog] = useState<Manifest>()
  const [checks, setChecks] = useState<CheckListItem[]>([])
  const [notebooks, setNotebooks] = useState<Notebook[]>([])
  const [scenarioId, setScenarioId] = useState('manual')
  const [photoSetId, setPhotoSetId] = useState('normal')
  const [screen, setScreen] = useState<Screen>('scenario')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const running = useRef(false)
  const scenario = catalog?.scenarios.find(value => value.id === scenarioId) ?? catalog?.scenarios[0]

  async function load(signal?: AbortSignal) {
    const response = await fetch('/ux-workbench/manifest.json', { signal, cache: 'no-store' })
    if (!response.ok) throw new Error('Каталог еще не подготовлен. Выполните seed UX-стенда.')
    const manifest = parseManifest(await response.json(), location.origin)
    const items: CheckListItem[] = []
    let cursor: string | undefined
    do {
      const page = await api.listChecks(cursor, signal)
      items.push(...page.items)
      cursor = page.next_cursor ?? undefined
    } while (cursor)
    if (!signal?.aborted) { setCatalog(manifest); setChecks(items) }
  }

  useEffect(() => {
    if (!WORKBENCH_ENABLED) return
    const controller = new AbortController()
    void load(controller.signal).catch(failure => {
      if (!controller.signal.aborted) setMessage(messageFor(failure))
    })
    return () => controller.abort()
  }, [api])

  useEffect(() => {
    if (!WORKBENCH_ENABLED || !currentId) { setNotebooks([]); return }
    const controller = new AbortController()
    api.getCheck(currentId, controller.signal).then(value => {
      if (controller.signal.aborted) return
      setNotebooks(value.notebooks)
      if (!value.notebooks.some(book => book.id === currentNotebookId)) selectNotebook(value.notebooks[0]?.id)
    }).catch(failure => { if (!controller.signal.aborted) setMessage(messageFor(failure)) })
    return () => controller.abort()
  }, [api, currentId, currentNotebookId, expanded, selectNotebook])

  async function run(work: () => Promise<void>, collapse = true) {
    if (!WORKBENCH_ENABLED || running.current) return
    running.current = true; setBusy(true); setMessage('')
    try { await work(); if (collapse) setExpanded(false) }
    catch (failure) { setMessage(messageFor(failure)) }
    finally { running.current = false; setBusy(false) }
  }

  async function write(id: string, action: Action) {
    const current = await api.getCheck(id)
    return intents.send(action, id, current.revision)
  }

  function seeded(value = scenario) {
    if (!value) throw new Error('Выберите сценарий.')
    const item = scenarioCheck(checks, value)
    if (!item) throw new Error('Сценарий еще не создан. Обновите набор после seed.')
    return item
  }

  function scenarioById(id: string) {
    const value = catalog?.scenarios.find(item => item.id === id)
    if (!value) throw new Error('Сценарий отсутствует в каталоге.')
    return value
  }

  async function notebook(id: string, requested = id === currentId ? currentNotebookId : undefined) {
    let current = await api.getCheck(id)
    if (current.phase === 'finalized') throw new Error('Состав закрыт. Создайте новую копию сценария.')
    if (!current.notebooks.length) await write(id, actions.createNotebook(id))
    current = await api.getCheck(id)
    return current.notebooks.find(book => book.id === requested) ?? current.notebooks[0]
  }

  async function addPhotos(id: string, photos: string[]) {
    const book = await notebook(id)
    let current = await api.getCheck(id)
    let bundle = current.notebooks.find(item => item.id === book.id)?.bundles.find(item => item.draft && !item.current_input)
    if (!bundle) {
      const made = await write(id, actions.createBundle(book.id))
      current = await api.getCheck(id)
      bundle = current.notebooks.find(item => item.id === book.id)?.bundles.find(item => item.id === made.entity_id)
    }
    if (!bundle?.draft) throw new Error('Не удалось открыть черновик.')
    const draftId = bundle.draft.id
    for (const path of photos) {
      const response = await fetch(workbenchAsset(path, location.origin), { cache: 'no-store' })
      if (!response.ok) throw new Error('Демо-фото недоступно.')
      const blob = await response.blob()
      const file = new File([blob], path.split('/').pop() || 'demo.png', { type: blob.type || 'image/png' })
      await write(id, actions.uploadPhoto(draftId, file))
    }
    return { book, bundleId: bundle.id, draftId }
  }

  async function fresh(value: Scenario) {
    const photos = value.photos.length ? value.photos : catalog?.photo_sets?.find(item => item.id === 'normal')?.photos
    if (!photos?.length) throw new Error('Для новой копии не подготовлены демо-фото.')
    const title = `[UX RUN ${value.id}] ${value.title.replace(/^\[UX \d+\]\s*/, '')} · ${new Date().toLocaleTimeString('ru-RU')}`
    const made = await intents.send(actions.createCheck({ title }), null, null)
    const id = made.check_id
    const added = await addPhotos(id, photos)
    await write(id, actions.submitBundle(added.bundleId, { input_version_id: added.draftId }))
    open(id, { page: 'notebook', notebook: added.book.id })
  }

  async function navigate(targetScreen: Screen = screen) {
    if (targetScreen === 'history') { history(); return }
    if (targetScreen === 'new') { create(); return }
    if (targetScreen === 'queue') { if (!scenario) throw new Error('Выберите сценарий.'); await fresh(scenario); return }
    const actualScreen = targetScreen === 'scenario' ?
      (scenario?.id === 'summary' ? 'summary' : scenario?.id === 'manual' || scenario?.id === 'retry' ? 'capture' : scenario?.id === 'unassessed' ? 'unassessed' : 'review') : targetScreen
    const target = actualScreen === 'summary' || actualScreen === 'stale' ? seeded(scenarioById('summary'))
      : actualScreen === 'unassessed' ? seeded(scenarioById('unassessed'))
        : targetScreen !== 'scenario' && ['review', 'correct', 'error', 'incomplete'].includes(actualScreen) ? seeded(scenarioById('mixed'))
          : targetScreen !== 'scenario' && actualScreen === 'capture' ? seeded(scenarioById(scenario?.id === 'retry' ? 'retry' : 'manual'))
            : seeded()
    const current = await api.getCheck(target.id)
    if (actualScreen === 'capture') {
      const book = await notebook(target.id)
      open(target.id, { page: 'notebook', notebook: book.id }); return
    }
    if (actualScreen === 'summary' || actualScreen === 'stale') {
      if (actualScreen === 'stale') {
        if (!current.title.startsWith('[UX 05] ')) throw new Error('Изменять можно только учебную сводку [UX 05].')
        const entry = selectTask(current)
        if (!entry) throw new Error('Нет разбора для изменения отзыва.')
        await write(target.id, actions.saveReview(entry.task.task_id, {
          analysis_id: entry.task.analysis_id,
          state: entry.task.review?.state === 'confirmed' ? 'system_error' : 'confirmed',
          comment: entry.task.review?.comment ?? '',
        }))
      }
      open(target.id, { page: 'summary' }); return
    }
    if (actualScreen === 'completion') {
      if (current.phase === 'editing') await write(target.id, actions.beginCompletion(target.id))
      open(target.id, { page: current.phase === 'finalized' ? 'summary' : 'completion' }); return
    }
    const filter: TaskFilter = ['correct', 'error', 'incomplete', 'unassessed'].includes(actualScreen) ? actualScreen as TaskFilter : 'any'
    const entry = selectTask(current, filter)
    if (!entry) throw new Error('Такого готового разбора здесь нет. Выберите подготовленный сценарий или дождитесь обработки.')
    open(target.id, { page: 'review', task: entry.task.task_id })
  }

  if (!WORKBENCH_ENABLED) return null
  return <section className="ux-toolbar" aria-label="Панель UX-стенда">
    <div className="ux-toolbar-heading"><strong>UX-стенд · только моки</strong>
      <button aria-expanded={expanded} onClick={() => setExpanded(value => !value)}>{expanded ? 'Скрыть панель' : 'Показать панель'}</button>
    </div>
    {expanded && <div className="stack">
      <p className="help">Это живой интерфейс с сохранением данных. ИИ не вызывается и загруженная математика не распознается.</p>
      <div className="button-row" aria-label="Быстрые переходы">
        {([['history', 'История'], ['new', 'Новая'], ['capture', 'Съемка'], ['review', 'Разбор'], ['summary', 'Сводка']] as const).map(([target, label]) =>
          <button key={target} disabled={busy || !catalog} onClick={() => void run(() => navigate(target))}>{label}</button>,
        )}
      </div>
      <label>Сценарий<select disabled={busy} value={scenario?.id ?? ''} onChange={event => setScenarioId(event.target.value)}>
        {catalog?.scenarios.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}
      </select></label>
      {scenario && <p className="help">{scenario.description}</p>}
      <label>Экран<select disabled={busy} value={screen} onChange={event => setScreen(event.target.value as Screen)}>
        <option value="scenario">Выбранный сценарий</option><option value="history">История проверок</option>
        <option value="new">Новая проверка</option><option value="capture">Съемка / тетрадь</option>
        <option value="queue">Очередь / обработка — новая копия</option><option value="review">Разбор и отзыв учителя</option>
        <option value="correct">Верное решение</option><option value="error">Первая ошибка</option>
        <option value="incomplete">Решение не закончено</option><option value="unassessed">Не удалось проверить задачу</option>
        <option value="completion">Просмотр перед завершением</option><option value="summary">Готовая сводка</option>
        <option value="stale">Изменить отзыв → устаревшая сводка</option>
      </select></label>
      <div className="button-row">
        <button className="primary" disabled={busy || !catalog} onClick={() => void run(() => navigate())}>Открыть экран</button>
        <button disabled={busy} onClick={() => { create(); setExpanded(false) }}>Пройти с начала</button>
        <button disabled={busy || !scenario} onClick={() => void run(async () => { if (scenario) await fresh(scenario) })}>Новая копия → обработка</button>
      </div>
      <label>Демо-фото<select disabled={busy} value={photoSetId} onChange={event => setPhotoSetId(event.target.value)}>
        {(catalog?.photo_sets ?? catalog?.scenarios ?? []).map(item => <option key={item.id} value={item.id}>{item.title}</option>)}
      </select></label>
      <label>Тетрадь для демо-фото<select disabled={busy || !notebooks.length} value={currentNotebookId ?? ''}
        onChange={event => selectNotebook(event.target.value)}>
        {!notebooks.length && <option value="">Сначала откройте съемку</option>}
        {notebooks.map(book => <option key={book.id} value={book.id}>Тетрадь {book.number}</option>)}
      </select></label>
      <div className="button-row">
        <button disabled={busy || !currentId || !catalog || !currentNotebookId} onClick={() => void run(async () => {
          if (!currentId || !catalog) return
          const sets = catalog.photo_sets ?? catalog.scenarios
          const set = sets.find(item => item.id === photoSetId) ?? sets[0]
          const added = await addPhotos(currentId, set.photos)
          open(currentId, { page: 'notebook', notebook: added.book.id })
        })}>Добавить демо-фото · тетрадь {notebooks.find(book => book.id === currentNotebookId)?.number ?? '–'}</button>
        <button disabled={busy} onClick={() => void run(() => load(), false)}>Обновить набор</button>
      </div>
      <p className="help">Новая копия не удаляет старые проверки. Сохраните комментарий перед переходом кнопками панели.</p>
    </div>}
    {busy && <p role="status">Подготавливаем учебный экран…</p>}
    {message && <p className="notice danger" role="alert">{message}</p>}
  </section>
}
