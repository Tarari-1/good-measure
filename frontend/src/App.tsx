import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { api, type Health, type Run } from './api'
import { ResetButton } from './components/ResetButton'
import { RunBanner } from './components/RunBanner'
import { dateLabel } from './lib/format'
import { useLoad } from './lib/usePoll'
import { Chase } from './tabs/Chase'
import { DigestTab } from './tabs/Digest'
import { Inbox } from './tabs/Inbox'
import { Review } from './tabs/Review'
import { RunDetails } from './tabs/RunDetails'
import { Safety } from './tabs/Safety'
import { Trackers } from './tabs/Trackers'

const TABS = [
  { id: 'inbox', label: 'Inbox', hint: 'Pick emails to process' },
  { id: 'review', label: 'Review', hint: 'Approve or reject changes' },
  { id: 'trackers', label: 'Trackers', hint: 'Budget and work plan' },
  { id: 'chase', label: 'Chase', hint: 'Who has not reported' },
  { id: 'digest', label: 'Digest', hint: 'The week at a glance' },
  { id: 'safety', label: 'Safety', hint: 'Defenses and blocks' },
  { id: 'run', label: 'Run details', hint: 'Agent trace and tokens' },
] as const
export type TabId = (typeof TABS)[number]['id']

export default function App() {
  const [tab, setTab] = useState<TabId>('inbox')
  const [version, setVersion] = useState(0) // bumped after anything that changes data
  const [runId, setRunId] = useState<string | null>(null)
  const [run, setRun] = useState<Run | null>(null)
  const [pending, setPending] = useState(0)
  const health = useLoad<Health>(api.health, [version], 15000)
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

  useEffect(() => {
    api
      .proposals()
      .then((p) => setPending(p.proposals.filter((x) => x.status === 'pending' || x.status === 'needs_decision').length))
      .catch(() => setPending(0))
  }, [version])

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

  return (
    <div className="app">
      <a className="skip" href="#main">Skip to content</a>
      <header className="masthead">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          <div>
            <h1>Good Measure</h1>
            <p className="tagline">Every update, for good measure.</p>
            <p className="org">{h?.org ?? 'Bright Futures Literacy Network'} · fictional demo data</p>
          </div>
        </div>
        <dl className="facts">
          <div>
            <dt>Today (demo)</dt>
            <dd>{h ? dateLabel(h.today) : '—'}</dd>
          </div>
          <div>
            <dt>Model</dt>
            <dd className="mono">{h?.model ?? '—'}</dd>
          </div>
          <div>
            <dt>Mode</dt>
            <dd>{h ? (h.mode === 'stub' ? 'Stub (no model)' : 'Live') : '—'}</dd>
          </div>
          <div>
            <dt>Backend</dt>
            <dd>
              <span className={`dot ${health.error ? 'bad' : h ? 'good' : ''}`} aria-hidden="true" />
              {health.error ? 'Offline' : h ? 'Connected' : 'Checking…'}
            </dd>
          </div>
        </dl>
        <ResetButton disabled={running} onDone={bump} />
      </header>

      {health.error && (
        <p className="alert bad" role="alert">
          {health.error} Start it with <code>.venv/bin/uvicorn backend.main:app --port 8000</code> from the repo folder.
        </p>
      )}

      <nav className="tabs" role="tablist" aria-label="Sections" onKeyDown={onKey}>
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
            <span className="tab-label">
              <span className="tab-num" aria-hidden="true">{i + 1}</span>
              {t.label}
              {t.id === 'review' && pending > 0 && (
                <span className="badge" aria-label={`${pending} pending`}>
                  {pending}
                </span>
              )}
            </span>
            <span className="tab-hint">{t.hint}</span>
          </button>
        ))}
      </nav>

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
  )
}
