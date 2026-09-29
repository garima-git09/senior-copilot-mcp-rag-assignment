"""ASGI entrypoint used for HTTP deployment (Docker/uvicorn), combining the
MCP streamable-HTTP app (mounted at /mcp by FastMCP) with a plain /health
route for container healthchecks and load balancers -- the MCP protocol
itself requires a session handshake, so it isn't a suitable healthcheck
target on its own.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from server.app import mcp

app = mcp.streamable_http_app()


async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "alarm-management-mcp"})


app.router.routes.insert(0, Route("/health", health, methods=["GET"]))
