"""Shared API dependencies."""

from __future__ import annotations

import hmac
from functools import lru_cache

from fastapi import Header, HTTPException, Request, status

from app.api.errors import error_detail
from app.core.config import settings
from app.services.memory.memory_manager import MemoryManager
from app.services.rate_limit.redis_rate_limiter import RateLimitExceeded, check_rate_limit
from app.storage.repositories import GraphRepository

memory_manager = MemoryManager()


@lru_cache(maxsize=1)
def get_graph_repository() -> GraphRepository:
    """Return a cached repository instance from settings."""

    return GraphRepository(settings.DATABASE_URL)


def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> None:
    """Enforce optional API key authentication for mutating endpoints."""

    expected_key = settings.API_KEY.strip()
    if not expected_key:
        return

    provided_key = _extract_api_key(x_api_key=x_api_key, authorization=authorization)
    if provided_key is not None and hmac.compare_digest(provided_key, expected_key):
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=error_detail("unauthorized", "Invalid or missing API key"),
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_rate_limit(request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    """Apply optional Redis-backed rate limiting."""

    identifier = x_api_key or (request.client.host if request.client else "anonymous")
    try:
        check_rate_limit(identifier)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=error_detail("rate_limited", "Rate limit exceeded"),
        ) from exc


def _extract_api_key(*, x_api_key: str | None, authorization: str | None) -> str | None:
    if x_api_key:
        return x_api_key.strip()
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token.strip():
            return token.strip()
    return None
