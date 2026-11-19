import { useEffect, useState } from 'react'
import type { PilotApi } from './api/client'
import type { Intents } from './api/intents'
import { useAuth } from './auth'
import { copy, fixtureLabel } from './copy'
import { ChecksScreen } from './screens/ChecksScreen'
import { LoginScreen } from './screens/LoginScreen'
import { NewCheckScreen } from './screens/NewCheckScreen'
import { CheckWorkspace } from './state/CheckWorkspace'
import { useLifecycle } from './telemetry/useLifecycle'

function readCheck() {
  const id = new URLSearchParams(location.search).get('check')
  return id && /^[\da-f-]{36}$/i.test(id) ? id : null
}

function TeacherApp({ api, intents }: { api: PilotApi; intents: Intents }) {
  const [id, setId] = useState(readCheck)
  const [newCheck, setNewCheck] = useState(false)
  const [setup, setSetup] = useState(false)
  const telemetry = useLifecycle(api)

  useEffect(() => {
    const update = () => { setSetup(false); setNewCheck(false); setId(readCheck()) }
    window.addEventListener('popstate', update)
    return () => window.removeEventListener('popstate', update)
  }, [])

  function navigate(checkId: string | null, createFirstNotebook = false, replace = false) {
    const url = new URL(location.href)
    if (checkId) url.searchParams.set('check', checkId)
    else url.searchParams.delete('check')
    if (replace) history.replaceState(null, '', url)
    else history.pushState(null, '', url)
    setId(checkId)
    setSetup(createFirstNotebook)
    setNewCheck(false)
  }

  if (id) return <CheckWorkspace key={id} id={id} api={api} intents={intents} setup={setup}
    done={() => navigate(null)} deleted={() => navigate(null, false, true)} emit={(...args) => telemetry.track(...args)} />
  if (newCheck) return <NewCheckScreen intents={intents} open={checkId => navigate(checkId, true)} back={() => setNewCheck(false)} />
  return <ChecksScreen api={api} open={item => navigate(item.id)} create={() => setNewCheck(true)} />
}

export function PilotApp() {
  const auth = useAuth()
  return <>
    <header className="masthead">
      <div className="masthead-inner">
        <span className="wordmark"><span aria-hidden="true" className="notebook-mark">▦</span> Умная тетрадь</span>
        {auth.session && <button className="subtle" disabled={auth.busy} onClick={() => void auth.logout()}>{copy('login.logout')}</button>}
      </div>
      {import.meta.env.VITE_PILOT_TRANSPORT === 'fixture' && <div className="fixture" title={copy('common.fixture_mode')}>{fixtureLabel}</div>}
    </header>
    <main className="container">
      {auth.session === undefined ? <p role="status">{copy('common.loading')}</p>
        : !auth.session ? <LoginScreen login={auth.login} busy={auth.busy} error={auth.error} />
        : auth.session.role === 'teacher' && auth.intents
          ? <TeacherApp key={auth.session.user_id} api={auth.api} intents={auth.intents} />
          : <p className="sheet" role="status">{copy('common.unavailable')}</p>}
      {auth.session && auth.error && <p className="notice danger" role="alert">{auth.error}</p>}
    </main>
  </>
}
