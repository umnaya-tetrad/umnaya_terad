import { useEffect, useRef, type ReactNode } from 'react'
import { copy } from '../copy'

export type Confirmation = { title: string; body: ReactNode; label: string; confirm: () => void; destructive?: boolean }

export function ConfirmDialog({ value, close }: { value: Confirmation; close: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const element = dialog.current!
    const trigger = document.activeElement
    element.showModal()
    return () => {
      element.close()
      if (trigger instanceof HTMLElement && trigger.isConnected) trigger.focus()
    }
  }, [])

  return (
    <dialog ref={dialog} onCancel={event => { event.preventDefault(); close() }} aria-labelledby="confirm-title">
      <h2 id="confirm-title">{value.title}</h2>
      <div>{value.body}</div>
      <div className="dialog-buttons">
        <button autoFocus onClick={close}>{copy('common.cancel')}</button>
        <button className={value.destructive ? 'danger' : 'primary'} onClick={() => { close(); value.confirm() }}>
          {value.label}
        </button>
      </div>
    </dialog>
  )
}
