"""HTTP middleware — request-id injection + structlog binding.

The middleware runs for every request regardless of route:

1. Read ``X-Request-Id`` if the caller supplied one, otherwise mint a new
   ULID — having a deterministic id even on generated values keeps log
   correlation trivial.
2. Bind ``request_id`` (and a minimal access-log envelope) into structlog's
   ``contextvars`` so every ``log.info`` automatically carries it.
3. Echo the id back in the response ``X-Request-Id`` header so the client
   can correlate client-side logs with server-side traces.
4. Emit one ``http_request`` info log per request with method, path, status,
   and latency — the access log, free.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from ulid import ULID

from weftlyflow.auth.constants import REQUEST_ID_HEADER

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request
    from starlette.responses import Response

_log = structlog.get_logger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Inject request id, bind structlog context, and emit an access log entry."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Wrap the downstream handler with observability scaffolding."""
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(ULID())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        started = time.perf_counter()
        response: Response | None = None
        try:
            response = await call_next(request)
            return response
        finally:
            latency_ms = int((time.perf_counter() - started) * 1000)
            status_code = response.status_code if response is not None else 500
            _log.info(
                "http_request",
                status=status_code,
                latency_ms=latency_ms,
            )
            if response is not None:
                response.headers[REQUEST_ID_HEADER] = request_id
            structlog.contextvars.clear_contextvars()
