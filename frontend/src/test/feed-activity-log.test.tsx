/**
 * The auto-trader activity log printed a stray "0" on most rows.
 *
 * Each row rendered `{row.notional && <span/>}` and `{row.score && <span/>}`.
 * React renders a falsy number, so a 0 is not "nothing" but the text "0". The
 * backend writes notional 0 on every skip (Kronos or MiroFish veto) and score
 * 0 on every exit (stop-loss, take-profit, insider sell), so those rows read
 * "skip AAPL 0 score 62" and "stop_loss MSFT $1,234 0". Watched failing first.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const get = vi.fn()

vi.mock('axios', () => {
  const instance = {
    get: (...a: any[]) => get(...a),
    post: vi.fn(),
    delete: vi.fn(),
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
}))

import App from '@/App'
import { queryClient } from '@/services/queryClient'

const LOG = [
  { id: 1, action: 'skip', ticker: 'AAPL', reason: 'Kronos veto', score: 62, price: 0, notional: 0, created_at: null },
  { id: 2, action: 'stop_loss', ticker: 'MSFT', reason: '-8.1%', score: 0, price: 9.5, notional: 1234, created_at: null },
  { id: 3, action: 'buy', ticker: 'NVDA', reason: 'ok', score: 71, price: 120, notional: 5000, created_at: null },
]

beforeEach(() => {
  vi.clearAllMocks()
  queryClient.clear()
  sessionStorage.setItem('filingslab_operator_token', 'an-operator-token')
  get.mockImplementation((url: string) => {
    if (url.startsWith('/feed/auto-trader/log')) return Promise.resolve({ data: { count: LOG.length, log: LOG } })
    if (url.startsWith('/feed/auto-trader/config')) return Promise.resolve({ data: { enabled: false } })
    if (url.startsWith('/feed/portfolio')) return Promise.resolve({ data: { account: {}, positions: [] } })
    return Promise.resolve({ data: { disclosures: [], count: 0 } })
  })
})

afterEach(() => {
  sessionStorage.clear()
  queryClient.clear()
})

const rowText = (ticker: string) => screen.getByText(ticker).parentElement!.textContent

describe('auto-trader activity log', () => {
  it('prints no bare zero for a missing notional or score', async () => {
    window.history.pushState({}, '', '/feed')
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: /auto-trader/i }))
    await waitFor(() => expect(screen.getByText('AAPL')).toBeInTheDocument())

    expect(rowText('AAPL')).toBe('skipAAPLscore 62')
    expect(rowText('MSFT')).toBe('stop_lossMSFT$1,234')
    expect(rowText('NVDA')).toBe('buyNVDA$5,000score 71')
  })
})
