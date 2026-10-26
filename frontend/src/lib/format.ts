import type { CellValue, DefenseKey } from '../api'

const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 })
const usdRound = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })
const int = new Intl.NumberFormat('en-US')

export const money = (n: number) => usd.format(n)
export const moneyShort = (n: number) => usdRound.format(n)
export const count = (n: number) => int.format(n)

export function cost(n: number): string {
  if (n === 0) return '$0.00'
  return n < 0.01 ? `$${n.toFixed(4)}` : `$${n.toFixed(3)}`
}

export function dateLabel(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(`${iso.slice(0, 10)}T12:00:00`)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export function timeLabel(ts: string | null | undefined): string {
  if (!ts) return '—'
  const d = new Date(ts)
  return Number.isNaN(d.getTime()) ? ts : d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export const FIELD_LABELS: Record<string, string> = {
  spent_to_date: 'Spent to date',
  committed: 'Committed',
  annual_budget: 'Annual budget',
  status: 'Status',
  percent_complete: '% complete',
  due_date: 'Due date',
  notes: 'Notes',
}

export const STATUS_LABELS: Record<string, string> = {
  not_started: 'Not started',
  in_progress: 'In progress',
  complete: 'Complete',
  at_risk: 'At risk',
  blocked: 'Blocked',
}

export function cellText(field: string, v: CellValue): string {
  if (v === null || v === undefined || v === '') return '—'
  if (field === 'spent_to_date' || field === 'committed' || field === 'annual_budget') return money(Number(v))
  if (field === 'percent_complete') return `${v}%`
  if (field === 'status') return STATUS_LABELS[String(v)] ?? String(v)
  if (field === 'due_date') return dateLabel(String(v))
  return String(v)
}

export const DEFENSE_HELP: Record<DefenseKey, string> = {
  untrusted_email: 'The email tried to give the AI instructions, so nothing from it is accepted automatically.',
  grounding: 'Every number and date must appear in the email, and the quote must be copied from it.',
  permission: 'Senders may only change rows that belong to their own program.',
  rules: 'Only allowed fields and values; no silent overspending.',
  caps: 'Per-run limits on emails and proposals.',
}

export interface Segment {
  text: string
  mark: boolean
}

const norm = (s: string) => s.replace(/\s+/g, ' ').toLowerCase()

/** Split `body` into segments with the first occurrence of `quote` marked (whitespace/case-insensitive). */
export function highlightQuote(body: string, quote: string): Segment[] {
  const q = norm(quote.trim())
  if (!q) return [{ text: body, mark: false }]
  // Map each character of the normalised body back to its index in the original.
  const map: number[] = []
  let flat = ''
  let prevSpace = false
  for (let i = 0; i < body.length; i++) {
    const ch = body[i] ?? ''
    if (/\s/.test(ch)) {
      if (prevSpace) continue
      prevSpace = true
      flat += ' '
    } else {
      prevSpace = false
      flat += ch.toLowerCase()
    }
    map.push(i)
  }
  const at = flat.indexOf(q)
  if (at < 0) return [{ text: body, mark: false }]
  const start = map[at] ?? 0
  const end = (map[at + q.length - 1] ?? body.length - 1) + 1
  return [
    { text: body.slice(0, start), mark: false },
    { text: body.slice(start, end), mark: true },
    { text: body.slice(end), mark: false },
  ].filter((s) => s.text.length > 0)
}

export function firstName(full: string): string {
  return full.split(' ')[0] ?? full
}
