import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Inbox } from './Inbox'

afterEach(() => vi.restoreAllMocks())

const emails = [
  { id: 'e01', from_name: 'Owen Castellano', from_email: 'o@x.example', subject: 'Books invoice paid', date: '2026-10-16',
    snippet: 'paid', selected: false, program: 'READ', on_roster: true, flagged: false },
  { id: 'e08', from_name: 'Rhea Mbatha', from_email: 'r@x.example', subject: 'Fwd: note', date: '2026-10-22',
    snippet: 'fwd', selected: false, program: 'LIB', on_roster: true, flagged: true },
]

describe('Inbox', () => {
  it('lets the user tick emails and start a run with exactly those ids', async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/api/emails')) return new Response(JSON.stringify({ emails, selected: [], max_per_run: 25 }))
      if (url.endsWith('/api/runs')) return new Response(JSON.stringify({ run_id: 'abcdef123456', status: 'queued' }), { status: 202 })
      return new Response(JSON.stringify({ selected: init ? JSON.parse(String(init.body)).email_ids : [] }))
    })
    vi.stubGlobal('fetch', fetchMock)
    const onStarted = vi.fn()
    render(<Inbox version={0} running={false} maxPerRun={25} onStarted={onStarted} />)
    expect(await screen.findByText('Books invoice paid')).toBeInTheDocument()
    expect(screen.getByText('suspicious instructions')).toBeInTheDocument()
    const go = screen.getByRole('button', { name: /Process selected/ })
    expect(go).toBeDisabled()
    await userEvent.click(screen.getByLabelText(/Select email from Owen Castellano/))
    expect(go).toHaveTextContent('Process selected (1)')
    await userEvent.click(go)
    const runCall = fetchMock.mock.calls.find(([u]) => String(u).endsWith('/api/runs'))!
    expect(JSON.parse(String(runCall[1]!.body))).toEqual({ email_ids: ['e01'] })
    expect(onStarted).toHaveBeenCalledWith('abcdef123456')
  })
})
