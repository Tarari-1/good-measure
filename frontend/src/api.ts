// Typed client for the Good Measure API (backend/main.py). Field names match the JSON exactly.

export const API_BASE: string = (import.meta.env.VITE_API_BASE ?? 'http://localhost:8000').replace(/\/+$/, '')

export const AGENTS = ['coordinator', 'intake', 'checker', 'chaser'] as const
export type AgentName = (typeof AGENTS)[number]

export interface Health {
  ok: boolean
  model: string
  org: string
  today: string
  env_source: string
  mode: 'live' | 'stub'
  run_in_progress: string | null
  email_source: string
  tracker_owner: string
  caps: { max_emails_per_run: number }
  measures: Record<string, boolean>
  imap_configured: boolean
  pricing: Pricing
}

export interface Pricing {
  placeholders: boolean
  source?: string
  input_per_mtok: number
  cached_input_per_mtok: number
  cache_write_per_mtok?: number
  output_per_mtok: number
}

export interface EmailSummary {
  id: string
  from_name: string
  from_email: string
  subject: string
  date: string
  snippet: string
  selected: boolean
  program: string | null
  on_roster: boolean
  flagged: boolean
  origin: 'sample' | 'pasted' | 'imported'
}

export interface EmailFull {
  id: string
  from_name: string
  from_email: string
  to: string
  subject: string
  date: string
  body: string
  flagged_phrases: string[]
}

export type DefenseKey = 'untrusted_email' | 'grounding' | 'permission' | 'rules' | 'caps'
export interface Block {
  defense: DefenseKey
  reason: string
}
export interface Warning {
  type: string
  message: string
}
export type ProposalStatus = 'pending' | 'blocked' | 'approved' | 'rejected'
export type CellValue = string | number | null

export interface Proposal {
  id: string
  run_id: string
  tracker: 'budget' | 'workplan'
  email_id: string
  row_id: string
  row_label: string | null
  field: string
  amount: number | null
  new_value: CellValue
  before: CellValue
  after: CellValue
  quote: string
  rationale: string
  overspend_flag: boolean
  program: string | null
  sender: string | null
  sender_name: string | null
  status: ProposalStatus
  blocks: Block[]
  warnings: Warning[]
  checker_review: { verdict: 'looks_right' | 'concern'; note: string; verified?: boolean; problems?: string[] } | null
  created_at: string
  decided_by: string | null
  decided_at: string | null
  rejection_reason?: string | null
  email: { subject: string; from_name: string; from_email: string; date: string; body: string } | null
}

export interface ProposalList {
  proposals: Proposal[]
  defenses: Record<DefenseKey, string>
}

export interface UsageRow {
  requests: number
  tool_calls: number
  input_tokens: number
  cached_input_tokens: number
  cache_write_tokens?: number
  output_tokens: number
  cost_usd: number
}
export interface UsageBlock {
  per_agent: Record<AgentName, UsageRow>
  total: UsageRow
  pricing: Pricing
  caps: { request_limit: number; tool_calls_limit: number; total_tokens_limit: number; run_timeout_s: number }
}

export type RunStatus = 'queued' | 'running' | 'finished' | 'stopped' | 'error'
export interface EmailOutcome {
  email_id: string
  outcome: string
  proposal_ids: string[]
  note: string
}
export interface EmailFlag {
  email_id: string
  defense: DefenseKey
  reason: string
  phrases: string[]
}
export interface Digest {
  headline: string
  burn_vs_plan: { program: string; burn_pct: number; plan_pct: number; comment: string }[]
  at_risk_milestones: string[]
  late_owners: string[]
  proposals_summary: string
  decisions_for_tracker_owner: string[]
}
export interface Run {
  run_id: string
  status: RunStatus
  mode: 'live' | 'stub'
  email_ids: string[]
  created_at: string
  finished_at: string | null
  reason: string | null
  history: { status: RunStatus; at: string }[]
  email_flags?: EmailFlag[]
  email_outcomes?: EmailOutcome[]
  digest?: Digest | null
  usage?: UsageBlock
  proposals?: { total: number; by_status: Partial<Record<ProposalStatus, number>>; blocked_by_defense: Partial<Record<DefenseKey, number>>; ids: string[] }
  nudge_ids?: string[]
  measures?: Record<string, boolean>
  per_email?: {
    emails: Record<string, UsageRow & { processed_by_model: boolean }>
    run_overhead: UsageRow
    method: string
  }
  checker?: { reviews: { proposal_id: string; verdict: string; note: string }[]; summary: string } | null
}
export interface RunListItem {
  run_id: string
  status: RunStatus
  mode: 'live' | 'stub'
  created_at: string
  finished_at: string | null
  email_ids: string[]
  reason: string | null
  proposals?: Run['proposals']
  usage?: UsageBlock
  measures?: Record<string, boolean>
}

export interface SafetyInfo {
  defenses: { key: DefenseKey; label: string; detail: string }[]
  latest_run: { run_id: string; mode: string; created_at: string; status: RunStatus } | null
  blocks: { id: string; email_id: string; row_id: string; field: string; amount: number | null; new_value: CellValue; status: ProposalStatus; blocks: Block[]; sender: string | null }[]
  quarantined: (EmailFlag & { email: EmailFull | null })[]
  skipped: EmailOutcome[]
}
export interface SelfTest {
  passed: number
  failed: number
  total: number
  model_calls: number
  tests: { name: string; passed: boolean; seconds: number }[]
}
export interface ImapMessage {
  uid: string
  from_name: string
  from_email: string
  subject: string
  date: string
}

export interface RunEvent {
  seq: number
  ts: string
  run_id: string
  agent: AgentName | null
  step: string
  name: string | null
  arguments: Record<string, unknown> | null
  result_summary: string | null
  usage: Record<string, number> | null
  stop_reason: string | null
}

export interface BudgetLine {
  line_id: string
  program: string
  category: string
  annual_budget: number
  spent_to_date: number
  committed: number
  owner: string
  remaining: number
  changed_fields: string[]
}
export interface Activity {
  id: string
  program: string
  activity: string
  owner: string
  due_date: string
  status: string
  percent_complete: number
  notes: string
  depends_on: string | null
  changed_fields: string[]
  overdue: boolean
}
export interface Program {
  code: string
  name: string
  lead_email: string
}
export interface Change {
  id: number
  tracker: 'budget' | 'workplan'
  row_id: string
  field: string
  old_value: string
  new_value: string
  proposal_id: string
  approved_by: string
  applied_at: string
}

export interface OverdueOwner {
  name: string
  email: string
  program: string
  program_name: string
  role: string
  team_reported: boolean
  last_email: string | null
  overdue_activities: { id: string; activity: string; due_date: string; percent_complete: number; status: string }[]
  reasons: string[]
}
export interface Nudge {
  id: string
  run_id: string
  recipient_name: string
  recipient_email: string
  program: string
  subject: string
  body: string
  reasons: string[]
  status: 'draft'
  sent: false
  created_at: string
}

export interface ProgramMetrics {
  program: string
  name: string
  annual_budget: number
  spent_to_date: number
  committed: number
  burn_pct: number
  committed_pct: number
  plan_pct: number
  variance_pts: number
  lines_over_90pct: string[]
}
export interface DigestResponse {
  metrics: {
    today: string
    plan_pct: number
    programs: ProgramMetrics[]
    totals: { annual_budget: number; spent_to_date: number; committed: number }
    at_risk: (Activity & { risk: string })[]
    late_owners: OverdueOwner[]
    pending_proposals: number
  }
  latest: { run_id: string; created_at: string; mode: string; digest: Digest } | null
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function detailMessage(detail: unknown, fallback: string): string {
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object' && 'reason' in detail && typeof detail.reason === 'string') return detail.reason
  if (Array.isArray(detail) && detail[0] && typeof detail[0] === 'object' && 'msg' in detail[0]) return String(detail[0].msg)
  return fallback
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
    })
  } catch {
    throw new ApiError(0, `Cannot reach the backend at ${API_BASE}. Is it running?`)
  }
  if (!res.ok) {
    let detail: unknown = null
    try {
      detail = ((await res.json()) as { detail?: unknown }).detail
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detailMessage(detail, `Request failed (${res.status})`))
  }
  return (await res.json()) as T
}

const post = <T>(path: string, body: unknown) => request<T>(path, { method: 'POST', body: JSON.stringify(body) })

export const api = {
  health: () => request<Health>('/api/health'),
  emails: () => request<{ emails: EmailSummary[]; selected: string[]; max_per_run: number }>('/api/emails'),
  email: (id: string) => request<EmailFull>(`/api/emails/${encodeURIComponent(id)}`),
  saveSelection: (ids: string[]) =>
    request<{ selected: string[] }>('/api/emails/selection', { method: 'PUT', body: JSON.stringify({ email_ids: ids }) }),
  startRun: (ids: string[]) => post<{ run_id: string; status: RunStatus }>('/api/runs', { email_ids: ids }),
  runs: () => request<{ runs: RunListItem[]; current: string | null }>('/api/runs'),
  run: (id: string) => request<Run>(`/api/runs/${id}`),
  events: (id: string, after = 0) =>
    request<{ events: RunEvent[]; next: number; total: number }>(`/api/runs/${id}/events?after=${after}`),
  proposals: () => request<ProposalList>('/api/proposals'),
  approve: (id: string, approver: string) => post<{ ok: true; proposal: Proposal }>(`/api/proposals/${id}/approve`, { approver }),
  reject: (id: string, approver: string, reason?: string) =>
    post<{ ok: true; proposal: Proposal }>(`/api/proposals/${id}/reject`, { approver, reason: reason || null }),
  budget: () => request<{ lines: BudgetLine[]; programs: Program[]; today: string }>('/api/trackers/budget'),
  workplan: () => request<{ activities: Activity[]; programs: Program[]; today: string }>('/api/trackers/workplan'),
  changes: () => request<{ changes: Change[] }>('/api/trackers/changes'),
  exportUrl: () => `${API_BASE}/api/trackers/export.xlsx`,
  overdue: () => request<{ owners: OverdueOwner[]; today: string; window_days: number }>('/api/chase/overdue'),
  drafts: () => request<{ drafts: Nudge[] }>('/api/chase/drafts'),
  digest: () => request<DigestResponse>('/api/digest'),
  reset: () => post<{ ok: boolean; checksums_match: boolean }>('/api/reset', { confirm: true }),
  paste: (e: { from_name: string; from_email: string; subject: string; body: string }) =>
    post<{ email_id: string; run_id: string; status: RunStatus }>('/api/emails/paste', e),
  safety: () => request<SafetyInfo>('/api/safety'),
  selftest: () => post<SelfTest>('/api/safety/selftest', {}),
  imapSearch: (q: { since?: string; sender?: string; subject?: string }) =>
    post<{ messages: ImapMessage[]; max: number }>('/api/imap/search', q),
  imapImport: (uids: string[]) => post<{ imported: string[] }>('/api/imap/import', { uids }),
}
