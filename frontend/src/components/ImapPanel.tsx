import { useState, type FormEvent } from 'react'
import { api, type ImapMessage } from '../api'
import { dateLabel } from '../lib/format'

/** Optional read-only inbox. Shown only when the backend has IMAP_* settings. */
export function ImapPanel({ onImported }: { onImported: () => void }) {
  const [since, setSince] = useState('')
  const [sender, setSender] = useState('')
  const [subject, setSubject] = useState('')
  const [found, setFound] = useState<ImapMessage[] | null>(null)
  const [pick, setPick] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ tone: 'good' | 'bad'; text: string } | null>(null)

  const search = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setMsg(null)
    try {
      const r = await api.imapSearch({ since: since || undefined, sender: sender || undefined, subject: subject || undefined })
      setFound(r.messages)
      setPick(new Set())
    } catch (err) {
      setMsg({ tone: 'bad', text: err instanceof Error ? err.message : 'Search failed.' })
    } finally {
      setBusy(false)
    }
  }
  const importPicked = async () => {
    setBusy(true)
    try {
      const r = await api.imapImport([...pick])
      setMsg({ tone: 'good', text: `Imported ${r.imported.length} email(s) into the Inbox list. Tick them and press Process.` })
      onImported()
    } catch (err) {
      setMsg({ tone: 'bad', text: err instanceof Error ? err.message : 'Import failed.' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel" aria-labelledby="imap-h">
      <h3 id="imap-h">Connect inbox (optional, read-only)</h3>
      <p className="muted small">
        Searches your mailbox without marking anything read. Nothing is ever sent, moved or deleted. Only the emails you pick are copied
        into the Inbox, where they are untrusted like any other email.
      </p>
      <form className="row" onSubmit={(e) => void search(e)}>
        <label>
          Since <input className="input" type="date" value={since} onChange={(e) => setSince(e.target.value)} />
        </label>
        <label>
          From <input className="input" value={sender} onChange={(e) => setSender(e.target.value)} maxLength={100} />
        </label>
        <label>
          Subject <input className="input" value={subject} onChange={(e) => setSubject(e.target.value)} maxLength={100} />
        </label>
        <button type="submit" className="btn small" disabled={busy}>
          Search
        </button>
      </form>
      {found && (
        <>
          <ul className="flat">
            {found.length === 0 && <li className="muted">No messages found.</li>}
            {found.map((m) => (
              <li key={m.uid}>
                <label className="check">
                  <input
                    type="checkbox"
                    checked={pick.has(m.uid)}
                    onChange={() => {
                      const next = new Set(pick)
                      if (next.has(m.uid)) next.delete(m.uid)
                      else next.add(m.uid)
                      setPick(next)
                    }}
                  />
                  <span>
                    <strong>{m.from_name || m.from_email}</strong> — {m.subject} <span className="muted small">{dateLabel(m.date)}</span>
                  </span>
                </label>
              </li>
            ))}
          </ul>
          <button type="button" className="btn small primary" disabled={busy || pick.size === 0} onClick={() => void importPicked()}>
            Import selected ({pick.size})
          </button>
        </>
      )}
      {msg && <p className={`alert ${msg.tone}`}>{msg.text}</p>}
    </section>
  )
}
