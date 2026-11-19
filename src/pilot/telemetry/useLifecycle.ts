import { useEffect } from 'react'
import type { Event } from '../api/contract'
import type { Telemetry } from './client'

export function useLifecycle(telemetry: Telemetry) {
  useEffect(() => {
    let visible = document.visibilityState === 'visible'
    telemetry.track(visible ? 'app_visible' : 'app_hidden')
    function setVisibility(next: boolean) {
      if (next === visible) return
      visible = next
      telemetry.track(visible ? 'app_visible' : 'app_hidden')
      void telemetry.flush(!visible)
    }
    const visibility = () => setVisibility(document.visibilityState === 'visible')
    const exit = () => { setVisibility(false); void telemetry.flush(true) }
    const timer = window.setInterval(() => {
      if (visible) telemetry.track('heartbeat')
      void telemetry.flush()
    }, 30_000)
    document.addEventListener('visibilitychange', visibility)
    window.addEventListener('pagehide', exit)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', visibility)
      window.removeEventListener('pagehide', exit)
    }
  }, [telemetry])
}

export type Emit = (name: Event['name'], checkId?: string, entityId?: string) => void
