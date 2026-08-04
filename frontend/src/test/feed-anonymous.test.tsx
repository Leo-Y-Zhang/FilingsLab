/**
 * An anonymous visitor must not call the token-gated API.
 *
 * The Feed page fetched `/feed/portfolio` on mount and the auto-trader panel
 * polled `/feed/auto-trader/config` and `/feed/auto-trader/log` every 15
 * seconds — all three require the operator bearer token and answer 401 to
 * everyone else. So the public page manufactured a steady stream of failed
 * requests for every visitor who will never hold a token, each one consuming
 * that visitor's rate-limit budget, and TanStack Query retried each failure on
 * top of it. The first symptom an ordinary user sees is a 429 on the feed they
 * are allowed to read.
 *
 * These tests render the real <App/> (so they exercise the app's real
 * QueryClient, retries included) and pin three rules:
 *   - no token, no request to a gated route
 *   - a token, and the paper portfolio still loads
 *   - a 401/403/429 is never retried
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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
import { queryClient } from '@/services/queryClient'

const TOKEN_KEY = 'filingslab_operator_token'
const GATED = ['/feed/portfolio', '/feed/broker/status', '/feed/auto-trader']

const calls = () => get.mock.calls.map(c => String(c[0]))
const gatedCalls = () => calls().filter(url => GATED.some(p => url.startsWith(p)))

function renderApp() {
  window.history.pushState({}, '', '/feed')
  return render(<App />)
}

beforeEach(() => {
  vi.clearAllMocks()
  sessionStorage.clear()
  queryClient.clear()
  get.mockResolvedValue({ data: { disclosures: [], count: 0 } })
})

afterEach(() => {
  sessionStorage.clear()
  queryClient.clear()
})

describe('anonymous visitor', () => {
  it('does not call any token-gated route on mount', async () => {
    renderApp()

    await waitFor(() => expect(get).toHaveBeenCalled())
    // Give any mount-time effect a chance to fire before asserting the absence.
    await new Promise(r => setTimeout(r, 50))
    expect(gatedCalls()).toEqual([])
  })

  it('still loads the open disclosure feed', async () => {
    renderApp()

    await waitFor(() =>
      expect(calls().some(u => u.startsWith('/feed/disclosures'))).toBe(true),
    )
  })

  it('does not start the auto-trader polling loop', async () => {
    renderApp()
    await waitFor(() => expect(get).toHaveBeenCalled())

    fireEvent.click(screen.getByRole('button', { name: /auto-trader/i }))

    await new Promise(r => setTimeout(r, 50))
    expect(gatedCalls()).toEqual([])
  })
})

describe('signed-in operator', () => {
  it('loads the paper portfolio once a token is present', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'an-operator-token')
    renderApp()

    await waitFor(() =>
      expect(calls().some(u => u.startsWith('/feed/portfolio'))).toBe(true),
    )
  })

  it('does not retry a rejected gated call into a storm', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'a-stale-token')
    get.mockImplementation((url: string) =>
      url.startsWith('/feed/portfolio')
        ? Promise.reject({ response: { status: 401 } })
        : Promise.resolve({ data: { disclosures: [], count: 0 } }),
    )

    renderApp()

    await waitFor(() =>
      expect(calls().filter(u => u.startsWith('/feed/portfolio')).length).toBeGreaterThan(0),
    )
    // Long enough to cover TanStack Query's first retry backoff (~1 s).
    await new Promise(r => setTimeout(r, 2000))
    expect(calls().filter(u => u.startsWith('/feed/portfolio'))).toHaveLength(1)
  })
})

describe('retry policy', () => {
  it('refuses to retry 401, 403 and 429 but allows one transport retry', () => {
    const retry = queryClient.getDefaultOptions().queries!.retry as (
      count: number,
      err: unknown,
    ) => boolean
    const http = (status: number) => ({ response: { status } })

    expect(retry(0, http(401))).toBe(false)
    expect(retry(0, http(403))).toBe(false)
    expect(retry(0, http(429))).toBe(false)
    expect(retry(0, new Error('Network Error'))).toBe(true)
    expect(retry(1, new Error('Network Error'))).toBe(false)
  })
})
