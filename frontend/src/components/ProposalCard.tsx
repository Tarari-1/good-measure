import { useState } from 'react'
import type { DefenseKey, Proposal } from '../api'
import { DEFENSE_HELP, FIELD_LABELS, cellText, dateLabel, highlightQuote, money } from '../lib/format'

interface Props {
  p: Proposal
  defenses: Record<DefenseKey, string>
  approver: string
  onApprove?: (id: string, acknowledged: boolean) => Promise<void>
  onReject?: (id: string, reason: string) => Promise<void>
}

const STATUS_TEXT: Record<Proposal['status'], string> = {
  pending: 'Waiting for approval',
  needs_decision: 'Needs decision',
  blocked: 'Blocked',
  approved: 'Approved and applied',
  rejected: 'Rejected',
}

export function ProposalCard({ p, defenses, approver, onApprove, onReject }: Props) {
  const [busy, setBusy] = useState(false)
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')
  const [showEmail, setShowEmail] = useState(p.status !== 'approved' && p.status !== 'rejected')
  const [ack, setAck] = useState(false)
  const o = p.overspend ?? null
  const waiting = p.status === 'pending' || p.status === 'needs_decision'
  const field = FIELD_LABELS[p.field] ?? p.field
  const noName = approver.trim().length < 2
  const segments = p.email ? highlightQuote(p.email.body, p.quote) : []
  const quoteFound = segments.some((s) => s.mark)

  const act = async (fn: () => Promise<void>) => {
    setBusy(true)
    try {
      await fn()
    } finally {
      setBusy(false)
    }
  }

  return (
    <article className={`card proposal ${p.status}`} aria-labelledby={`${p.id}-title`}>
      <header className="card-head">
        <div>
          <p className="eyebrow">
            {p.id} · {p.tracker === 'budget' ? 'Budget' : 'Work plan'} · from {p.email_id}
          </p>
          <h3 id={`${p.id}-title`}>
            <span className="mono">{p.row_id}</span> {p.row_label ?? ''} — {field}
          </h3>
        </div>
        <span className={`status-pill ${p.status}`}>{STATUS_TEXT[p.status]}</span>
      </header>

      <div className="diff" role="group" aria-label={`Change to ${field}`}>
        <div className="diff-cell before">
          <span className="diff-label">Before</span>
          <span className="diff-value">{cellText(p.field, p.before)}</span>
        </div>
        <span className="diff-arrow" aria-hidden="true">→</span>
        <div className="diff-cell after">
          <span className="diff-label">After</span>
          <span className="diff-value">{cellText(p.field, p.after)}</span>
        </div>
        {p.tracker === 'budget' && p.amount !== null && (
          <div className="diff-cell delta">
            <span className="diff-label">Change</span>
            <span className="diff-value">
              {Number(p.amount) >= 0 ? '+' : ''}
              {cellText(p.field, p.amount)}
            </span>
          </div>
        )}
      </div>

      {o && (
        <section className={`overbudget ${o.kind}`} aria-label="Over budget">
          <p className="overbudget-title">
            <span aria-hidden="true">▲</span> Over budget{o.kind === 'commitment' ? ' — needs a decision' : ' — spend is recorded, not rejected'}
          </p>
          <dl className="overbudget-grid">
            <div><dt>Line</dt><dd className="mono">{o.line_id}</dd></div>
            <div><dt>Budget</dt><dd>{money(o.budget)}</dd></div>
            <div><dt>Spent after</dt><dd>{money(o.spent_after)}</dd></div>
            <div><dt>Committed</dt><dd>{money(o.committed_after)}</dd></div>
            <div><dt>Over by</dt><dd className="neg">{money(o.overage)}</dd></div>
            <div><dt>Remaining</dt><dd className={o.new_remaining < 0 ? 'neg' : ''}>{money(o.new_remaining)}</dd></div>
            <div><dt>Unfunded commitments</dt><dd className={o.unfunded_commitments > 0 ? 'neg' : ''}>{money(o.unfunded_commitments)}</dd></div>
          </dl>
          <p className="overbudget-consequence">{o.consequence}</p>
          {waiting && onApprove && (
            <label className="check ack">
              <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
              <span>
                I understand {o.line_id} will be {money(o.overage)} over budget
                {o.unfunded_commitments > 0 ? ` and ${money(o.unfunded_commitments)} of commitments will be unfunded` : ''}.
              </span>
            </label>
          )}
          {p.overspend_acknowledged && <p className="small">Overspend acknowledged by {p.decided_by}.</p>}
        </section>
      )}

      {p.blocks.length > 0 && (
        <div className="defense-list" role="note">
          <p className="defense-title">Stopped by {p.blocks.length === 1 ? 'a defense' : `${p.blocks.length} defenses`}</p>
          <ul>
            {p.blocks.map((b, i) => (
              <li key={i}>
                <span className={`defense-tag d-${b.defense}`} title={DEFENSE_HELP[b.defense]}>
                  {defenses[b.defense] ?? b.defense}
                </span>
                <span>{b.reason}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {p.warnings.length > 0 && (
        <ul className="warnings">
          {p.warnings.map((w, i) => (
            <li key={i}>
              <span className="warn-tag">{w.type === 'overspend' ? 'OVERSPEND' : w.type === 'dependency' ? 'Dependency' : 'Check'}</span>
              {w.message}
            </li>
          ))}
        </ul>
      )}

      {p.checker_review && (
        <p className={`checker ${p.checker_review.verdict}`}>
          <strong>Checker agent:</strong> {p.checker_review.verdict === 'concern' ? 'Concern — ' : 'Looks right — '}
          {p.checker_review.note}
          {p.checker_review.verified === false && (
            <span className="tag bad" title={(p.checker_review.problems ?? []).join('; ')}>
              unverified note: {(p.checker_review.problems ?? []).join('; ')}
            </span>
          )}
        </p>
      )}

      <div className="evidence">
        <button type="button" className="link" aria-expanded={showEmail} onClick={() => setShowEmail(!showEmail)}>
          {showEmail ? 'Hide' : 'Show'} the email{p.email ? ` from ${p.email.from_name}` : ''}
        </button>
        {showEmail && p.email && (
          <figure className="email-quote">
            <figcaption>
              {p.email.subject} · {p.email.from_email} · {dateLabel(p.email.date)}
              {!quoteFound && <span className="tag bad">quoted text not found in this email</span>}
            </figcaption>
            <pre className="email-text">
              {segments.map((s, i) => (s.mark ? <mark key={i}>{s.text}</mark> : <span key={i}>{s.text}</span>))}
            </pre>
            {p.rationale && <p className="muted small">Agent’s reasoning: {p.rationale}</p>}
          </figure>
        )}
      </div>

      {waiting && onApprove && onReject && (
        <footer className="card-actions">
          {rejecting ? (
            <>
              <label className="sr-only" htmlFor={`${p.id}-reason`}>
                Reason for rejecting (optional)
              </label>
              <input
                id={`${p.id}-reason`}
                className="input"
                placeholder="Reason (optional)"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                maxLength={300}
              />
              <button type="button" className="btn danger" disabled={busy || noName} onClick={() => void act(() => onReject(p.id, reason))}>
                Confirm reject
              </button>
              <button type="button" className="btn ghost" onClick={() => setRejecting(false)}>
                Cancel
              </button>
            </>
          ) : (
            <>
              <button type="button" className="btn primary" disabled={busy || noName || (o !== null && !ack)} onClick={() => void act(() => onApprove(p.id, ack))}>
                {busy ? 'Applying…' : 'Approve and apply'}
              </button>
              <button type="button" className="btn ghost" disabled={busy || noName} onClick={() => setRejecting(true)}>
                Reject
              </button>
              {noName && <span className="muted small">Type your name above to approve or reject.</span>}
              {!noName && o !== null && !ack && <span className="muted small">Tick the over-budget acknowledgement to approve.</span>}
            </>
          )}
        </footer>
      )}
      {(p.status === 'approved' || p.status === 'rejected') && p.decided_by && (
        <p className="muted small decided">
          {p.status === 'approved' ? 'Approved' : 'Rejected'} by {p.decided_by}
          {p.rejection_reason ? ` — “${p.rejection_reason}”` : ''}
        </p>
      )}
      {p.status === 'blocked' && onReject && (
        <footer className="card-actions">
          <button type="button" className="btn ghost small" disabled={busy || noName} onClick={() => void act(() => onReject(p.id, 'dismissed blocked proposal'))}>
            Dismiss
          </button>
          <span className="muted small">Blocked changes can never be applied. Dismiss to clear it from the list.</span>
        </footer>
      )}
    </article>
  )
}
