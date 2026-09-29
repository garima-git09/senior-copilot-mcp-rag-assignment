"""Trace/correlation propagation and structured logging middleware."""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("alarm_api")


class TraceMiddleware(BaseHTTPMiddleware):
    """Reads (or generates) trace_id / x-client-id / x-metadata-tag headers,
    echoes them back on the response, and logs each request as structured
    JSON-ish key=value pairs without ever logging secrets (the Authorization
    header is deliberately excluded).
    """

    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("trace_id") or request.headers.get("x-trace-id") or f"trace-{uuid.uuid4().hex[:12]}"
        client_id = request.headers.get("x-client-id", "unknown-client")
        metadata_tag = request.headers.get("x-metadata-tag", "")

        request.state.trace_id = trace_id
        request.state.client_id = client_id

        start = time.perf_counter()
        response: Response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        response.headers["trace_id"] = trace_id
        response.headers["x-client-id"] = client_id
        if metadata_tag:
            response.headers["x-metadata-tag"] = metadata_tag

        logger.info(
            "request_completed method=%s path=%s status=%s duration_ms=%s trace_id=%s client_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            trace_id,
            client_id,
        )
        return response
