"""
Server-side API authentication
==============================
A single shared bearer token, read from the ``API_TOKEN`` environment variable,
gates every mutating route and the whole auto-trader / paper-broker control
surface. This is deliberately *not* a user system: there is one operator, and
the thing being protected is a simulated portfolio and a bot that trades it.

Two properties matter more than the mechanism:

* **Fails closed.** With no ``API_TOKEN`` configured the admin surface returns
  503, not 200. An unconfigured deployment must not be an open one.
* **Constant-time comparison**, so the token cannot be recovered a byte at a
  time from response timing.

Read-only research routes are intentionally left open — see SECURITY.md.
"""
from __future__ import annotations

import hmac
import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings

logger = logging.getLogger("app.security")

_bearer = HTTPBearer(
    auto_error=False,
    description="Shared operator token, set as API_TOKEN on the server.",
)


def _deny(request: Request, reason: str, status_code: int, detail: str) -> None:
    logger.warning(
        "auth_failed reason=%s request_id=%s client_ip=%s method=%s path=%s",
        reason,
        getattr(request.state, "request_id", "-"),
        request.client.host if request.client else "-",
        request.method,
        request.url.path,
    )
    raise HTTPException(
        status_code=status_code,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_api_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> None:
    """FastAPI dependency: allow the request only with a valid bearer token."""
    expected = get_settings().api_token.strip()

    if not expected:
        _deny(
            request,
            "server_token_not_configured",
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Admin API is disabled: no API_TOKEN is configured on the server.",
        )

    if credentials is None or credentials.scheme.lower() != "bearer":
        _deny(
            request,
            "missing_token",
            status.HTTP_401_UNAUTHORIZED,
            "Missing bearer token.",
        )

    if not hmac.compare_digest(credentials.credentials, expected):
        _deny(
            request,
            "bad_token",
            status.HTTP_401_UNAUTHORIZED,
            "Invalid bearer token.",
        )
