import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { Run, RunListItem, UsageRow } from '../api'
import { PerEmailTable, RunsTable } from './RunDetails'

const u = (input: number, cached: number, output: number, cost: number): UsageRow => ({
  requests: 1, tool_calls: 1, input_tokens: input, cached_input_tokens: cached, cache_write_tokens: 0, output_tokens: output, cost_usd: cost,
})

describe('Run details cost tables', () => {
  it('shows cost per run and per email, including emails skipped before any model call', () => {
    const runs: RunListItem[] = [{ run_id: 'abcdef123456', status: 'finished', mode: 'live', created_at: '', finished_at: null,
      email_ids: ['e01', 'e18'], reason: null, measures: { prefilter_emails: true, batch_intake: false },
      usage: { per_agent: {} as never, total: u(10000, 4000, 500, 0.00119), pricing: { placeholders: false, input_per_mtok: 0.1, cached_input_per_mtok: 0.01, output_per_mtok: 0.5 },
        caps: { request_limit: 80, tool_calls_limit: 220, total_tokens_limit: 700000, run_timeout_s: 900 } } }]
    render(<RunsTable runs={runs} current="abcdef123456" onPick={vi.fn()} />)
    expect(screen.getByText('off: batch intake')).toBeInTheDocument()
    expect(screen.getByText('$0.0012')).toBeInTheDocument()

    const run = { run_id: 'abcdef123456', email_outcomes: [{ email_id: 'e18', outcome: 'skipped_auto_reply', proposal_ids: [], note: '' }],
      per_email: { method: 'split evenly.', emails: { e01: { ...u(3000, 1000, 200, 0.0003), processed_by_model: true },
        e18: { ...u(0, 0, 0, 0), processed_by_model: false } }, run_overhead: u(7000, 3000, 300, 0.0006) } } as unknown as Run
    render(<PerEmailTable run={run} />)
    expect(screen.getByText(/skipped auto reply \(no model call\)/)).toBeInTheDocument()
    expect(screen.getByText('Run overhead')).toBeInTheDocument()
  })
})
