/**
 * Operator token store.
 *
 * The paper-broker and auto-trader routes are gated server-side by a shared
 * bearer token (`API_TOKEN`). It is deliberately NOT baked into the build — a
 * token in the bundle is a published token. The operator pastes it once and it
 * lives in sessionStorage for that tab only.
 *
 * This is a tiny external store rather than a plain getter because the UI has
 * to *react* to it: without a token the gated queries must not run at all, and
 * a query's `enabled:` flag can only depend on something React re-renders on.
 * Reading sessionStorage during render produced a value the components never
 * re-evaluated, which is part of how the page ended up firing gated requests
 * for anonymous visitors.
 *
 * The snapshot is a string, so `Object.is` comparison is by value and
 * useSyncExternalStore stays stable without any caching of its own.
 */
import { useSyncExternalStore } from 'react'

export const TOKEN_KEY = 'filingslab_operator_token'

const listeners = new Set<() => void>()

export function getOperatorToken(): string {
  try {
    return sessionStorage.getItem(TOKEN_KEY) ?? ''
  } catch {
    // sessionStorage can throw in a locked-down browser context.
    return ''
  }
}

export function setOperatorToken(token: string): void {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token)
    else sessionStorage.removeItem(TOKEN_KEY)
  } catch {
    /* nothing we can do; the request interceptor will simply see no token */
  }
  listeners.forEach(fn => fn())
}

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange)
  return () => {
    listeners.delete(onChange)
  }
}

export function useOperatorToken(): string {
  return useSyncExternalStore(subscribe, getOperatorToken, () => '')
}
