import { useEffect, useState } from 'react'
import { AGENTS, api, type Run, type RunEvent, type RunListItem } from '../api'
import { cost, count, timeLabel } from '../lib/format'
import { useLoad } from '../lib/usePoll'

const STEP_TEXT: Record<string, string> = {
  run_start: 'Run started',
  run_end: 'Run ended',
  agent_start: 'Agent started',
  model_response: 'Model replied',
  tool_result: 'Tool',
  delegation: 'Delegated',
  final_answer: 'Finished',
  limit_stop: 'Limit / loop stop',
  error: 'Error',
  email_quarantined: 'Email quarantined',
  approved_and_applied: 'Human approved',
  rejected: 'Human rejected',
  approval_blocked: 'Approval re-check failed',
  email_skipped: 'Skipped by pre-filter',
  note_check_retry: 'Checker note sent back',
}

export function UsageTable({ run }: { run: Run }) {
  const u = run.usage
  if (!u) return <p className="muted">No token data for this run.</p>
  return (
    <>
      {u.pricing.placeholders ? (
        <p className="alert warn">
          Costs use <strong>placeholder prices</strong> from <code>config/pricing.py</code>. They are estimates until the real prices are
          filled in.
        </p>
      ) : (
        <p className="muted small">
          Prices per million tokens{u.pricing.source ? ` (${u.pricing.source})` : ''}: input ${u.pricing.input_per_mtok}, cached input $
          {u.pricing.cached_input_per_mtok}, cache write ${u.pricing.cache_write_per_mtok ?? '—'}, output ${u.pricing.output_per_mtok}.
          Cached and cache-write tokens are part of the input count and billed at their own rate.
        </p>
      )}
      <div className="table-wrap">
        <table className="grid">
          <caption className="sr-only">Tokens and estimated cost per agent</caption>
          <thead>
            <tr>
              <th scope="col">Agent</th>
              <th scope="col" className="num">Requests</th>
              <th scope="col" className="num">Tool calls</th>
              <th scope="col" className="num">Input tokens</th>
              <th scope="col" className="num">of which cached</th>
              <th scope="col" className="num">Cache writes</th>
              <th scope="col" className="num">Output tokens</th>
              <th scope="col" className="num">Est. cost</th>
            </tr>
          </thead>
          <tbody>
            {AGENTS.map((a) => {
              const r = u.per_agent[a]
              return (
                <tr key={a}>
                  <th scope="row" className="cap">{a}</th>
                  <td className="num">{count(r.requests)}</td>
                  <td className="num">{count(r.tool_calls)}</td>
                  <td className="num">{count(r.input_tokens)}</td>
                  <td className="num">{count(r.cached_input_tokens)}</td>
                  <td className="num">{count(r.cache_write_tokens ?? 0)}</td>
                  <td className="num">{count(r.output_tokens)}</td>
                  <td className="num">{cost(r.cost_usd)}</td>
                </tr>
              )
            })}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row">Total</th>
              <td className="num">
                {count(u.total.requests)} <span className="muted small">/ {u.caps.request_limit}</span>
              </td>
              <td className="num">
                {count(u.total.tool_calls)} <span className="muted small">/ {u.caps.tool_calls_limit}</span>
              </td>
              <td className="num">{count(u.total.input_tokens)}</td>
              <td className="num">{count(u.total.cached_input_tokens)}</td>
              <td className="num">{count(u.total.cache_write_tokens ?? 0)}</td>
              <td className="num">{count(u.total.output_tokens)}</td>
              <td className="num">{cost(u.total.cost_usd)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
      <p className="muted small">
        Shared caps for the whole run: {count(u.caps.request_limit)} requests, {count(u.caps.tool_calls_limit)} tool calls,{' '}
        {count(u.caps.total_tokens_limit)} tokens, {u.caps.run_timeout_s}s.
      </p>
    </>
  )
}

function measuresOff(m?: Record<string, boolean>): string {
  if (!m) return '—'
  const off = Object.entries(m)
    .filter(([, on]) => !on)
    .map(([k]) => k.replaceAll('_', ' '))
  return off.length ? `off: ${off.join(', ')}` : 'all on'
}

export function RunsTable({ runs, current, onPick }: { runs: RunListItem[]; current: string | null; onPick: (id: string) => void }) {
  return (
    <div className="table-wrap">
      <table className="grid">
        <caption className="sr-only">Tokens and cost per run</caption>
        <thead>
          <tr>
            <th scope="col">Run</th>
            <th scope="col">Mode</th>
            <th scope="col">Cost measures</th>
            <th scope="col" className="num">Emails</th>
            <th scope="col" className="num">Requests</th>
            <th scope="col" className="num">Input</th>
            <th scope="col" className="num">Cached</th>
            <th scope="col" className="num">Output</th>
            <th scope="col" className="num">Cost</th>
            <th scope="col" className="num">Cost / email</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => {
            const t = r.usage?.total
            return (
              <tr key={r.run_id} className={r.run_id === current ? 'current' : undefined}>
                <th scope="row">
                  <button type="button" className="link mono" onClick={() => onPick(r.run_id)} aria-current={r.run_id === current}>
                    {r.run_id}
                  </button>
                </th>
                <td>{r.mode}</td>
                <td className="small">{measuresOff(r.measures)}</td>
                <td className="num">{r.email_ids.length}</td>
                <td className="num">{t ? count(t.requests) : '—'}</td>
                <td className="num">{t ? count(t.input_tokens) : '—'}</td>
                <td className="num">{t ? count(t.cached_input_tokens) : '—'}</td>
                <td className="num">{t ? count(t.output_tokens) : '—'}</td>
                <td className="num">{t ? cost(t.cost_usd) : '—'}</td>
                <td className="num">{t && r.email_ids.length ? cost(t.cost_usd / r.email_ids.length) : '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export function PerEmailTable({ run }: { run: Run }) {
  const pe = run.per_email
  if (!pe) return <p className="muted">No per-email data for this run (runs before stage 2 did not record it).</p>
  const outcome = new Map((run.email_outcomes ?? []).map((o) => [o.email_id, o.outcome]))
  return (
    <>
      <p className="muted small">{pe.method} Coordinator, Checker and Chaser work for the whole run is shown as overhead.</p>
      <div className="table-wrap">
        <table className="grid">
          <caption className="sr-only">Tokens and cost per email</caption>
          <thead>
            <tr>
              <th scope="col">Email</th>
              <th scope="col">Outcome</th>
              <th scope="col" className="num">Input</th>
              <th scope="col" className="num">Cached</th>
              <th scope="col" className="num">Output</th>
              <th scope="col" className="num">Cost</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(pe.emails).map(([id, r]) => (
              <tr key={id}>
                <th scope="row" className="mono">{id}</th>
                <td className="small">{(outcome.get(id) ?? '—').replaceAll('_', ' ')}{r.processed_by_model ? '' : ' (no model call)'}</td>
                <td className="num">{count(Math.round(r.input_tokens))}</td>
                <td className="num">{count(Math.round(r.cached_input_tokens))}</td>
                <td className="num">{count(Math.round(r.output_tokens))}</td>
                <td className="num">{cost(r.cost_usd)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row">Run overhead</th>
              <td className="small">Coordinator, Checker, Chaser</td>
              <td className="num">{count(pe.run_overhead.input_tokens)}</td>
              <td className="num">{count(pe.run_overhead.cached_input_tokens)}</td>
              <td className="num">{count(pe.run_overhead.output_tokens)}</td>
              <td className="num">{cost(pe.run_overhead.cost_usd)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </>
  )
}

export function RunDetails({ version, preferredRunId }: { version: number; preferredRunId: string | null }) {
  const runs = useLoad(api.runs, [version])
  const [id, setId] = useState<string | null>(preferredRunId)
  const [run, setRun] = useState<Run | null>(null)
  const [events, setEvents] = useState<RunEvent[]>([])

  useEffect(() => {
    if (!id && runs.data?.runs[0]) setId(runs.data.runs[0].run_id)
  }, [runs.data, id])
  useEffect(() => {
    if (preferredRunId) setId(preferredRunId)
  }, [preferredRunId])

  useEffect(() => {
    if (!id) return
    let alive = true
    const load = async () => {
      try {
        const [r, ev] = await Promise.all([api.run(id), api.events(id)])
        if (!alive) return
        setRun(r)
        setEvents(ev.events)
        if (r.status === 'queued' || r.status === 'running') window.setTimeout(load, 2000)
      } catch {
        /* ignore */
      }
    }
    void load()
    return () => {
      alive = false
    }
  }, [id, version])

  const list = runs.data?.runs ?? []
  return (
    <div className="stack">
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>Run details</h2>
            <p className="muted">What each agent did, and what it cost. Every step here is also in the append-only audit trail.</p>
          </div>
          {list.length > 0 && (
            <div>
              <label htmlFor="run-pick" className="sr-only">
                Run
              </label>
              <select id="run-pick" className="input" value={id ?? ''} onChange={(e) => setId(e.target.value)}>
                {list.map((r) => (
                  <option key={r.run_id} value={r.run_id}>
                    {r.run_id} · {r.mode} · {r.status} · {r.email_ids.length} emails · {new Date(r.created_at).toLocaleString()}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
        {list.length === 0 && <p className="empty">No runs yet.</p>}
        {run && (
          <dl className="facts inline">
            <div>
              <dt>Status</dt>
              <dd>
                {run.status}
                {run.reason ? ` — ${run.reason}` : ''}
              </dd>
            </div>
            <div>
              <dt>Emails</dt>
              <dd>{run.email_ids.length}</dd>
            </div>
            <div>
              <dt>Proposals</dt>
              <dd>
                {run.proposals?.total ?? '…'} ({run.proposals?.by_status.blocked ?? 0} blocked)
              </dd>
            </div>
            <div>
              <dt>Blocked by</dt>
              <dd>
                {run.proposals && Object.keys(run.proposals.blocked_by_defense).length > 0
                  ? Object.entries(run.proposals.blocked_by_defense)
                      .map(([k, v]) => `${k} ×${v}`)
                      .join(', ')
                  : '—'}
              </dd>
            </div>
          </dl>
        )}
      </section>

      {list.length > 0 && (
        <section className="panel" aria-labelledby="runs-h">
          <h3 id="runs-h">All runs: tokens and cost</h3>
          <RunsTable runs={list} current={id} onPick={setId} />
        </section>
      )}

      {run && (
        <section className="panel" aria-labelledby="tok-h">
          <h3 id="tok-h">Tokens and cost by agent ({run.run_id})</h3>
          <UsageTable run={run} />
        </section>
      )}

      {run && (
        <section className="panel" aria-labelledby="pe-h">
          <h3 id="pe-h">Tokens and cost by email</h3>
          <PerEmailTable run={run} />
        </section>
      )}

      {run && (
        <section className="panel" aria-labelledby="trace-h">
          <h3 id="trace-h">Agent trace ({events.length} steps)</h3>
          <ol className="trace">
            {events.map((e) => (
              <li key={e.seq} className={`ev ev-${e.step}`}>
                <span className="ev-time mono">{timeLabel(e.ts)}</span>
                <span className={`agent-chip a-${e.agent ?? 'system'}`}>{e.agent ?? 'system'}</span>
                <span className="ev-step">{STEP_TEXT[e.step] ?? e.step}</span>
                <span className="ev-name mono">{e.name ?? ''}</span>
                <span className="ev-detail">
                  {e.stop_reason && e.step !== 'final_answer' ? e.stop_reason : e.result_summary ?? ''}
                  {e.step === 'model_response' && e.usage
                    ? ` · in ${count(e.usage.input_tokens ?? 0)} (cached ${count(e.usage.cached_input_tokens ?? 0)}) / out ${count(e.usage.output_tokens ?? 0)}`
                    : ''}
                </span>
              </li>
            ))}
          </ol>
        </section>
      )}
    </div>
  )
}
