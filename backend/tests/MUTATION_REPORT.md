# Mutation-guided unit tests

Added 120 fast tests across six files. Application code, dependencies and CI
are unchanged. CI already runs `python -m pytest -q` from `backend`.

The sample prioritizes ingestion's two validity checkers, followed by disclosure
normalization, Form 4 parsing, persistence/counting, portfolio accounting and
ranking. Existing tests already cover authentication, request validation,
statistics, signal scoring and disclosure-date simulation. This is a targeted
mutation sample, not an exhaustive mutation score for the repository.

| Module (under `backend/app`) | Mutants tried | Killed before | Killed after |
| --- | ---: | ---: | ---: |
| `ingestion/validator.py` | 18 | 0 | 18 |
| `ingestion/normalizer.py` | 12 | 0 | 12 |
| `services/edgar.py` (XML parser) | 8 | 0 | 8 |
| `simulation/portfolio.py` | 9 | 2 | 9 |
| `ingestion/pipeline.py` | 7 | 0 | 7 |
| `analytics/ranking.py` | 6 | 0 | 6 |
| **Total** | **60** | **2** | **60** |

All 58 original survivors are killed by the new tests. The two original kills
were P04 (buy adds cash instead of subtracting it) and P08 (selling adds shares
instead of subtracting them), both caught by `test_simulation_engine.py`.

Each new test file kills at least these original survivors. Locations refer to
functions in the module named in the mutation table; exact replacement fragments
and stable mutation IDs are in `mutation_probe.py`.

| New file under `backend/tests` | Mutant | Mutation and location | Detecting example |
| --- | --- | --- | --- |
| `test_ingestion_validation.py` | V17 | `validate_price_record`: closing price `<= 0` becomes `< 0` | A zero closing price must be rejected; positive prices are accepted. |
| `test_ingestion_normalizer.py` | N12 | `normalise_record`: use the lower bound instead of the midpoint for `value_estimate` | The complete typed record must contain Decimal `8000.5`, not `1001`. |
| `test_edgar_parser.py` | E02 | `_parse_xml`: disable the P/S transaction-code filter | A valid purchase/sale is accepted; an acquisition-code transaction is excluded without losing its valid neighbor. |
| `test_portfolio_accounting.py` | P02 | `Portfolio.buy`: remove `min(allocation, self.cash)` | An oversized buy spends only the available cash, including its fee. |
| `test_ingestion_pipeline.py` | I02 | `ingest_trades`: bypass the normalised-record validity check | An excessive-value disclosure is counted as an error and never persisted. |
| `test_ranking_contract.py` | R04 | `compute_rankings`: add the weighted drawdown instead of subtracting it | Hand-calculated ranking scores must be `[0.6, 0]`. |

Both ingestion checkers have valid-record tests and single-field corruption and
removed-field tests. Trade tests cover minimum/today dates, disclosure ordering,
720/721-day delays and value bounds; price tests cover absent symbols/dates and
missing/zero/negative closing prices. The XML tests reject truncated documents,
missing identity or transaction fields, unsupported transaction codes, invalid
numbers and undersized transactions. Pipeline tests check exact counts against
persisted rows, including duplicates and updates. Tests use hand-built records,
in-memory XML and SQLite. They make no network requests and run no solvers.

Measurement method: each child process installs an import hook that replaces
exactly one unique fragment in one module, then runs the full backend pytest
gate with `--maxfail=1`. Application files are never rewritten. Each phase first
requires its unmutated reference gate to pass. The `before` phase explicitly
excludes the six new test files, so it remains reproducible with this patch
present. `after` includes the entire combined gate. Three isolated processes run
concurrently. Only test failures count as kills; infrastructure errors and
120-second child timeouts abort the measurement. Raw per-mutant results, failure
node IDs and pytest summaries are in `mutation_before.json` and
`mutation_after.json`. There were no final surviving mutants or infrastructure
errors in either completed measurement.

## Commands and results

Re-measured on a real checkout with Python 3.13 (the CI version) and the
pinned `backend/requirements.txt`, from `backend/`:

| Command | Result |
| --- | --- |
| `python tests/mutation_probe.py before --jobs 3` | 2/60 killed |
| `python tests/mutation_probe.py after --jobs 3` | 60/60 killed |
| `python -m pytest -q` | 394 passed (the warnings are existing Starlette/Pydantic deprecations) |
| `git diff --check` | Clean |

No application seam or other non-test code change was needed. The new tests use
hand-built records, in-memory XML and SQLite; they make no network requests.
