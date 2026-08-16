# FilingsLab - backtesting the disclosure delay in political and insider trades

[![CI](https://github.com/Leo-Y-Zhang/FilingsLab/actions/workflows/ci.yml/badge.svg)](https://github.com/Leo-Y-Zhang/FilingsLab/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
Proprietary - All Rights Reserved (c) 2026 Leo-Y-Zhang - portfolio viewing only. [LICENSE](LICENSE)

Public trading disclosures by US politicians (STOCK Act) and corporate insiders (SEC Form 4) arrive *late* — a filing is published days or weeks after the trade. FilingsLab takes that constraint seriously: it only executes simulated trades at `disclosure_date + delay_days`, never at the original (non-public) trade date, so the backtest cannot see information a real follower couldn't have had. Around that point-in-time-safe core it measures how fast the disclosure edge decays with delay, runs Monte Carlo ensembles, tests two stated hypotheses, and can drive an Alpaca **paper-trading** bot off the live SEC feed.

> **Disclaimer:** For **educational and research use only** — this is **not** financial advice. FilingsLab ingests **real public-disclosure data** (SEC EDGAR, US Senate/House filings) where configured, with a synthetic fallback for offline/demo use. **Trading runs in paper (simulated) mode by default; live, real-money order placement is hard-disabled** unless you deliberately enable it (see *Data & Trading* below). Past performance — simulated or real — does not predict future results.

---

## Features

| Feature | Description |
|---|---|
| **Disclosure-date execution** | Trades fire at `disclosure_date + delay_days`, not the trade date, so the backtest has no look-ahead into non-public information |
| **Alpha decay analysis** | Sweeps execution delay (0–60 days) and reports the excess-return half-life and the delay at which the signal reaches zero |
| **Monte Carlo engine** | N independent runs with optional delay noise; reports 68% and 95% bootstrap confidence intervals |
| **Hypothesis testing** | H1: disclosed trades earn excess returns vs a buy-and-hold benchmark; H2: shorter disclosure delay outperforms longer delay |
| **Multi-trader comparison** | 2–6 traders simulated under identical config, side-by-side, with a portfolio overlay chart |
| **Composite ranking** | Cross-population min-max normalised score: `0.35·return + 0.30·Sharpe − 0.20·|drawdown| + 0.15·win_rate` (weights configurable) |
| **Sortino ratio** | Downside-only risk adjustment, alongside Sharpe, annualised volatility, and max drawdown |
| **Live feed + paper bot** | Pulls recent Form 4 filings from SEC EDGAR, scores them, and can place Alpaca **paper** orders via an optional auto-trader |

---

## Stack

**Backend** — Python 3.11, FastAPI, SQLAlchemy 2.0, Pydantic v2. Analytics (bootstrap CIs, t-tests, ratios) are hand-written on NumPy with no heavyweight stats dependency. Real disclosure ingestion (SEC EDGAR / Senate / House) with a synthetic Geometric-Brownian-Motion fallback. Optional Kronos (PyTorch) price forecasting and an Alpaca paper-trading broker, both of which degrade gracefully when absent.

**Frontend** — React 18 + TypeScript + Vite, TanStack Query for server state, Recharts for visualisation, Tailwind CSS.

---

## Quick Start

### With Docker Compose (recommended)

```bash
git clone https://github.com/Leo-Y-Zhang/FilingsLab.git filingslab
cd filingslab
docker compose up --build
```

- Frontend: http://localhost (nginx, port 80); for the dev server, npm run dev serves http://localhost:5173
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/api/docs

### Local development

**Backend**
```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Frontend**
```bash
cd frontend
npm install
npm run dev
```

### Tests

```bash
cd backend
python -m pytest -q      # 118 tests (analytics + API security + rate-limit contract + resource bounds)
```

43 tests cover the pure-Python analytics layer (returns, Sharpe/Sortino, drawdown, win rate, bootstrap CIs, t-tests); 42 cover the API security boundary — authentication, rate limiting, request-field bounds, and request logging; 7 pin the rate-limit *contract* (a limited endpoint still answers 200 with a body, and its bucket is the route rather than the concrete URL); 8 pin that neither the SEC EDGAR crawl nor the per-disclosure enrichment ever runs on a request thread; 5 pin that every caller-keyed dictionary on a public path stays bounded when driven with 500 distinct keys; 5 pin the cold-start contract (data on the second request, and a warming response that states the wait); 6 pin that the auto-trader gets its Kronos forecast in process rather than over its own rate-limited loopback API; 2 pin that a seeded performance row records the trade activity the simulation actually produced instead of an empty win rate and trade count. Ingestion and the simulation routers are still untested. The frontend has 22 tests (`cd frontend && npm test`): 8 routing, 6 covering what an anonymous visitor is allowed to request, 8 covering the warming poll interval and banner.

---

## API Reference

All routes are served under `/api`. Full interactive docs at `/api/docs` (Swagger) and `/api/redoc`.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/traders` | List traders (filter by `?category=`) |
| `GET` | `/api/traders/{id}` | Trader detail with performance |
| `GET` | `/api/traders/{id}/trades` | All trades for a trader |
| `GET` | `/api/rankings` | Composite ranked leaderboard |
| `POST` | `/api/simulate` | Run a portfolio simulation |
| `POST` | `/api/simulate/monte-carlo` | Run a Monte Carlo ensemble |
| `POST` | `/api/compare` | Multi-trader comparison (2–6 traders) |
| `GET` | `/api/research/experiments` | The 3 structured research experiments |
| `GET` | `/api/research/alpha-decay/{id}` | Alpha decay curve for a trader |
| `GET` | `/api/research/hypothesis/h1` | H1 excess-returns test |
| `GET` | `/api/research/hypothesis/h2` | H2 early-vs-late delay test |
| `GET` | `/api/feed/disclosures` | Recent Form 4 filings, scored |
| `GET` | `/api/forecast/status` | Kronos forecaster availability |
| `GET` | `/api/health` | Liveness check |

The `/api/feed/*` namespace also exposes the paper-portfolio status, position list, manual paper-trade execution, and the optional auto-trader config/run/log endpoints — see the Swagger docs for the full set.

### Authentication

The research and disclosure routes above are open. **Everything that touches the paper account or the auto-trader requires an operator bearer token**, because `server_setup.sh` deploys this on a public host with port 8000 exposed:

```bash
# generate one, put it in .env as API_TOKEN, and never commit it
python -c "import secrets; print(secrets.token_urlsafe(32))"

curl -H "Authorization: Bearer $API_TOKEN" http://localhost:8000/api/feed/portfolio
```

With no `API_TOKEN` set those routes return **503 (disabled)** — never 200. In the UI, click *Sign in* on the Feed page and paste the token; it is kept in that browser tab only and is never built into the bundle. Rate limits apply per client IP to every route. See [SECURITY.md](SECURITY.md) for the threat model and what is deliberately left open.

---

## Research Methodology

### Disclosure-date execution model

Trades are executed at `disclosure_date + delay_days`. Using the actual `trade_date` would introduce look-ahead bias, since a disclosure is only publicly available after the disclosure date.

```
Simulated execution date = disclosure_date + delay_days
```

### Alpha decay

The disclosure edge is measured across a range of execution delays (0–60 days). The alpha decay curve plots excess return vs delay and reports:
- **Half-life** — delay at which excess return falls to 50% of its peak
- **Signal duration** — delay at which excess return crosses zero

### Sortino ratio

```
Sortino = (mean daily excess return / downside deviation) × √252
```

Downside deviation counts only returns *below* the daily risk-free rate, which suits return distributions with positive skew better than Sharpe.

---

## Project Structure

```
filingslab/
├── backend/
│   ├── app/
│   │   ├── analytics/        # performance metrics, ranking, statistics
│   │   ├── api/              # FastAPI routers (traders, rankings, simulate, research, feed, forecast, compare)
│   │   ├── core/             # config, database, seed data
│   │   ├── ingestion/        # normalizer, validator, pipeline
│   │   ├── models/           # SQLAlchemy ORM models
│   │   ├── research/         # alpha decay, experiments, hypothesis tests
│   │   ├── schemas/          # Pydantic v2 schemas
│   │   ├── services/         # Alpaca broker, EDGAR feed, Kronos forecaster
│   │   ├── simulation/       # engine, portfolio, monte carlo
│   │   └── main.py
│   ├── tests/                # analytics unit tests (40)
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/       # charts, cards, layout
│   │   ├── hooks/            # useApi (TanStack Query)
│   │   ├── pages/            # Dashboard, Rankings, Traders, Simulation, Research, Comparison
│   │   ├── services/         # Axios API client
│   │   ├── types/            # TypeScript interfaces
│   │   └── utils/            # format helpers
│   └── package.json
└── docker-compose.yml
```

---

## Data & Trading

**Data sources.** Where configured, FilingsLab ingests **real public-disclosure data** — US Senate/House STOCK Act filings and SEC Form 4 insider filings — for point-in-time-safe research. When no live source is available (offline/demo), it falls back to **synthetic data** (Geometric Brownian Motion price paths and example traders) so the app always runs.

**Forecasting.** An optional [Kronos](setup_kronos.py) time-series model (third-party, ShiYu/MIT) provides price forecasts; the app degrades gracefully when the model is not installed. The auto-trader calls the forecaster **in process**, not over `http://localhost:8000/api/forecast/{ticker}`: with rate-limit buckets keyed on the route template, a loopback self-call shared one 10/minute budget across a whole scoring cycle and quietly returned `None` — which silently disabled the Kronos veto. When a forecast is genuinely unavailable the auto-trader now says so in its activity log rather than omitting it.

**Trading & safety.** Any trading runs in **paper (simulated) mode by default** via Alpaca. Live, real-money order placement is **hard-disabled**: it requires *both* `ALPACA_PAPER=false` *and* `ALLOW_LIVE_TRADING=I_UNDERSTAND_THE_RISK` — a single stray environment variable can never place a real order. With no broker keys configured, no orders (paper or live) are placed at all.

---

## Limitations & scope

- This is a research and portfolio project, not a production trading system.
- Backtest results depend on the completeness and timeliness of the disclosure feed; the synthetic fallback is illustrative only and carries no predictive meaning.
- Value-based fills use midpoint estimates and standard transaction-cost assumptions, not real fill data or market impact.
- Automated tests cover the analytics layer, the API security boundary, the rate-limit contract, resource bounds and the cold-start contract (118 backend tests) plus 22 frontend tests; ingestion and the simulation routers are not under test.
- Rate limiting is in-process memory, so it resets on restart and is per-worker — a brake on casual abuse, not a distributed defence. Nothing alerts on the request log.
- The disclosure feed is served from a 15-minute cache refreshed in the background, so a cold start returns `warming: true` and an empty list rather than holding the request open. The cold path is two chained background stages — crawl SEC EDGAR, then price every filing — and the warming response carries `retry_after_seconds` so the client polls at 15 seconds instead of its steady-state 5 minutes. Measured end to end on a real cold process: the browser rendered 24 filings 49 seconds after first load, with no user action. It is *seconds to a minute*, not instant, and can be several minutes when EDGAR is slow.
- Kronos forecasting is optional and unvalidated here — it is a demonstration integration, not an evaluated signal.

---

*Educational and research use only. This is not financial advice.*
