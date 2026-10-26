import { useEffect, useMemo, useState } from 'react'
import { api, type Proposal, type Run } from '../api'
import { ProposalCard } from '../components/ProposalCard'
import { useLoad } from '../lib/usePoll'

type Filter = 'pending' | 'blocked' | 'decided'

const OUTCOME_TEXT: Record<string, string> = {
  needs_clarification: 'Needs clarification',
  no_matching_row: 'No matching tracker row',
  not_a_tracker_update: 'Not a tracker update',
  suspicious: 'Suspicious — ignored',
  not_processed: 'Not processed',
  claimed_without_proposal: 'Claimed but not proposed',
  skipped_quarantined: 'Skipped: quarantined',
  skipped_not_on_roster: 'Skipped: sender not on roster',
  skipped_no_tracker_rows: 'Skipped: sender owns no rows',
  skipped_auto_reply: 'Skipped: automatic reply',
}

export function Review({ version, onChanged }: { version: number; onChanged: () => void }) {
  const data = useLoad(api.proposals, [version])
  const runs = useLoad(api.runs, [version])
  const [latest, setLatest] = useState<Run | null>(null)
  const [filter, setFilter] = useState<Filter>('pending')
  const [approver, setApprover] = useState(() => localStorage.getItem('approver') ?? '')
  const [msg, setMsg] = useState<{ tone: 'good' | 'bad'; text: string } | null>(null)

  useEffect(() => {
    localStorage.setItem('approver', approver)
  }, [approver])

  const lastRunId = runs.data?.runs.find((r) => r.status !== 'queued' && r.status !== 'running')?.run_id
  useEffect(() => {
    if (!lastRunId) return
    api
      .run(lastRunId)
      .then(setLatest)
      .catch(() => setLatest(null))
  }, [lastRunId, version])

  const all: Proposal[] = useMemo(() => [...(data.data?.proposals ?? [])].reverse(), [data.data])
  const groups = {
    pending: all.filter((p) => p.status === 'pending' || p.status === 'needs_decision'),
    blocked: all.filter((p) => p.status === 'blocked'),
    decided: all.filter((p) => p.status === 'approved' || p.status === 'rejected'),
  }
  const shown = groups[filter]

  const approve = async (id: string, acknowledged: boolean) => {
    setMsg(null)
    try {
      await api.approve(id, approver.trim(), acknowledged)
      setMsg({ tone: 'good', text: `${id} approved and written to the tracker.` })
    } catch (e) {
      setMsg({ tone: 'bad', text: `${id}: ${e instanceof Error ? e.message : 'failed'}` })
    }
    onChanged()
  }
  const reject = async (id: string, reason: string) => {
    setMsg(null)
    try {
      await api.reject(id, approver.trim(), reason)
      setMsg({ tone: 'good', text: `${id} rejected. Nothing was changed.` })
    } catch (e) {
      setMsg({ tone: 'bad', text: `${id}: ${e instanceof Error ? e.message : 'failed'}` })
    }
    onChanged()
  }

  const noProposal = (latest?.email_outcomes ?? []).filter((o) => o.outcome !== 'proposed')
  const flags = latest?.email_flags ?? []

  return (
    <div className="stack">
      <section className="panel" aria-labelledby="review-h">
        <div className="panel-head">
          <div>
            <h2 id="review-h">Review proposed changes</h2>
            <p className="muted">
              Each card is one cell change with the email that supports it. Approving re-checks it against the current tracker and then
              writes it. Blocked changes show which defense stopped them.
            </p>
          </div>
          <div className="approver">
            <label htmlFor="approver">Approver name</label>
            <input
              id="approver"
              className="input"
              value={approver}
              onChange={(e) => setApprover(e.target.value)}
              placeholder="e.g. Demo Approver"
              autoComplete="name"
              maxLength={60}
            />
          </div>
        </div>
        <div className="segmented" role="radiogroup" aria-label="Show">
          {(['pending', 'blocked', 'decided'] as Filter[]).map((f) => (
            <button key={f} type="button" role="radio" aria-checked={filter === f} className={filter === f ? 'seg on' : 'seg'} onClick={() => setFilter(f)}>
              {f === 'pending' ? 'Waiting for you' : f === 'blocked' ? 'Blocked by defenses' : 'Decided'}
              <span className="seg-count">{groups[f].length}</span>
            </button>
          ))}
        </div>
        {msg && (
          <p className={`alert ${msg.tone}`} role="status">
            {msg.text}
          </p>
        )}
        {data.error && <p className="alert bad">{data.error}</p>}
      </section>

      {shown.length === 0 && !data.loading && (
        <p className="empty panel">
          {filter === 'pending'
            ? all.length === 0
              ? 'No proposals yet. Go to Inbox, tick some emails and press “Process selected”.'
              : 'Nothing is waiting for approval.'
            : filter === 'blocked'
              ? 'No blocked proposals.'
              : 'No decisions yet.'}
        </p>
      )}
      <div className="cards">
        {shown.map((p) => (
          <ProposalCard key={p.id} p={p} defenses={data.data!.defenses} approver={approver} onApprove={approve} onReject={reject} />
        ))}
      </div>

      {latest && (flags.length > 0 || noProposal.length > 0) && (
        <section className="panel" aria-labelledby="noprop-h">
          <h2 id="noprop-h" className="h3">
            Emails from the last run with no change proposed
          </h2>
          {flags.length > 0 && (
            <ul className="flat">
              {flags.map((f) => (
                <li key={f.email_id}>
                  <span className="defense-tag d-untrusted_email">{data.data?.defenses.untrusted_email ?? 'Untrusted email'}</span>
                  <strong className="mono">{f.email_id}</strong> {f.reason}
                </li>
              ))}
            </ul>
          )}
          <ul className="flat">
            {noProposal.map((o) => (
              <li key={o.email_id}>
                <span className="tag">{OUTCOME_TEXT[o.outcome] ?? o.outcome}</span> <strong className="mono">{o.email_id}</strong> {o.note}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
