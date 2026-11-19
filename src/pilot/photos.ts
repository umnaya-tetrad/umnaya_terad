import { useEffect, useState } from 'react'
import type { PilotApi } from './api/client'

export function usePhoto(api: PilotApi, id: string) {
  const [photo, setPhoto] = useState<{ id: string; url?: string; failed?: boolean }>()
  useEffect(() => {
    const controller = new AbortController()
    let url: string | undefined
    api.getPhoto(id, controller.signal).then(blob => {
      if (controller.signal.aborted) return
      url = URL.createObjectURL(blob)
      setPhoto({ id, url })
    }).catch(() => {
      if (!controller.signal.aborted) setPhoto({ id, failed: true })
    })
    return () => {
      controller.abort()
      if (url) URL.revokeObjectURL(url)
    }
  }, [api, id])
  return photo?.id === id ? photo : undefined
}

export function movePhoto(ids: string[], id: string, delta: -1 | 1) {
  const index = ids.indexOf(id)
  const destination = index + delta
  if (index < 0 || destination < 0 || destination >= ids.length) return ids
  const ordered = [...ids]
  ;[ordered[destination], ordered[index]] = [ordered[index], ordered[destination]]
  return ordered
}
