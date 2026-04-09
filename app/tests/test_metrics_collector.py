"""MetricsCollector tests."""

from __future__ import annotations

import unittest

from app.core.metrics import MetricsCollector


class MetricsCollectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.collector = MetricsCollector()

    def test_increment_counter(self) -> None:
        self.collector.increment("requests")
        self.collector.increment("requests")
        self.collector.increment("requests", 3)
        self.assertEqual(self.collector.get_counter("requests"), 5)

    def test_get_counter_returns_zero_for_unknown(self) -> None:
        self.assertEqual(self.collector.get_counter("unknown"), 0)

    def test_observe_histogram_and_stats(self) -> None:
        for value in [10.0, 20.0, 30.0, 40.0, 50.0]:
            self.collector.observe("latency", value)
        stats = self.collector.get_histogram_stats("latency")
        self.assertEqual(stats["min"], 10.0)
        self.assertEqual(stats["max"], 50.0)
        self.assertEqual(stats["count"], 5)
        self.assertAlmostEqual(stats["avg"], 30.0, places=2)

    def test_histogram_stats_empty(self) -> None:
        stats = self.collector.get_histogram_stats("empty")
        self.assertEqual(stats["count"], 0)
        self.assertEqual(stats["min"], 0.0)

    def test_snapshot_returns_all_metrics(self) -> None:
        self.collector.increment("a")
        self.collector.observe("b", 1.0)
        snap = self.collector.snapshot()
        self.assertIn("counters", snap)
        self.assertIn("histograms", snap)
        self.assertEqual(snap["counters"]["a"], 1)
        self.assertIn("b", snap["histograms"])

    def test_reset_clears_everything(self) -> None:
        self.collector.increment("x", 5)
        self.collector.observe("y", 99.0)
        self.collector.reset()
        self.assertEqual(self.collector.get_counter("x"), 0)
        self.assertEqual(self.collector.get_histogram_stats("y")["count"], 0)


if __name__ == "__main__":
    unittest.main()
