# Security notes

## Threat model — this is a publicly reachable service, not a localhost tool

Worth settling first, because it decides how bad everything below is.

The README's quick-start is `localhost`, which reads like a local research tool.
It is not the only way this ships:

* **`server_setup.sh` provisions a public cloud host.** It installs Docker, opens
  iptables 80 and 8000, brings the stack up, and then prints
  `http://$(curl -s ifconfig.me)` and `http://$(curl -s ifconfig.me):8000/docs`.
  Announcing your public IP as the API URL is not an accident of configuration.
* **`docker-compose.yml` publishes the backend on `8000:8000`** — every
  interface, not loopback. The database is the only service bound to
  `127.0.0.1`, and the comment there explains exactly why the distinction
  matters.
* **The backend is reachable two ways at once**: through the nginx container on
  port 80 (`/api/` proxied, `X-Real-IP` set) *and* directly on port 8000. Any
  control that trusts a proxy header has to survive the second path.

So the correct assumption is: **every route is reachable by an unauthenticated
stranger.** "It only ever binds to localhost" would have been a legitimate
answer that downgraded these findings — it is not the answer here.

## What is gated, and what is deliberately not

| Surface | Routes | Access |
|---|---|---|
| Paper account | `GET /api/feed/portfolio`, `GET /api/feed/broker/status` | **Bearer token** |
| Paper trading | `POST /api/feed/execute`, `DELETE /api/feed/position/{ticker}` | **Bearer token** |
| Auto-trader | `GET`/`POST /api/feed/auto-trader/config`, `POST /api/feed/auto-trader/run`, `GET /api/feed/auto-trader/log` | **Bearer token** |
| Disclosure feed | `GET /api/feed/disclosures`, `GET /api/feed/disclosures/{ticker}` | Open, 10/min |
| Research + simulation | `/api/traders`, `/api/rankings`, `/api/research/*`, `/api/simulate*`, `/api/compare`, `/api/forecast/*` | Open, rate limited |

**Why the research surface stays open.** It is read-only computation over public
data — SEC EDGAR and STOCK Act filings, plus a synthetic seed — and it holds
nothing private about anyone. It is also the entire demonstrable point of the
project; gating it behind a token would leave a portfolio piece nobody can look
at. What it *was* vulnerable to is cost, not disclosure, and cost is answered by
rate limiting. `POST /api/simulate` and `POST /api/compare` are mutating only in
HTTP verb: they compute and return, they persist nothing.

Authentication is one shared operator token in `API_TOKEN`, compared in constant
time, and it **fails closed** — with no token configured the admin routes return
`503`, never `200`. There is one operator; a user system would be scaffolding
around a problem this project does not have.

## Findings fixed (2026-08-03)

**1. Unauthenticated resource exhaustion — `GET /api/feed/disclosures` (HIGH).**
`limit` went straight into the EDGAR cache key, so each distinct `N` was a
guaranteed miss, and each miss slept ~18 s inside the request handler (a
`time.sleep(0.15)` per hit, up to 120 hits) while pinning a threadpool worker.
A loop over `N=1..200` was therefore 200 full misses from one anonymous client.
Fixed in two places, because either alone is insufficient:

* `limit` is now bucketed onto `(25, 50, 100, 200)` before it reaches the cache,
  so at most four upstream fetches can exist however many values are asked for.
  The result is still sliced to the requested `limit`, so responses are
  unchanged, and the UI's 25/50/100 options land on their own buckets.
* The endpoint is limited to **10/min per client IP**, with a 120/min default on
  everything else and tighter limits on Monte Carlo (5/min), experiments
  (5/min), comparison and forecasts (10/min), and manual auto-trader runs
  (5/min).

Two smaller instances of the same class went with it: `GET
/api/feed/disclosures/{ticker}` took an arbitrary path segment as a cache key
and an EDGAR search (now validated against the same symbol whitelist the
forecast router uses), and `/api/research/alpha-decay/{id}?delays=` ran one full
simulation per comma-separated entry with no cap (now ≤20 delays, each 0–365).
The EDGAR cache also evicts at 64 entries regardless.

**2. Negative notional fabricated money (MEDIUM).**
`POST /api/feed/execute` with `{"notional": -1000000}` reached
`paper_broker.execute_trade`, which computes `shares = notional / price` and on
a buy does `account.cash -= shares * price` — subtracting a negative, i.e.
crediting the account a million dollars it never had, and inflating
`total_return_pct` on the dashboard. `notional` and `qty` are now
`gt=0` with sane ceilings, `side` is a `Literal`, and `ticker` is
pattern-bounded. Every other numeric request field was swept: the auto-trader
config had none at all (`run_interval_mins=0` busy-loops the background thread;
a negative one raises inside `time.sleep` and kills the loop until restart), and
the activity-log `limit` had an upper bound but no lower one. The simulation,
Monte Carlo, and comparison schemas were already bounded and were left alone.

**3. No authentication on the control surface (HIGH).**
The auto-trader config, its manual trigger, its log, the paper portfolio and
manual trade execution were all open to the internet. All now require the
bearer token. The frontend does **not** ship the token in its bundle — a token
in a bundle is a published token; the operator pastes it into the Feed page and
it is held in `sessionStorage` for that tab only.

**4. No detection (MEDIUM).**
There was nothing in the log to distinguish an attack from normal use. Every
request now emits one parseable line — request id, method, path, status,
duration, client IP, forwarded-for, user agent — and the id is returned as
`X-Request-ID`. Failed auth logs `auth_failed` at WARNING with the reason,
request id and IP, so brute-force and token-probing show up as a pattern.
Rate-limit rejections appear as `status=429` on the same line format.

Ids are always server-generated; a client-supplied `X-Request-ID` is ignored so
it cannot be used to collide or poison log lines.

**Rate-limit keying.** Because port 8000 is exposed directly, forwarded headers
are believed only when the immediate peer is inside `trusted_proxy_networks`
(loopback and the private ranges by default, which covers the bundled nginx).
Anyone hitting the backend directly is keyed on their real socket address, so
they cannot mint a fresh bucket per request with a spoofed `X-Forwarded-For`.

**Still open, and deliberately not fixed here.** The rate-limit state is
in-process memory: it resets on restart and is per-worker, so it is a brake on
casual abuse rather than a distributed defence. Alerting is still absent — there
is now something to alert *on*, which there was not before, but nothing watches
it. Neither is a code change; both are honest limits of a single-container
research deployment.

> Superseded in part by round 2 below: the claim that this finding was closed by
> bucketing plus rate limiting was **premature**. Bucketing bounded the number of
> distinct crawls; it left each crawl running on a request thread. See finding 9.

Covered by `backend/tests/test_api_security.py` (42 tests), each written against
the pre-fix code and observed failing first.

## Findings fixed (round 2, 2026-08-03)

The round-1 hardening above closed the findings it claimed to close and **broke
the application doing it**. A review of that commit found four defects. A
hardened API that answers 500 is worse than the unhardened one it replaced, so
they are recorded here at full weight rather than as a footnote.

**5. Every rate-limited endpoint returned HTTP 500 on success (CRITICAL).**
`Limiter(headers_enabled=True)` makes slowapi's decorator finish with
`self._inject_headers(kwargs.get("response"), ...)`, and `_inject_headers`
raises `Exception("parameter response must be an instance of
starlette.responses.Response")` on anything that is not a `Response`. None of
the nine decorated endpoints declared one, so `/api/feed/disclosures`,
`/api/simulate`, `/api/simulate/monte-carlo`, `/api/compare`,
`/api/research/experiments`, `/api/research/alpha-decay/{id}`,
`/api/forecast/{symbol}`, `/api/feed/disclosures/{ticker}` and
`/api/feed/auto-trader/run` answered 500 to every caller — including the very
first one, before any limit was reached.

Fixed by declaring `response: Response` on all nine, **not** by setting
`headers_enabled=False`. Headers are the only place slowapi emits `Retry-After`,
which is what lets a client back off; disabling them would have removed the
working half of the feature to avoid fixing the broken half.

**6. No test asserted a success response on a rate-limited route (HIGH).**
The round-1 suite asserted on internal state (`_bucket_limit`) and on the
*presence of a 429 somewhere in a flood* — a condition satisfied perfectly by an
endpoint that returns 500 until the limiter starts returning 429. That is how a
whole-API outage passed 82 green tests.
`backend/tests/test_rate_limit_contract.py` now asserts status **and** body on
rate-limited routes, and walks every `@limiter.limit` route to fail the build if
a new one omits `response: Response`.

**7. The rate limit was bypassable on every path-parameterised route (HIGH).**
slowapi defaults to `key_style="url"`, so the bucket key is the *concrete* path.
`/api/feed/disclosures/AAA` and `/api/feed/disclosures/AAB` were separate
10/minute budgets, and `/api/traders/{id}` a separate 120/minute budget per id:
300 requests to varying paths produced zero 429s. Now `key_style="endpoint"`,
so the bucket is the route template. Verified against a live uvicorn process:
10 × 200 then 429 across 30 distinct tickers, and 120 × 404 then 429 across 140
distinct trader ids.

**8. The frontend manufactured its own 429s (HIGH).**
`Feed.tsx` fetched `/feed/portfolio` on mount and the auto-trader panel polled
`/feed/auto-trader/config` and `/log` every 15 s — all three token-gated, all
three answering 401 to the anonymous visitors who make up every public hit, and
each 401 still consuming that visitor's rate-limit budget before TanStack Query
retried it. The first thing it broke was the public feed those visitors *are*
allowed to read. Gated queries are now disabled while no operator token is
present, the retry policy refuses to retry any 4xx (401/403/429), and a 429 on
the open feed pauses the background poll instead of feeding it.

**9. Residual root cause of finding 1: the crawl ran on the request thread
(HIGH).** Bucketing the cache key bounded how many *distinct* crawls could
exist; it did not stop a single crawl from running inside the request handler.
`edgar.fetch_recent` submits up to 120 archive jobs paced `time.sleep(0.15)`
apart — about 18 s — on an anyio worker. That pool is 40 threads for the whole
process, so roughly 14 source IPs staying *within* the 10/min limit could stall
every route in the app, health check included.

The request path is now cache-only: it answers from the 15-minute cache (fresh,
or stale if that is all there is) and schedules the crawl in the background,
single-flight per key, at most two crawls process-wide, and at most one attempt
per key per two minutes so an EDGAR outage cannot be converted into a crawl per
request. A cold feed returns `warming: true` so the UI can say "fetching" rather
than "nothing found". The auto-trader loop, which runs on its own thread and
cannot act without data, keeps a blocking entry point (`refresh_recent_now`).

**10. The same bug class one layer up: enrichment (HIGH).**
Taking the crawl off the request thread is only half of it. `_enrich` runs per
disclosure, and per disclosure it makes two yfinance calls (`_current_price`,
`_volume_ratio` — neither cached) and one Kronos call. At `limit=200` that is up
to 600 network round trips on the same anyio worker the crawl used to hold: a
cached feed that blocks on enrichment has moved the stall, not removed it. The
enriched payload now gets the same treatment as the raw one — cache-first,
scheduled in the background, single flight per key, at most two jobs
process-wide, keyed on a fingerprint of the raw rows so new filings enrich
promptly and repeat requests never re-enrich the same data. Measured: the
endpoint answers in 22 ms on a cold cache against a live uvicorn process.

Covered by `backend/tests/test_rate_limit_contract.py` (7),
`backend/tests/test_edgar_non_blocking.py` (8) and
`frontend/src/test/feed-anonymous.test.tsx` (6) — all observed failing against
the pre-fix code first, with the measured numbers quoted in each file.

## Dependency advisories — current assessment (2026-07-27)

> Also fixed while here: `backend/requirements.txt` pinned `pytest==9.0.3`
> alongside `pytest-asyncio==0.25.0`, which **cannot resolve** — the backend test
> suite was uninstallable from a clean checkout. `pytest-asyncio` is now `1.4.0`
> (it accepts `pytest<10,>=8.4`), keeping the security-pinned pytest 9. Backend
> suite: **40 passed**.

Four Dependabot alerts were open against `frontend/package-lock.json`. **All four
are now fixed** — the fourth (the `react-router` RSC advisory) was accepted with a
reason on 2026-07-27 and then remediated on 2026-07-31; both the fix and the
original reasoning are recorded below so the next reader does not have to
re-derive them. `npm audit` reports **0 vulnerabilities**.

### Fixed

| Severity | Package | Action |
|---|---|---|
| HIGH | `postcss` — path traversal via `sourceMappingURL` auto-loading | bumped to **8.5.23** (advisory patched in 8.5.18). The existing `^8.5.10` range already permitted it; only the lockfile was pinning an old build. |
| MEDIUM (x2) | `react-router` — arbitrary constructor injection via `deserializeErrors()`; open redirect via backslash in `<Link>`/`useNavigate` | migrated to **`react-router` 7.18.1** (both patched in 7.18.0). |
| MEDIUM | `react-router-dom` — open redirect leading to XSS | **dependency removed.** There is no patched release in the 6.x line, so no bump could fix it. React Router v7 merges the DOM bindings into the `react-router` package, so `react-router-dom` is gone from the tree entirely. |

The v6 → v7 migration was small because this app only uses declarative-mode
APIs, all of which v7 keeps with identical signatures: `BrowserRouter`, `Routes`,
`Route`, `Navigate`, `Link`, `useLocation`, `useParams`, `useSearchParams`. Seven
files changed, one import specifier each. Verified with `npm run build`
(`tsc && vite build`) green before and after.

### Previously accepted — now REMEDIATED (2026-07-31)

**`react-router` — "RSC Mode CSRF Bypass Allows Action Execution Before 400
Response" (HIGH, affects `>=7.12.0 <8.3.0`).**

**Closed by upgrading to `react` 19.2.8 + `react-router` 8.3.0.** `npm audit` now
reports **0 vulnerabilities**. The upgrade needed **zero source-code changes** —
only `frontend/package.json` and the lockfile — because this app uses only
declarative-mode APIs, all unchanged in v8, and the one relevant v8 breaking
change was the React floor (`>=19.2.7`). `recharts` moved 2.14.1→2.15.4 within its
existing caret range, which declares React 19 support; no peer warnings tree-wide,
and no React 19 removed APIs were in use (no `propTypes`, `defaultProps`,
`ReactDOM.render`, `findDOMNode`).

Verified before applying: **8/8 routing tests pass**, `npm run build` exits 0,
`npm audit` clean, and the *built bundle was run in real Chromium* — all three
routes render, both redirects land on `/feed`, **0 console errors and 0 page
errors**. The browser check mattered because jsdom cannot exercise `recharts`
(no `ResizeObserver`), so the unit tests alone could not have caught a React 19
rendering regression.

> **Do not take the `react-router` 8.3.0 bump on its own.** A dependency-bot PR
> that bumps `react-router` to 8.3.0 while leaving `react` at 18.3.1 makes
> `npm ci` fail with `ERESOLVE` — and `frontend/Dockerfile` runs `npm ci`, so
> merging one would break the Docker build. Any such PR is superseded by this
> upgrade, which moves React and the router together.

The original reasoning is kept below, because it explains why the delay was
correct at the time rather than negligent.

---

**Why it was accepted until now.** Two facts held:

1. **It is not reachable in this application.** The advisory is specific to React
   Server Components mode. This frontend is a client-only Vite SPA: it mounts
   `<BrowserRouter>` (declarative mode), has no server entry point, does not use
   `createBrowserRouter`/`RouterProvider`, and defines no route `loader` or
   `action`. There is no RSC request pipeline for the bypass to act on.
2. **The fix is gated behind a second major upgrade.** It is patched only in
   `react-router` 8.3.0, which requires `react >= 19.2.7`; this app is on React
   18.3.1. Clearing the alert therefore means React 18 → 19 *and* Router 7 → 8.

At the time that decision was made the frontend had **no tests at all** — only
`npm run build`, and a passing build does not demonstrate that the app still
routes. Taking two majors on that basis would trade a non-reachable advisory for
unverified regression risk in code that renders real trading information.

**Correction to an earlier version of this file,** which said the *project* had
no test suite: that was too broad. The **backend** has 40 pytest tests
(`backend/tests/`). What was missing was frontend coverage — the part a React or
Router upgrade actually threatens.

**That gap is now closed.** `frontend/src/test/routing.test.tsx` (8 tests,
`npm test`) asserts the route table itself: both redirects (`/` and the `*`
catch-all) land on `/feed`, each real route is served without being rewritten by
the catch-all, `<Link>` still resolves to real hrefs, and the risk disclaimer
survives. It deliberately tests routing rather than page content, so it stays
meaningful across an upgrade, and the API layer is mocked so it needs no backend.
Verified to actually catch a break: pointing the `*` route at a blank element
fails exactly one test, and restoring it goes green.

**That plan was executed on 2026-07-31** — `npm install react@^19 react-dom@^19
react-router@^8`, then `npm test` and `npm run build`. In the event there were **no
React 19 breaking changes to work through**: the routing tests stayed green
untouched and no source file needed editing. The remaining caveat from that plan
still stands for future work — the 8 routing tests assert navigation, not page
behaviour, so extend them before relying on this suite to guard a larger refactor.

---

## Round 3 residuals (2026-08-03)

Three findings the reviewer raised after round 2 was signed off as sound. All
three are closed; each has tests that were watched failing against the code as
it stood.

**7. An unbounded caller-keyed dictionary (MEDIUM).**
Round 2 capped `edgar._cache` at 64 entries and stopped there. Driving 500
distinct tickers through `GET /api/feed/disclosures/{ticker}` with the network
stubbed held `_cache` at 64 and grew `edgar._last_attempt` — written from the
same caller-controlled key — to 500, with no eviction of any kind. The same
defect existed one layer up in `feed._enrich_last_attempt`, capped nowhere while
`_enrich_cache` beside it was capped at 32.

Both are now bounded (128 and 64). The eviction rule drops records that have
aged past their backoff window first and only evicts a live one when every
record is still inside its window, so the bound cannot be bought by throwing
away the retry suppression the dictionary exists to provide —
`tests/test_memory_bounds.py` pins that specifically, because a dict that simply
empties itself on overflow passes every size assertion and reintroduces the
retry storm.

**8. The cold path took about ten minutes, and the UI said "a few seconds" (MEDIUM).**
Taking the crawl off the request thread was right; describing the result was
not. The cold path is two background stages, and nothing connected the end of
the first to the start of the second, so stage two could only begin on the
*next* inbound request — one client poll interval, five minutes, per stage.

Fixed without putting any work back on the request thread. `edgar._cache_first`
takes an `on_refresh` callback that fires on the background thread when a crawl
lands, and the feed uses it to start enrichment immediately; and the warming
response now carries `retry_after_seconds: 15`, which the UI honours in place of
its steady-state 5-minute poll. The hint is a body field rather than
`Retry-After`, because slowapi already writes that header on every response from
a limited route where it means the rate-limit window — two meanings, two fields.
Measured on a real cold process through a real browser: warming banner at 3 s,
24 filings rendered at 49 s, no user action.

**9. A rate limit silently disabled a trading safety check (HIGH).**
`auto_trader._kronos_expected_return` fetched its forecast by calling this app's
own API back over the loopback. That was survivable only while slowapi keyed
buckets on the concrete URL, which is exactly the enumeration hole finding 4
closed: with `key_style="endpoint"`, one process calling one route template is
**one** 10/minute budget for a whole scoring cycle. From the 11th ticker the
call returned 429, a bare `except Exception` swallowed it, and the function
returned `None` — a valid value meaning "no forecast", which disables the Kronos
veto in `_run_cycle`. A financial-correctness bug, not a rate-limit nuisance.

The forecaster is now called in process: no HTTP boundary, no limiter, no budget
to exhaust, and the symbol whitelist the route used to apply moved with it.
What remains of the failure path is loud — an unexpected failure logs a WARNING
naming the ticker, and a buy made with no forecast records
`Kronos n/a (veto inactive)` in the activity log — with the deliberate exception
that "Kronos is not installed" stays at DEBUG, since the app is documented to
run without the optional ~2 GB extra and a warning per ticker per cycle is how a
real warning gets ignored.
