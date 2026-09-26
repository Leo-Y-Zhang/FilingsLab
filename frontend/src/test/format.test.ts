/**
 * Calendar dates from the API are "YYYY-MM-DD" strings. `new Date()` reads
 * those as midnight UTC, so everywhere west of Greenwich rendered them one day
 * early: the Forecast table labelled Monday's prediction "Sun 27 Sept" in New
 * York, and TraderDetail showed every trade and disclosure date a day before
 * the filing. On a page about disclosure delay, the dates are the data.
 *
 * Pinned in America/New_York, where the bug shows. Watched failing first.
 */
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'
import { fmtDate, parseDate } from '@/utils/format'

beforeAll(() => {
  vi.stubEnv('TZ', 'America/New_York')
})

afterAll(() => {
  vi.unstubAllEnvs()
})

describe('date-only strings are calendar days', () => {
  it('parses to the same day in a timezone behind UTC', () => {
    const d = parseDate('2026-09-28')
    expect([d.getFullYear(), d.getMonth(), d.getDate(), d.getDay()]).toEqual([2026, 8, 28, 1])
  })

  it('formats a disclosure date as the date it is', () => {
    expect(fmtDate('2026-09-28')).toBe('Sep 28, 2026')
    expect(fmtDate('2024-01-01')).toBe('Jan 1, 2024')
  })

  it('labels a forecast day with its own weekday', () => {
    expect(
      parseDate('2026-09-28').toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' }),
    ).toMatch(/^Mon 28 Sept?$/)
  })

  it('leaves timestamps with a time part to Date', () => {
    expect(parseDate('2026-09-28T12:00:00Z').toISOString()).toBe('2026-09-28T12:00:00.000Z')
  })

  it('still renders a dash for a missing date', () => {
    expect(fmtDate(null)).toBe('—')
    expect(fmtDate('')).toBe('—')
  })
})
