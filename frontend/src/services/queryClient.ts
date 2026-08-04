/**
 * Shared TanStack Query client.
 *
 * Lives in its own module for one reason: the retry policy is a security
 * control, not a preference, and a control that cannot be tested is not a
 * control. The default (`retry: 1`) turned every rejected request into two,
 * which is the wrong direction for the two rejections this app actually
 * produces:
 *
 *   401/403 — the caller has no operator token. Retrying cannot help; the
 *             answer will be the same until a human pastes a token.
 *   429     — the caller is already over the rate limit. Retrying is the
 *             textbook way to stay over it.
 *
 * So 4xx is never retried, and only transport-level failures get a single
 * second chance.
 */
import { QueryClient } from '@tanstack/react-query'

/** HTTP status of an axios-style rejection, if it carries one. */
export function statusOf(error: unknown): number | undefined {
  const response = (error as { response?: { status?: number } } | null)?.response
  return typeof response?.status === 'number' ? response.status : undefined
}

/** True when the error means "you are asking too often" or "you may not". */
export function isNotWorthRetrying(error: unknown): boolean {
  const status = statusOf(error)
  return status !== undefined && status >= 400 && status < 500
}

export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (isNotWorthRetrying(error)) return false
  return failureCount < 1
}

// ── Disclosure-feed poll interval ─────────────────────────────────────────────
// Same reasoning as the retry policy, which is why it lives here: how often the
// page asks is a rate-limit control, and a control that cannot be tested is not
// a control.
//
// The feed has two states with completely different right answers. Warm, it is
// backed by a 15-minute server cache and five minutes is generous. Cold, the
// server is running two background stages and answers `warming: true` with a
// `retry_after_seconds` hint; polling that at five minutes made a lone visitor
// wait about ten minutes for work that takes well under one.

/** Steady-state poll: the server cache is 15 minutes, so this is plenty. */
export const FEED_IDLE_POLL_MS = 5 * 60_000

/** Fallback while warming, if the server sends no hint of its own. */
export const FEED_WARMING_POLL_MS = 15_000

/**
 * Floor on any poll interval. The public feed allows 10 requests a minute per
 * client, so a server asking for a 1-second poll — or a zero, or a negative —
 * must not be obeyed into a self-inflicted 429.
 */
export const MIN_FEED_POLL_MS = 6_000

interface FeedBody {
  warming?: boolean
  retry_after_seconds?: number
}

/**
 * How long to wait before asking the disclosure feed again.
 * `false` means stop polling altogether.
 */
export function feedPollIntervalMs(data: unknown, error: unknown): number | false {
  // Polling through a rate limit is how a limit becomes permanent.
  if (statusOf(error) === 429) return false

  const body = (data ?? undefined) as FeedBody | undefined
  if (body && !body.warming) return FEED_IDLE_POLL_MS

  // No body yet is the very first load, which is the cold case by definition.
  const hint = body?.retry_after_seconds
  const requested =
    typeof hint === 'number' && Number.isFinite(hint) && hint > 0
      ? hint * 1000
      : FEED_WARMING_POLL_MS
  return Math.max(requested, MIN_FEED_POLL_MS)
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: shouldRetry,
        refetchOnWindowFocus: false,
      },
      mutations: {
        retry: false,
      },
    },
  })
}

export const queryClient = createQueryClient()
