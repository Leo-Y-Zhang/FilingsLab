/**
 * Routing tests.
 *
 * These exist for a specific reason. `SECURITY.md` records one accepted
 * Dependabot advisory whose only fix is `react-router` 8, which in turn needs
 * React 19 — two majors. That upgrade was declined because nothing here could
 * verify it: the build passing does not show that the app still routes. These
 * tests are the missing instrument. They assert the route table's behaviour
 * (including both redirects) rather than any page's content, so they stay
 * meaningful across a Router or React upgrade and will fail loudly if one
 * breaks navigation.
 *
 * The API layer is mocked: this is about routing, not data fetching, and a
 * routing test that needs a backend is a routing test nobody runs.
 */
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

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

function renderAt(path: string) {
  window.history.pushState({}, '', path)
  return render(<App />)
}

describe('route table', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the app shell without crashing', () => {
    renderAt('/feed')
    // The disclaimer is part of the shell on every route; if the shell renders,
    // the Router mounted and the layout survived.
    expect(document.querySelector('nav')).toBeTruthy()
  })

  it('redirects the index route to /feed', async () => {
    renderAt('/')
    await waitFor(() => expect(window.location.pathname).toBe('/feed'))
  })

  it('redirects an unknown route to /feed rather than showing nothing', async () => {
    renderAt('/no-such-page')
    await waitFor(() => expect(window.location.pathname).toBe('/feed'))
  })

  it.each(['/feed', '/forecast', '/simulation'])(
    'serves %s without falling through to the catch-all redirect',
    async (path) => {
      renderAt(path)
      // A real route must NOT be rewritten by the "*" route.
      await waitFor(() => expect(window.location.pathname).toBe(path))
      // and something rendered inside the shell
      expect(document.querySelector('main')?.textContent ?? '').not.toBe('')
    },
  )

  it('exposes the primary navigation as real links', () => {
    renderAt('/feed')
    const hrefs = Array.from(document.querySelectorAll('nav a')).map((a) =>
      a.getAttribute('href'),
    )
    // <Link> must resolve to real hrefs — this is what breaks if the Router's
    // DOM bindings change shape under an upgrade.
    expect(hrefs).toContain('/feed')
    expect(hrefs).toContain('/forecast')
  })

  it('keeps the risk disclaimer on the page', () => {
    renderAt('/feed')
    // Not decoration: this app displays trading information, and the
    // disclaimer must not silently vanish behind a layout or routing change.
    // appears in more than one place (banner + footer), so assert presence, not uniqueness
    expect(screen.getAllByText(/not (financial|investment) advice/i).length).toBeGreaterThan(0)
  })
})
