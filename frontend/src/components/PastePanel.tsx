import { useState, type FormEvent } from 'react'
import { api } from '../api'

/** Process one pasted email through the same pipeline (same defenses) as the sample mailbox. */
export function PastePanel({ running, onStarted }: { running: boolean; onStarted: (runId: string) => void }) {
  const [open, setOpen] = useState(false)
  const [fromName, setFromName] = useState('')
  const [fromEmail, setFromEmail] = useState('')
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ tone: 'good' | 'bad'; text: string } | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setMsg(null)
    setBusy(true)
    try {
      const r = await api.paste({ from_name: fromName, from_email: fromEmail, subject, body })
      setMsg({ tone: 'good', text: `Saved as ${r.email_id} and processing now. Results appear in Review.` })
      setBody('')
      onStarted(r.run_id)
    } catch (err) {
      setMsg({ tone: 'bad', text: err instanceof Error ? err.message : 'Could not process the email.' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel paste" aria-labelledby="paste-h">
      <div className="panel-head">
        <div>
          <h3 id="paste-h">Paste an email</h3>
          <p className="muted small">
            Try your own text. It is treated exactly like the sample emails: untrusted, quarantined if it addresses the AI, and every
            number, date and sender is checked. Use a staff address from the roster (for example saoirse.calloway@brightfutures.example)
            or the permission defense will block any change.
          </p>
        </div>
        <button type="button" className="btn small ghost" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? 'Hide' : 'Paste an email'}
        </button>
      </div>
      {open && (
        <form className="paste-form" onSubmit={(e) => void submit(e)}>
          <label>
            From name <span className="muted small">(optional)</span>
            <input className="input" value={fromName} onChange={(e) => setFromName(e.target.value)} maxLength={80} />
          </label>
          <label>
            From email
            <input className="input" type="email" required value={fromEmail} onChange={(e) => setFromEmail(e.target.value)} maxLength={120} />
          </label>
          <label className="wide">
            Subject
            <input className="input" required value={subject} onChange={(e) => setSubject(e.target.value)} maxLength={200} />
          </label>
          <label className="wide">
            Body
            <textarea className="input" required minLength={10} rows={6} value={body} onChange={(e) => setBody(e.target.value)} maxLength={5000} />
          </label>
          <div className="wide row">
            <button type="submit" className="btn primary" disabled={busy || running}>
              {running ? 'A run is in progress…' : busy ? 'Starting…' : 'Process this email'}
            </button>
            <span className="muted small">Calls the model for this one email (unless the backend runs in stub mode).</span>
          </div>
        </form>
      )}
      {msg && (
        <p className={`alert ${msg.tone}`} role="status">
          {msg.text}
        </p>
      )}
    </section>
  )
}
