# FilingsLab

A point-in-time-safe backtesting tool for the disclosure delay in political
(STOCK Act) and corporate-insider (SEC Form 4) trades: it only simulates
trades at `disclosure_date + delay_days` — never the true trade date — so the
backtest cannot see information a real follower couldn't have had. It measures
alpha decay against delay, runs Monte Carlo ensembles and two hypothesis
tests, and can optionally drive an Alpaca **paper**-trading bot off a live SEC
feed (live/real-money order placement is hard-disabled by default). Backend
is FastAPI/SQLAlchemy/Pydantic v2 on Postgres; frontend is React/Vite/
TanStack Query/Recharts/Tailwind. Optional Kronos (PyTorch, ~2GB) price
forecasting degrades gracefully when absent.

## Directory layout

- `backend/app/` — `api/`, `analytics/` (pure-Python stats: bootstrap CIs,
  Sharpe/Sortino, t-tests), `simulation/`, `research/` (hypothesis tests),
  `ingestion/` (EDGAR/Senate/House + synthetic GBM fallback), `kronos/`
  (optional forecasting), `services/`, `models/`, `schemas/`, `core/`
  (config, database, security/rate-limit, request logging).
- `backend/tests/` — 12 files, 165 tests, e.g. `test_statistics.py`,
  `test_api_security.py`, `test_rate_limit_contract.py`,
  `test_edgar_non_blocking.py`, `test_error_disclosure.py`,
  `test_research_integrity.py`, `test_log_injection.py`.
- `frontend/src/` — `pages/`, `components/`, `hooks/`, `services/`, `types/`,
  `utils/`, `test/` (3 files, 22 tests: routing, anonymous-visitor,
  warming-poll).
- `docker-compose.yml` (Postgres + backend + nginx/frontend),
  `backend/Dockerfile`, `frontend/Dockerfile`, `.env.example`.

## Install

```
# backend
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
# frontend
cd frontend && npm ci
```
(`npm ci` is the canonical/CI frontend command; the SessionStart hook uses
`npm install` instead so the container's cached `node_modules` layer is
reused. Kronos extras — `pip install -r backend/requirements-kronos.txt`,
~2GB torch — are optional and deliberately not installed by CI or the hook.)

## Lint / format / typecheck

No linter is configured for either side: no ruff/flake8/mypy config or CI
step for the backend, no eslint config or `lint` script for the frontend.
The closest thing to a static check is the frontend build's TS compile:
```
cd frontend && npx tsc --noEmit
```

## Test

```
# backend (no DB needed — tests override the DB dependency with an in-memory fake)
cd backend && .venv/bin/python -m pytest -q     # 165 passed, ~19s
# frontend
cd frontend && npm test                          # vitest run — 22 passed, ~9s
```
Fastest useful subset:
```
cd backend && .venv/bin/python -m pytest -q tests/test_statistics.py
cd frontend && npx vitest run src/test/routing.test.tsx
```

## Verification gate (source of truth)

CI's two independent jobs — backend `pytest -q` and frontend `npm test` — are
the gate; neither needs Postgres, Docker, or real secrets/network (tests
inject a fake DB and never call EDGAR/Alpaca/Kronos for real). The
security/contract suites are the part of the gate that matters most given
this app's risk surface: `test_api_security.py` (44, auth + rate limiting +
field bounds), `test_rate_limit_contract.py` (7), `test_error_disclosure.py`
(20, that an unexpected exception never leaks a traceback into the response),
and `test_research_integrity.py` (9, that a hypothesis test discloses the
actual sample it used when a trader is dropped) — these encode the security
and honesty guarantees the README makes, not just feature coverage.

## Environment caveats (from audit)

- Backend tests need **no** database, `API_TOKEN`, or network access — the
  test fixture overrides `get_db` with an in-process fake, so `DATABASE_URL`
  can stay at its Postgres-shaped default unset/unreachable.
- Kronos (`requirements-kronos.txt`, torch, ~2GB) is optional; the
  Kronos-dependent test file passes without it (it tests the in-process call
  contract, not real inference) — do not install it in the hook.
- `docker-compose.yml` is for running the full stack (Postgres + backend +
  nginx frontend), not for tests; the hook does not need Docker.
- Frontend test run shows benign React "not wrapped in act(...)" warnings and
  one intentionally-uncaught mock error (exercises an ErrorBoundary path) —
  both non-fatal.

## CI / conventions

- `ci.yml` has 3 jobs: backend `pytest -q` (Python 3.13, deps from
  `backend/requirements.txt` only), frontend (`npm ci`, `npm run build`,
  `npm test`, Node 22, lockfile-pinned), and `gitleaks` over full history.
- `backend/Dockerfile` uses Python 3.12-slim; this sandbox's system Python is
  3.11, which satisfies the README's stated 3.11+ minimum.
- No coverage floor is enforced on either side.
