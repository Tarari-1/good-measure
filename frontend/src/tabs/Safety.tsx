import { useState } from 'react'
import { api, type SelfTest } from '../api'
import { cellText, dateLabel } from '../lib/format'
import { useLoad } from '../lib/usePoll'

const SKIP_TEXT: Record<string, string> = {
  skipped_quarantined: 'Quarantined',
  skipped_not_on_roster: 'Sender not on roster',
  skipped_no_tracker_rows: 'Sender owns no tracker rows',
  skipped_auto_reply: 'Automatic reply',
}

export function Safety({ version }: { version: number }) {
  const info = useLoad(api.safety, [version])
  const [test, setTest] = useState<SelfTest | null>(null)
  const [running, setRunning] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const d = info.data

  const runTests = async () => {
    setRunning(true)
    setErr(null)
    try {
      setTest(await api.selftest())
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'The self-test failed to run.')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="stack">
      <section className="panel" aria-labelledby="safety-h">
        <h2 id="safety-h">Safety</h2>
        <p className="muted">
          Five checks written in plain code (no AI) stand between an email and your trackers. Agents can only propose; a change is written
          only after these checks pass, a person approves it, and the checks pass again.
        </p>
        <ol className="defenses">
          {d?.defenses.map((x) => (
            <li key={x.key} className="defense-card">
              <span className={`defense-tag d-${x.key}`}>{x.label}</span>
              <p>{x.detail}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="panel" aria-labelledby="selftest-h">
        <div className="panel-head">
          <div>
            <h3 id="selftest-h">Check the defenses now</h3>
            <p className="muted small">
              Runs the deterministic defense tests (tests/test_defenses.py) on a scratch copy of the data. No model is called.
            </p>
          </div>
          <button type="button" className="btn primary" onClick={() => void runTests()} disabled={running}>
            {running ? 'Running tests…' : 'Run defense tests'}
          </button>
        </div>
        {err && <p className="alert bad">{err}</p>}
        {test && (
          <>
            <p className={`alert ${test.failed ? 'bad' : 'good'}`} role="status">
              {test.passed} of {test.total} tests passed{test.failed ? `, ${test.failed} failed` : ''}. Model calls: {test.model_calls}.
            </p>
            <ul className="test-list">
              {test.tests.map((t) => (
                <li key={t.name} className={t.passed ? 'pass' : 'fail'}>
                  <span className="test-mark" aria-hidden="true">{t.passed ? '✓' : '✗'}</span>
                  <span className="mono">{t.name.replace(/^test_/, '').replaceAll('_', ' ')}</span>
                  <span className="sr-only">{t.passed ? 'passed' : 'failed'}</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      <section className="panel" aria-labelledby="blocks-h">
        <h3 id="blocks-h">Blocks in the latest run{d?.latest_run ? ` (${d.latest_run.run_id}, ${d.latest_run.mode})` : ''}</h3>
        {!d?.latest_run && <p className="empty">No runs yet.</p>}
        {d?.latest_run && d.blocks.length === 0 && <p className="empty">No proposal was blocked in this run.</p>}
        <ul className="flat">
          {d?.blocks.map((b) => (
            <li key={b.id} className="block-row">
              <strong className="mono">{b.id}</strong> <span className="mono">{b.row_id}</span> {b.field} →{' '}
              {cellText(b.field, b.amount ?? b.new_value)} <span className="muted small">from {b.email_id}</span>
              <ul className="reasons">
                {b.blocks.map((x, i) => (
                  <li key={i}>
                    <span className={`defense-tag d-${x.defense}`}>{d.defenses.find((k) => k.key === x.defense)?.label}</span> {x.reason}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
        {d && d.skipped.length > 0 && (
          <>
            <h4 className="h4">Skipped by code before any model call</h4>
            <ul className="flat">
              {d.skipped.map((s) => (
                <li key={s.email_id}>
                  <span className="tag">{SKIP_TEXT[s.outcome] ?? s.outcome}</span> <strong className="mono">{s.email_id}</strong> {s.note}
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      <section className="panel" aria-labelledby="quar-h">
        <h3 id="quar-h">Quarantined emails</h3>
        {d?.quarantined.length === 0 && <p className="empty">No email in the latest run tried to instruct the AI.</p>}
        {d?.quarantined.map((q) => (
          <article key={q.email_id} className="card blocked">
            <p className="eyebrow">
              {q.email_id} · {q.email?.from_email} · {dateLabel(q.email?.date)}
            </p>
            <h4 className="h4">{q.email?.subject}</h4>
            <p>
              <span className="defense-tag d-untrusted_email">1 · Untrusted email</span> {q.reason}
            </p>
            <p className="small">
              Phrases that triggered it:{' '}
              {q.phrases.map((p, i) => (
                <mark key={i}>{p}</mark>
              ))}
            </p>
            {q.email && <pre className="email-text">{q.email.body}</pre>}
          </article>
        ))}
      </section>
    </div>
  )
}
