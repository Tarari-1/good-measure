import { useMemo, useState } from 'react'
import { api, type Change } from '../api'
import { STATUS_LABELS, cellText, dateLabel, money } from '../lib/format'
import { useLoad } from '../lib/usePoll'

export function Trackers({ version }: { version: number }) {
  const budget = useLoad(api.budget, [version])
  const plan = useLoad(api.workplan, [version])
  const changes = useLoad(api.changes, [version])
  const [program, setProgram] = useState('all')

  const changeFor = useMemo(() => {
    const m = new Map<string, Change>()
    for (const c of changes.data?.changes ?? []) m.set(`${c.tracker}:${c.row_id}:${c.field}`, c)
    return m
  }, [changes.data])

  const programs = budget.data?.programs ?? []
  const lines = (budget.data?.lines ?? []).filter((l) => program === 'all' || l.program === program)
  const acts = (plan.data?.activities ?? []).filter((a) => program === 'all' || a.program === program)
  const nChanged = changes.data?.changes.length ?? 0

  const cell = (tracker: 'budget' | 'workplan', row: string, field: string, changed: string[]) => {
    if (!changed.includes(field)) return { className: undefined, title: undefined }
    const c = changeFor.get(`${tracker}:${row}:${field}`)
    return {
      className: 'changed',
      title: c
        ? `Changed by ${c.proposal_id}: ${cellText(field, c.old_value)} → ${cellText(field, c.new_value)}, approved by ${c.approved_by}`
        : 'Changed',
    }
  }

  return (
    <div className="stack">
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>Trackers</h2>
            <p className="muted">
              The working copy of the budget and work plan. <span className="legend changed">Highlighted</span> cells were changed by an approved
              proposal ({nChanged} so far). Hover a highlighted cell to see who approved it.
            </p>
          </div>
          <div className="row">
            <label className="sr-only" htmlFor="prog">
              Program
            </label>
            <select id="prog" className="input" value={program} onChange={(e) => setProgram(e.target.value)}>
              <option value="all">All programs</option>
              {programs.map((p) => (
                <option key={p.code} value={p.code}>
                  {p.name}
                </option>
              ))}
            </select>
            <a className="btn primary" href={api.exportUrl()} download>
              Download .xlsx
            </a>
          </div>
        </div>
      </section>

      <section className="panel" aria-labelledby="budget-h">
        <h3 id="budget-h">Budget</h3>
        {budget.error && <p className="alert bad">{budget.error}</p>}
        <div className="table-wrap">
          <table className="grid">
            <caption className="sr-only">Budget lines with spent, committed and remaining amounts</caption>
            <thead>
              <tr>
                <th scope="col">Line</th>
                <th scope="col">Program</th>
                <th scope="col">Category</th>
                <th scope="col" className="num">Annual budget</th>
                <th scope="col" className="num">Spent to date</th>
                <th scope="col" className="num">Committed</th>
                <th scope="col" className="num">Remaining</th>
                <th scope="col">Used</th>
                <th scope="col">Owner</th>
              </tr>
            </thead>
            <tbody>
              {lines.map((l) => {
                const used = l.annual_budget ? (l.spent_to_date + l.committed) / l.annual_budget : 0
                return (
                  <tr key={l.line_id}>
                    <th scope="row" className="mono">{l.line_id}</th>
                    <td>{l.program}</td>
                    <td>{l.category}</td>
                    <td className="num">{money(l.annual_budget)}</td>
                    <td className={`num ${cell('budget', l.line_id, 'spent_to_date', l.changed_fields).className ?? ''}`} title={cell('budget', l.line_id, 'spent_to_date', l.changed_fields).title}>
                      {money(l.spent_to_date)}
                    </td>
                    <td className={`num ${cell('budget', l.line_id, 'committed', l.changed_fields).className ?? ''}`} title={cell('budget', l.line_id, 'committed', l.changed_fields).title}>
                      {money(l.committed)}
                    </td>
                    <td className={`num ${l.remaining < 0 ? 'neg' : ''}`}>{money(l.remaining)}</td>
                    <td>
                      <span className="meter" role="img" aria-label={`${Math.round(used * 100)}% of budget used or committed`}>
                        <span className={used > 1 ? 'over' : used > 0.9 ? 'hot' : ''} style={{ width: `${Math.min(used, 1) * 100}%` }} />
                      </span>
                    </td>
                    <td>{l.owner}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel" aria-labelledby="plan-h">
        <h3 id="plan-h">Work plan</h3>
        {plan.error && <p className="alert bad">{plan.error}</p>}
        <div className="table-wrap">
          <table className="grid">
            <caption className="sr-only">Work plan activities with due dates, status and progress</caption>
            <thead>
              <tr>
                <th scope="col">ID</th>
                <th scope="col">Program</th>
                <th scope="col">Activity</th>
                <th scope="col">Owner</th>
                <th scope="col">Due</th>
                <th scope="col">Status</th>
                <th scope="col" className="num">Done</th>
                <th scope="col">Depends on</th>
                <th scope="col">Notes</th>
              </tr>
            </thead>
            <tbody>
              {acts.map((a) => (
                <tr key={a.id}>
                  <th scope="row" className="mono">{a.id}</th>
                  <td>{a.program}</td>
                  <td>{a.activity}</td>
                  <td>{a.owner}</td>
                  <td className={cell('workplan', a.id, 'due_date', a.changed_fields).className} title={cell('workplan', a.id, 'due_date', a.changed_fields).title}>
                    {dateLabel(a.due_date)}
                    {a.overdue && <span className="tag bad">overdue</span>}
                  </td>
                  <td className={cell('workplan', a.id, 'status', a.changed_fields).className} title={cell('workplan', a.id, 'status', a.changed_fields).title}>
                    <span className={`st st-${a.status}`}>{STATUS_LABELS[a.status] ?? a.status}</span>
                  </td>
                  <td className={`num ${cell('workplan', a.id, 'percent_complete', a.changed_fields).className ?? ''}`} title={cell('workplan', a.id, 'percent_complete', a.changed_fields).title}>
                    {a.percent_complete}%
                  </td>
                  <td className="mono">{a.depends_on ?? '—'}</td>
                  <td className={cell('workplan', a.id, 'notes', a.changed_fields).className} title={cell('workplan', a.id, 'notes', a.changed_fields).title}>
                    {a.notes || <span className="muted">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
