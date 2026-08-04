"""
Rate limiting
=============
The backend is published on a public port by ``docker-compose.yml`` and
``server_setup.sh`` (which prints ``http://<public-ip>:8000/docs``), so every
route is reachable by anonymous callers. Several of them are expensive:
``/api/feed/disclosures`` sleeps ~18 s in-request and issues up to 120 SEC
Archives fetches on a cache miss, and the Monte Carlo / experiment endpoints
run thousands of simulations.

Keying
------
The backend is reachable **two** ways at once: through the nginx container
(which sets ``X-Real-IP``/``X-Forwarded-For``) and directly on port 8000. So
forwarded headers may only be believed when the immediate peer is a trusted
proxy — otherwise anyone hitting port 8000 could mint a fresh rate-limit bucket
per request just by varying a header. Peers outside the trusted networks are
keyed on their real socket address and their forwarded headers are ignored.

Scoping
-------
slowapi's ``key_style`` defaults to ``"url"``, which makes the bucket key the
*concrete* request path. Every path-parameterised route was therefore
effectively unlimited: ``/api/feed/disclosures/AAA`` and
``/api/feed/disclosures/AAB`` are different URLs, so a caller working through a
symbol list got a fresh 10/minute budget per symbol, and ``/api/traders/{id}``
a fresh 120/minute budget per id. ``"endpoint"`` keys on the view function
instead, so the bucket is the route template and varying a path parameter buys
the caller nothing.

Headers
-------
``headers_enabled=True`` is kept deliberately. It is the only switch that makes
slowapi emit ``Retry-After`` (see ``Limiter._inject_headers``), and
``Retry-After`` is what lets a client back off instead of retrying straight
back into the limit. The cost is that slowapi's decorator ends with
``self._inject_headers(kwargs.get("response"), ...)``, which *raises* — a 500 on
the success path — unless the decorated endpoint declares ``response:
Response``. So every ``@limiter.limit`` endpoint declares one, and
``tests/test_rate_limit_contract.py`` fails the build if a new one does not.
The alternative, ``headers_enabled=False``, also removes the 500, but it throws
away the back-off signal to work around a missing parameter: that is deleting
the working half of the feature to avoid fixing the broken half.
"""
from __future__ import annotations

import ipaddress
import logging

from slowapi import Limiter
from starlette.requests import Request

from app.core.config import get_settings

logger = logging.getLogger("app.security")


def _is_trusted_proxy(host: str) -> bool:
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    for cidr in get_settings().trusted_proxy_networks:
        try:
            if addr in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            logger.warning("Ignoring malformed trusted_proxy_networks entry: %r", cidr)
    return False


def client_key(request: Request) -> str:
    """Return the rate-limit bucket key for *request* (the real client IP)."""
    peer = request.client.host if request.client else "unknown"
    if not _is_trusted_proxy(peer):
        return peer

    real_ip = (request.headers.get("x-real-ip") or "").strip()
    if real_ip:
        return real_ip

    # nginx appends the peer address to any client-supplied X-Forwarded-For,
    # so the rightmost entry is the one the proxy itself observed.
    forwarded = request.headers.get("x-forwarded-for") or ""
    parts = [p.strip() for p in forwarded.split(",") if p.strip()]
    if parts:
        return parts[-1]
    return peer


limiter = Limiter(
    key_func=client_key,
    default_limits=["120/minute"],
    headers_enabled=True,
    # Bucket per (client, route template) — never per (client, concrete URL).
    key_style="endpoint",
)
