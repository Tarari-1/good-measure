import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PastePanel } from './PastePanel'

afterEach(() => vi.restoreAllMocks())

describe('PastePanel', () => {
  it('sends the pasted email to the paste route and reports the run', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ email_id: 'p001', run_id: 'abcdef123456', status: 'queued' }), { status: 202 }))
    vi.stubGlobal('fetch', fetchMock)
    const onStarted = vi.fn()
    render(<PastePanel running={false} onStarted={onStarted} />)
    await userEvent.click(screen.getByRole('button', { name: 'Paste an email' }))
    await userEvent.type(screen.getByLabelText('From email'), 'saoirse.calloway@brightfutures.example')
    await userEvent.type(screen.getByLabelText('Subject'), 'Progress')
    await userEvent.type(screen.getByLabelText('Body'), 'The workshop series (WP-16) is now 60% complete.')
    await userEvent.click(screen.getByRole('button', { name: 'Process this email' }))
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toMatch(/\/api\/emails\/paste$/)
    expect(JSON.parse(String(init.body))).toMatchObject({ from_email: 'saoirse.calloway@brightfutures.example', subject: 'Progress' })
    expect(onStarted).toHaveBeenCalledWith('abcdef123456')
    expect(await screen.findByText(/Saved as p001/)).toBeInTheDocument()
  })
})
