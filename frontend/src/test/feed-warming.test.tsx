/**
 * A cold visitor must not be left on the steady-state poll.
 *
 * The backend answers a cold feed with `warming: true` and an empty list while
 * two background stages run (crawl SEC EDGAR, then price every filing). The UI
 * polled every 5 minutes regardless, so a lone visitor needed two poll
 * intervals to see data and the page told them it would take "a few seconds".
 * The review measured about ten minutes.
 *
 * The server now states how soon to come back, in `retry_after_seconds`. These
 * tests pin that the client honours it, that the fast poll is confined to the
 * warming state, that it can never be talked into hammering a rate-limited
 * route, and that the banner shows the server's honest wording.
 */
import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const get = vi.fn()
const post = vi.fn()
const del = vi.fn()

vi.mock('axios', () => {
  const instance = {
    get: (...a: any[]) => get(...a),
    post: (...a: any[]) => post(...a),
    delete: (...a: any[]) => del(...a),
    interceptors: { request: { use: vi.fn() } },
  }
  return { default: { create: () => instance } }
})

vi.mock('@/services/api', () => ({
  fetchTraders: vi.fn().mockResolvedValue([]),
  fetchTrader: vi.fn().mockResolvedValue(null),
  fetchTraderTrades: vi.fn().mockResolvedValue([]),
  fetchRankings: vi.fn().mockResolvedValue([]),
  fetchExperiments: vi.fn().mockResolvedValue([]),
  runSimulation: vi.fn().mockResolvedValue({}),
  runMonteCarlo: vi.fn().mockResolvedValue({}),
  runComparison: vi.fn().mockResolvedValue({}),
  fetchFeed: vi.fn().mockResolvedValue([]),
  fetchForecast: vi.fn().mockResolvedValue([]),
}))

import App from '@/App'
import {
  FEED_IDLE_POLL_MS,
  MIN_FEED_POLL_MS,
  feedPollIntervalMs,
  queryClient,
} from '@/services/queryClient'

const warming = (retry?: number) => ({
  configured: true,
  count: 0,
  disclosures: [],
  warming: true,
  message: 'Warming up. This page retries automatically every 15 seconds.',
  ...(retry === undefined ? {} : { retry_after_seconds: retry }),
})

const settled = {
  configured: true,
  count: 1,
  disclosures: [{ ticker: 'AAPL', action: 'buy', score: 90 }],
  warming: false,
  message: null,
}

beforeEach(() => {
  vi.clearAllMocks()
  sessionStorage.clear()
  queryClient.clear()
  get.mockResolvedValue({ data: settled })
})

afterEach(() => {
  sessionStorage.clear()
  queryClient.clear()
})

describe('feed poll interval', () => {
  it('honours the retry interval the warming response asks for', () => {
    expect(feedPollIntervalMs(warming(15), undefined)).toBe(15_000)
    expect(feedPollIntervalMs(warming(20), undefined)).toBe(20_000)
  })

  it('polls fast while warming even if the server sends no hint', () => {
    const interval = feedPollIntervalMs(warming(), undefined)
    expect(interval).toBeLessThanOrEqual(30_000)
    expect(interval).toBeGreaterThanOrEqual(MIN_FEED_POLL_MS)
  })

  it('drops back to the steady-state poll once data arrives', () => {
    expect(feedPollIntervalMs(settled, undefined)).toBe(FEED_IDLE_POLL_MS)
  })

  it('never polls faster than the public rate limit tolerates', () => {
    // The route allows 10 requests a minute per client. A server that asked for
    // a 1-second poll — or a zero, or a negative — must not be obeyed into a
    // self-inflicted 429.
    for (const silly of [0, -5, 1, 0.001]) {
      expect(feedPollIntervalMs(warming(silly), undefined)).toBeGreaterThanOrEqual(
        MIN_FEED_POLL_MS,
      )
    }
    expect(MIN_FEED_POLL_MS).toBeGreaterThanOrEqual(6_000)
  })

  it('stops polling entirely once rate limited, warming or not', () => {
    const rateLimited = { response: { status: 429 } }
    expect(feedPollIntervalMs(warming(15), rateLimited)).toBe(false)
    expect(feedPollIntervalMs(settled, rateLimited)).toBe(false)
  })

  it('polls fast when there is no body yet at all', () => {
    // First mount: no data, no error. Sitting on the 5-minute poll here is the
    // same defect from the other end.
    expect(feedPollIntervalMs(undefined, undefined)).toBeLessThanOrEqual(30_000)
  })
})

describe('warming banner', () => {
  it('shows the wait the server actually reports, not "a few seconds"', async () => {
    get.mockImplementation((url: string) =>
      url.startsWith('/feed/disclosures')
        ? Promise.resolve({ data: warming(15) })
        : Promise.resolve({ data: {} }),
    )

    window.history.pushState({}, '', '/feed')
    render(<App />)

    await waitFor(() =>
      expect(screen.getByText(/retries automatically every 15 seconds/i)).toBeTruthy(),
    )
    const banner = screen.getByRole('status')
    expect(banner.textContent).not.toMatch(/a few seconds/i)
    // And the banner says when it will look again, so the visitor knows the
    // page is working rather than stuck.
    expect(banner.textContent).toMatch(/checking again every 15 seconds/i)
  })

  it('does not fall back to an optimistic wait when the server sends no message', async () => {
    const { message, ...noMessage } = warming(15)
    get.mockImplementation((url: string) =>
      url.startsWith('/feed/disclosures')
        ? Promise.resolve({ data: noMessage })
        : Promise.resolve({ data: {} }),
    )

    window.history.pushState({}, '', '/feed')
    render(<App />)

    // The banner specifically, not the table's loading line, which also
    // mentions SEC EDGAR and would otherwise satisfy this wait before the
    // banner had rendered at all.
    await waitFor(() => expect(screen.getByRole('status')).toBeTruthy())
    expect(screen.getByRole('status').textContent).not.toMatch(/a few seconds/i)
  })
})
