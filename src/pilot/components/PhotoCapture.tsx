import { useRef, useState, type ChangeEvent } from 'react'
import { copy } from '../copy'

const accepted = 'image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif'

export function PhotoCapture({ select, opened, busy, single = false }: {
  select: (files: File[]) => void; opened: () => void; busy: boolean; single?: boolean
}) {
  const camera = useRef<HTMLInputElement>(null)
  const gallery = useRef<HTMLInputElement>(null)
  const [denied, setDenied] = useState(false)

  function changed(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.currentTarget.files ?? [])
    event.currentTarget.value = ''
    if (files.length) select(files)
  }

  function openCamera() {
    opened()
    // Native capture opens the system camera or the platform's file chooser.
    camera.current?.click()
    void navigator.permissions?.query({ name: 'camera' }).then(permission => {
      setDenied(permission.state === 'denied')
    }).catch(() => {})
  }

  return <>
    <div className="button-row">
      <button className="primary" disabled={busy} onClick={openCamera}>{copy('capture.camera')}</button>
      <button disabled={busy} onClick={() => { opened(); gallery.current?.click() }}>{copy('capture.gallery')}</button>
      <input ref={camera} hidden type="file" accept="image/*" capture="environment" onChange={changed} />
      <input ref={gallery} hidden type="file" accept={accepted} multiple={!single} onChange={changed} />
    </div>
    {denied && <p role="status">{copy('capture.denied')}</p>}
  </>
}
