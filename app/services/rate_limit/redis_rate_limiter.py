"""Redis-backed fixed-window rate limiting."""

from __future__ import annotations

from app.core.config import settings
from app.storage.redis_client import RedisLike, get_redis_client, redis_key


class RateLimitExceeded(Exception):
    """Raised when a client exceeds the configured request rate."""


def check_rate_limit(identifier: str, redis_client: RedisLike | None = None) -> None:
    """Apply a fixed-window Redis rate limit when configured."""

    if not settings.RATE_LIMIT_ENABLED:
        return
    client = redis_client if redis_client is not None else get_redis_client()
    if client is None:
        return

    key = redis_key("rate", identifier)
    count = int(client.incr(key))
    if count == 1:
        client.expire(key, settings.RATE_LIMIT_WINDOW_SECONDS)
    if count > settings.RATE_LIMIT_REQUESTS:
        raise RateLimitExceeded("Rate limit exceeded")
