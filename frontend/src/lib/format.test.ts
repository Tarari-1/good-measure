import { describe, expect, it } from 'vitest'
import { cellText, highlightQuote } from './format'

describe('highlightQuote', () => {
  it('marks the quote ignoring case and extra whitespace', () => {
    const body = 'Hi Jordan,\n\nWe paid Little Owl Books $1,240.50\ntoday. Thanks'
    const segs = highlightQuote(body, 'we paid little owl books $1,240.50 today')
    expect(segs.filter((s) => s.mark).map((s) => s.text)).toEqual(['We paid Little Owl Books $1,240.50\ntoday'])
    expect(segs.map((s) => s.text).join('')).toBe(body)
  })
  it('returns the body unmarked when the quote is not present', () => {
    expect(highlightQuote('abc', 'xyz')).toEqual([{ text: 'abc', mark: false }])
  })
})

describe('cellText', () => {
  it('formats money, percent and status', () => {
    expect(cellText('spent_to_date', 4090.5)).toBe('$4,090.50')
    expect(cellText('percent_complete', 60)).toBe('60%')
    expect(cellText('status', 'in_progress')).toBe('In progress')
  })
})
