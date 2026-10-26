import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { DefenseKey, Proposal } from '../api'
import { ProposalCard } from './ProposalCard'

const defenses: Record<DefenseKey, string> = {
  untrusted_email: '1 · Untrusted email',
  grounding: '2 · Grounding',
  permission: '3 · Permission',
  rules: '4 · Rules',
  caps: '5 · Run caps',
}

function proposal(over: Partial<Proposal> = {}): Proposal {
  return {
    id: 'PR-0001', run_id: 'abc', tracker: 'budget', email_id: 'e01', row_id: 'READ-02', row_label: 'Levelled readers & books',
    field: 'spent_to_date', amount: 1240.5, new_value: null, before: 2850, after: 4090.5,
    quote: 'we paid Little Owl Books $1,240.50 today', rationale: 'invoice paid', overspend_flag: false, program: 'READ',
    sender: 'owen@x.example', sender_name: 'Owen', status: 'pending', blocks: [], warnings: [], checker_review: null,
    created_at: '', decided_by: null, decided_at: null,
    email: { subject: 'Books', from_name: 'Owen Castellano', from_email: 'owen@x.example', date: '2026-10-16',
      body: 'Hi,\nwe paid Little Owl Books $1,240.50 today for readers.' },
    ...over,
  }
}

describe('ProposalCard', () => {
  it('shows before/after and highlights the supporting quote', () => {
    render(<ProposalCard p={proposal()} defenses={defenses} approver="Jordan" onApprove={vi.fn()} onReject={vi.fn()} />)
    expect(screen.getByText('$2,850.00')).toBeInTheDocument()
    expect(screen.getByText('$4,090.50')).toBeInTheDocument()
    expect(document.querySelector('mark')?.textContent).toBe('we paid Little Owl Books $1,240.50 today')
  })

  it('needs an approver name before approving', async () => {
    const onApprove = vi.fn().mockResolvedValue(undefined)
    const { rerender } = render(<ProposalCard p={proposal()} defenses={defenses} approver="" onApprove={onApprove} onReject={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Approve and apply' })).toBeDisabled()
    rerender(<ProposalCard p={proposal()} defenses={defenses} approver="Demo Approver" onApprove={onApprove} onReject={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: 'Approve and apply' }))
    expect(onApprove).toHaveBeenCalledWith('PR-0001', false)
  })

  it('shows the defense that blocked a proposal and offers no approve button', () => {
    const p = proposal({ status: 'blocked', blocks: [{ defense: 'permission', reason: 'Marcus (TEEN) may only change TEEN rows.' }] })
    render(<ProposalCard p={p} defenses={defenses} approver="Jordan" onApprove={vi.fn()} onReject={vi.fn()} />)
    expect(screen.getByText('3 · Permission')).toBeInTheDocument()
    expect(screen.getByText(/may only change TEEN rows/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Approve and apply' })).toBeNull()
  })

  it('shows the amber Over budget panel and needs the acknowledgement before approving', async () => {
    const onApprove = vi.fn().mockResolvedValue(undefined)
    const p = proposal({ email_id: 'e10', row_id: 'FAM-01', row_label: 'Catering & meals', amount: 2850, before: 4300, after: 7150,
      overspend_flag: true, warnings: [{ type: 'overspend', message: 'OVERSPEND' }],
      overspend: { line_id: 'FAM-01', kind: 'spend', budget: 8000, spent_after: 7150, committed_after: 900, overage: 50,
        spent_over_budget: 0, new_remaining: -50, unfunded_commitments: 50,
        consequence: 'Approving records this spend (money already spent). FAM-01 is then over budget by $50.00; $50.00 of existing commitments are now unfunded.' } })
    render(<ProposalCard p={p} defenses={defenses} approver="Demo Approver" onApprove={onApprove} onReject={vi.fn()} />)
    expect(screen.getByLabelText('Over budget')).toHaveTextContent('spend is recorded, not rejected')
    expect(screen.getByText(/over budget by \$50.00/)).toBeInTheDocument()
    const btn = screen.getByRole('button', { name: 'Approve and apply' })
    expect(btn).toBeDisabled()
    await userEvent.click(screen.getByRole('checkbox', { name: /I understand FAM-01 will be \$50.00 over budget/ }))
    expect(btn).toBeEnabled()
    await userEvent.click(btn)
    expect(onApprove).toHaveBeenCalledWith('PR-0001', true)
  })
})
