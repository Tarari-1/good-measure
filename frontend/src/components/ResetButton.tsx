import { useRef, useState } from 'react'
import { api } from '../api'

/** Restores the original tracker data after an explicit confirmation. */
export function ResetButton({ disabled, onDone }: { disabled?: boolean; onDone: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)

  const open = () => {
    setMsg(null)
    const d = ref.current
    if (d && typeof d.showModal === 'function') d.showModal()
    else d?.setAttribute('open', '')
  }
  const close = () => {
    const d = ref.current
    if (d && typeof d.close === 'function') d.close()
    else d?.removeAttribute('open')
  }

  const confirm = async () => {
    setBusy(true)
    try {
      const r = await api.reset()
      setMsg(r.checksums_match ? 'Reset complete. Original data restored and verified.' : 'Reset finished, but the checksum did not match.')
      onDone()
      close()
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Reset failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <button type="button" className="btn ghost" onClick={open} disabled={disabled} title={disabled ? 'Wait for the run to finish' : undefined}>
        Reset demo data
      </button>
      {msg && (
        <p className="sr-only" role="status">
          {msg}
        </p>
      )}
      <dialog ref={ref} aria-labelledby="reset-title" className="dialog">
        <h2 id="reset-title">Reset the demo?</h2>
        <p>
          This restores both trackers to the original data and clears all proposals, nudge drafts and the inbox selection. The
          audit trail is kept.
        </p>
        {msg && <p className="alert bad">{msg}</p>}
        <div className="row end">
          <button type="button" className="btn ghost" onClick={close} disabled={busy}>
            Cancel
          </button>
          <button type="button" className="btn danger" onClick={() => void confirm()} disabled={busy}>
            {busy ? 'Resetting…' : 'Yes, reset everything'}
          </button>
        </div>
      </dialog>
    </>
  )
}
