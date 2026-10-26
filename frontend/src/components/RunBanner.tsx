import type { Run } from '../api'
import { count } from '../lib/format'

export function RunBanner({ run, onOpenReview, onOpenRun }: { run: Run; onOpenReview: () => void; onOpenRun: () => void }) {
  const active = run.status === 'queued' || run.status === 'running'
  const p = run.proposals
  const tone = active ? 'info' : run.status === 'finished' ? 'good' : 'bad'
  return (
    <section className={`banner ${tone}`} role="status" aria-live="polite">
      {active ? (
        <>
          <span className="spinner" aria-hidden="true" />
          <p>
            <strong>Processing {run.email_ids.length} emails…</strong> The agents read each email, propose changes, check them and
            draft nudges. This can take a few minutes.
          </p>
          <button type="button" className="btn small ghost" onClick={onOpenRun}>
            Watch the trace
          </button>
        </>
      ) : (
        <>
          <p>
            <strong>
              Run {run.status}
              {run.reason ? `: ${run.reason}` : ''}.
            </strong>{' '}
            {p ? (
              <>
                {count(p.total)} proposed changes ({p.by_status.pending ?? 0} waiting for you, {p.by_status.blocked ?? 0} blocked by a
                defense).
              </>
            ) : null}
            {run.usage && run.mode === 'live' ? <> {count(run.usage.total.input_tokens + run.usage.total.output_tokens)} tokens used.</> : null}
          </p>
          <button type="button" className="btn small" onClick={onOpenReview}>
            Review changes
          </button>
          <button type="button" className="btn small ghost" onClick={onOpenRun}>
            Run details
          </button>
        </>
      )}
    </section>
  )
}
