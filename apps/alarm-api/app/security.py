"""Bearer-token authentication for the Alarm Management API simulator."""

from __future__ import annotations

from fastapi import Header, HTTPException, status

from app.config import settings


async def require_bearer_token(authorization: str | None = Header(default=None)) -> None:
    """Validate the `Authorization: Bearer <token>` header.

    Raises 401 for a missing header and 403 for a wrong token, matching
    conventional REST semantics so the MCP server can map them distinctly.
    """
    if authorization is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization header must be 'Bearer <token>'")
    if token != settings.auth_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API token")
