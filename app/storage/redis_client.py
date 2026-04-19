"""Redis client factory."""

from __future__ import annotations

from functools import lru_cache
from typing import Protocol

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class RedisLike(Protocol):
    """Subset of Redis commands used by the application."""

    def set(self, name: str, value: str, ex: int | None = None, nx: bool = False) -> bool | None:
        """Set a key."""

    def delete(self, *names: str) -> int:
        """Delete keys."""

    def get(self, name: str) -> bytes | str | int | None:
        """Get a key."""

    def incr(self, name: str) -> int:
        """Increment a key."""

    def expire(self, name: str, time: int) -> bool:
        """Expire a key."""

    def zadd(self, name: str, mapping: dict[str, float]) -> int:
        """Add members to a sorted set."""

    def zrange(self, name: str, start: int, end: int) -> list[bytes | str]:
        """Read sorted-set members in ascending score order."""

    def zrevrange(self, name: str, start: int, end: int) -> list[bytes | str]:
        """Read sorted-set members in descending score order."""

    def zrem(self, name: str, *values: str) -> int:
        """Remove members from a sorted set."""


@lru_cache(maxsize=1)
def get_redis_client() -> RedisLike | None:
    """Return a Redis client when Redis integration is enabled."""

    if not settings.REDIS_ENABLED:
        return None
    try:
        from redis import Redis

        client = Redis.from_url(settings.REDIS_URL, decode_responses=False)
        client.ping()
        return client
    except Exception as exc:  # pragma: no cover - depends on deployment service
        logger.warning("redis_unavailable", extra={"context": {"error": str(exc)}})
        return None


def redis_key(*parts: str) -> str:
    """Build a namespaced Redis key."""

    normalized = ":".join(part.strip(":") for part in parts if part)
    return f"{settings.REDIS_KEY_PREFIX}:{normalized}"


def redis_decode(value: bytes | str | int | None) -> str | None:
    """Decode Redis scalar values to text."""

    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)
