const toNum = (v: unknown): number => (typeof v === 'number' ? v : Number(v))

export const pct = (v?: number | string | null, d = 2): string => {
  if (v === undefined || v === null || v === '') return '—'
  const n = toNum(v)
  return `${n >= 0 ? '+' : ''}${n.toFixed(d)}%`
}

export const pctRaw = (v?: number | string | null, d = 2): string => {
  if (v === undefined || v === null || v === '') return '—'
  const n = toNum(v) * 100
  return `${n.toFixed(d)}%`
}

export const currency = (v: number | string, decimals = 0): string =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: decimals }).format(toNum(v))

export const fmt2 = (v?: number | string | null): string =>
  v === undefined || v === null || v === '' ? '—' : toNum(v).toFixed(2)

/** Alias for fmt2 — formats a plain number to 2 decimal places */
export const num = fmt2

export const fmt4 = (v?: number | string | null): string =>
  v === undefined || v === null || v === '' ? '—' : toNum(v).toFixed(4)

/**
 * Parse a date from the API. Calendar dates arrive as "YYYY-MM-DD", and
 * `new Date("2026-09-28")` reads that as midnight UTC, which every timezone
 * west of Greenwich then displays as the day before: a Monday forecast showed
 * as "Sun 27 Sept" in New York, and a filing's disclosure date a day early. A
 * date-only string names a calendar day, so it is built at local midnight;
 * anything with a time part is left to `Date`.
 */
export const parseDate = (s: string): Date => {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s)
  return m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : new Date(s)
}

export const fmtDate = (s?: string | null): string => {
  if (!s) return '—'
  return parseDate(s).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
}

export const capitalize = (s: string): string => s.charAt(0).toUpperCase() + s.slice(1)
