import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { PilotApi } from './api/client'
import type { Login, Session } from './api/contract'
import { ApiError, errorText } from './api/errors'
import { Intents, resetIntentStorage } from './api/intents'
import { copy } from './copy'
import { Telemetry } from './telemetry/client'
import { PhotoUploadQueue } from './uploads/queue'

const lastAccount = 'smartnote:account'
const cookieVersionKey = 'smartnote:cookie-version'

function cookieVersion() {
  return localStorage.getItem(cookieVersionKey)
}

function markCookieChange() {
  const version = crypto.randomUUID()
  localStorage.setItem(cookieVersionKey, version)
  return version
}

type ActiveSession = {
  session: Session
  intents: Intents
  telemetry: Telemetry
  version: string | null
  uploads?: PhotoUploadQueue
}

export function useAuth() {
  const [active, setActive] = useState<ActiveSession | null>()
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const current = useRef<ActiveSession | null>(null)
  const logoutPending = useRef(false)
  const authChanges = useRef<BroadcastChannel | null>(null)

  const clear = useCallback(() => {
    current.current?.telemetry.discard()
    current.current?.intents.expire()
    current.current?.uploads?.stop()
    current.current = null
    setActive(null)
  }, [])

  const api = useMemo(() => new PilotApi(fetch, () => {
    clear()
    setError(copy('common.session_expired'))
  }), [clear])

  const accept = useCallback((next: Session, version: string | null) => {
    current.current?.telemetry.discard()
    current.current?.intents.expire()
    current.current?.uploads?.stop()
    if (sessionStorage.getItem(lastAccount) !== next.user_id) {
      resetIntentStorage(sessionStorage)
      history.replaceState(null, '', location.pathname)
    }
    sessionStorage.setItem(lastAccount, next.user_id)
    const nextActive = {
      session: next,
      intents: new Intents(api, next.user_id, sessionStorage),
      telemetry: new Telemetry(api, undefined, () => cookieVersion() === version),
      version,
      uploads: next.role === 'teacher' ? new PhotoUploadQueue(api, next.user_id) : undefined,
    }
    current.current = nextActive
    setActive(nextActive)
  }, [api])

  useEffect(() => {
    let disposed = false
    const version = cookieVersion()
    api.getSession().then(next => {
      if (disposed) return
      if (cookieVersion() === version) accept(next, version)
      else setActive(null)
    }).catch(failure => {
      if (disposed) return
      setActive(null)
      if (!(failure instanceof ApiError && failure.status === 401)) setError(errorText(failure))
    })
    return () => { disposed = true }
  }, [api, accept])

  useEffect(() => {
    if (typeof BroadcastChannel === 'undefined') return
    const channel = new BroadcastChannel('smartnote:auth')
    authChanges.current = channel
    channel.onmessage = () => {
      if (current.current?.version === cookieVersion()) return
      clear()
      setError(copy('common.session_expired'))
    }
    return () => {
      authChanges.current = null
      channel.close()
    }
  }, [clear])

  async function login(payload: Login) {
    setBusy(true)
    setError('')
    try {
      // Fence old tabs before a login request can replace the shared cookie.
      const version = markCookieChange()
      await api.login(payload)
      authChanges.current?.postMessage('changed')
      const next = await api.getSession()
      if (cookieVersion() === version) accept(next, version)
    } catch (failure) {
      setError(failure instanceof ApiError && failure.status === 401 ? copy('login.invalid') : errorText(failure))
    } finally {
      setBusy(false)
    }
  }

  async function logout() {
    const snapshot = current.current
    if (!snapshot || logoutPending.current) return
    logoutPending.current = true
    setBusy(true)
    setError('')
    snapshot.uploads?.stop()
    try {
      await snapshot.telemetry.finish()
      if (current.current !== snapshot || cookieVersion() !== snapshot.version) {
        if (current.current === snapshot) clear()
        return
      }
      await api.logout()
      if (current.current !== snapshot || cookieVersion() !== snapshot.version) return
      markCookieChange()
      authChanges.current?.postMessage('changed')
      clear()
      sessionStorage.removeItem(lastAccount)
      history.replaceState(null, '', location.pathname)
    } catch (failure) {
      if (current.current === snapshot && cookieVersion() === snapshot.version) {
        const next = { ...snapshot, uploads: snapshot.session.role === 'teacher' ? new PhotoUploadQueue(api, snapshot.session.user_id) : undefined, telemetry: new Telemetry(api, undefined, () => cookieVersion() === snapshot.version) }
        current.current = next
        setActive(next)
        setError(errorText(failure))
      }
    } finally {
      logoutPending.current = false
      setBusy(false)
    }
  }

  return {
    api, session: active ? active.session : active, intents: active?.intents, telemetry: active?.telemetry,
    uploads: active?.uploads, busy, error, login, logout,
  }
}
