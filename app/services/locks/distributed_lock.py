"""Redis-backed distributed locks."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import uuid4

from app.core.config import settings
from app.storage.redis_client import RedisLike, get_redis_client, redis_key


@contextmanager
def redis_lock(name: str, ttl_seconds: int | None = None, redis_client: RedisLike | None = None) -> Iterator[bool]:
    """Acquire a Redis lock and release it when owned by this process."""

    client = redis_client if redis_client is not None else get_redis_client()
    if client is None:
        yield True
        return

    token = uuid4().hex
    key = redis_key("lock", name)
    acquired = bool(client.set(key, token, ex=ttl_seconds or settings.REPO_INDEX_LOCK_TTL_SECONDS, nx=True))
    try:
        yield acquired
    finally:
        if acquired:
            current = client.get(key)
            if _decode(current) == token:
                client.delete(key)


def _decode(value: bytes | str | int | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)
