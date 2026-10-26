import { useEffect, useMemo, useState } from 'react'
import { api, type EmailFull, type EmailSummary } from '../api'
import { ImapPanel } from '../components/ImapPanel'
import { PastePanel } from '../components/PastePanel'
import { dateLabel } from '../lib/format'
import { useLoad } from '../lib/usePoll'

interface Props {
  version: number
  running: boolean
  maxPerRun: number
  imapConfigured?: boolean
  onStarted: (runId: string) => void
}

export function Inbox({ version, running, maxPerRun, imapConfigured = false, onStarted }: Props) {
  const list = useLoad(api.emails, [version])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [openId, setOpenId] = useState<string | null>(null)
  const [open, setOpen] = useState<EmailFull | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)

  useEffect(() => {
    if (list.data) setSelected(new Set(list.data.selected))
  }, [list.data])

  useEffect(() => {
    if (!openId) return setOpen(null)
    let alive = true
    api
      .email(openId)
      .then((e) => alive && setOpen(e))
      .catch(() => alive && setOpen(null))
    return () => {
      alive = false
    }
  }, [openId])

  const emails: EmailSummary[] = useMemo(() => list.data?.emails ?? [], [list.data])

  const update = (next: Set<string>) => {
    setSelected(next)
    void api.saveSelection([...next]).catch(() => undefined)
  }
  const toggle = (id: string) => {
    const next = new Set(selected)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    update(next)
  }

  const start = async () => {
    setError(null)
    setStarting(true)
    try {
      const r = await api.startRun([...selected])
      onStarted(r.run_id)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start the run.')
    } finally {
      setStarting(false)
    }
  }

  const tooMany = selected.size > maxPerRun
  const allOn = emails.length > 0 && emails.every((e) => selected.has(e.id))

  return (
    <div className="stack">
    <div className="split">
      <section className="panel" aria-labelledby="inbox-h">
        <div className="panel-head">
          <div>
            <h2 id="inbox-h">Inbox</h2>
            <p className="muted">
              Staff emails from the sample mailbox. Tick the ones to turn into proposed tracker updates. Nothing changes until you
              approve it in Review.
            </p>
          </div>
        </div>
        <div className="toolbar">
          <label className="check">
            <input
              type="checkbox"
              checked={allOn}
              onChange={() => update(allOn ? new Set() : new Set(emails.map((e) => e.id)))}
              aria-label={allOn ? 'Clear selection' : 'Select all emails'}
            />
            <span>{allOn ? 'Clear all' : 'Select all'}</span>
          </label>
          <span className="muted" aria-live="polite">
            {selected.size} of {emails.length} selected
          </span>
          <button
            type="button"
            className="btn primary"
            disabled={selected.size === 0 || running || starting || tooMany}
            onClick={() => void start()}
          >
            {running ? 'A run is in progress…' : starting ? 'Starting…' : `Process selected (${selected.size})`}
          </button>
        </div>
        {tooMany && <p className="alert bad">At most {maxPerRun} emails per run.</p>}
        {error && (
          <p className="alert bad" role="alert">
            {error}
          </p>
        )}
        {list.error && <p className="alert bad">{list.error}</p>}
        {list.loading && !list.data && <p className="muted">Loading emails…</p>}
        <ul className="mail-list">
          {emails.map((e) => (
            <li key={e.id} className={`mail ${openId === e.id ? 'open' : ''} ${selected.has(e.id) ? 'on' : ''}`}>
              <input
                type="checkbox"
                id={`sel-${e.id}`}
                checked={selected.has(e.id)}
                onChange={() => toggle(e.id)}
                aria-label={`Select email from ${e.from_name}: ${e.subject}`}
              />
              <button type="button" className="mail-body" onClick={() => setOpenId(openId === e.id ? null : e.id)} aria-expanded={openId === e.id}>
                <span className="mail-top">
                  <span className="mail-from">{e.from_name}</span>
                  {e.program ? <span className="tag">{e.program}</span> : <span className="tag warn">not on staff roster</span>}
                  {e.flagged && <span className="tag bad">suspicious instructions</span>}
                  {e.origin && e.origin !== 'sample' && <span className="tag warn">{e.origin}</span>}
                  <span className="mail-date">{dateLabel(e.date)}</span>
                </span>
                <span className="mail-subject">{e.subject}</span>
                <span className="mail-snippet">{e.snippet}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <aside className="panel reader" aria-label="Email preview">
        {open ? (
          <article>
            <p className="eyebrow">{open.id}</p>
            <h3>{open.subject}</h3>
            <p className="muted small">
              From {open.from_name} &lt;{open.from_email}&gt; · {dateLabel(open.date)}
            </p>
            {open.flagged_phrases.length > 0 && (
              <p className="alert bad">
                This email contains text aimed at an AI ({open.flagged_phrases.slice(0, 2).map((p) => `“${p}”`).join(', ')}). It will be
                quarantined: the agents treat it as data and code blocks any change from it.
              </p>
            )}
            <pre className="email-text">{open.body}</pre>
          </article>
        ) : (
          <div className="empty">
            <p>
              <strong>Select an email to read it here.</strong>
            </p>
            <p className="muted">
              Emails are treated as untrusted: the agents never follow instructions inside them, and code checks every number, date and
              sender before a change can be proposed.
            </p>
          </div>
        )}
      </aside>
    </div>
    <PastePanel running={running} onStarted={onStarted} />
    {imapConfigured && <ImapPanel onImported={list.reload} />}
    </div>
  )
}
