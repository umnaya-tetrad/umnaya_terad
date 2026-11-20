import { lazy, Suspense, useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { PilotApi } from './api/client'
import type { Intents } from './api/intents'
import { useAuth } from './auth'
import { copy, fixtureLabel } from './copy'
import { ChecksScreen } from './screens/ChecksScreen'
import { LoginScreen } from './screens/LoginScreen'
import { NewCheckScreen } from './screens/NewCheckScreen'
import { StaffCheckScreen, StaffChecksScreen } from './staff/StaffScreens'
import { CheckWorkspace } from './state/CheckWorkspace'
import type { Telemetry } from './telemetry/client'
import { useLifecycle } from './telemetry/useLifecycle'
import { WORKBENCH_ENABLED, readWorkbenchView, type WorkbenchView } from './dev/workbench'

const WorkbenchToolbar = WORKBENCH_ENABLED ? lazy(() => import('./dev/WorkbenchToolbar')) : undefined

function readCheck() {
  const id = new URLSearchParams(location.search).get('check')
  return id && /^[\da-f-]{36}$/i.test(id) ? id : null
}

function TeacherApp({ api, intents, telemetry }: { api: PilotApi; intents: Intents; telemetry: Telemetry }) {
  const [id, setId] = useState(readCheck)
  const [newCheck, setNewCheck] = useState(false)
  const [setup, setSetup] = useState(false)
  const [workbenchView, setWorkbenchView] = useState(() => readWorkbenchView(location.search))
  const [workbenchKey, setWorkbenchKey] = useState(0)
  const [workbenchNotebook, setWorkbenchNotebook] = useState<string>()
  useLifecycle(telemetry)

  useEffect(() => {
    const update = () => {
      setSetup(false); setNewCheck(false); setId(readCheck())
      if (WORKBENCH_ENABLED) { setWorkbenchView(readWorkbenchView(location.search)); setWorkbenchKey(value => value + 1) }
    }
    window.addEventListener('popstate', update)
    return () => window.removeEventListener('popstate', update)
  }, [])

  function navigate(checkId: string | null, createFirstNotebook = false, replace = false) {
    const url = new URL(location.href)
    if (checkId) url.searchParams.set('check', checkId)
    else url.searchParams.delete('check')
    if (WORKBENCH_ENABLED) {
      for (const key of ['ux_view', 'ux_task', 'ux_notebook']) url.searchParams.delete(key)
      setWorkbenchView(undefined)
    }
    if (replace) history.replaceState(null, '', url)
    else history.pushState(null, '', url)
    setId(checkId)
    setSetup(createFirstNotebook)
    setNewCheck(false)
  }

  function openWorkbench(checkId: string, view: WorkbenchView) {
    if (!WORKBENCH_ENABLED) return
    const url = new URL(location.href)
    url.searchParams.set('check', checkId)
    url.searchParams.set('ux_view', view.page)
    for (const [key, value] of [['ux_task', view.task], ['ux_notebook', view.notebook]] as const) {
      if (value) url.searchParams.set(key, value)
      else url.searchParams.delete(key)
    }
    history.pushState(null, '', url)
    setSetup(false); setNewCheck(false); setId(checkId); setWorkbenchView(view); setWorkbenchKey(value => value + 1)
  }

  const content = id ? <CheckWorkspace key={id + (WORKBENCH_ENABLED ? `:${workbenchKey}` : '')} id={id} api={api} intents={intents} setup={setup}
    initialWorkbenchView={workbenchView} workbenchContext={WORKBENCH_ENABLED ? setWorkbenchNotebook : undefined}
    done={() => navigate(null)} deleted={() => navigate(null, false, true)} emit={(...args) => telemetry.track(...args)} />
    : newCheck ? <NewCheckScreen intents={intents} open={checkId => navigate(checkId, true)} back={() => setNewCheck(false)} />
      : <ChecksScreen api={api} open={item => navigate(item.id)} create={() => setNewCheck(true)} />
  return <>
    {WorkbenchToolbar && <Suspense fallback={null}><WorkbenchToolbar api={api} intents={intents} currentId={id}
      currentNotebookId={workbenchNotebook} selectNotebook={setWorkbenchNotebook}
      open={openWorkbench} history={() => navigate(null)} create={() => { navigate(null); setNewCheck(true) }} /></Suspense>}
    {content}
  </>
}

function StaffApp({ api }: { api: PilotApi }) {
  const [id, setId] = useState(readCheck)
  useEffect(() => {
    const update = () => setId(readCheck())
    window.addEventListener('popstate', update)
    return () => window.removeEventListener('popstate', update)
  }, [])

  function navigate(checkId: string | null) {
    const url = new URL(location.href)
    if (checkId) url.searchParams.set('check', checkId)
    else url.searchParams.delete('check')
    history.pushState(null, '', url)
    setId(checkId)
  }

  if (id) return <StaffCheckScreen key={id} api={api} id={id} back={() => navigate(null)} />
  return <StaffChecksScreen api={api} open={item => navigate(item.id)} />
}

export function PilotApp() {
  const auth = useAuth()
  const masthead = useRef<HTMLElement>(null)
  useLayoutEffect(() => {
    const header = masthead.current
    if (!header) return
    const updateHeight = () => document.documentElement.style.setProperty('--masthead-height', `${header.getBoundingClientRect().height}px`)
    updateHeight()
    const observer = new ResizeObserver(updateHeight)
    observer.observe(header)
    return () => {
      observer.disconnect()
      document.documentElement.style.removeProperty('--masthead-height')
    }
  }, [])
  return <>
    <header className="masthead" ref={masthead}>
      <div className="masthead-inner">
        <a className="wordmark" href={location.pathname} aria-label="Умная тетрадь — Мои проверки">
          <svg className="notebook-mark" viewBox="0 0 52 52" aria-hidden="true" focusable="false">
            <path fill="#ff1f46" d="M0 0h24v52H0z" />
            <path fill="#0b579c" d="M24 0h28v52H24z" />
            <path fill="#fff" fillOpacity=".18" d="M0 0h52v2H0z" />
            <rect x="16.5" y="16" width="19" height="20" rx=".5" fill="none" stroke="#fff" strokeWidth="1.6" />
            <path fill="#fff" d="M23 16h12v20H23z" />
            <path d="M20 19v14" stroke="#fff" strokeWidth="1.3" />
            <path d="M26 23h6m-6 4h6" stroke="#0b579c" strokeWidth="1.5" />
          </svg>
          <span>УМНАЯ ТЕТРАДЬ</span>
        </a>
        {auth.session && <button className="subtle" disabled={auth.busy} onClick={() => void auth.logout()}>{copy('login.logout')}</button>}
      </div>
      {import.meta.env.VITE_PILOT_TRANSPORT === 'fixture' && <div className="fixture" title={copy('common.fixture_mode')}>{fixtureLabel}</div>}
    </header>
    <main className="container">
      {auth.session === undefined ? <p role="status">{copy('common.loading')}</p>
        : !auth.session ? <LoginScreen login={auth.login} busy={auth.busy} error={auth.error} />
        : auth.session.role === 'teacher' && auth.intents && auth.telemetry
          ? <TeacherApp key={auth.telemetry.sessionId} api={auth.api} intents={auth.intents} telemetry={auth.telemetry} />
        : auth.session.role === 'staff'
          ? <StaffApp key={auth.session.user_id} api={auth.api} />
          : <p className="sheet" role="status">{copy('common.unavailable')}</p>}
      {auth.session && auth.error && <p className="notice danger" role="alert">{auth.error}</p>}
    </main>
  </>
}
