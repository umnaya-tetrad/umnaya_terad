import { useCallback, useEffect, useState } from 'react'
import type { PilotApi } from '../api/client'
import type { Check } from '../api/contract'
import { ApiError, errorText } from '../api/errors'
import { CheckStore } from './checkStore'

export function useCheckPolling(api: PilotApi, checkId: string) {
  const [store] = useState(() => new CheckStore())
  const [check, setCheck] = useState<Check | null>(null)
  const [readError, setReadError] = useState('')
  const refresh = useCallback(async (signal?: AbortSignal) => {
    const sequence = store.beginRead()
    try {
      const next = await api.getCheck(checkId, signal)
      if (!signal?.aborted && store.commit(sequence, next)) {
        setCheck(next)
        setReadError('')
      }
      return store.current
    } catch (error) {
      const missing = error instanceof ApiError && (error.status === 401 || error.status === 404)
      if (!signal?.aborted && store.acceptFailure(sequence, missing)) {
        setReadError(errorText(error))
        if (missing) setCheck(null)
      }
      return null
    }
  }, [api, checkId, store])

  useEffect(() => {
    const controller = new AbortController()
    const update = () => {
      if (document.visibilityState === 'visible') void refresh(controller.signal)
    }
    void refresh(controller.signal)
    const timer = window.setInterval(update, 4000)
    document.addEventListener('visibilitychange', update)
    return () => {
      controller.abort()
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', update)
    }
  }, [refresh])

  return { check, readError, refresh, store }
}
