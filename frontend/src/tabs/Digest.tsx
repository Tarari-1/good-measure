import { api } from '../api'
import { STATUS_LABELS, dateLabel, moneyShort } from '../lib/format'
import { useLoad } from '../lib/usePoll'

export function DigestTab({ version }: { version: number }) {
  const d = useLoad(api.digest, [version])
  const m = d.data?.metrics
  const latest = d.data?.latest

  return (
    <div className="stack">
      <section className="panel" aria-labelledby="digest-h">
        <h2 id="digest-h">Weekly digest</h2>
        <p className="muted">
          Numbers below are computed by code from the current trackers (they update as you approve changes). The narrative is written
          by the Coordinator agent at the end of each run.
        </p>
        {d.error && <p className="alert bad">{d.error}</p>}
        {latest ? (
          <div className="narrative">
            <p className="eyebrow">
              Coordinator · run {latest.run_id} · {dateLabel(latest.created_at)}
              {latest.mode === 'stub' ? ' · stub run (no model)' : ''}
            </p>
            <p className="headline">{latest.digest.headline}</p>
            {latest.digest.proposals_summary && <p>{latest.digest.proposals_summary}</p>}
            {latest.digest.decisions_for_tracker_owner.length > 0 && (
              <>
                <h3 className="h4">For the tracker owner</h3>
                <ul>
                  {latest.digest.decisions_for_tracker_owner.map((x, i) => (
                    <li key={i}>{x}</li>
                  ))}
                </ul>
              </>
            )}
          </div>
        ) : (
          <p className="empty">No digest yet: process emails from the Inbox to get one.</p>
        )}
      </section>

      {m && (
        <section className="panel" aria-labelledby="burn-h">
          <h3 id="burn-h">Budget burn vs plan</h3>
          <p className="muted small">
            Bar = share of annual budget spent. The tick marks where spending would be if it were even through the year ({m.plan_pct}% on{' '}
            {dateLabel(m.today)}).
          </p>
          <ul className="burn">
            {m.programs.map((p) => {
              const ahead = p.variance_pts
              const label = `${p.name}: ${p.burn_pct}% spent vs ${p.plan_pct}% plan (${ahead >= 0 ? '+' : ''}${ahead} points); ${p.committed_pct}% including commitments`
              return (
                <li key={p.program} className="burn-row" title={label}>
                  <span className="burn-name">
                    <strong>{p.program}</strong> <span className="muted small">{p.name}</span>
                  </span>
                  <span className="burn-track" role="img" aria-label={label}>
                    <span className="burn-committed" style={{ width: `${Math.min(p.committed_pct, 100)}%` }} />
                    <span className="burn-spent" style={{ width: `${Math.min(p.burn_pct, 100)}%` }} />
                    <span className="burn-plan" style={{ left: `${Math.min(p.plan_pct, 100)}%` }} />
                  </span>
                  <span className="burn-num mono">
                    {p.burn_pct}% <span className="muted">({ahead >= 0 ? '+' : ''}{ahead} pts)</span>
                  </span>
                  <span className="burn-money muted small">
                    {moneyShort(p.spent_to_date)} of {moneyShort(p.annual_budget)}
                    {p.lines_over_90pct.length > 0 && <> · over 90% used: {p.lines_over_90pct.join(', ')}</>}
                  </span>
                </li>
              )
            })}
          </ul>
          <p className="legend-row small muted">
            <span className="key spent" aria-hidden="true" /> Spent <span className="key committed" aria-hidden="true" /> Spent + committed{' '}
            <span className="key plan" aria-hidden="true" /> Even-spend plan
          </p>
        </section>
      )}

      {m && (
        <div className="split even">
          <section className="panel" aria-labelledby="risk-h">
            <h3 id="risk-h">At-risk milestones ({m.at_risk.length})</h3>
            <ul className="flat">
              {m.at_risk.map((a) => (
                <li key={a.id}>
                  <span className={`tag ${a.risk === 'overdue' ? 'bad' : 'warn'}`}>{a.risk}</span> <strong className="mono">{a.id}</strong>{' '}
                  {a.activity} — {a.owner}, due {dateLabel(a.due_date)}, {a.percent_complete}% ({STATUS_LABELS[a.status] ?? a.status})
                </li>
              ))}
            </ul>
          </section>
          <section className="panel" aria-labelledby="late-h">
            <h3 id="late-h">Late owners ({m.late_owners.length})</h3>
            <ul className="flat">
              {m.late_owners.map((o) => (
                <li key={o.email}>
                  <strong>{o.name}</strong> <span className="tag">{o.program}</span>
                  <span className="muted small"> {o.reasons.join(' ')}</span>
                </li>
              ))}
            </ul>
            <p className="muted small">{m.pending_proposals} proposed change(s) waiting for approval.</p>
          </section>
        </div>
      )}
    </div>
  )
}
