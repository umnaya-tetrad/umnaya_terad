import { useEffect, useRef, useState } from 'react'
import type { PilotApi } from '../api/client'
import { copy } from '../copy'
import { usePhoto } from '../photos'

export function PhotoViewer({ api, id, label, close }: { api: PilotApi; id: string; label: string; close: () => void }) {
  const [zoom, setZoom] = useState(false)
  const photo = usePhoto(api, id)
  const dialog = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const trigger = document.activeElement
    const element = dialog.current!
    element.showModal()
    return () => {
      element.close()
      if (trigger instanceof HTMLElement && trigger.isConnected) trigger.focus()
    }
  }, [])

  return (
    <dialog ref={dialog} className="photo-viewer" aria-label={label}
      onCancel={event => { event.preventDefault(); close() }}>
      <div className="button-row">
        <button autoFocus onClick={close}>{copy('common.close')}</button>
        {photo?.url && <button aria-pressed={zoom} onClick={() => setZoom(value => !value)}>{copy('result.enlarge')}</button>}
      </div>
      <div className="photo-viewport" tabIndex={0}>
        {photo?.url && <img className={zoom ? 'zoomed' : ''} src={photo.url} alt={label} />}
        {photo?.failed && <p role="alert">{copy('common.unavailable')}</p>}
        {!photo && <p role="status">{copy('common.loading')}</p>}
      </div>
    </dialog>
  )
}
