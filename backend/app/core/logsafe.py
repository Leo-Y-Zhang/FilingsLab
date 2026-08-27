"""
Log-safe rendering of externally sourced text
=============================================
A log line is a record with a shape, so anything that can put a newline into one
can forge the record after it — an operator reading the log, or a tool parsing
it, sees an event that never happened.

Validation at the boundary is the first defence and stays exactly where it is:
``api/feed._validate_ticker`` and ``api/forecast._validate_symbol`` allow-list
their path parameters, and the request schemas type ``trader_id`` as ``int``.
This module is the second one, at the sink, for the service-layer functions
whose callers are *not* all request handlers. Three values reach those sinks
from somewhere nobody validated:

  * ``services/edgar._parse_xml`` takes ``issuerTradingSymbol`` straight out of
    a remote SEC Form 4 document, uppercases and strips it, and that ticker
    travels through the auto-trader into ``services/paper_broker`` — the only
    path to an order log that never passes an allow-list;
  * third-party exception text (``yfinance``) is logged verbatim;
  * ``api/research.hypothesis_h1`` takes ``category`` as free-text query input.

``scrub`` is deliberately the whole module. One helper at seven call sites is
auditable; seven inline ``replace`` chains are not.
"""
from __future__ import annotations

# Long enough for a ticker, a category, a cache key or a one-line exception
# message; short enough that one value cannot flood the log.
_MAX_LOGGED_CHARS = 200


def scrub(value: object, limit: int = _MAX_LOGGED_CHARS) -> str:
    """
    Return *value* as a single-line, printable string that is safe to log.

    Every non-printable character is replaced by its backslash escape. That is
    CR and LF above all — they are what forges a record — but also TAB, ESC
    (which drives the terminal that renders the log) and the rest of the C0/C1
    range, including NEL and the Unicode line and paragraph separators, each of
    which some log reader treats as a line break. Over-long values are
    truncated so a single field cannot fill the log.
    """
    text = value if isinstance(value, str) else str(value)
    cleaned = "".join(
        ch if ch.isprintable() else ch.encode("unicode_escape").decode("ascii")
        for ch in text
    )
    if len(cleaned) > limit:
        cleaned = cleaned[:limit] + "...[truncated]"
    return cleaned
