import { useState } from 'react'
import { api, type Nudge } from '../api'
import { dateLabel } from '../lib/format'
import { useLoad } from '../lib/usePoll'

export function CopyButton({ text, label }: { text: string; label: string }) {
  const [state, setState] = useState<'idle' | 'done' | 'fail'>('idle')
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setState('done')
    } catch {
      setState('fail')
    }
    window.setTimeout(() => setState('idle'), 2000)
  }
  return (
    <button type="button" className="btn small" onClick={() => void copy()} aria-label={label}>
      {state === 'done' ? 'Copied' : state === 'fail' ? 'Copy failed' : 'Copy email'}
      <span className="sr-only" role="status">
        {state === 'done' ? 'Copied to clipboard' : ''}
      </span>
    </button>
  )
}

export function Chase({ version }: { version: number }) {
  const overdue = useLoad(api.overdue, [version])
  const drafts = useLoad(api.drafts, [version])
  const latestByRecipient = new Map<string, Nudge>()
  for (const d of drafts.data?.drafts ?? []) latestByRecipient.set(d.recipient_email, d)
  const nudges = [...latestByRecipient.values()].reverse()

  return (
    <div className="split even">
      <section className="panel" aria-labelledby="overdue-h">
        <h2 id="overdue-h">Who is overdue</h2>
        <p className="muted">
          People whose team sent no update in the last {overdue.data?.window_days ?? 7} days, or who own a past-due activity and have not written.
          Worked out by code from the mailbox and work plan, as of {dateLabel(overdue.data?.today)}.
        </p>
        {overdue.error && <p className="alert bad">{overdue.error}</p>}
        {overdue.data?.owners.length === 0 && <p className="empty">Everyone is up to date.</p>}
        <ul className="people">
          {overdue.data?.owners.map((o) => (
            <li key={o.email} className="person">
              <div className="person-head">
                <strong>{o.name}</strong>
                <span className="tag">{o.program}</span>
                {!o.team_reported && <span className="tag bad">team silent this week</span>}
              </div>
              <p className="muted small">
                {o.role}, {o.program_name}
              </p>
              <ul className="reasons">
                {o.reasons.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel" aria-labelledby="drafts-h">
        <h2 id="drafts-h">Drafted nudges</h2>
        <p className="muted">Written by the Chaser agent as drafts only. Nothing is sent: copy one into your email client if you want to use it.</p>
        {drafts.error && <p className="alert bad">{drafts.error}</p>}
        {nudges.length === 0 && <p className="empty">No drafts yet. Process some emails in the Inbox and the Chaser will draft nudges.</p>}
        <div className="cards">
          {nudges.map((n) => (
            <article key={n.id} className="card nudge" aria-labelledby={`${n.id}-subj`}>
              <header className="card-head">
                <div>
                  <p className="eyebrow">
                    {n.id} · draft · to {n.recipient_name} &lt;{n.recipient_email}&gt;
                  </p>
                  <h3 id={`${n.id}-subj`}>{n.subject}</h3>
                </div>
                <CopyButton text={`To: ${n.recipient_email}\nSubject: ${n.subject}\n\n${n.body}`} label={`Copy nudge to ${n.recipient_name}`} />
              </header>
              <pre className="email-text">{n.body}</pre>
            </article>
          ))}
        </div>
      </section>
    </div>
  )
}
