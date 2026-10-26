export interface Stat {
  label: string
  value: string
  note?: string
  tone?: 'default' | 'warn' | 'good' | 'bad'
}

/** Full-width band at the top of each screen: a title, one-line purpose, and 2-4 big numbers. */
export function HeadlineBand({ title, purpose, stats }: { title: string; purpose: string; stats: Stat[] }) {
  return (
    <section className="band" aria-labelledby="band-title">
      <div className="band-inner">
        <div className="band-text">
          <h2 id="band-title">{title}</h2>
          <p>{purpose}</p>
        </div>
        <dl className="stats">
          {stats.map((s) => (
            <div key={s.label} className={`stat ${s.tone ?? 'default'}`}>
              <dt>{s.label}</dt>
              <dd>
                <span className="stat-value">{s.value}</span>
                {s.note && <span className="stat-note">{s.note}</span>}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  )
}

const STEPS = [
  { n: 1, title: 'Choose emails', text: 'Tick the staff emails to read.' },
  { n: 2, title: 'Review proposed changes', text: 'See each change next to the email that supports it.' },
  { n: 3, title: 'Approve', text: 'Nothing changes in a tracker until you approve it.' },
  { n: 4, title: 'Chase late updates', text: 'Copy a drafted nudge to whoever has not reported.' },
]

export function HowItWorks() {
  return (
    <ol className="how" aria-label="How it works">
      {STEPS.map((s) => (
        <li key={s.n}>
          <span className="how-n" aria-hidden="true">
            {s.n}
          </span>
          <span>
            <strong>{s.title}</strong>
            <span className="how-text">{s.text}</span>
          </span>
        </li>
      ))}
    </ol>
  )
}
