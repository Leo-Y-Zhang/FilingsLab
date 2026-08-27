"""
Log-injection contract tests
============================
CodeQL's ``py/log-injection`` flagged eleven sinks in this backend. Most of them
were already closed by a validator it cannot see — ``trader_id`` is typed
``int``, ``_validate_ticker`` and ``_validate_symbol`` allow-list their path
parameters, and ``%r`` escapes what it renders. Three were not:

  * ``services/edgar._parse_xml`` lifts ``issuerTradingSymbol`` out of a remote
    SEC Form 4 with nothing but ``.upper().strip()``, and the auto-trader hands
    that ticker to ``services/paper_broker.execute_trade``, which logs it. An
    interior newline survives ``.strip()``, so that is the one path to a log
    record from a document nobody here wrote;
  * ``kronos/service._fetch_ohlcv`` logs a third-party exception verbatim;
  * ``api/research.hypothesis_h1`` takes ``category`` as free-text query input
    and it reaches two loggers two modules apart.

Three claims, each watched failing against the unscrubbed code first:

  A. ``scrub`` neutralises the characters that forge a record
  B. the *wiring* holds — every sink still imports ``scrub`` and still passes
     its untrusted argument through it. A helper nobody calls fixes nothing, so
     this reads the five call sites rather than the helper. It is a source-level
     check in the same spirit as
     ``test_rate_limit_contract.test_every_rate_limited_endpoint_declares_a_response_parameter``,
     and needs no database, no network and no import of what it guards.
  C. one real sink, run, with the record read back. ``edgar._claim_refresh`` is
     the one reachable without a database or a network. Against the pre-fix
     code it printed the forgery this now prevents:

         DEBUG app.services.edgar:edgar.py:131 EDGAR refresh for ticker:AAPL
         WARNING:app.services.edgar:forged record skipped: 2 already running
"""
from __future__ import annotations

import ast
import logging
from pathlib import Path

import pytest

from app.core.logsafe import scrub

_BACKEND = Path(__file__).resolve().parents[1]


# ── A. the helper neutralises what forges a record ────────────────────────────

@pytest.mark.parametrize(
    "hostile",
    [
        "AAPL\nWARNING:app:forged record",          # LF: the classic
        "AAPL\r\nWARNING:app:forged record",        # CRLF
        "AAPL\x85WARNING:app:forged record",        # NEL, a line break to some readers
        "AAPL" + chr(0x2028) + "WARNING:app:forged record",      # Unicode line separator
        "AAPL" + chr(0x2029) + "WARNING:app:forged record",      # Unicode paragraph separator
    ],
)
def test_scrub_leaves_nothing_that_can_start_a_new_record(hostile):
    cleaned = scrub(hostile)
    assert cleaned.splitlines() == [cleaned], (
        f"scrub({hostile!r}) still spans lines: {cleaned!r}"
    )
    assert "\n" not in cleaned and "\r" not in cleaned


def test_scrub_escapes_terminal_control_sequences():
    """ESC is not a line break, but it rewrites what the operator sees."""
    assert scrub("AAPL\x1b[2J\x1b[H") == "AAPL\\x1b[2J\\x1b[H"


def test_scrub_leaves_legitimate_values_untouched():
    """A defence that mangles the normal case gets removed by the next reader."""
    for good in ("AAPL", "BRK.A", "BF-B", "politician", "ticker:AAPL", "recent:50"):
        assert scrub(good) == good


def test_scrub_renders_non_strings():
    assert scrub(ValueError("boom\nforged")) == "boom\\nforged"
    assert scrub(42) == "42"


def test_scrub_caps_the_length_of_one_field():
    cleaned = scrub("A" * 5_000)
    assert len(cleaned) < 250, f"one field wrote {len(cleaned)} characters to the log"
    assert cleaned.endswith("...[truncated]")


# ── B. the wiring: every sink still scrubs ────────────────────────────────────

_LOG_METHODS = {"debug", "info", "warning", "error", "exception", "critical"}

# (module, a fragment of the log format string, the arguments that must be
# scrubbed at that call site). Sources, in order: a cache key built from a
# request ticker; a symbol and a yfinance exception; an order side and a ticker
# that reached the broker from remote Form 4 XML; a free-text query parameter,
# at both of the sinks it reaches.
_CONTRACT = [
    ("app/services/edgar.py",        "EDGAR refresh for %s skipped", {"scrub(key)"}),
    ("app/kronos/service.py",        "yfinance error for %s",        {"scrub(symbol)", "scrub(exc)"}),
    ("app/services/paper_broker.py", "Paper %s: %s",                 {"scrub(side.upper())", "scrub(ticker)"}),
    ("app/api/research.py",          "H1 hypothesis test failed",    {"scrub(category)"}),
    ("app/research/hypothesis.py",   "H1 for category %r ran on",    {"scrub(category)"}),
]


def _logging_call_with(source: str, fragment: str) -> ast.Call:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in _LOG_METHODS or not node.args:
            continue
        fmt = node.args[0]
        if isinstance(fmt, ast.Constant) and isinstance(fmt.value, str) and fragment in fmt.value:
            return node
    raise AssertionError(f"no logging call whose format string contains {fragment!r}")


def _imports_scrub(source: str) -> bool:
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module == "app.core.logsafe"
        and any(alias.name == "scrub" for alias in node.names)
        for node in ast.walk(ast.parse(source))
    )


@pytest.mark.parametrize("relpath,fragment,required", _CONTRACT)
def test_every_flagged_sink_scrubs_its_untrusted_argument(relpath, fragment, required):
    """
    Reading the call site rather than the helper is the point. Pre-fix these
    read, for example, ``logger.info("Paper %s: %s ...", side.upper(), ticker,
    ...)`` and this test named the arguments that were missing.
    """
    source = (_BACKEND / relpath).read_text(encoding="utf-8")

    # Every one of these sinks is on an error branch, so a missing import is a
    # NameError nobody meets until the day the branch runs. Check it here.
    assert _imports_scrub(source), f"{relpath} no longer imports scrub"

    call = _logging_call_with(source, fragment)
    rendered = {ast.unparse(arg) for arg in call.args[1:]}

    missing = required - rendered
    assert not missing, (
        f"{relpath}: the log call for {fragment!r} no longer scrubs "
        f"{sorted(missing)} — it passes {sorted(rendered)}"
    )


def test_the_contract_would_notice_a_removed_scrub():
    """
    The guard above is only worth having if it can go red, so exercise its
    failure mode on a copy of the pre-fix source rather than on the repository.
    """
    pre_fix_source = 'logger.info("Paper %s: %s %.4f", side.upper(), ticker, shares)'
    call = _logging_call_with(pre_fix_source, "Paper %s: %s")
    rendered = {ast.unparse(arg) for arg in call.args[1:]}

    assert {"scrub(side.upper())", "scrub(ticker)"} - rendered


# ── C. one sink end to end ────────────────────────────────────────────────────

def test_a_hostile_cache_key_cannot_forge_an_edgar_log_record(caplog):
    """
    The two checks above are static. This one runs the real sink and reads the
    record that came out, because that — one record, not two — is the property
    being defended. ``_claim_refresh`` is the sink that needs no database and no
    network to reach: fill the in-flight set and it takes the skip branch.
    """
    pytest.importorskip("httpx", reason="app.services.edgar imports httpx")
    from app.services import edgar

    hostile = "ticker:AAPL" + chr(10) + "WARNING:app.services.edgar:forged record"
    held = set(edgar._inflight)
    edgar._inflight.update(f"busy-{n}" for n in range(edgar._MAX_CONCURRENT_REFRESHES))
    try:
        with caplog.at_level(logging.DEBUG, logger="app.services.edgar"):
            assert edgar._claim_refresh(hostile) is False
    finally:
        edgar._inflight.clear()
        edgar._inflight.update(held)

    messages = [r.getMessage() for r in caplog.records]
    assert messages, "the skip branch logged nothing, so this proves nothing"
    for message in messages:
        assert message.splitlines() == [message], f"forged a second record: {message!r}"
