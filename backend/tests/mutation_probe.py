"""Run a fixed, reviewable mutation sample without modifying application files.

From backend: python tests/mutation_probe.py before|after
Each child process uses an import hook to change exactly one source fragment.
Only assertion/test failures count as kills; collection errors and timeouts abort.
The before phase excludes the new tests even when rerun after they are added.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.abc
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys


BACKEND = Path(__file__).resolve().parents[1]
NEW_TESTS = (
    "test_ingestion_validation.py",
    "test_ingestion_normalizer.py",
    "test_ingestion_pipeline.py",
    "test_edgar_parser.py",
    "test_portfolio_accounting.py",
    "test_ranking_contract.py",
)

# (id, module, original fragment, replacement); fragments must be unique.
MUTANTS = [
    ("V01", "ingestion.validator", "if not trade_date:", "if False:"),
    ("V02", "ingestion.validator", "trade_date < MIN_DATE", "trade_date <= MIN_DATE"),
    ("V03", "ingestion.validator", "trade_date < MIN_DATE", "False"),
    ("V04", "ingestion.validator", "trade_date > date.today()", "trade_date >= date.today()"),
    ("V05", "ingestion.validator", "trade_date > date.today()", "False"),
    ("V06", "ingestion.validator", "disclosure_date < trade_date", "disclosure_date <= trade_date"),
    ("V07", "ingestion.validator", "disclosure_date and disclosure_date < trade_date", "False"),
    ("V08", "ingestion.validator", "delay > MAX_DISCLOSURE_DELAY_DAYS", "delay >= MAX_DISCLOSURE_DELAY_DAYS"),
    ("V09", "ingestion.validator", "delay > MAX_DISCLOSURE_DELAY_DAYS", "False"),
    ("V10", "ingestion.validator", "val < MIN_VALUE", "val <= MIN_VALUE"),
    ("V11", "ingestion.validator", "val > MAX_VALUE", "val >= MAX_VALUE"),
    ("V12", "ingestion.validator", "val < MIN_VALUE", "False"),
    ("V13", "ingestion.validator", "val > MAX_VALUE", "False"),
    ("V14", "ingestion.validator", "not symbol or len(symbol) < 1", "False"),
    ("V15", "ingestion.validator", "if not symbol:\n        return False, \"missing asset_symbol\"", "if False:\n        return False, \"missing asset_symbol\""),
    ("V16", "ingestion.validator", "if not price_date:", "if False:"),
    ("V17", "ingestion.validator", "float(closing) <= 0", "float(closing) < 0"),
    ("V18", "ingestion.validator", "closing is None or float(closing) <= 0", "closing is None"),
    ("N01", "ingestion.normalizer", "(lo + hi) / 2\n\n    m = _RANGE_RE", "(lo - hi) / 2\n\n    m = _RANGE_RE"),
    ("N02", "ingestion.normalizer", "lo, hi = hi, lo", "lo, hi = lo, hi"),
    ("N03", "ingestion.normalizer", "hi = lo * 3", "hi = lo * 2"),
    ("N04", "ingestion.normalizer", "return datetime.strptime(value.strip(), fmt).date()", "return None"),
    ("N05", "ingestion.normalizer", "if raw_clean in sell_synonyms:", "if False:"),
    ("N06", "ingestion.normalizer", "1 <= len(clean) <= 10", "1 <= len(clean) < 10"),
    ("N07", "ingestion.normalizer", "if not raw.get(key) and raw.get(key) != 0:", "if False:"),
    ("N08", "ingestion.normalizer", "if not trade_date:", "if False:"),
    ("N09", "ingestion.normalizer", "disclosure_date = trade_date\n\n    txn", "disclosure_date = disclosure_date\n\n    txn"),
    ("N10", "ingestion.normalizer", "if not txn:", "if False:"),
    ("N11", "ingestion.normalizer", "if not symbol:", "if False:"),
    ("N12", "ingestion.normalizer", "Decimal(str(mid))", "Decimal(str(lo))"),
    ("E01", "services.edgar", "if not ticker:\n        return []", "if False:\n        return []"),
    ("E02", "services.edgar", "if code not in (\"P\", \"S\"):", "if False:"),
    ("E03", "services.edgar", "if price <= 0 or shares <= 0:", "if False:"),
    ("E04", "services.edgar", "amount < 10_000", "amount <= 10_000"),
    ("E05", "services.edgar", "amount < 10_000", "False"),
    ("E06", "services.edgar", "\"buy\" if code == \"P\" else \"sell\"", "\"buy\" if code != \"P\" else \"sell\""),
    ("E07", "services.edgar", "round(shares * price, 2)", "round(shares + price, 2)"),
    ("E08", "services.edgar", "if is_off:\n        role", "if not is_off:\n        role"),
    ("P01", "simulation.portfolio", "execution_price <= 0 or allocation <= 0", "execution_price <= 0 and allocation <= 0"),
    ("P02", "simulation.portfolio", "min(allocation, self.cash)", "allocation"),
    ("P03", "simulation.portfolio", "affordable * (1 - transaction_cost)", "affordable * (1 + transaction_cost)"),
    ("P04", "simulation.portfolio", "self.cash -= affordable", "self.cash += affordable"),
    ("P05", "simulation.portfolio", "total_cost / total_shares", "execution_price"),
    ("P06", "simulation.portfolio", "min(target_value, max_sell_value)", "target_value"),
    ("P07", "simulation.portfolio", "execution_price * (1 - transaction_cost)", "execution_price * (1 + transaction_cost)"),
    ("P08", "simulation.portfolio", "remaining = pos.shares - shares_to_sell", "remaining = pos.shares + shares_to_sell"),
    ("P09", "simulation.portfolio", "current_prices.get(sym, pos.avg_cost)", "current_prices.get(sym, 0.0)"),
    ("I01", "ingestion.pipeline", "if normalised is None:", "if normalised is not None:"),
    ("I02", "ingestion.pipeline", "if not ok:\n                errors += 1\n                continue\n\n            exists", "if False:\n                errors += 1\n                continue\n\n            exists"),
    ("I03", "ingestion.pipeline", "if exists:", "if False:"),
    ("I04", "ingestion.pipeline", "skipped += 1", "skipped += 0"),
    ("I05", "ingestion.pipeline", "if not ok:\n                errors += 1\n                continue\n\n            symbol", "if False:\n                errors += 1\n                continue\n\n            symbol"),
    ("I06", "ingestion.pipeline", "existing.closing_price = Decimal(str(raw[\"closing_price\"]))", "existing.closing_price = existing.closing_price"),
    ("I07", "ingestion.pipeline", "updated += 1", "updated += 0"),
    ("R01", "analytics.ranking", "(v - lo) / spread", "(v + lo) / spread"),
    ("R02", "analytics.ranking", "[0.5] * len(values)", "[0.0] * len(values)"),
    ("R03", "analytics.ranking", "abs(_f(p.max_drawdown if p else None))", "_f(p.max_drawdown if p else None)"),
    ("R04", "analytics.ranking", "- w.rank_w_drawdown", "+ w.rank_w_drawdown"),
    ("R05", "analytics.ranking", "reverse=True", "reverse=False"),
    ("R06", "analytics.ranking", "r.rank = i + 1", "r.rank = i"),
]


def install_mutant(mutant):
    _, module, old, new = mutant
    name = "app." + module
    path = BACKEND / (name.replace(".", "/") + ".py")
    source = path.read_text()
    if source.count(old) != 1:
        raise RuntimeError(f"{mutant[0]}: fragment is not unique")
    code = compile(source.replace(old, new, 1), str(path), "exec")

    class MutantLoader(importlib.abc.Loader):
        def create_module(self, spec):
            return None

        def exec_module(self, module):
            exec(code, module.__dict__)

    class MutantFinder(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname == name:
                return importlib.util.spec_from_file_location(
                    fullname, str(BACKEND / (name.replace(".", "/") + ".py")),
                    loader=MutantLoader(),
                )

    sys.meta_path.insert(0, MutantFinder())


def worker(phase, mutant_id):
    sys.path.insert(0, str(BACKEND))
    if mutant_id != "reference":
        install_mutant(next(m for m in MUTANTS if m[0] == mutant_id))
    import pytest

    args = ["-q", "--maxfail=1", "-p", "no:cacheprovider"]
    if phase == "before":
        args += [f"--ignore=tests/{name}" for name in NEW_TESTS]
    return pytest.main(args)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("before", "after"))
    parser.add_argument("--jobs", type=int, choices=range(1, 5), default=1)
    parser.add_argument("--worker", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        return worker(args.phase, args.worker)

    def measure(mutant_id):
        proc = subprocess.run(
            [sys.executable, __file__, args.phase, "--worker", mutant_id],
            cwd=BACKEND, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, timeout=120,
        )
        output = proc.stdout
        if proc.returncode not in (0, 1) or (proc.returncode == 1 and not re.search(r"\d+ failed", output)):
            raise RuntimeError(f"{mutant_id}: infrastructure failure\n{output}")
        if mutant_id == "reference":
            if proc.returncode:
                raise RuntimeError(f"Unmutated gate failed\n{output}")
            print(output, flush=True)
            return None
        mutant = next(m for m in MUTANTS if m[0] == mutant_id)
        result = {
            "id": mutant_id, "module": mutant[1], "old": mutant[2], "new": mutant[3],
            "killed": proc.returncode == 1,
            "summary": output.strip().splitlines()[-1],
            "failure": next((s for s in output.splitlines() if s.startswith("FAILED ")), None),
        }
        print(f"{mutant_id}: {'killed' if result['killed'] else 'SURVIVED'}", flush=True)
        return result

    measure("reference")
    results = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for result in pool.map(measure, [m[0] for m in MUTANTS]):
            results.append(result)
            (BACKEND / "tests" / f"mutation_{args.phase}.json").write_text(
                json.dumps(results, indent=2) + "\n"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
