"""Caching layer tests."""

from __future__ import annotations

import unittest

from app.services.indexing.embedding_builder import EmbeddingBuilder
from app.storage.repositories import _TTLCache


class TTLCacheTests(unittest.TestCase):
    def test_get_returns_cached_value(self) -> None:
        clock = _FakeClock(0.0)
        cache = _TTLCache(ttl=60, time_fn=clock)
        cache.set("k1", "v1")
        self.assertEqual(cache.get("k1"), "v1")

    def test_get_returns_none_after_expiry(self) -> None:
        clock = _FakeClock(0.0)
        cache = _TTLCache(ttl=10, time_fn=clock)
        cache.set("k1", "v1")
        clock.now = 11.0
        self.assertIsNone(cache.get("k1"))

    def test_clear_removes_all(self) -> None:
        cache = _TTLCache(ttl=60)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        self.assertIsNone(cache.get("a"))
        self.assertIsNone(cache.get("b"))


class EmbeddingCacheTests(unittest.TestCase):
    def test_encode_summary_caches_result(self) -> None:
        call_count = 0

        class _CountingModel:
            def encode(self, texts, **_kwargs):
                nonlocal call_count
                call_count += len(texts)
                return [[0.6, 0.8] for _ in texts]

        builder = EmbeddingBuilder(
            provider="sentence-transformer",
            model_name="test",
            dimension=2,
            sentence_transformer_model=_CountingModel(),
        )

        first = builder.encode_summary("hello world")
        second = builder.encode_summary("hello world")
        self.assertEqual(first, second)
        self.assertEqual(call_count, 1)

        info = builder.cache_info()
        self.assertEqual(info.hits, 1)
        self.assertEqual(info.misses, 1)


class _FakeClock:
    def __init__(self, start: float) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


if __name__ == "__main__":
    unittest.main()
