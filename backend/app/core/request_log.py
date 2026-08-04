"""
Structured request logging
==========================
Without this there is no detection: an anonymous caller could loop the feed
endpoint for hours and nothing in the log would distinguish it from normal use.

Every request gets a server-generated id (client-supplied ids are ignored so
they cannot be used to poison or collide log lines), and every response is
logged as a single parseable key=value line:

    request_id=... method=GET path=/api/feed/disclosures status=429
    duration_ms=1.4 client_ip=203.0.113.9 forwarded_for=- ua="curl/8.5.0"

The id is echoed back as ``X-Request-ID`` so a report can be tied to a log line.
"""
from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

logger = logging.getLogger("app.request")


class RequestLogMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        request_id = uuid.uuid4().hex
        request.state.request_id = request_id
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - started) * 1000
            logger.exception(
                "request_id=%s method=%s path=%s status=500 duration_ms=%.1f "
                'client_ip=%s forwarded_for=%s ua="%s"',
                request_id,
                request.method,
                request.url.path,
                duration_ms,
                request.client.host if request.client else "-",
                request.headers.get("x-forwarded-for", "-"),
                request.headers.get("user-agent", "-")[:120],
            )
            raise

        duration_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "request_id=%s method=%s path=%s status=%d duration_ms=%.1f "
            'client_ip=%s forwarded_for=%s ua="%s"',
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request.client.host if request.client else "-",
            request.headers.get("x-forwarded-for", "-"),
            request.headers.get("user-agent", "-")[:120],
        )
        response.headers["X-Request-ID"] = request_id
        return response
