import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { api, type Health, type Run } from './api'
import { HeadlineBand, type Stat } from './components/HeadlineBand'
import { ResetButton } from './components/ResetButton'
import { RunBanner } from './components/RunBanner'
import { cost, count, dateLabel } from './lib/format'
import { useLoad } from './lib/usePoll'
import { Chase } from './tabs/Chase'
import { DigestTab } from './tabs/Digest'
import { Inbox } from './tabs/Inbox'
import { Review } from './tabs/Review'
import { RunDetails } from './tabs/RunDetails'
import { Safety } from './tabs/Safety'
import { Trackers } from './tabs/Trackers'

const TABS = [
  { id: 'inbox', label: 'Inbox', purpose: 'Turn the emails staff already send into proposed tracker updates.' },
  { id: 'review', label: 'Review', purpose: 'Check each proposed change against its email, then approve or reject it.' },
  { id: 'trackers', label: 'Trackers', purpose: 'The live budget and work plan; approved changes are highlighted.' },
  { id: 'chase', label: 'Chase', purpose: 'Who has not reported this week, with a friendly nudge ready to copy.' },
  { id: 'digest', label: 'Digest', purpose: 'The week at a glance: spending against plan, risks and late updates.' },
  { id: 'safety', label: 'Safety', purpose: 'Five checks in plain code stand between an email and your trackers.' },
  { id: 'run', label: 'Run details', purpose: 'What each agent did in a run, and what it cost.' },
] as const
export type TabId = (typeof TABS)[number]['id']

export default function App() {
  const [tab, setTab] = useState<TabId>('inbox')
  const [version, setVersion] = useState(0) // bumped after anything that changes data
  const [runId, setRunId] = useState<string | null>(null)
  const [run, setRun] = useState<Run | null>(null)
  const health = useLoad<Health>(api.health, [version], 15000)
  const emails = useLoad(api.emails, [version])
  const props = useLoad(api.proposals, [version])
  const digest = useLoad(api.digest, [version])
  const runs = useLoad(api.runs, [version])
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([])
  const bump = useCallback(() => setVersion((v) => v + 1), [])

  // Pick up a run already in progress (e.g. after a page reload).
  useEffect(() => {
    if (health.data?.run_in_progress && !runId) setRunId(health.data.run_in_progress)
  }, [health.data, runId])

  // Follow the active run until it ends.
  useEffect(() => {
    if (!runId) return
    let alive = true
    const tick = async () => {
      try {
        const r = await api.run(runId)
        if (!alive) return
        setRun(r)
        if (r.status !== 'queued' && r.status !== 'running') {
          bump()
          return
        }
      } catch {
        /* keep polling */
      }
      if (alive) window.setTimeout(tick, 1500)
    }
    void tick()
    return () => {
      alive = false
    }
  }, [runId, bump])

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const i = TABS.findIndex((t) => t.id === tab)
    const next = e.key === 'ArrowRight' ? i + 1 : e.key === 'ArrowLeft' ? i - 1 : e.key === 'Home' ? 0 : e.key === 'End' ? TABS.length - 1 : null
    if (next === null) return
    e.preventDefault()
    const j = (next + TABS.length) % TABS.length
    setTab(TABS[j]!.id)
    tabRefs.current[j]?.focus()
  }

  const running = run !== null && (run.status === 'queued' || run.status === 'running')
  const h = health.data
  const all = props.data?.proposals ?? []
  const waiting = all.filter((p) => p.status === 'pending' || p.status === 'needs_decision').length
  const blocked = all.filter((p) => p.status === 'blocked').length
  const decided = all.filter((p) => p.status === 'approved' || p.status === 'rejected').length
  const flagged = all.filter((p) => p.overspend && (p.status === 'pending' || p.status === 'needs_decision')).length
  const m = digest.data?.metrics
  const burn = m && m.totals.annual_budget ? (100 * m.totals.spent_to_date) / m.totals.annual_budget : null
  const lastLive = runs.data?.runs.find((r) => r.mode === 'live' && r.usage)
  const current = TABS.find((t) => t.id === tab)!
  const dash = '—'

  const stats: Record<TabId, Stat[]> = {
    inbox: [
      { label: 'Emails in inbox', value: emails.data ? count(emails.data.emails.length) : dash },
      { label: 'Selected', value: emails.data ? count(emails.data.selected.length) : dash },
      { label: 'Waiting for approval', value: count(waiting), tone: waiting ? 'warn' : 'default' },
    ],
    review: [
      { label: 'Waiting for you', value: count(waiting), tone: waiting ? 'warn' : 'default' },
      { label: 'Over budget, need acknowledgement', value: count(flagged), tone: flagged ? 'warn' : 'default' },
      { label: 'Blocked by a defense', value: count(blocked), tone: blocked ? 'bad' : 'default' },
      { label: 'Decided', value: count(decided), tone: 'good' },
    ],
    trackers: [
      { label: 'Annual budget', value: m ? `$${count(Math.round(m.totals.annual_budget))}` : dash },
      { label: 'Spent so far', value: burn !== null ? `${burn.toFixed(1)}%` : dash, note: m ? `plan ${m.plan_pct}%` : undefined },
      { label: 'Changes waiting', value: count(waiting), tone: waiting ? 'warn' : 'default' },
    ],
    chase: [
      { label: 'People to chase', value: m ? count(m.late_owners.length) : dash, tone: m && m.late_owners.length ? 'warn' : 'default' },
      { label: 'Overdue activities', value: m ? count(m.at_risk.filter((a) => a.risk === 'overdue').length) : dash },
    ],
    digest: [
      { label: 'Budget burn', value: burn !== null ? `${burn.toFixed(1)}%` : dash, note: m ? `vs ${m.plan_pct}% plan` : undefined },
      { label: 'At-risk milestones', value: m ? count(m.at_risk.length) : dash, tone: m && m.at_risk.length ? 'warn' : 'default' },
      { label: 'Late owners', value: m ? count(m.late_owners.length) : dash },
    ],
    safety: [
      { label: 'Code defenses', value: '5' },
      { label: 'Blocked proposals', value: count(blocked), tone: blocked ? 'bad' : 'default' },
      { label: 'Over-budget flags waiting', value: count(flagged), tone: flagged ? 'warn' : 'default' },
    ],
    run: [
      { label: 'Last live run', value: lastLive ? lastLive.run_id.slice(0, 7) : dash, note: lastLive ? `${lastLive.email_ids.length} emails` : undefined },
      { label: 'Model requests', value: lastLive?.usage ? count(lastLive.usage.total.requests) : dash },
      { label: 'Tokens (in + out)', value: lastLive?.usage ? count(lastLive.usage.total.input_tokens + lastLive.usage.total.output_tokens) : dash },
      { label: 'Cost', value: lastLive?.usage ? cost(lastLive.usage.total.cost_usd) : dash },
    ],
  }

  return (
    <div className="app">
      <a className="skip" href="#main">
        Skip to content
      </a>
      <header className="topbar">
        <div className="topbar-inner">
          <div className="brand">
            <span className="brand-mark" aria-hidden="true">
              <i />
              <i />
              <i />
            </span>
            <div>
              <h1>Good Measure</h1>
              <p className="tagline">Every update, for good measure.</p>
            </div>
          </div>
          <nav className="nav" role="tablist" aria-label="Sections" onKeyDown={onKey}>
            {TABS.map((t, i) => (
              <button
                key={t.id}
                ref={(el) => {
                  tabRefs.current[i] = el
                }}
                role="tab"
                id={`tab-${t.id}`}
                aria-selected={tab === t.id}
                aria-controls="main"
                tabIndex={tab === t.id ? 0 : -1}
                className={tab === t.id ? 'tab active' : 'tab'}
                onClick={() => setTab(t.id)}
              >
                {t.label}
                {t.id === 'review' && waiting > 0 && (
                  <span className="badge" aria-label={`${waiting} waiting`}>
                    {waiting}
                  </span>
                )}
              </button>
            ))}
          </nav>
          <div className="topbar-side">
            <ResetButton disabled={running} onDone={bump} />
          </div>
        </div>
      </header>

      <HeadlineBand title={current.label} purpose={current.purpose} stats={stats[tab]} />

      <div className="page">
        <div className="statusline">
          <p className="org-line">{h?.org ?? 'Bright Futures Literacy Network'} · fictional demo data</p>
          <dl className="facts">
              <div>
                <dt>Today (demo)</dt>
                <dd>{h ? dateLabel(h.today) : dash}</dd>
              </div>
              <div>
                <dt>Model</dt>
                <dd className="mono">{h?.model ?? dash}</dd>
              </div>
              <div>
                <dt>Mode</dt>
                <dd>{h ? (h.mode === 'stub' ? 'Stub (no model)' : 'Live') : dash}</dd>
              </div>
              <div>
                <dt>Backend</dt>
                <dd>
                  <span className={`dot ${health.error ? 'bad' : h ? 'good' : ''}`} aria-hidden="true" />
                  {health.error ? 'Offline' : h ? 'Connected' : 'Checking…'}
                </dd>
              </div>
            </dl>
        </div>
        {health.error && (
          <p className="alert bad" role="alert">
            {health.error} Start it with <code>.venv/bin/uvicorn backend.main:app --port 8000</code> from the repo folder.
          </p>
        )}

        {run && <RunBanner run={run} onOpenReview={() => setTab('review')} onOpenRun={() => setTab('run')} />}

        <main id="main" role="tabpanel" aria-labelledby={`tab-${tab}`} tabIndex={-1}>
          {tab === 'inbox' && (
            <Inbox
              version={version}
              running={running}
              maxPerRun={h?.caps.max_emails_per_run ?? 25}
              imapConfigured={h?.imap_configured ?? false}
              onStarted={(id) => {
                setRun(null)
                setRunId(id)
              }}
            />
          )}
          {tab === 'review' && <Review version={version} onChanged={bump} />}
          {tab === 'trackers' && <Trackers version={version} />}
          {tab === 'chase' && <Chase version={version} />}
          {tab === 'digest' && <DigestTab version={version} />}
          {tab === 'safety' && <Safety version={version} />}
          {tab === 'run' && <RunDetails version={version} preferredRunId={runId} />}
        </main>
        <footer className="foot">
          All people, organisations and emails are fictional. Agents only propose; every change needs a named human approver.
        </footer>
      </div>
    </div>
  )
}
