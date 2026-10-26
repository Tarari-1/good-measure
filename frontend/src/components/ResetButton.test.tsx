import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ResetButton } from './ResetButton'

afterEach(() => vi.restoreAllMocks())

describe('ResetButton', () => {
  it('only resets after the user confirms', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true, checksums_match: true }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const onDone = vi.fn()
    render(<ResetButton onDone={onDone} />)
    await userEvent.click(screen.getByRole('button', { name: 'Reset demo data' }))
    expect(fetchMock).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Yes, reset everything', hidden: true }))
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toMatch(/\/api\/reset$/)
    expect(JSON.parse(String(init.body))).toEqual({ confirm: true })
    expect(onDone).toHaveBeenCalled()
  })
})
