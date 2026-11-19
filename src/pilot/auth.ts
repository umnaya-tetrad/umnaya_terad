import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { PilotApi } from './api/client'
import type { Login, Session } from './api/contract'
import { ApiError, errorText } from './api/errors'
import { Intents, resetIntentStorage } from './api/intents'
import { copy } from './copy'

const lastAccount = 'smartnote:account'

export function useAuth() {
  const [session, setSession] = useState<Session | null>()
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [intents, setIntents] = useState<Intents | null>(null)
  const currentIntents = useRef<Intents | null>(null)
  const authChanges = useRef<BroadcastChannel | null>(null)

  const clear = useCallback(() => {
    currentIntents.current?.expire()
    currentIntents.current = null
    setIntents(null)
    setSession(null)
  }, [])

  const api = useMemo(() => new PilotApi(fetch, () => {
    clear()
    setError(copy('common.session_expired'))
  }), [clear])

  const accept = useCallback((next: Session) => {
    if (sessionStorage.getItem(lastAccount) !== next.user_id) {
      resetIntentStorage(sessionStorage)
      history.replaceState(null, '', location.pathname)
    }
    sessionStorage.setItem(lastAccount, next.user_id)
    const nextIntents = new Intents(api, next.user_id, sessionStorage)
    currentIntents.current = nextIntents
    setIntents(nextIntents)
    setSession(next)
  }, [api])

  useEffect(() => {
    let disposed = false
    api.getSession().then(next => {
      if (!disposed) accept(next)
    }).catch(failure => {
      if (disposed) return
      setSession(null)
      if (!(failure instanceof ApiError && failure.status === 401)) setError(errorText(failure))
    })
    return () => { disposed = true }
  }, [api, accept])

  useEffect(() => {
    if (typeof BroadcastChannel === 'undefined') return
    const channel = new BroadcastChannel('smartnote:auth')
    authChanges.current = channel
    channel.onmessage = () => {
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
      await api.login(payload)
      authChanges.current?.postMessage('changed')
      accept(await api.getSession())
    } catch (failure) {
      setError(failure instanceof ApiError && failure.status === 401 ? copy('login.invalid') : errorText(failure))
    } finally {
      setBusy(false)
    }
  }

  async function logout() {
    setBusy(true)
    setError('')
    try {
      await api.logout()
      authChanges.current?.postMessage('changed')
      clear()
      sessionStorage.removeItem(lastAccount)
      history.replaceState(null, '', location.pathname)
    } catch (failure) {
      setError(errorText(failure))
    } finally {
      setBusy(false)
    }
  }

  return { api, session, intents, busy, error, login, logout }
}
